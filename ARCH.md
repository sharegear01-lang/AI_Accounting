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
    messages: Annotated[list, add_messages]   # 对话历史（含 OCR 增强后的文本）
    current_user_id: str                       # 当前登录用户（JWT 注入，多租户隔离）
    user_input: str                            # 本次请求原始文本（preprocess 消费后清空）
    ocr_block: dict | None                     # OCR 防幻觉拦截信息（respond_blocked 消费后清空）
```

> **图片不经过 state**：图片 base64 经 `config["configurable"]["image_base64"]`
> 传入 preprocess 节点，避免 checkpointer 持久化图片字节（隐私 + 体积）。

### 节点 (Nodes)

- **preprocess_node**：接收 `user_input`（+ 可选图片）。有图片时调用 Qwen3-OCR
  识别，过**防幻觉闸门**：识别失败 / 金额不可信 → 写入 `ocr_block` 走拦截分支，
  绝不进入 agent（防 LLM 猜金额记账）；识别成功 → 组装含 OCR 上下文的 HumanMessage。
  无图片时直接透传用户文本。
- **respond_blocked_node**：OCR 拦截回复节点，直接返回错误提示，不调用 LLM。
- **agent_node**：绑定工具集（add/query/update/delete + 批量版），调用 DeepSeek 推理。
- **tools_node**：执行工具调用，强制注入 `current_user_id`（防越权）。

### 边 (Edges)

```
START -> preprocess
preprocess -> respond_blocked (OCR 拦截) / agent (正常)
agent -> tools (有工具调用) / END (无工具调用)
tools -> agent
respond_blocked -> END
```

### HITL 人工复核（修改/删除）

- update/delete 工具内 `interrupt()` 暂停（无需独立节点），预览含完整明细，
  interrupt payload 携带与预览一致的结构化数据（transaction_ids / fields）。
- 审批恢复由 API 层 `_resume_graph` 从 checkpoint 读取 interrupt payload，
  调用公共执行函数 `execute_delete` / `execute_update` 后 `aupdate_state` 修补。
  **不迁移 `Command(resume)`**：LangGraph 1.2.9 的 resume 语义为重放整个
  tools 节点，已完成工具会被重复执行（官方已知缺陷，PR #3126 修复未合并），
  手动执行路径可精确控制（见 PROJECT_STATE 决策记录）。

### 多租户隔离

- 工具**不暴露 user_id 参数**：当前用户 ID 由 JWT 鉴权写入
  `config["configurable"]["user_id"]`，经 LangChain 自动注入工具 config 参数，
  LLM 看不到也无法伪造，从根源杜绝跨用户越权。

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

## 7. 前端架构（Phase 2）

### 技术栈

| 组件 | 选型 | 关键职责 |
|------|------|---------|
| 框架 | Vue 3 + Vite | 单页应用，dev server 端口 5173 |
| UI 库 | Element Plus | 表单 / 按钮 / 消息 / 布局 |
| 路由 | vue-router | 登录页 / 聊天页 + 路由守卫 |
| HTTP | axios | 统一封装，JWT 自动附加，401 跳登录 |
| Markdown | marked | AI 回复 markdown 渲染（表格等） |

### 目录结构

```
frontend/
├── index.html
├── vite.config.js          # /api 代理到后端 8000
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router/index.js      # 路由守卫（未登录跳 /login）
│   ├── api/index.js         # axios 实例 + JWT 拦截器
│   ├── views/
│   │   ├── Login.vue        # 登录 / 注册
│   │   └── Chat.vue         # 聊天主界面（文本+图片+消息列表）
│   └── components/
│       └── ApprovalCard.vue # HITL 确认卡片（批准/拒绝）
```

### 前后端交互

- 所有请求走 `/api` 前缀，Vite dev 代理转发至 `http://127.0.0.1:8000`。
- JWT token 存 localStorage，axios 请求拦截器自动附加 `Authorization: Bearer`。
- HITL：interrupt 暂停时 `/chat` 返回结构化响应（`requires_confirmation=true` + `preview` + `expires_in_seconds`），前端据此渲染 ApprovalCard 的『同意/拒绝』按钮；点击后带 `approve` 字段重新请求 `/chat`，后端直接恢复被暂停的图（不再使用自然语言“确认/取消”，避免误判）。确认超时（`HITL_EXPIRY_SECONDS`，默认 300s）或用户发新消息打断时自动按拒绝取消，防止 interrupt 永久挂起；新消息打断会返回 `cancelled_confirmations` 数量，前端把仍在展示的确认卡片标记为『已取消』，避免点击失效按钮得到“无需重复确认”的困惑提示。
- 图片：前端 canvas 压缩至长边 512px / JPEG 0.7，转 base64 随聊天发送。

## 8. 部署方案

- PostgreSQL 通过 Docker Compose 部署，`docker compose up -d` 一键启动。
- 后端通过 `python main.py` 或 `uvicorn main:app` 启动。
