"""交易记录 REST API - 网页端的直接查账 / 记账 / 修改 / 删除

与 Agent 工具（app/agent/tools/crud.py）并存：
- Agent 工具：聊天自然语言入口，修改/删除带 HITL interrupt 确认
- 本模块：网页表单入口，确认动作由前端弹窗完成（编辑表单 / 删除确认框），
  后端直接执行，不走 interrupt

所有接口均以 JWT 鉴权，数据严格按 current_user.id 隔离。
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.auth.dependencies import get_current_user
from app.database import async_session_factory
from app.logger import get_logger
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import (
    CategoryStat,
    DashboardSummary,
    TransactionCreate,
    TransactionListResponse,
    TransactionOut,
    TransactionUpdate,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])

# 标准分类（前端也维护同一份，见 frontend/src/constants.js）
DEFAULT_CATEGORIES = ["餐饮", "交通", "购物", "娱乐", "居住", "医疗", "教育", "工资", "理财", "其他"]

_MAX_PAGE_SIZE = 100
_DEFAULT_PAGE_SIZE = 20


# ─── 首页仪表盘 ──────────────────────────────────────────────────────────────

@router.get("/stats", response_model=DashboardSummary, summary="首页统计汇总")
async def dashboard_stats(current_user: User = Depends(get_current_user)):
    """首页仪表盘数据：本月收支、分类汇总、最近消费"""
    user_id = current_user.id
    today = date.today()
    month_start = date(today.year, today.month, 1)

    try:
        async with async_session_factory() as session:
            # 本月全部金额（含符号），用于收支/笔数统计
            month_rows = await session.execute(
                select(Transaction.amount, Transaction.id).where(
                    Transaction.user_id == user_id,
                    Transaction.transaction_date >= month_start,
                )
            )
            month_rows = month_rows.all()
            month_expense = sum(float(r[0]) for r in month_rows if float(r[0]) > 0)
            month_income = abs(sum(float(r[0]) for r in month_rows if float(r[0]) < 0))

            # 本月分类汇总
            cat_rows = await session.execute(
                select(
                    Transaction.category,
                    func.sum(Transaction.amount),
                    func.count(Transaction.id),
                )
                .where(
                    Transaction.user_id == user_id,
                    Transaction.transaction_date >= month_start,
                )
                .group_by(Transaction.category)
                .order_by(func.sum(Transaction.amount))
            )
            category_stats = [
                CategoryStat(category=c, amount=float(a), count=n)
                for c, a, n in cat_rows.all()
            ]

            # 全部统计
            all_rows = await session.execute(
                select(Transaction.amount).where(Transaction.user_id == user_id)
            )
            amounts = [float(r[0]) for r in all_rows.all()]
            total_expense = sum(a for a in amounts if a > 0)

            # 最近消费（日期倒序，最多 10 条）
            recent_rows = await session.execute(
                select(Transaction)
                .where(Transaction.user_id == user_id)
                .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
                .limit(10)
            )
            recent = list(recent_rows.scalars().all())
    except Exception as e:
        logger.exception(f"[transactions/stats] 查询失败: {e}")
        raise HTTPException(status_code=500, detail="统计数据查询失败") from e

    logger.info(f"[transactions/stats] user={current_user.username} | 本月支出 {month_expense:.2f} | 记录 {len(month_rows)} 笔")
    return DashboardSummary(
        month=f"{today.year:04d}-{today.month:02d}",
        month_expense=month_expense,
        month_income=month_income,
        month_count=len(month_rows),
        total_expense=total_expense,
        total_count=len(amounts),
        recent=recent,
        category_stats=category_stats,
    )


# ─── 查询 ────────────────────────────────────────────────────────────────────

@router.get("", response_model=TransactionListResponse, summary="分页查询交易记录")
async def list_transactions(
    start_date: str = Query(default="", description="起始日期 YYYY-MM-DD（含）"),
    end_date: str = Query(default="", description="结束日期 YYYY-MM-DD（含）"),
    category: str = Query(default="", description="分类精确筛选"),
    merchant: str = Query(default="", description="商户模糊搜索"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE, description="每页条数"),
    current_user: User = Depends(get_current_user),
):
    """查账：按日期范围 / 分类 / 商户筛选，分页返回"""
    user_id = current_user.id

    def _parse(q: str, field: str) -> date | None:
        try:
            return date.fromisoformat(q)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{field} 格式错误，应为 YYYY-MM-DD") from None

    conditions = [Transaction.user_id == user_id]
    if start_date:
        conditions.append(Transaction.transaction_date >= _parse(start_date, "start_date"))
    if end_date:
        conditions.append(Transaction.transaction_date <= _parse(end_date, "end_date"))
    if category:
        conditions.append(Transaction.category == category)
    if merchant:
        conditions.append(Transaction.merchant.ilike(f"%{merchant}%"))

    try:
        async with async_session_factory() as session:
            total = (
                await session.execute(
                    select(func.count(Transaction.id)).where(*conditions)
                )
            ).scalar_one()

            rows = await session.execute(
                select(Transaction)
                .where(*conditions)
                .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = list(rows.scalars().all())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[transactions/list] 查询失败: {e}")
        raise HTTPException(status_code=500, detail="交易记录查询失败") from e

    logger.info(f"[transactions/list] user={current_user.username} | 筛选: {start_date or '不限'}~{end_date or '不限'} 分类={category or '全部'} | 命中 {total} 条")
    return TransactionListResponse(items=items, total=total, page=page, page_size=page_size)


# ─── 记账 ────────────────────────────────────────────────────────────────────

@router.post("", response_model=TransactionOut, status_code=201, summary="新增一笔交易记录")
async def create_transaction(
    payload: TransactionCreate,
    current_user: User = Depends(get_current_user),
):
    """记账：表单直接写入（网页端『记一笔』）"""
    try:
        async with async_session_factory() as session:
            txn = Transaction(
                user_id=current_user.id,
                merchant=payload.merchant.strip(),
                amount=payload.amount,
                category=payload.category or "其他",
                transaction_date=payload.transaction_date,
                description=payload.description or None,
            )
            session.add(txn)
            await session.commit()
            await session.refresh(txn)
    except Exception as e:
        logger.exception(f"[transactions/create] 写入失败: {e}")
        raise HTTPException(status_code=500, detail="记账失败：数据库写入异常") from e

    logger.info(f"[transactions/create] user={current_user.username} | #{txn.id} {txn.merchant} ¥{float(txn.amount):.2f}")
    return txn


# ─── 修改 ────────────────────────────────────────────────────────────────────

@router.put("/{transaction_id}", response_model=TransactionOut, summary="修改一笔交易记录")
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    current_user: User = Depends(get_current_user),
):
    """改账：按 ID 更新传入字段（前端编辑表单确认后调用）"""
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="没有需要修改的内容")
    if "description" in data and data["description"] == "":
        data["description"] = None

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Transaction).where(
                    Transaction.id == transaction_id,
                    Transaction.user_id == current_user.id,
                )
            )
            txn = result.scalar_one_or_none()
            if txn is None:
                raise HTTPException(status_code=404, detail="交易记录不存在")
            for k, v in data.items():
                setattr(txn, k, v)
            await session.commit()
            await session.refresh(txn)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[transactions/update] 更新失败: {e}")
        raise HTTPException(status_code=500, detail="修改失败：数据库异常") from e

    logger.info(f"[transactions/update] user={current_user.username} | #{txn.id} → {txn.merchant} ¥{float(txn.amount):.2f}")
    return txn


# ─── 删除 ────────────────────────────────────────────────────────────────────

@router.delete("/{transaction_id}", summary="删除一笔交易记录")
async def delete_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
):
    """删账：按 ID 删除（前端删除确认框后调用）"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Transaction).where(
                    Transaction.id == transaction_id,
                    Transaction.user_id == current_user.id,
                )
            )
            txn = result.scalar_one_or_none()
            if txn is None:
                raise HTTPException(status_code=404, detail="交易记录不存在")
            await session.delete(txn)
            await session.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[transactions/delete] 删除失败: {e}")
        raise HTTPException(status_code=500, detail="删除失败：数据库异常") from e

    logger.info(f"[transactions/delete] user={current_user.username} | 已删除 #{transaction_id}")
    return {"message": "删除成功"}
