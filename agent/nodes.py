import os
import json
import re
import random
import uuid
import httpx
import sqlite3
import psycopg
from langchain_core.messages import AIMessage
from datetime import date, datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()

# 初始化 LLM（DeepSeek 兼容 OpenAI 格式）
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0
)

AMAP_KEY = os.getenv("AMAP_API_KEY")
DB_PATH =  r"D:\pracise\Zhengzhou Hotel assistant\hotel.db" # 指向你】原来的数据库

# 获取连接字符串
DB_URI = os.getenv("DB_URI")

def search_node(state):
    """从 PostgreSQL 中查询酒店"""
    # 简单的语义模拟：根据用户提到的地标搜索酒店
    # 实际项目中你可能会用向量搜索或高德API，这里演示从PG取数
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, price, score, address FROM hotels WHERE price < 5000")
            rows = cur.fetchall()
            
            hotels_list = []
            for r in rows:
                hotels_list.append({"name": r[0], "price": r[1], "score": r[2], "address": r[3]})
    
    # 将查询结果放入 state，供下一节点使用
    return {"hotels_list": hotels_list, "messages": [AIMessage(content=f"为您找到{len(hotels_list)}家酒店...")]}

def book_node(state):
    """将订单持久化到 PostgreSQL"""
    info = state.get("booking_info")
    
    # 真正的数据库插入操作
    try:
        with psycopg.connect(DB_URI) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders (order_id, hotel_name, guest_name, check_in, check_out)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (info["order_id"], info["hotel_name"], info["guest_name"], info["check_in"], info["check_out"])
                )
        res_msg = f"预订成功！订单已持久化至数据库。订单号：{info['order_id']}"
    except Exception as e:
        res_msg = f"预订失败：{str(e)}"

    return {"messages": [AIMessage(content=res_msg)]}

def stream_llm(messages: list) -> str:
    """流式调用 LLM，逐字打印，返回完整内容"""
    print("\n助手：", end="", flush=True)
    full_content = ""
    for chunk in llm.stream(messages):
        piece = chunk.content
        print(piece, end="", flush=True)
        full_content += piece
    print()  # 换行
    return full_content

def print_streaming(text: str):
    """模拟流式打印"""
    import time
    print("\n助手：", end="", flush=True)
    for char in text:
        print(char, end="", flush=True)
        time.sleep(0.02)  # 每个字间隔20ms
    print()

# ── 节点一：意图分类 ──────────────────────────────────

def classifier_node(state: dict) -> dict:
    user_msg = state["messages"][-1].content

    response = llm.invoke([
        SystemMessage(content="""判断用户输入的意图，只输出以下四个词之一，不要任何其他文字：
- query：用户想查询酒店
- book：用户想预订酒店
- weather：用户想查天气
- knowledge：闲聊或问景点知识"""),
        HumanMessage(content=user_msg)
    ])

    # llm.invoke 返回 AIMessage 对象，用 .content 取文本
    if hasattr(response, "content"):
        intent = response.content.strip().lower()
    else:
        intent = str(response).strip().lower()

    # 清理可能的 think 标签
    
    intent = re.sub(r'<think>.*?</think>', '', intent, flags=re.DOTALL).strip()

    if intent not in ["query", "book", "weather", "knowledge"]:
        intent = "knowledge"

    return {"intent": intent}
def search_node(state: dict) -> dict:
    """调用高德API查询酒店，动态写入库存并生成 hotels_list"""
    user_msg = state["messages"][-1].content

    # 👇 优化 1：让大模型连“城市”一起提取出来，解决洛阳查不到的问题
    extract = llm.invoke([
        SystemMessage(content="""从用户输入中提取城市、地点和最高价格，以JSON输出，不要其他文字。
如果没有明确提到城市，默认给"郑州"：
{"city": "城市名称", "location": "地点名称", "max_price": 数字或5000}"""),
        HumanMessage(content=user_msg)
    ])

    extract_text = extract.content if hasattr(extract, "content") else str(extract)
    extract_text = re.sub(r'<think>.*?</think>', '', extract_text, flags=re.DOTALL).strip()

    try:
        match = re.search(r'\{.*\}', extract_text, re.DOTALL)
        params = json.loads(match.group()) if match else {}
        city = params.get("city", "郑州")
        location = params.get("location", "郑州")
        max_price = params.get("max_price", 5000)
    except:
        city, location, max_price = "郑州", "郑州", 5000

    # 调用高德 API
    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/place/text",
            params={
                "key": AMAP_KEY,
                "keywords": f"{location} 酒店",
                "city": city, # 👇 使用动态提取的城市
                "types": "accommodation",
                "offset": 5,
                "extensions": "base"
            },
            timeout=5
        )
        pois = resp.json().get("pois", [])
    except:
        pois = []

    # 查本地数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hotels = []

    for poi in pois:
        name = poi.get("name", "").strip()
        address = poi.get("address", "未知地址")
        if not name:
            continue
            
        # 先尝试精准查询
        cursor.execute(
            "SELECT name, price, rating, address, stock FROM hotel WHERE name=? AND price<=? AND stock>0",
            (name, max_price)
        )
        row = cursor.fetchone()
        
        if row:
            hotels.append({
                "name": row[0], "price": row[1], "rating": row[2], 
                "address": row[3], "stock": row[4]
            })
        else:
            # 👇 优化 2：神级 DEMO 技巧 —— 动态补全库存！
            # 如果高德查到了现实里的酒店，但我们的数据库没有，动态生成一个合理的价格写入数据库！
            fake_price = random.randint(150, 480) # 随机价格
            if fake_price <= max_price:
                fake_rating = round(random.uniform(3.8, 4.9), 1) # 随机评分
                
                try:
                    # 尝试插入本地库，确保下一步的 book_node 也能找到它去扣库存
                    cursor.execute(
                        "INSERT INTO hotel (name, price, rating, address, stock) VALUES (?, ?, ?, ?, ?)",
                        (name, fake_price, fake_rating, address, 10) # 默认给10间房库存
                    )
                    conn.commit()
                    print(f"✅ [DEBUG] 成功将 {name} 的假库存写入 SQLite！") # 成功了会打印这句
                except Exception as e:
                    # 忽略已存在等错误
                    print(f"🚨 [DEBUG] 写入数据库失败，原因: {e}") 
                
                hotels.append({
                    "name": name, "price": fake_price, "rating": fake_rating, 
                    "address": address, "stock": 10
                })

    conn.close()

    # 生成回复
    if hotels:
        hotel_text = "\n".join([
            "{i}. {name}，{price}元/晚，评分{rating}，地址：{address}".format(
                i=i+1, name=h["name"], price=h["price"], 
                rating=h["rating"], address=h["address"]
            )
            for i, h in enumerate(hotels)
        ])
        reply = f"为您找到{location}附近{max_price}元以内的酒店：\n{hotel_text}"
    else:
        reply = f"抱歉，未找到{location}附近{max_price}元以内有库存的酒店。"

    # 这里需要确保你有 print_streaming 函数
    try:
        print_streaming(reply)
    except:
        pass # 如果没定义就跳过，由 main.py 处理打印

    return {
        "hotels_list": hotels,
        "messages": [AIMessage(content=reply)]
    }
# ── 节点三：预订酒店 ──────────────────────────────────

def book_node(state: dict) -> dict:
    user_msg = state["messages"][-1].content
    hotels_list = state.get("hotels_list", [])

    hotels_ctx = "\n".join([
        "{i}. {name}，{price}元/晚".format(i=i+1, name=h["name"], price=h["price"])
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
{{"hotel_name": "xxx或null", "check_in": "YYYY-MM-DD或null", "check_out": "YYYY-MM-DD或null", "guest_name": "xxx或null"}}""".format(today=today, hotels_ctx=hotels_ctx)),
        HumanMessage(content=user_msg)
    ])

    # 取出文本
    if hasattr(extract, "content"):
        extract_text = extract.content
    else:
        extract_text = str(extract)


    try:
        cleaned = re.sub(r'<think>.*?</think>', '', extract_text, flags=re.DOTALL).strip()
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            raise ValueError("no json")
        params = json.loads(match.group())
    except:
        reply = "参数解析失败，请重新描述预订信息。"
        print_streaming(reply)
        return {"messages": [AIMessage(content=reply)]}

    missing = [f for f in ["hotel_name", "check_in", "check_out", "guest_name"] if not params.get(f)]
    if missing:
        reply = "还缺少以下信息：{}，请补充后再试。".format("、".join(missing))
        print_streaming(reply)
        return {"messages": [AIMessage(content=reply)]}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.isolation_level = None
        cursor = conn.cursor()

        cursor.execute("BEGIN")
        cursor.execute("SELECT stock FROM hotel WHERE name=?", (params["hotel_name"],))
        row = cursor.fetchone()

        if not row:
            conn.rollback()
            conn.close()
            hotel_name = params["hotel_name"]
            reply = "系统中没有\"{}\"的记录，请先查询该地区酒店。".format(hotel_name)
            print_streaming(reply)
            return {"messages": [AIMessage(content=reply)]}

        if row[0] <= 0:
            conn.rollback()
            conn.close()
            hotel_name = params["hotel_name"]
            reply = "{}已满房，请选择其他酒店。".format(hotel_name)
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
             params["check_in"], params["check_out"], nights)
        )

        cursor.execute("COMMIT")
        conn.close()

        reply = "预订成功！\n订单号：{order_id}\n酒店：{hotel_name}\n入住：{check_in} → 退房：{check_out}（{nights}晚）\n入住人：{guest_name}".format(
            order_id=order_id,
            hotel_name=params["hotel_name"],
            check_in=params["check_in"],
            check_out=params["check_out"],
            nights=nights,
            guest_name=params["guest_name"]
        )
        print_streaming(reply)
        return {
            "booking_info": params,
            "messages": [AIMessage(content=reply)]
        }

    except Exception as e:
        reply = "预订失败：{}".format(str(e))
        print_streaming(reply)
        return {"messages": [AIMessage(content=reply)]}

# ── 节点四：天气查询 ──────────────────────────────────

def weather_node(state: dict) -> dict:
    """查询天气"""
    user_msg = state["messages"][-1].content

    city_extract = llm.invoke([
        SystemMessage(content="从用户输入提取城市英文名，只输出英文城市名。没有明确城市就输出 Zhengzhou。"),
        HumanMessage(content=user_msg)
    ])
    city = city_extract.content.strip()

    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh"},
            timeout=5
        ).json()
        result = geo["results"][0]
        lat, lon = result["latitude"], result["longitude"]
    except:
        lat, lon = 34.7466, 113.6254

    try:
        weather = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weathercode,windspeed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max",
                "forecast_days": 7,
                "timezone": "Asia/Shanghai"
            },
            timeout=5
        ).json()
    except:
        return {"messages": [AIMessage(content="天气服务暂时不可用，请稍后再试。")]}

    today = date.today().isoformat()

    content = stream_llm([
        SystemMessage(content=f"""根据天气JSON数据回答用户问题。
今天日期：{today}
daily数组索引规则：index 0=今天，index 1=明天，index 2=后天，以此类推。
请根据用户问的是哪天，从对应index取数据。
weathercode: 0=晴，1-3=多云，45-48=雾，51-67=雨，80-82=阵雨，95=雷阵雨。
给出温度、天气状况和出行建议，语气友好。"""),
        HumanMessage(content=f"用户问题：{user_msg}\n天气数据：{json.dumps(weather, ensure_ascii=False)}")
    ])

    return {"messages": [AIMessage(content=content)]}

# ── 节点五：知识/闲聊 ────────────────────────────────

def knowledge_node(state: dict) -> dict:
    messages = state["messages"]
    content = stream_llm([
        SystemMessage(content="你是郑州本地旅行助手，熟悉郑州的景点、历史、交通和美食。友好地回答用户问题。")
    ] + messages)
    return {"messages": [AIMessage(content=content)]}