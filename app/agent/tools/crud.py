"""数据库 CRUD 工具 - 供 Agent 调用"""

from datetime import date, datetime
from decimal import Decimal

from langchain_core.tools import tool
from langgraph.types import interrupt, Command
from langgraph.errors import GraphInterrupt
from sqlalchemy import select, update, delete, func

from app.database import async_session_factory
from app.models.transaction import Transaction
from app.logger import get_logger

logger = get_logger(__name__)


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
    logger.info(f"[add_transaction] 开始记账 | 商户: {merchant} | 金额: {amount} | 日期: {transaction_date} | 分类: {category}")

    try:
        parsed_date = date.fromisoformat(transaction_date)
    except ValueError:
        logger.warning(f"[add_transaction] 日期格式错误: '{transaction_date}'")
        return f"❌ 日期格式错误：'{transaction_date}'，请使用 YYYY-MM-DD 格式。"

    try:
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

        logger.info(f"[add_transaction] 记账成功 | ID: {txn.id}")
    except Exception as e:
        logger.exception(f"[add_transaction] 数据库写入失败: {e}")
        return f"❌ 记账失败：数据库写入异常。"

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
    logger.info(f"[query_transactions] 查询 | 日期: {start_date or '不限'}~{end_date or '不限'} | 分类: {category or '全部'} | 商户: {merchant or '全部'} | limit: {limit}")

    try:
        async with async_session_factory() as session:
            stmt = select(Transaction).where(Transaction.user_id == user_id)

            # 日期范围筛选
            if start_date:
                try:
                    stmt = stmt.where(
                        Transaction.transaction_date >= date.fromisoformat(start_date)
                    )
                except ValueError:
                    logger.warning(f"[query_transactions] 起始日期格式错误: '{start_date}'")
                    return f"❌ 起始日期格式错误：'{start_date}'"

            if end_date:
                try:
                    stmt = stmt.where(
                        Transaction.transaction_date <= date.fromisoformat(end_date)
                    )
                except ValueError:
                    logger.warning(f"[query_transactions] 结束日期格式错误: '{end_date}'")
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
    except Exception as e:
        logger.exception(f"[query_transactions] 数据库查询失败: {e}")
        return "❌ 查询失败：数据库异常。"

    logger.info(f"[query_transactions] 查询完成 | 结果数: {len(records)}")

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


@tool
async def update_transaction(
    transaction_id: int,
    user_id: str = "default_user",
    merchant: str = "",
    amount: float = 0.0,
    transaction_date: str = "",
    category: str = "",
    description: str = "",
) -> str:
    """修改一笔已有的交易记录。修改前需要用户确认。

    Args:
        transaction_id: 要修改的交易记录ID
        user_id: 用户ID（系统自动填充）
        merchant: 新的商户名称，留空表示不修改
        amount: 新的金额，0表示不修改
        transaction_date: 新的日期（YYYY-MM-DD），留空表示不修改
        category: 新的分类，留空表示不修改
        description: 新的描述，留空表示不修改
    """
    logger.info(f"[update_transaction] 修改交易 ID={transaction_id}")

    try:
        async with async_session_factory() as session:
            # 查询原始记录
            stmt = select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id,
            )
            result = await session.execute(stmt)
            txn = result.scalar_one_or_none()

            if not txn:
                return f"❌ 未找到ID为 {transaction_id} 的交易记录。"

            # 构造变更预览
            changes = {}
            if merchant:
                changes["商户"] = f"{txn.merchant} → {merchant}"
            if amount != 0.0:
                changes["金额"] = f"¥{float(txn.amount):.2f} → ¥{amount:.2f}"
            if transaction_date:
                changes["日期"] = f"{txn.transaction_date.isoformat()} → {transaction_date}"
            if category:
                changes["分类"] = f"{txn.category} → {category}"
            if description:
                changes["描述"] = f"{txn.description or '无'} → {description}"

            if not changes:
                return "⚠️ 没有提供任何修改字段。"

            preview_lines = [f"📝 修改交易 #{transaction_id}："]
            for k, v in changes.items():
                preview_lines.append(f"  {k}：{v}")
            preview = "\n".join(preview_lines)

            # interrupt 暂停，等待用户确认
            approved = interrupt({
                "type": "update_preview",
                "preview": preview,
                "transaction_id": transaction_id,
                "changes": changes,
            })

            if not approved:
                return "❌ 用户拒绝了修改操作。"

            # 用户批准，执行修改
            update_values = {}
            if merchant:
                update_values["merchant"] = merchant
            if amount != 0.0:
                update_values["amount"] = Decimal(str(amount))
            if transaction_date:
                try:
                    update_values["transaction_date"] = date.fromisoformat(transaction_date)
                except ValueError:
                    return f"❌ 日期格式错误：'{transaction_date}'"
            if category:
                update_values["category"] = category
            if description:
                update_values["description"] = description

            if update_values:
                stmt = update(Transaction).where(
                    Transaction.id == transaction_id,
                    Transaction.user_id == user_id,
                ).values(**update_values)
                await session.execute(stmt)
                await session.commit()

            logger.info(f"[update_transaction] 修改成功 | ID={transaction_id}")
            return f"✅ 交易 #{transaction_id} 修改成功！\n" + "\n".join(f"  {k}：{v}" for k, v in changes.items())

    except GraphInterrupt:
        raise  # interrupt 必须向上传播，不能被 except Exception 吞掉
    except Exception as e:
        logger.exception(f"[update_transaction] 修改失败: {e}")
        return f"❌ 修改失败：{str(e)}"


@tool
async def delete_transaction(
    transaction_id: int,
    user_id: str = "default_user",
) -> str:
    """删除一笔交易记录。删除前会暂停并展示预览，等待用户确认。

    Args:
        transaction_id: 要删除的交易记录ID
        user_id: 用户ID（系统自动填充）
    """
    logger.info(f"[delete_transaction] 删除交易 ID={transaction_id}")

    try:
        async with async_session_factory() as session:
            # 查询原始记录
            stmt = select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id,
            )
            result = await session.execute(stmt)
            txn = result.scalar_one_or_none()

            if not txn:
                return f"❌ 未找到ID为 {transaction_id} 的交易记录。"

            preview = (
                f"🗑️ 即将删除交易 #{transaction_id}：\n"
                f"  商户：{txn.merchant}\n"
                f"  金额：¥{float(txn.amount):.2f}\n"
                f"  分类：{txn.category}\n"
                f"  日期：{txn.transaction_date.isoformat()}\n"
                f"  描述：{txn.description or '无'}"
            )

            # interrupt 暂停，等待用户确认
            approved = interrupt({
                "type": "delete_preview",
                "preview": preview,
                "transaction_id": transaction_id,
            })

            if not approved:
                return "❌ 用户拒绝了删除操作。"

            # 用户批准，执行删除
            stmt = delete(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id,
            )
            await session.execute(stmt)
            await session.commit()

            logger.info(f"[delete_transaction] 删除成功 | ID={transaction_id}")
            return f"✅ 交易 #{transaction_id} 已删除。"

    except GraphInterrupt:
        raise  # interrupt 必须向上传播，不能被 except Exception 吞掉
    except Exception as e:
        logger.exception(f"[delete_transaction] 删除失败: {e}")
        return f"❌ 删除失败：{str(e)}"
