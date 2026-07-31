# PROJECT_STATE：AI 会计助手 - 项目状态追踪

## 当前阶段：MVP 核心功能已完成，进入联调优化

## 已完成

- [x] 需求分析与 PRD 编写
- [x] 技术架构设计
- [x] 技术选型确认
- [x] 开发计划对齐

## MVP 开发计划

### Step 1: 基础设施搭建 ✅
- [x] docker-compose.yml（PostgreSQL）
- [x] requirements.txt
- [x] app/config.py（环境变量加载）
- [x] app/database.py（异步数据库连接）
- [x] app/models/transaction.py（ORM 模型 & 建表）

### Step 2: Agent 核心 ✅
- [x] app/agent/state.py（AgentState）
- [x] app/agent/tools/crud.py（add_transaction / query_transactions）
- [x] app/agent/nodes.py（agent 节点 + ToolNode）
- [x] app/agent/graph.py（状态机组装）

### Step 3: OCR 功能 ✅
- [x] app/services/image.py（图片压缩）
- [x] app/services/ocr_service.py（Qwen3-OCR 调用）
- [x] OCR 集成于 API 层（图片 base64 → OCR → Agent）

### Step 4: API 层 ✅
- [x] app/schemas/chat.py（请求/响应模型）
- [x] app/api/chat.py（POST /chat，SSE 流式）
- [x] main.py（FastAPI 入口 + 路由注册）

### Step 5: 联调测试
- [x] 文本录入端到端测试（SSE 流式 + 数据库写入）
- [ ] 图片 OCR 录入测试
- [x] 自然语言查询测试
- [x] SSE 流式输出验证

## 后续迭代 (Phase 2)

- [ ] HITL 人工复核（update/delete + interrupt）
- [ ] JWT 完整鉴权
- [ ] Vue3 前端
- [ ] 图片前端压缩

## 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-07-30 | 去除 MCP，使用 LangGraph 原生工具 | 减少复杂度，MVP 无需跨进程调用 |
| 2026-07-30 | 去除 Redis | LangGraph Checkpoint 已满足状态暂存需求 |
| 2026-07-30 | MVP 鉴权简化为硬编码 user_id | 优先核心功能 |
| 2026-07-30 | 图片策略以 .env 为准（200KB/512px/5s） | 统一配置源 |
| 2026-07-30 | OCR 纳入 MVP 核心功能 | 图片录入是产品核心卖点 |
| 2026-07-30 | DeepSeek 模型：deepseek-v4-flash | 最新一代模型 |
| 2026-07-30 | 数据库驱动：postgresql+psycopg | 环境已有 psycopg 3.3.2，无需额外安装 asyncpg |
| 2026-07-30 | Windows 事件循环：SelectorEventLoopPolicy | psycopg 异步不支持 ProactorEventLoop |
