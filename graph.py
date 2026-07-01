from langgraph.graph import END, StateGraph
from langgraph.types import Send

from nodes import (
    aggregator_node,
    book_node,
    classifier_node,
    knowledge_node,
    search_node,
    weather_node,
)
from state import AgentState


VALID_INTENTS = {"query", "book", "weather", "knowledge"}


def route_intent(state: dict) -> str:
    """Route a single intent to its graph node, keeping knowledge as fallback."""
    intent = state.get("intent") or "knowledge"
    routing = {
        "query": "search",
        "book": "book",
        "weather": "weather",
        "knowledge": "knowledge",
    }
    return routing.get(intent, "knowledge")


def fan_out(state: dict):
    """Fan out to one or more intent-specific nodes."""
    intents = state.get("intents") or ["knowledge"]
    unique_intents = []
    for intent in intents:
        normalized = intent if intent in VALID_INTENTS else "knowledge"
        if normalized not in unique_intents:
            unique_intents.append(normalized)

    return [Send(route_intent({"intent": intent}), state) for intent in unique_intents]


def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    # 注册节点
    graph.add_node("classifier", classifier_node)
    graph.add_node("search", search_node)
    graph.add_node("book", book_node)
    graph.add_node("weather", weather_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("aggregator", aggregator_node)

    # 入口
    graph.set_entry_point("classifier")

    # classifier → 条件路由
    graph.add_conditional_edges("classifier", fan_out, ["search", "book", "weather", "knowledge"])




    # 各节点 → 结束
    graph.add_edge("search", "aggregator")
    graph.add_edge("book", "aggregator")
    graph.add_edge("weather", "aggregator")
    graph.add_edge("knowledge", "aggregator")
    graph.add_edge("aggregator", END)

    return graph.compile(checkpointer=checkpointer)
