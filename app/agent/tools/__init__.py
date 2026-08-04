"""Agent 工具集"""

from app.agent.tools.crud import (
    add_transaction,
    query_transactions,
    update_transaction,
    delete_transaction,
)

ALL_TOOLS = [add_transaction, query_transactions, update_transaction, delete_transaction]
