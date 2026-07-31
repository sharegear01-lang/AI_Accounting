"""数据库 CRUD 工具 - 供 Agent 调用"""

from datetime import date, datetime
from decimal import Decimal

from langchain_core.tools import tool
from sqlalchemy import select, func

from app.database import async_session_factory
from app.models.transaction import Transaction


@tool
async def add_transaction(
    merchant: str,
    amount: float,
    transaction_date: str,
    category: str = "其他",
    description: str = "",
    user_id: str = "default_user",
) -> str:
    """添加一笔新的交易记录到数据库。

    Args:
        merchant: 商户名称，如"星巴克"、"美团外卖"
        amount: 金额（正数为支出，负数为收入）
        transaction_date: 交易日期，格式为 YYYY-MM-DD
        category: 分类，如"餐饮"、"购物"、"交通"、"娱乐"、"居住"、"其他"
        description: 补充描述（可选）
        user_id: 用户ID（系统自动填充）
    """
    try:
        parsed_date = date.fromisoformat(transaction_date)
    except ValueError:
        return f"❌ 日期格式错误：'{transaction_date}'，请使用 YYYY-MM-DD 格式。"

    async with async_session_factory() as session:
        txn = Transaction(
            user_id=user_id,
            merchant=merchant,
            amount=Decimal(str(amount)),
            category=category,
            transaction_date=parsed_date,
            description=description or None,
        )
        session.add(txn)
        await session.commit()
        await session.refresh(txn)

    return (
        f"✅ 记账成功！\n"
        f"  商户：{merchant}\n"
        f"  金额：¥{amount:.2f}\n"
        f"  分类：{category}\n"
        f"  日期：{parsed_date.isoformat()}\n"
        f"  描述：{description or '无'}\n"
        f"  记录ID：{txn.id}"
    )


@tool
async def query_transactions(
    user_id: str = "default_user",
    start_date: str = "",
    end_date: str = "",
    category: str = "",
    merchant: str = "",
    limit: int = 50,
) -> str:
    """查询交易记录。支持按日期范围、分类、商户进行筛选。

    Args:
        user_id: 用户ID（系统自动填充）
        start_date: 起始日期（含），格式 YYYY-MM-DD，为空则不限
        end_date: 结束日期（含），格式 YYYY-MM-DD，为空则不限
        category: 按分类筛选，如"餐饮"，为空则不限
        merchant: 按商户名称模糊搜索，为空则不限
        limit: 最多返回条数，默认50
    """
    async with async_session_factory() as session:
        stmt = select(Transaction).where(Transaction.user_id == user_id)

        # 日期范围筛选
        if start_date:
            try:
                stmt = stmt.where(
                    Transaction.transaction_date >= date.fromisoformat(start_date)
                )
            except ValueError:
                return f"❌ 起始日期格式错误：'{start_date}'"

        if end_date:
            try:
                stmt = stmt.where(
                    Transaction.transaction_date <= date.fromisoformat(end_date)
                )
            except ValueError:
                return f"❌ 结束日期格式错误：'{end_date}'"

        # 分类筛选
        if category:
            stmt = stmt.where(Transaction.category == category)

        # 商户模糊搜索
        if merchant:
            stmt = stmt.where(Transaction.merchant.ilike(f"%{merchant}%"))

        # 按日期倒序
        stmt = stmt.order_by(Transaction.transaction_date.desc()).limit(limit)

        result = await session.execute(stmt)
        records = result.scalars().all()

    if not records:
        return "📭 没有找到符合条件的交易记录。"

    # 统计汇总
    total = sum(float(r.amount) for r in records)
    total_expense = sum(float(r.amount) for r in records if float(r.amount) > 0)
    total_income = sum(float(r.amount) for r in records if float(r.amount) < 0)

    lines = [f"📊 查询到 {len(records)} 条记录（支出合计 ¥{total_expense:.2f}，收入合计 ¥{abs(total_income):.2f}）\n"]
    lines.append(f"{'ID':<5} {'日期':<12} {'商户':<15} {'金额':>10} {'分类':<8} {'描述'}")
    lines.append("-" * 75)

    for r in records:
        desc = (r.description or "")[:20]
        lines.append(
            f"{r.id:<5} {r.transaction_date.isoformat():<12} "
            f"{r.merchant:<15} {'¥' + f'{float(r.amount):.2f}':>10} "
            f"{r.category:<8} {desc}"
        )

    return "\n".join(lines)
