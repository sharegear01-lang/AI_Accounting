"""Agent 工具集"""

from app.agent.tools.crud import (
    add_transaction,
    query_transactions,
    update_transaction,
    delete_transaction,
    update_transactions,
    delete_transactions,
)

ALL_TOOLS = [
    add_transaction,
    query_transactions,
    update_transaction,
    delete_transaction,
    update_transactions,
    delete_transactions,
]
