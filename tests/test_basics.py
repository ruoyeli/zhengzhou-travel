"""基础单元测试：路由、路径、API 降级、think 标签清理。"""

from graph import route_intent
from nodes import _fetch_amap_hotels, _strip_think_tags
from paths import DATA_DIR, HOTEL_DB_PATH, PROJECT_ROOT


def test_route_intent():
    """意图路由应把 query/book/weather 映射到对应节点，未知意图回退 knowledge。"""
    assert route_intent({"intent": "query"}) == "search"
    assert route_intent({"intent": "book"}) == "book"
    assert route_intent({"intent": "weather"}) == "weather"
    assert route_intent({"intent": "knowledge"}) == "knowledge"
    assert route_intent({"intent": "unknown"}) == "knowledge"
    assert route_intent({}) == "knowledge"


def test_hotel_db_path():
    """SQLite 数据库应位于项目 data/ 目录下，而非硬编码绝对路径。"""
    assert HOTEL_DB_PATH == PROJECT_ROOT / "data" / "hotel.db"
    assert DATA_DIR == PROJECT_ROOT / "data"
    assert HOTEL_DB_PATH.name == "hotel.db"
    assert "data" in HOTEL_DB_PATH.parts


def test_fetch_amap_hotels_without_key(monkeypatch):
    """未配置高德 Key 时应安全返回空列表，不抛异常。"""
    import nodes

    monkeypatch.setattr(nodes, "AMAP_KEY", None)
    result = _fetch_amap_hotels("郑州东站", "郑州")
    assert result == []


def test_strip_think_tags_removes_reasoning():
    """<think> 标签及内容应被完全移除，只保留最终输出。"""
    assert _strip_think_tags("<think>用户想查酒店\nintent=query</think>query") == "query"
    assert _strip_think_tags("<think>推理过程</think>  book  ") == "book"
    assert _strip_think_tags("weather") == "weather"
    assert _strip_think_tags("") == ""


def test_strip_think_tags_multiline():
    """多行 think 标签也应正确移除。"""
    result = _strip_think_tags(
        "<think>\n用户想要预订\n第二天入住\n</think>\nbook\n"
    )
    assert result == "book"
