from langgraph.graph import StateGraph, END
from state import AgentState
from nodes import (
    classifier_node, search_node,
    book_node, weather_node, knowledge_node
)
def route_intent(state: dict) -> str:
    """根据 intent 字段决定下一个节点"""
    intent = state.get("intent", "knowledge")
    routing = {
        "query": "search",
        "book": "book",
        "weather": "weather",
        "knowledge": "knowledge"
    }
    return routing.get(intent, "knowledge")
def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    # 注册节点
    graph.add_node("classifier", classifier_node)
    graph.add_node("search", search_node)
    graph.add_node("book", book_node)
    graph.add_node("weather", weather_node)
    graph.add_node("knowledge", knowledge_node)
    # 入口
    graph.set_entry_point("classifier")

    # classifier → 条件路由
    graph.add_conditional_edges(
        "classifier",
        route_intent,
        {
            "search": "search",
            "book": "book",
            "weather": "weather",
            "knowledge": "knowledge"
        }
    )
    # 各节点 → 结束
    graph.add_edge("search", END)
    graph.add_edge("book", END)
    graph.add_edge("weather", END)
    graph.add_edge("knowledge", END)

    return graph.compile(checkpointer=checkpointer)