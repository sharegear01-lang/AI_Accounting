"""LangGraph 节点包：按图拓扑组织

模块职责与 graph 节点一一对应：
- llm:        System Prompt + LLM 工厂（agent 节点共享依赖）
- ocr:        图片识别 + 防幻觉闸门（独立图节点，LangSmith 可见独立 span）
- preprocess: 消息组装 + 拦截回复
- agent:      Agent 推理 + 历史裁剪 + 结束路由
- tools:      工具执行
"""

from app.agent.nodes.agent import agent_node, should_continue
from app.agent.nodes.llm import SYSTEM_PROMPT, _get_llm
from app.agent.nodes.ocr import ocr_node
from app.agent.nodes.preprocess import preprocess_node, respond_blocked_node, should_block
from app.agent.nodes.tools import tools_node

__all__ = [
    "SYSTEM_PROMPT",
    "_get_llm",
    "agent_node",
    "ocr_node",
    "preprocess_node",
    "respond_blocked_node",
    "should_block",
    "should_continue",
    "tools_node",
]
