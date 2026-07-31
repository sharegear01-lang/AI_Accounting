"""Agent 工具集"""

from app.agent.tools.crud import add_transaction, query_transactions

ALL_TOOLS = [add_transaction, query_transactions]
