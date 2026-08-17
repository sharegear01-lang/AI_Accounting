"""数据库 CRUD 工具 - 供 Agent 调用

安全说明：工具不再暴露 user_id 参数——当前用户 ID 经运行时 config
（config["configurable"]["user_id"]）注入，由 API 层 JWT 鉴权写入。
LLM 看不到、也无法伪造该字段，从根源上杜绝跨用户越权。
"""

from datetime import date, datetime
from decimal import Decimal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from sqlalchemy import select, update, delete, func

from app.database import async_session_factory
from app.models.transaction import Transaction
from app.logger import get_logger

logger = get_logger(__name__)


def _user_id(config: RunnableConfig | None) -> str:
    """从运行时 config 读取当前登录用户 ID（由 JWT 鉴权注入）"""
    if config is None:
        return "default_user"
    return (config.get("configurable") or {}).get("user_id", "default_user")


def _parse_date(value: str) -> date | None:
    """解析 YYYY-MM-DD；非法返回 None"""
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# ─── 公共执行函数（interrupt 批准后 与 审批路径 共用，杜绝双实现漂移）──────────

async def execute_delete(ids: list[int], user_id: str) -> tuple[int, str]:
    """批量删除执行。返回 (rowcount, 错误信息)；成功时错误信息为空"""
    try:
        async with async_session_factory() as session:
            stmt = delete(Transaction).where(
                Transaction.id.in_(ids), Transaction.user_id == user_id
            )
            result = await session.execute(stmt)
            await session.commit()
        return result.rowcount, ""
    except Exception as e:
        logger.exception(f"[execute_delete] 批量删除失败: {e}")
        return 0, "❌ 批量删除失败：数据库异常。"


async def execute_update(ids: list[int], fields: dict, user_id: str) -> tuple[int, str]:
    """批量修改执行。返回 (rowcount, 错误信息)；成功时错误信息为空

    fields 中 amount / transaction_date 可能是字符串（interrupt payload 序列化后
    传入），这里统一转换类型，保证与工具内直接构造的字段行为一致。
    """
    clean: dict = {}
    for k, v in fields.items():
        if k == "transaction_date" and isinstance(v, str):
            parsed = _parse_date(v)
            if parsed is None:
                return 0, f"❌ 日期格式错误：'{v}'"
            clean[k] = parsed
        elif k == "amount" and isinstance(v, str):
            try:
                clean[k] = Decimal(v)
            except Exception:
                return 0, f"❌ 金额格式错误：'{v}'"
        else:
            clean[k] = v
    try:
        async with async_session_factory() as session:
            stmt = update(Transaction).where(
                Transaction.id.in_(ids), Transaction.user_id == user_id
            ).values(**clean)
            result = await session.execute(stmt)
            await session.commit()
        return result.rowcount, ""
    except Exception as e:
        logger.exception(f"[execute_update] 批量修改失败: {e}")
        return 0, "❌ 批量修改失败：数据库异常。"


# ─── 工具 ─────────────────────────────────────────────────────────────────────

@tool
async def add_transaction(
    merchant: str,
    amount: float,
    transaction_date: str,
    category: str = "其他",
    description: str = "",
    config: RunnableConfig = None,
) -> str:
    """添加一笔新的交易记录到数据库。

    Args:
        merchant: 商户名称，如"星巴克"、"美团外卖"
        amount: 金额（正数为支出，负数为收入）
        transaction_date: 交易日期，格式为 YYYY-MM-DD
        category: 分类，如"餐饮"、"购物"、"交通"、"娱乐"、"居住"、"其他"
        description: 补充描述（可选）
    """
    user_id = _user_id(config)
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
    start_date: str = "",
    end_date: str = "",
    category: str = "",
    merchant: str = "",
    limit: int = 50,
    config: RunnableConfig = None,
) -> str:
    """查询交易记录。支持按日期范围、分类、商户进行筛选。

    Args:
        start_date: 起始日期（含），格式 YYYY-MM-DD，为空则不限
        end_date: 结束日期（含），格式 YYYY-MM-DD，为空则不限
        category: 按分类筛选，如"餐饮"，为空则不限
        merchant: 按商户名称模糊搜索，为空则不限
        limit: 最多返回条数，默认50
    """
    user_id = _user_id(config)
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
    merchant: str = "",
    amount: float = 0.0,
    transaction_date: str = "",
    category: str = "",
    description: str = "",
    config: RunnableConfig = None,
) -> str:
    """修改一笔已有的交易记录。修改前需要用户确认。

    Args:
        transaction_id: 要修改的交易记录ID
        merchant: 新的商户名称，留空表示不修改
        amount: 新的金额，0表示不修改
        transaction_date: 新的日期（YYYY-MM-DD），留空表示不修改
        category: 新的分类，留空表示不修改
        description: 新的描述，留空表示不修改
    """
    user_id = _user_id(config)
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

            # 构造变更预览（跳过与当前值相同的字段，避免"无变化修改"触发多余确认）
            changes = {}
            if merchant and merchant != txn.merchant:
                changes["商户"] = f"{txn.merchant} → {merchant}"
            if amount != 0.0 and Decimal(str(amount)) != txn.amount:
                changes["金额"] = f"¥{float(txn.amount):.2f} → ¥{amount:.2f}"
            if transaction_date and transaction_date != txn.transaction_date.isoformat():
                changes["日期"] = f"{txn.transaction_date.isoformat()} → {transaction_date}"
            if category and category != txn.category:
                changes["分类"] = f"{txn.category} → {category}"
            if description and description != (txn.description or ""):
                changes["描述"] = f"{txn.description or '无'} → {description}"

            if not changes:
                return "⚠️ 该记录与要修改的内容一致，无需修改。"

            preview_lines = [f"📝 修改交易 #{transaction_id}："]
            for k, v in changes.items():
                preview_lines.append(f"  {k}：{v}")
            preview = "\n".join(preview_lines)

            # 构建结构化修改字段（interrupt 前完成，审批路径复用）
            update_values = {}
            if merchant:
                update_values["merchant"] = merchant
            if amount != 0.0:
                update_values["amount"] = Decimal(str(amount))
            if transaction_date:
                parsed = _parse_date(transaction_date)
                if parsed is None:
                    return f"❌ 日期格式错误：'{transaction_date}'"
                update_values["transaction_date"] = parsed
            if category:
                update_values["category"] = category
            if description:
                update_values["description"] = description

            # interrupt 暂停，等待用户确认
            approved = interrupt({
                "type": "update_preview",
                "preview": preview,
                "transaction_id": transaction_id,
                "changes": changes,
                "fields": {k: str(v) for k, v in update_values.items()},
            })

            if not approved:
                return "❌ 用户拒绝了修改操作。"

        # 用户批准，执行修改（公共执行函数）
        rowcount, err = await execute_update([transaction_id], update_values, user_id)
        if err:
            return err

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
    config: RunnableConfig = None,
) -> str:
    """删除一笔交易记录。删除前会暂停并展示预览，等待用户确认。

    Args:
        transaction_id: 要删除的交易记录ID
    """
    user_id = _user_id(config)
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

        # 用户批准，执行删除（公共执行函数）
        rowcount, err = await execute_delete([transaction_id], user_id)
        if err:
            return err

        logger.info(f"[delete_transaction] 删除成功 | ID={transaction_id}")
        return f"✅ 交易 #{transaction_id} 已删除。"

    except GraphInterrupt:
        raise  # interrupt 必须向上传播，不能被 except Exception 吞掉
    except Exception as e:
        logger.exception(f"[delete_transaction] 删除失败: {e}")
        return f"❌ 删除失败：{str(e)}"


@tool
async def delete_transactions(
    transaction_ids: list[int],
    config: RunnableConfig = None,
) -> str:
    """批量删除一笔或多笔交易记录。删除前会暂停并展示全部记录的明细预览，等待用户一次性确认。

    用户要求删除多条记录时，必须用本工具（一次性传入所有 ID，只确认一次），
    禁止为每条记录分别调用 delete_transaction。

    Args:
        transaction_ids: 要删除的交易记录ID列表（可传单个或多个）
    """
    user_id = _user_id(config)
    logger.info(f"[delete_transactions] 批量删除 | IDs: {transaction_ids}")

    # 去重并保持顺序
    try:
        ids = list(dict.fromkeys(int(i) for i in transaction_ids))
    except (TypeError, ValueError):
        return "❌ transaction_ids 必须是整数 ID 列表。"
    if not ids:
        return "❌ 未提供任何交易记录ID。"

    try:
        async with async_session_factory() as session:
            stmt = select(Transaction).where(
                Transaction.id.in_(ids),
                Transaction.user_id == user_id,
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
    except Exception as e:
        logger.exception(f"[delete_transactions] 查询失败: {e}")
        return "❌ 批量删除失败：数据库异常。"

    if not records:
        return "❌ 未找到任何匹配的交易记录。"

    found_ids = {r.id for r in records}
    missing = [i for i in ids if i not in found_ids]

    # 构造完整明细预览（一次性展示全部，避免多条记录逐条确认）
    lines = [f"🗑️ 即将删除 {len(records)} 笔交易记录："]
    for r in records:
        lines.append(
            f"  #{r.id} | {r.transaction_date.isoformat()} | {r.merchant} "
            f"| ¥{float(r.amount):.2f} | {r.category} | {(r.description or '无')[:20]}"
        )
    if missing:
        lines.append(f"  ⚠️ 以下 ID 不存在，将跳过: {missing}")
    preview = "\n".join(lines)

    # interrupt 一次，等待用户一次性确认
    approved = interrupt({
        "type": "delete_preview",
        "preview": preview,
        "transaction_ids": ids,
        "skipped_missing": missing,
    })

    if not approved:
        return "❌ 用户拒绝了删除操作。"

    # 用户批准，批量删除（公共执行函数）
    rowcount, err = await execute_delete(list(found_ids), user_id)
    if err:
        return err

    logger.info(f"[delete_transactions] 批量删除成功 | 数量: {len(found_ids)}")
    msg = f"✅ 已批量删除 {len(found_ids)} 笔交易记录。"
    if missing:
        msg += f"\n⚠️ 未找到并跳过的 ID: {missing}"
    return msg


@tool
async def update_transactions(
    transaction_ids: list[int],
    merchant: str = "",
    amount: float = 0.0,
    transaction_date: str = "",
    category: str = "",
    description: str = "",
    config: RunnableConfig = None,
) -> str:
    """批量修改一笔或多笔已有的交易记录（所有记录应用相同的修改字段）。修改前会暂停并展示全部变更预览，等待用户一次性确认。

    用户要求批量修改多条记录时，必须用本工具（一次性传入所有 ID，只确认一次），
    禁止为每条记录分别调用 update_transaction。

    Args:
        transaction_ids: 要修改的交易记录ID列表
        merchant: 新的商户名称，留空表示不修改
        amount: 新的金额，0表示不修改
        transaction_date: 新的日期（YYYY-MM-DD），留空表示不修改
        category: 新的分类，留空表示不修改
        description: 新的描述，留空表示不修改
    """
    user_id = _user_id(config)
    logger.info(f"[update_transactions] 批量修改 | IDs: {transaction_ids} | amount={amount} | category={category}")

    try:
        ids = list(dict.fromkeys(int(i) for i in transaction_ids))
    except (TypeError, ValueError):
        return "❌ transaction_ids 必须是整数 ID 列表。"
    if not ids:
        return "❌ 未提供任何交易记录ID。"

    try:
        async with async_session_factory() as session:
            stmt = select(Transaction).where(
                Transaction.id.in_(ids),
                Transaction.user_id == user_id,
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
    except Exception as e:
        logger.exception(f"[update_transactions] 查询失败: {e}")
        return "❌ 批量修改失败：数据库异常。"

    if not records:
        return "❌ 未找到任何匹配的交易记录。"

    found_ids = {r.id for r in records}
    missing = [i for i in ids if i not in found_ids]

    # 逐条构造变更预览（跳过与当前值相同的字段，避免"无变化修改"触发多余确认）
    per_record_changes: dict[int, dict] = {}
    for r in records:
        changes: dict[str, str] = {}
        if merchant and merchant != r.merchant:
            changes["商户"] = f"{r.merchant} → {merchant}"
        if amount != 0.0 and Decimal(str(amount)) != r.amount:
            changes["金额"] = f"¥{float(r.amount):.2f} → ¥{amount:.2f}"
        if transaction_date and transaction_date != r.transaction_date.isoformat():
            changes["日期"] = f"{r.transaction_date.isoformat()} → {transaction_date}"
        if category and category != r.category:
            changes["分类"] = f"{r.category} → {category}"
        if description and description != (r.description or ""):
            changes["描述"] = f"{r.description or '无'} → {description}"
        if changes:
            per_record_changes[r.id] = changes

    if not per_record_changes:
        return "⚠️ 这些记录与要修改的内容一致，无需修改。"

    # 构建结构化修改字段（interrupt 前完成，审批路径复用）
    update_values = {}
    if merchant:
        update_values["merchant"] = merchant
    if amount != 0.0:
        update_values["amount"] = Decimal(str(amount))
    if transaction_date:
        parsed = _parse_date(transaction_date)
        if parsed is None:
            return f"❌ 日期格式错误：'{transaction_date}'"
        update_values["transaction_date"] = parsed
    if category:
        update_values["category"] = category
    if description:
        update_values["description"] = description

    lines = [f"📝 即将批量修改 {len(per_record_changes)} 笔交易记录："]
    for rid, changes in per_record_changes.items():
        lines.append(f"  #{rid}: " + "；".join(f"{k} {v}" for k, v in changes.items()))
    if missing:
        lines.append(f"  ⚠️ 以下 ID 不存在，将跳过: {missing}")
    preview = "\n".join(lines)

    # interrupt 一次，等待用户一次性确认
    approved = interrupt({
        "type": "update_preview",
        "preview": preview,
        "transaction_ids": list(per_record_changes.keys()),
        "changes": {str(k): v for k, v in per_record_changes.items()},
        "skipped_missing": missing,
        "fields": {k: str(v) for k, v in update_values.items()},
    })

    if not approved:
        return "❌ 用户拒绝了修改操作。"

    # 用户批准，批量修改（公共执行函数；仅作用于有实际变更的记录）
    rowcount, err = await execute_update(list(per_record_changes.keys()), update_values, user_id)
    if err:
        return err

    logger.info(f"[update_transactions] 批量修改成功 | 数量: {len(per_record_changes)}")
    msg = f"✅ 已批量修改 {len(per_record_changes)} 笔交易记录。"
    if missing:
        msg += f"\n⚠️ 未找到并跳过的 ID: {missing}"
    return msg
