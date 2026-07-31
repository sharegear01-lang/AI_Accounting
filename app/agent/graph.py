"""LangGraph 状态机组装与编译"""
from langgraph.graph import StateGraph, START, END

from app.agent.state import AgentState
from app.agent.nodes import agent_node, tools_node, should_continue

def build_graph() -> StateGraph:
    """构建并编译 Agent 状态机

    流程:
        START -> agent_node -> (有工具调用?) -> tools_node -> agent_node
                            -> (无工具调用?) -> END
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)

    # 添加边
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "__end__": END,
        },
    )
    graph.add_edge("tools", "agent")

    return graph


def compile_graph(checkpointer=None):
    """编译图，可选注入 checkpointer 实现会话记忆

    Args:
        checkpointer: LangGraph checkpointer 实例（如 PostgresSaver）
    """
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer)

