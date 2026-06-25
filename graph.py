from langgraph.graph import StateGraph, END
from langgraph.types import Send
from state import AgentState
from nodes import (
    classifier_node, search_node,
    book_node, weather_node, knowledge_node,
    aggregator_node
)
def fan_out(state: dict):
    """返回 Send 列表，LangGraph 并行执行每个意图对应的节点。"""
    intents = state.get("intents", ["knowledge"])
    sends = []
    for intent in intents:
        if intent == "query":
            sends.append(Send("search", state))
        elif intent == "book":
            sends.append(Send("book", state))
        elif intent == "weather":
            sends.append(Send("weather", state))
        else:
            sends.append(Send("knowledge", state))
    return sends

    return routing.get(intent, "knowledge")
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