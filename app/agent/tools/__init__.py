"""Agent 工具集"""

from app.agent.tools.crud import (
    add_transactions,
    query_transactions,
    update_transactions,
    delete_transactions,
)

ALL_TOOLS = [
    add_transactions,
    query_transactions,
    update_transactions,
    delete_transactions,
]
