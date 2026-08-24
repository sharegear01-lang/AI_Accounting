"""LangGraph 状态机组装与编译"""
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    agent_node,
    ocr_node,
    preprocess_node,
    respond_blocked_node,
    should_block,
    should_continue,
    tools_node,
)
from app.agent.state import AgentState


def build_graph() -> StateGraph:
    """构建并编译 Agent 状态机

    流程:
        START -> ocr -> (OCR 拦截?) -> respond_blocked_node -> END
                      -> (正常)      -> preprocess -> agent -> (有工具调用?) -> tools -> agent
                                                            -> (无工具调用?) -> END
    """
    graph = StateGraph(AgentState)

    # 添加节点（节点实现分散在 app/agent/nodes/ 包，与图拓扑一一对应）
    graph.add_node("ocr", ocr_node)
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("respond_blocked", respond_blocked_node)

    # 添加边
    graph.add_edge(START, "ocr")
    graph.add_conditional_edges(
        "ocr",
        should_block,
        {
            "blocked": "respond_blocked",
            "proceed": "preprocess",
        },
    )
    # 正常路径：OCR 通过 → 组装消息 → agent 推理
    graph.add_edge("preprocess", "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "__end__": END,
        },
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("respond_blocked", END)

    return graph


def compile_graph(checkpointer=None):
    """编译图，可选注入 checkpointer 实现会话记忆

    Args:
        checkpointer: LangGraph checkpointer 实例（如 PostgresSaver）
    """
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer)

