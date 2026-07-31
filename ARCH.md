# ARCH：AI 会计助手 (AIAcct) - 技术架构设计

## 1. 总体架构图 (逻辑视图)

```
[客户端/测试] <--(SSE)--> [FastAPI 网关] <--> [LangGraph Agent 编排器]
                                  |                   |
                                  v                   v
                            [PostgreSQL]      [Qwen3-OCR Service]
                            (数据/检查点)      (图片识别 via Dashscope)
```

> MVP 阶段去除 Redis 和 MCP，使用 LangGraph 原生工具调用 + PostgreSQL Checkpoint。

## 2. 技术栈选型

| 层级 | 组件 | 选型 | 关键职责 |
|------|------|------|---------|
| AI 编排 | LangGraph | langgraph | 构建状态机，后续支持 HITL interrupt |
| 记忆机制 | Postgres Checkpointer | langgraph-checkpoint-postgres | thread_id 会话状态持久化，实现短期记忆 |
| LLM | DeepSeek | langchain-deepseek | 主决策大脑，模型：deepseek-v4-flash |
| OCR | Qwen3-OCR | Dashscope API (qwen3.5-ocr) | 提取图片中的密集文字信息 |
| 数据库 | PostgreSQL | psycopg / asyncpg | 存储业务数据 + LangGraph 检查点 |
| Web 框架 | FastAPI | fastapi + uvicorn | API 网关，SSE 流式推送 |
| ORM | SQLAlchemy 2.0 | sqlalchemy[asyncio] | 异步数据库操作 |
| 配置管理 | pydantic-settings | pydantic-settings | 环境变量加载与校验 |
| 图片处理 | Pillow | Pillow | 后端图片压缩 |

## 3. LangGraph 状态机设计 (核心)

### AgentState

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    current_user_id: str
```

### 节点 (Nodes) - MVP

- **preprocess_node**：接收用户输入。若有图片，调用 Qwen3-OCR 转写为文本，拼接到 user_message。
- **agent_node**：绑定工具集（add_transaction, query_transactions），调用 DeepSeek 推理。
- **tools_node**：执行工具调用并返回结果。

### 边 (Edges) - MVP

```
START -> preprocess_node -> agent_node
agent_node -> tools_node (有工具调用) / END (无工具调用)
tools_node -> agent_node (工具结果返回后继续推理)
```

### Phase 2 扩展节点

- **human_review_node**：处理 update/delete，触发 interrupt 挂起等待人工响应。

## 4. OCR 标准化处理流程

1. **后端接收**：FastAPI 校验文件大小，若 > 200KB 则使用 PIL 压缩至 512px 宽。
2. **超时熔断**：调用 Qwen3-OCR 设置 asyncio.timeout(5s)。超时则降级提示用户"图片解析超时，请手动输入"。
3. **Prompt 加工**：OCR 输出文本附带在消息中，告知 DeepSeek "这是一张订单截图识别出的文本，请提取金额、商户、时间等信息"。

## 5. 数据库 Schema 设计

### 表: transactions

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID / SERIAL PK | 主键 |
| user_id | VARCHAR (Index) | 用户标识 |
| merchant | VARCHAR | 商户名称 |
| amount | DECIMAL(10,2) | 金额 |
| category | VARCHAR | 分类（餐饮/购物/交通等） |
| transaction_date | DATE | 交易日期 |
| description | TEXT | 描述 |
| raw_ocr_text | TEXT | OCR 原始文本（图片录入时保存） |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### LangGraph Checkpoint 表

由 langgraph-checkpoint-postgres 自动创建和管理，无需手动建表。

## 6. 项目目录结构

```
AI_Accounting/
├── docker-compose.yml           # PostgreSQL 容器编排
├── .env                         # 环境变量
├── requirements.txt             # Python 依赖
├── main.py                      # FastAPI 启动入口
├── app/
│   ├── __init__.py
│   ├── config.py                # pydantic-settings 配置
│   ├── database.py              # 异步数据库引擎 & 会话
│   ├── models/                  # SQLAlchemy ORM
│   │   ├── __init__.py
│   │   └── transaction.py
│   ├── schemas/                 # Pydantic 模型
│   │   ├── __init__.py
│   │   └── chat.py
│   ├── api/                     # 路由层
│   │   ├── __init__.py
│   │   └── chat.py              # POST /chat (SSE)
│   ├── agent/                   # LangGraph 核心
│   │   ├── __init__.py
│   │   ├── graph.py             # 状态机组装 & 编译
│   │   ├── state.py             # AgentState 定义
│   │   ├── nodes.py             # 节点实现
│   │   └── tools/               # Agent 工具
│   │       ├── __init__.py
│   │       ├── crud.py          # add / query
│   │       └── ocr.py           # OCR 工具
│   └── services/                # 基础服务
│       ├── __init__.py
│       ├── image.py             # 图片压缩
│       └── ocr_service.py       # Qwen3-OCR API 封装
├── PRD.md
├── ARCH.md
└── PROJECT_STATE.md
```

## 7. 部署方案

- PostgreSQL 通过 Docker Compose 部署，`docker compose up -d` 一键启动。
- 后端通过 `python main.py` 或 `uvicorn main:app` 启动。
