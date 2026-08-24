"""工具执行节点"""

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from app.agent.state import AgentState
from app.agent.tools import ALL_TOOLS
from app.logger import get_logger

logger = get_logger(__name__)


async def tools_node(state: AgentState, config: RunnableConfig) -> dict:
    """执行 LLM 请求的工具调用

    安全说明：工具不再接收 user_id 参数——当前用户 ID 由 JWT 鉴权写入
    config["configurable"]["user_id"]，经 LangChain 自动注入到工具的
    config 参数中。LLM 看不到也无法伪造该字段，保证多租户数据隔离。
    """
    last_message = state["messages"][-1]
    tool_map = {t.name: t for t in ALL_TOOLS}
    results: list[ToolMessage] = []

    for tc in last_message.tool_calls:
        name = tc["name"]
        args = dict(tc.get("args", {}) or {})

        tool = tool_map.get(name)
        if tool is None:
            content = f"❌ 未知工具: {name}"
        else:
            try:
                content = str(await tool.ainvoke(args, config=config))
            except GraphInterrupt:
                raise  # interrupt 必须向上传播，不能被吞掉
            except Exception as e:
                logger.exception(f"[Tools] {name} 执行失败: {e}")
                content = f"❌ 工具 {name} 执行失败：{e}"
        logger.debug(f"[Tools] {name}({args}) → {content[:120]}")
        results.append(ToolMessage(content=content, tool_call_id=tc["id"]))

    return {"messages": results}
