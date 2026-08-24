"""交易记录的请求/响应模型（直接 CRUD REST API，不经 Agent）"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TransactionCreate(BaseModel):
    """新增一笔交易记录"""

    merchant: str = Field(..., min_length=1, max_length=200, description="商户名称")
    amount: float = Field(..., description="金额（正数为支出，负数为收入）")
    category: str = Field(default="其他", max_length=50, description="分类")
    transaction_date: date = Field(..., description="交易日期 YYYY-MM-DD")
    description: str | None = Field(default=None, max_length=2000, description="补充描述")


class TransactionUpdate(BaseModel):
    """修改一笔交易记录（只更新传入的字段）"""

    merchant: str | None = Field(default=None, min_length=1, max_length=200)
    amount: float | None = Field(default=None)
    category: str | None = Field(default=None, max_length=50)
    transaction_date: date | None = Field(default=None)
    description: str | None = Field(default=None, max_length=2000)


class TransactionOut(BaseModel):
    """交易记录输出模型"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant: str
    amount: float
    category: str
    transaction_date: date
    description: str | None
    raw_ocr_text: str | None
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    """分页查询结果"""

    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class CategoryStat(BaseModel):
    """单分类汇总（金额带符号：正=支出，负=收入）"""

    category: str
    amount: float
    count: int


class DashboardSummary(BaseModel):
    """首页仪表盘汇总数据"""

    month: str  # 如 "2026-08"
    month_expense: float  # 本月支出合计（正数金额之和）
    month_income: float   # 本月收入合计（绝对值）
    month_count: int      # 本月记录笔数
    total_expense: float  # 全部支出合计
    total_count: int      # 全部记录笔数
    recent: list[TransactionOut]  # 最近消费（按日期倒序，最多 10 条）
    category_stats: list[CategoryStat]  # 本月分类汇总
