"""数据库 CRUD 工具 - 供 Agent 调用

安全说明：工具不再暴露 user_id 参数——当前用户 ID 经运行时 config
（config["configurable"]["user_id"]）注入，由 API 层 JWT 鉴权写入。
LLM 看不到、也无法伪造该字段，从根源上杜绝跨用户越权。

设计说明：工具收敛为 4 个（add_transactions / query_transactions /
update_transactions / delete_transactions）。单条与批量统一走同一套逻辑——
单条就是长度为 1 的批量，杜绝双实现漂移；确认类操作（修改/删除）一律
一次 interrupt、一次确认，禁止逐条确认。
"""

from datetime import date
from decimal import Decimal
import time

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete

from app.database import async_session_factory
from app.models.transaction import Transaction
from app.logger import get_logger

logger = get_logger(__name__)


def _user_id(config: RunnableConfig | None) -> str:
    """从运行时 config 读取当前登录用户 ID（由 JWT 鉴权注入）

    缺失即视为运行时错误：工具只允许在鉴权注入的 config 下执行，
    绝不允许静默落到共享的 default_user（fail-open 会导致跨用户数据混写）。
    """
    user_id = (config.get("configurable") or {}).get("user_id") if config else None
    if not user_id:
        raise RuntimeError(
            "运行时缺少 user_id：工具必须在 JWT 鉴权注入 "
            "config['configurable']['user_id'] 后执行"
        )
    return user_id


def _parse_date(value: str) -> date | None:
    """解析 YYYY-MM-DD；非法返回 None"""
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _normalize_ids(transaction_ids: int | list[int]) -> tuple[list[int], str]:
    """把 LLM 传入的 ID（单个 int 或 list）归一为去重列表。

    返回 (ids, 错误信息)；错误信息为空表示成功。单条与批量共用，单条即 [id]。
    """
    raw = transaction_ids if isinstance(transaction_ids, list) else [transaction_ids]
    try:
        ids = list(dict.fromkeys(int(i) for i in raw))
    except (TypeError, ValueError):
        return [], "❌ transaction_ids 必须是整数 ID（或整数 ID 列表）。"
    if not ids:
        return [], "❌ 未提供任何交易记录ID。"
    return ids, ""


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

class TransactionItem(BaseModel):
    """单笔交易记录输入（add_transactions 的元素）"""

    merchant: str = Field(description="商户名称，如“星巴克”、“美团外卖”")
    amount: float = Field(description="金额（正数为支出，负数为收入）")
    transaction_date: str = Field(description="交易日期，格式 YYYY-MM-DD")
    category: str = Field(default="其他", description="分类，如“餐饮”、“购物”、“交通”、“娱乐”、“居住”、“其他”")
    description: str = Field(default="", description="补充描述（可选）")


@tool
async def add_transactions(
    transactions: list[TransactionItem],
    config: RunnableConfig = None,
) -> str:
    """新增一笔或多笔交易记录到数据库（一次性写入，无需确认）。

    单笔记账也用本工具，传单元素列表即可。适合用户一次描述多笔消费、
    或一张小票 OCR 出多笔明细时一次调用全部写入。

    Args:
        transactions: 要新增的交易记录列表（一笔或多笔）
    """
    user_id = _user_id(config)

    if not transactions:
        return "❌ 未提供任何交易记录。"

    # 先整体校验（日期/金额），任一非法则整批拒绝，避免部分写入
    items: list[dict] = []
    for idx, t in enumerate(transactions, start=1):
        parsed_date = _parse_date(t.transaction_date)
        if parsed_date is None:
            return f"❌ 第 {idx} 条日期格式错误：'{t.transaction_date}'，请使用 YYYY-MM-DD 格式。"
        items.append({
            "merchant": t.merchant,
            "amount": Decimal(str(t.amount)),
            "category": t.category,
            "transaction_date": parsed_date,
            "description": t.description or None,
        })

    logger.info(f"[add_transactions] 开始记账 | 笔数: {len(items)}")
    try:
        async with async_session_factory() as session:
            rows = []
            for it in items:
                txn = Transaction(user_id=user_id, **it)
                session.add(txn)
                rows.append(txn)
            await session.commit()
            for txn in rows:
                await session.refresh(txn)
    except Exception as e:
        logger.exception(f"[add_transactions] 数据库写入失败: {e}")
        return "❌ 记账失败：数据库写入异常。"

    if len(rows) == 1:
        t = rows[0]
        logger.info(f"[add_transactions] 记账成功 | ID: {t.id}")
        return (
            f"✅ 记账成功！\n"
            f"  商户：{t.merchant}\n"
            f"  金额：¥{float(t.amount):.2f}\n"
            f"  分类：{t.category}\n"
            f"  日期：{t.transaction_date.isoformat()}\n"
            f"  描述：{t.description or '无'}\n"
            f"  记录ID：{t.id}"
        )

    logger.info(f"[add_transactions] 批量记账成功 | 笔数: {len(rows)}")
    lines = [f"✅ 记账成功！新增 {len(rows)} 笔："]
    for t in rows:
        lines.append(
            f"  #{t.id} | {t.transaction_date.isoformat()} | {t.merchant} "
            f"| ¥{float(t.amount):.2f} | {t.category} | {t.description or '无'}"
        )
    return "\n".join(lines)


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
async def update_transactions(
    transaction_ids: int | list[int],
    merchant: str = "",
    amount: float = 0.0,
    transaction_date: str = "",
    category: str = "",
    description: str = "",
    config: RunnableConfig = None,
) -> str:
    """修改一笔或多笔已有的交易记录（所有记录应用相同的修改字段）。修改前会暂停并展示全部变更预览，等待用户一次性确认。

    单条修改也用本工具（ID 可传 5 或 [5]）。用户要求修改多条记录时，
    必须一次性传入全部 ID（展示完整明细、只确认一次）。

    Args:
        transaction_ids: 要修改的交易记录ID（单个整数或整数列表）
        merchant: 新的商户名称，留空表示不修改
        amount: 新的金额，0表示不修改
        transaction_date: 新的日期（YYYY-MM-DD），留空表示不修改
        category: 新的分类，留空表示不修改
        description: 新的描述，留空表示不修改
    """
    user_id = _user_id(config)
    ids, err = _normalize_ids(transaction_ids)
    if err:
        return err
    logger.info(f"[update_transactions] 修改交易 | IDs: {ids} | amount={amount} | category={category}")

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

    # 按用户传入的 ID 顺序重排（SQL 无 ORDER BY，返回顺序不可靠），保证预览与意图一致
    by_id = {r.id: r for r in records}
    records = [by_id[i] for i in ids if i in by_id]

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

    # 预览：单条用详细块，多条用紧凑行（一次 interrupt、一次确认）
    if len(records) == 1:
        rid, changes = next(iter(per_record_changes.items()))
        preview = f"📝 修改交易 #{rid}：\n" + "\n".join(f"  {k}：{v}" for k, v in changes.items())
    else:
        lines = [f"📝 即将批量修改 {len(per_record_changes)} 笔交易记录："]
        for rid, changes in per_record_changes.items():
            lines.append(f"  #{rid}: " + "；".join(f"{k} {v}" for k, v in changes.items()))
        if missing:
            lines.append(f"  ⚠️ 以下 ID 不存在，将跳过: {missing}")
        preview = "\n".join(lines)

    approved = interrupt({
        "type": "update_preview",
        "preview": preview,
        "transaction_ids": list(per_record_changes.keys()),
        "changes": {str(k): v for k, v in per_record_changes.items()},
        "skipped_missing": missing,
        "fields": {k: str(v) for k, v in update_values.items()},
        "interrupt_at": time.time(),
    })

    if not approved:
        return "❌ 用户拒绝了修改操作。"

    # 用户批准，执行修改（公共执行函数；仅作用于有实际变更的记录）
    rowcount, err = await execute_update(list(per_record_changes.keys()), update_values, user_id)
    if err:
        return err

    logger.info(f"[update_transactions] 修改成功 | 数量: {len(per_record_changes)}")
    msg = f"✅ 已修改 {len(per_record_changes)} 笔交易记录。"
    if missing:
        msg += f"\n⚠️ 未找到并跳过的 ID: {missing}"
    return msg


@tool
async def delete_transactions(
    transaction_ids: int | list[int],
    config: RunnableConfig = None,
) -> str:
    """删除一笔或多笔交易记录。删除前会暂停并展示全部记录的明细预览，等待用户一次性确认。

    单条删除也用本工具（ID 可传 5 或 [5]）。用户要求删除多条记录时，
    必须一次性传入全部 ID（展示完整明细、只确认一次）。

    Args:
        transaction_ids: 要删除的交易记录ID（单个整数或整数列表）
    """
    user_id = _user_id(config)
    ids, err = _normalize_ids(transaction_ids)
    if err:
        return err
    logger.info(f"[delete_transactions] 删除 | IDs: {ids}")

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

    # 按用户传入的 ID 顺序重排（SQL 无 ORDER BY，返回顺序不可靠），保证预览与意图一致
    by_id = {r.id: r for r in records}
    records = [by_id[i] for i in ids if i in by_id]

    found_ids = {r.id for r in records}
    missing = [i for i in ids if i not in found_ids]
    ordered_ids = [r.id for r in records]  # 按用户输入顺序（set 无序，不能直接 list(found_ids)）

    # 预览：单条用详细块，多条用紧凑行（一次 interrupt、一次确认）
    if len(records) == 1:
        r = records[0]
        preview = (
            f"🗑️ 即将删除交易 #{r.id}：\n"
            f"  商户：{r.merchant}\n"
            f"  金额：¥{float(r.amount):.2f}\n"
            f"  分类：{r.category}\n"
            f"  日期：{r.transaction_date.isoformat()}\n"
            f"  描述：{r.description or '无'}"
        )
    else:
        lines = [f"🗑️ 即将删除 {len(records)} 笔交易记录："]
        for r in records:
            lines.append(
                f"  #{r.id} | {r.transaction_date.isoformat()} | {r.merchant} "
                f"| ¥{float(r.amount):.2f} | {r.category} | {(r.description or '无')[:20]}"
            )
        if missing:
            lines.append(f"  ⚠️ 以下 ID 不存在，将跳过: {missing}")
        preview = "\n".join(lines)

    approved = interrupt({
        "type": "delete_preview",
        "preview": preview,
        "transaction_ids": ordered_ids,
        "skipped_missing": missing,
        "interrupt_at": time.time(),
    })

    if not approved:
        return "❌ 用户拒绝了删除操作。"

    # 用户批准，批量删除（公共执行函数）
    rowcount, err = await execute_delete(ordered_ids, user_id)
    if err:
        return err

    logger.info(f"[delete_transactions] 删除成功 | 数量: {len(ordered_ids)}")
    msg = f"✅ 已删除 {len(ordered_ids)} 笔交易记录。"
    if missing:
        msg += f"\n⚠️ 未找到并跳过的 ID: {missing}"
    return msg
