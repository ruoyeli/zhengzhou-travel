import json
import os
import random
import re
import sqlite3
import time
import uuid
from datetime import date, datetime
from langchain_core.tools import tool
from typing import Optional
from rag import search_docs 
import httpx
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from paths import get_sqlite_connection

load_dotenv()

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0,
)

AMAP_KEY = os.getenv("AMAP_API_KEY")


def stream_llm(messages: list) -> str:
    """流式调用 LLM，逐字打印，返回完整内容。"""
    print("\n助手：", end="", flush=True)
    full_content = ""
    for chunk in llm.stream(messages):
        piece = chunk.content
        print(piece, end="", flush=True)
        full_content += piece
    print()
    return full_content


def print_streaming(text: str) -> None:
    """终端模式下模拟流式打印。"""
    print("\n助手：", end="", flush=True)
    for char in text:
        print(char, end="", flush=True)
        time.sleep(0.02)
    print()


def _llm_text(response) -> str:
    if hasattr(response, "content"):
        return response.content.strip()
    return str(response).strip()


def _strip_think_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _init_hotel_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hotel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            rating REAL,
            address TEXT,
            stock INTEGER
        )
    """)


def _init_order_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS "order" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            hotel_name TEXT,
            guest_name TEXT,
            check_in TEXT,
            check_out TEXT,
            total_nights INTEGER,
            status TEXT
        )
    """)


def _fetch_amap_hotels(location: str, city: str) -> list:
    """调用高德 POI 接口，失败时返回空列表。"""
    if not AMAP_KEY:
        print("[WARN] 未配置 AMAP_API_KEY，跳过高德查询")
        return []

    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/place/text",
            params={
                "key": AMAP_KEY,
                "keywords": f"{location} 酒店",
                "city": city,
                "types": "accommodation",
                "offset": 5,
                "extensions": "base",
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("status")) != "1":
            raise ValueError(data.get("info", "高德 API 返回错误"))
        return data.get("pois") or []
    except httpx.HTTPError as e:
        print(f"[WARN] 高德 API 请求失败: {e}")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"[WARN] 高德 API 响应异常: {e}")
    return []


def _fetch_open_meteo_coords(city: str) -> tuple[float, float]:
    """Open-Meteo 地理编码，失败时回退郑州坐标。"""
    default = (34.7466, 113.6254)
    try:
        resp = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh"},
            timeout=5,
        )
        resp.raise_for_status()
        geo = resp.json()
        result = geo["results"][0]
        return result["latitude"], result["longitude"]
    except httpx.HTTPError as e:
        print(f"[WARN] Open-Meteo 地理编码请求失败: {e}")
    except (KeyError, IndexError, TypeError, ValueError) as e:
        print(f"[WARN] Open-Meteo 地理编码响应异常: {e}")
    return default


def _fetch_open_meteo_forecast(lat: float, lon: float) -> Optional[dict]:
    """Open-Meteo 天气预报，失败时返回 None。"""
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weathercode,windspeed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max",
                "forecast_days": 7,
                "timezone": "Asia/Shanghai",
            },
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as e:
        print(f"[WARN] Open-Meteo 预报请求失败: {e}")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[WARN] Open-Meteo 预报响应异常: {e}")
    return None

@tool
def classify_intents(intents: list[str]) -> str:
    """识别用户输入中包含的所有意图。intents 是意图列表，每项为 query（查酒店）、book（预订）、weather（天气）、knowledge（闲聊/知识问答）之一。"""
    return "ok"

def classifier_node(state: dict) -> dict:
    user_msg = state["messages"][-1].content

    llm_with_tools = llm.bind_tools([classify_intents])

    response = llm_with_tools.invoke([
        SystemMessage(content="识别用户消息中的意图，调用 classify_intents 工具返回。"),
        HumanMessage(content=user_msg),
    ])

    # 从 tool_calls 提取结构化数据（不会格式错误，不需要 try/except）
    intents = ["knowledge"]  # 默认兜底
    if response.tool_calls:
        args = response.tool_calls[0].get("args", {})
        intent_list = args.get("intents", [])
        valid = [i for i in intent_list if i in ["query", "book", "weather", "knowledge"]]
        if valid:
            intents = valid

    return {"intents": intents}

def search_node(state: dict) -> dict:
    """调用高德 API 查询酒店，写入 SQLite 库存并生成 hotels_list。"""
    user_msg = state["messages"][-1].content

    extract = llm.invoke([
        SystemMessage(content="""从用户输入中提取城市、地点和最高价格，以JSON输出，不要其他文字。
如果没有明确提到城市，默认给"郑州"：
{"city": "城市名称", "location": "地点名称", "max_price": 数字或5000}"""),
        HumanMessage(content=user_msg),
    ])

    extract_text = _strip_think_tags(_llm_text(extract))

    try:
        match = re.search(r"\{.*\}", extract_text, re.DOTALL)
        params = json.loads(match.group()) if match else {}
        city = params.get("city", "郑州")
        location = params.get("location", "郑州")
        max_price = params.get("max_price", 5000)
    except (json.JSONDecodeError, AttributeError):
        city, location, max_price = "郑州", "郑州", 5000

    pois = _fetch_amap_hotels(location, city)
    hotels = []

    try:
        conn = get_sqlite_connection()
        cursor = conn.cursor()
        _init_hotel_table(cursor)

        for poi in pois:
            name = poi.get("name", "").strip()
            address = poi.get("address", "未知地址")
            if not name:
                continue

            cursor.execute(
                "SELECT name, price, rating, address, stock FROM hotel WHERE name=? AND price<=? AND stock>0",
                (name, max_price),
            )
            row = cursor.fetchone()

            if row:
                hotels.append({
                    "name": row[0], "price": row[1], "rating": row[2],
                    "address": row[3], "stock": row[4],
                })
                continue

            fake_price = random.randint(150, 480)
            if fake_price > max_price:
                continue

            fake_rating = round(random.uniform(3.8, 4.9), 1)
            try:
                cursor.execute(
                    "INSERT INTO hotel (name, price, rating, address, stock) VALUES (?, ?, ?, ?, ?)",
                    (name, fake_price, fake_rating, address, 10),
                )
            except sqlite3.IntegrityError:
                pass

            cursor.execute(
                "SELECT name, price, rating, address, stock FROM hotel WHERE name=? AND price<=? AND stock>0",
                (name, max_price),
            )
            row = cursor.fetchone()
            if row:
                hotels.append({
                    "name": row[0], "price": row[1], "rating": row[2],
                    "address": row[3], "stock": row[4],
                })

        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        reply = f"本地数据库错误，暂时无法查询酒店：{e}"
        print_streaming(reply)
        return {"hotels_list": [], "messages": [AIMessage(content=reply)]}

    if hotels:
        hotel_text = "\n".join([
            "{i}. {name}，{price}元/晚，评分{rating}，地址：{address}".format(
                i=i + 1, name=h["name"], price=h["price"],
                rating=h["rating"], address=h["address"],
            )
            for i, h in enumerate(hotels)
        ])
        reply = f"为您找到{location}附近{max_price}元以内的酒店：\n{hotel_text}"
    else:
        reply = f"抱歉，未找到{location}附近{max_price}元以内有库存的酒店。"

    print_streaming(reply)
    return {"hotels_list": hotels, "messages": [AIMessage(content=reply)]}


def book_node(state: dict) -> dict:
    user_msg = state["messages"][-1].content
    hotels_list = state.get("hotels_list", [])

    hotels_ctx = "\n".join([
        "{i}. {name}，{price}元/晚".format(i=i + 1, name=h["name"], price=h["price"])
        for i, h in enumerate(hotels_list)
    ]) if hotels_list else "暂无历史查询记录"

    today = date.today().isoformat()

    extract = llm.invoke([
        SystemMessage(content="""你是预订助手。提取预订参数，输出严格JSON，不要其他文字。
今天日期：{today}
历史查询酒店列表：
{hotels_ctx}

如果用户说"第一家"、"最便宜的"、"最贵的"等，从列表中找对应酒店全名。
"今天"转为{today}，"明天"、"后天"、"大后天"自行换算。

输出格式：
{{"hotel_name": "xxx或null", "check_in": "YYYY-MM-DD或null", "check_out": "YYYY-MM-DD或null", "guest_name": "xxx或null"}}""".format(
            today=today, hotels_ctx=hotels_ctx
        )),
        HumanMessage(content=user_msg),
    ])

    extract_text = _strip_think_tags(_llm_text(extract))

    try:
        match = re.search(r"\{.*\}", extract_text, re.DOTALL)
        if not match:
            raise ValueError("no json")
        params = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        reply = "参数解析失败，请重新描述预订信息。"
        print_streaming(reply)
        return {"messages": [AIMessage(content=reply)]}

    missing = [f for f in ["hotel_name", "check_in", "check_out", "guest_name"] if not params.get(f)]
    if missing:
        reply = "还缺少以下信息：{}，请补充后再试。".format("、".join(missing))
        print_streaming(reply)
        return {"messages": [AIMessage(content=reply)]}

    try:
        conn = get_sqlite_connection()
        conn.isolation_level = None
        cursor = conn.cursor()
        _init_hotel_table(cursor)
        _init_order_table(cursor)

        cursor.execute("BEGIN")
        cursor.execute("SELECT stock FROM hotel WHERE name=?", (params["hotel_name"],))
        row = cursor.fetchone()

        if not row:
            conn.rollback()
            conn.close()
            reply = "系统中没有\"{}\"的记录，请先查询该地区酒店。".format(params["hotel_name"])
            print_streaming(reply)
            return {"messages": [AIMessage(content=reply)]}

        if row[0] <= 0:
            conn.rollback()
            conn.close()
            reply = "{}已满房，请选择其他酒店。".format(params["hotel_name"])
            print_streaming(reply)
            return {"messages": [AIMessage(content=reply)]}

        cursor.execute("UPDATE hotel SET stock = stock - 1 WHERE name=?", (params["hotel_name"],))

        order_id = "ORD-" + str(uuid.uuid4())[:8].upper()
        check_in = datetime.strptime(params["check_in"], "%Y-%m-%d").date()
        check_out = datetime.strptime(params["check_out"], "%Y-%m-%d").date()
        nights = (check_out - check_in).days

        cursor.execute(
            """INSERT INTO "order" (order_id, hotel_name, guest_name, check_in, check_out, total_nights, status)
               VALUES (?, ?, ?, ?, ?, ?, 'confirmed')""",
            (order_id, params["hotel_name"], params["guest_name"],
             params["check_in"], params["check_out"], nights),
        )
        cursor.execute("COMMIT")
        conn.close()

        reply = (
            "预订成功！\n订单号：{order_id}\n酒店：{hotel_name}\n"
            "入住：{check_in} → 退房：{check_out}（{nights}晚）\n入住人：{guest_name}"
        ).format(
            order_id=order_id,
            hotel_name=params["hotel_name"],
            check_in=params["check_in"],
            check_out=params["check_out"],
            nights=nights,
            guest_name=params["guest_name"],
        )
        print_streaming(reply)
        return {
            "booking_info": {
                "hotel_name": params["hotel_name"],
                "check_in": params["check_in"],
                "check_out": params["check_out"],
                "guest_name": params["guest_name"],
            },
            "messages": [AIMessage(content=reply)],
        }

    except sqlite3.Error as e:
        reply = f"预订失败（数据库错误）：{e}"
        print_streaming(reply)
        return {"messages": [AIMessage(content=reply)]}
    except ValueError as e:
        reply = f"预订失败（日期格式错误）：{e}"
        print_streaming(reply)
        return {"messages": [AIMessage(content=reply)]}


def weather_node(state: dict) -> dict:
    user_msg = state["messages"][-1].content

    city_extract = llm.invoke([
        SystemMessage(content="从用户输入提取城市英文名，只输出英文城市名。没有明确城市就输出 Zhengzhou。"),
        HumanMessage(content=user_msg),
    ])
    city = _llm_text(city_extract)

    lat, lon = _fetch_open_meteo_coords(city)
    weather = _fetch_open_meteo_forecast(lat, lon)
    if weather is None:
        return {"messages": [AIMessage(content="天气服务暂时不可用，请稍后再试。")]}

    today = date.today().isoformat()
    content = stream_llm([
        SystemMessage(content=f"""根据天气JSON数据回答用户问题。
今天日期：{today}
daily数组索引规则：index 0=今天，index 1=明天，index 2=后天，以此类推。
请根据用户问的是哪天，从对应index取数据。
weathercode: 0=晴，1-3=多云，45-48=雾，51-67=雨，80-82=阵雨，95=雷阵雨。
给出温度、天气状况和出行建议，语气友好。"""),
        HumanMessage(content=f"用户问题：{user_msg}\n天气数据：{json.dumps(weather, ensure_ascii=False)}"),
    ])

    return {"messages": [AIMessage(content=content)]}

def knowledge_node(state: dict) -> dict:
    user_msg = state["messages"][-1].content

    # 从文档库检索相关内容
    context = search_docs(user_msg, "chroma_db")

    if context:
        system_prompt = (
            "你是郑州本地旅行助手。如果用户问到涉及参考资料的问题，必须根据参考资料回答用户问题。"
            "如果参考资料中没有相关信息，请如实告知，并结合自身知识补充。\n\n"
            "规则：\n"
            "1.只使用参考资料中明确提到的信息\n"
            "2. 不要编造参考资料中没有的来源、数据或引用\n"
            "3. 如果资料不足以回答，必须明确告知信息来源于大模型本身自带的知识\n\n"
            f"参考资料：\n{context}"
        )
    else:
        system_prompt = "你是郑州本地旅行助手，熟悉郑州的景点、历史、交通和美食。友好地回答用户问题。"

    content = stream_llm([
        SystemMessage(content=system_prompt),
    ] + state["messages"])
    return {"messages": [AIMessage(content=content)]}
1

def aggregator_node(state: dict) -> dict:
    """将多个节点的输出融合为一段自然回复。"""
    messages = state["messages"]
    if not messages:
        return {"messages": [AIMessage(content="抱歉，我暂时无法处理您的请求。")]}

    content = stream_llm([
        SystemMessage(content=(
            "你是郑州旅行助手。请把以下多条查询结果融合成一段自然、连贯的回复。"
            "不要简单拼接，要用自己的话自然过渡。如果某项结果为空或失败，简单带过即可。"
        )),
    ] + messages)

    return {"messages": [AIMessage(content=content)]}
