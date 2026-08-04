# PROJECT_STATE：AI 会计助手 - 项目状态追踪

## 当前阶段：Phase 2 迭代中（鉴权 ✅ / 会话记忆 ✅ / HITL 复核 ✅）

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
- [x] app/api/chat.py（POST /chat，ainvoke 直接返回 JSON）
- [x] main.py（FastAPI 入口 + 路由注册）

### Step 5: 联调测试 ✅
- [x] 文本录入端到端测试（ainvoke + 数据库写入）
- [x] 图片 OCR 录入测试（图片压缩 → OCR → Agent 记账）
- [x] 自然语言查询测试
- [x] ainvoke 直接响应验证

### Step 6: 日志系统 ✅
- [x] app/logger.py（统一日志配置：控制台 + 文件轮转 + 错误单独文件）
- [x] 全模块日志覆盖（API/Agent/CRUD/OCR/Image）
- [x] uvicorn reload_excludes 排除 logs/ 目录（防止无限重启循环）

## 后续迭代 (Phase 2)

- [x] JWT 完整鉴权
  - [x] 用户注册 / 登录 API（app/api/auth.py）
  - [x] JWT token 签发与校验（app/auth/jwt.py）
  - [x] 鉴权依赖注入（app/auth/dependencies.py）
  - [x] User ORM 模型（app/models/user.py）
- [x] 会话记忆持久化（Phase 2-1）
  - [x] AsyncPostgresSaver checkpointer（app/checkpointer.py）
  - [x] chat.py 使用 checkpointer 编译图，thread_id 隔离会话
  - [x] 多轮对话记忆验证通过
- [x] HITL 人工复核（Phase 2-2）
  - [x] update_transaction / delete_transaction 工具（工具内 interrupt() 暂停）
  - [x] System Prompt 支持修改/删除
  - [x] interrupt 预览返回 + 孤儿 tool_calls 修补
  - [x] /approve /reject 端点 + /chat 内"确认/取消"快捷回复
  - [x] 审批流程：手动执行工具 + aupdate_state 修补 checkpoint（弃用 Command(resume)，因其无法正确从 tools 节点恢复）
  - [x] 删除+批准 / 删除+拒绝 / 修改+批准 全流程验证通过
- [x] Vue3 前端（frontend/）
  - [x] Vite + Vue3 + Element Plus + vue-router + axios 技术栈
  - [x] 登录 / 注册页面（JWT token 持久化 + 路由守卫）
  - [x] 聊天主界面（markdown 渲染 + 图片上传前端压缩 512px）
  - [x] HITL 确认卡片组件（检测 interrupt 预览 → 批准/拒绝按钮 → 调 /approve /reject）
  - [x] Vite 代理 /api → 后端 8000，联调测试通过
- [ ] 图片前端压缩（已实现基础版，待精细化）

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
| 2026-07-31 | API 从 SSE 流式改为 ainvoke 直接返回 | Swagger UI 对流式支持差，MVP 阶段直接返回更直观 |
| 2026-07-31 | 统一日志系统（控制台+文件轮转） | 便于排查问题，error.log 单独记录异常 |
| 2026-08-05 | LangGraph 1.2.9 + AsyncPostgresSaver 会话记忆 | thread_id 隔离会话，checkpointer 持久化消息历史 |
| 2026-08-05 | 工具内 interrupt() 实现 HITL 复核 | LLM 直接调工具，interrupt 自然暂停等待确认 |
| 2026-08-05 | 审批用 手动执行+aupdate_state，弃用 Command(resume) | LangGraph 1.2.9 的 resume 无法从 tools 节点恢复，导致 agent 重新决策 |
