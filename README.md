# AI 会计助手 (AIAcct)

> 基于 LangGraph + DeepSeek 的智能记账系统：通过截图或自然语言，让 AI 帮你完成记账、查询与记账信息维护。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 项目简介

AI 会计助手（AIAcct）是一款面向个人 / 家庭的 AI 财务记账助手。你只需通过 **截图**（网购订单、电子小票）或 **自然语言** 描述一笔消费，系统便会自动提取关键财务要素（商户、金额、类别、时间）并写入数据库。系统同时支持基于自然语言的查询，以及带 **人工复核（HITL）** 的修改 / 删除操作。

## 功能特性

- **📝 文本记账**：输入"昨天下午在星巴克花了45元买咖啡"，AI 自动提取并入库。
- **📷 图片记账**：上传电商订单截图，后端调用 Qwen3-OCR 识别文字，自动补全记账信息。
- **🔍 自然语言查询**：如"上个月吃饭花了多少钱"、"显示我本月所有的网购记录"。
- **🛡️ 人工复核 (HITL)**：修改 / 删除记账信息时，Agent 暂停执行，前端弹出确认卡片，批准后才真正操作数据库。
- **👤 JWT 鉴权**：注册 / 登录 + Bearer Token，所有数据严格按 `user_id` 隔离。
- **🧠 会话记忆**：基于 PostgreSQL Checkpointer 的 `thread_id` 会话隔离，多轮对话上下文不丢失。
- **🎨 现代前端**：Vue 3 + Element Plus，Markdown 渲染 + 图片前端压缩。

## 技术栈

| 层级 | 组件 | 说明 |
|------|------|------|
| AI 编排 | LangGraph | 状态机编排，支持 interrupt 人工复核 |
| LLM | DeepSeek | 主决策大脑（deepseek-v4-flash） |
| OCR | Qwen3-OCR (Dashscope) | 图片文字识别 |
| 后端 | FastAPI + Uvicorn | API 网关 |
| 数据库 | PostgreSQL 16 | 业务数据 + LangGraph Checkpoint |
| ORM | SQLAlchemy 2.0 (async) | 异步数据库操作 |
| 前端 | Vue 3 + Vite + Element Plus | 单页应用 |

## 架构概览

```
[Vue3 前端 :5173] <--/api 代理--> [FastAPI 网关 :8000] <--> [LangGraph Agent 编排器]
                                        |                        |
                                        v                        v
                                  [PostgreSQL]           [Qwen3-OCR Service]
                                 (数据/检查点)          (图片识别 via Dashscope)
```

核心链路：`用户输入/图片` → `OCR(可选)` → `LangGraph Agent 推理` → `工具调用(增删改查)` → `PostgreSQL 入库`。修改 / 删除类操作经 `interrupt()` 暂停，等待人工批准。

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Docker（用于启动 PostgreSQL）
- DeepSeek / Dashscope API Key

### 1. 启动数据库

```bash
docker compose -f docker-compose.yml up -d
```

### 2. 配置环境变量

复制并修改 `.env`：

```bash
# DeepSeek
DEEPSEEK_API_KEY=your_deepseek_api_key

# Qwen OCR (Dashscope)
DASHSCOPE_API_KEY=your_dashscope_api_key

# JWT（生产环境务必修改）
SECRET_KEY=your-256-bit-secret-key-change-in-production
```

### 3. 启动后端

```bash
pip install -r requirements.txt
python main.py
```

服务启动于 `http://127.0.0.1:8000`，Swagger 文档见 `http://127.0.0.1:8000/docs`。

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行于 `http://127.0.0.1:5173`，Vite 已将 `/api` 代理至后端 8000 端口。

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/register` | 用户注册 |
| POST | `/login` | 登录，返回 JWT token |
| POST | `/chat` | 与 AI 记账助手对话（支持文本 + 图片 base64） |
| GET | `/health` | 健康检查 |

> 所有业务接口均需携带 `Authorization: Bearer <token>`。

## 项目结构

```
AI_Accounting/
├── main.py                      # FastAPI 启动入口
├── docker-compose.yml           # PostgreSQL 容器编排
├── requirements.txt             # Python 依赖
├── app/
│   ├── config.py                # pydantic-settings 环境配置
│   ├── database.py              # 异步数据库引擎 & 会话
│   ├── checkpointer.py          # LangGraph Postgres Checkpointer
│   ├── logger.py                # 统一日志（文件轮转）
│   ├── models/                  # SQLAlchemy ORM（user / transaction）
│   ├── schemas/                 # Pydantic 请求/响应模型
│   ├── api/                     # 路由层（auth / chat）
│   ├── auth/                    # JWT 签发与鉴权依赖
│   ├── agent/                   # LangGraph 状态机（graph / nodes / tools）
│   └── services/                # 图片压缩 & Qwen3-OCR 封装
└── frontend/                    # Vue 3 前端（登录 / 聊天 / HITL 卡片）
```

## 文档

- [PRD.md](PRD.md) - 产品需求文档
- [ARCH.md](ARCH.md) - 技术架构设计
- [PROJECT_STATE.md](PROJECT_STATE.md) - 项目状态追踪与关键决策记录

## 许可证

[MIT](LICENSE) © 2026 sharegear01-lang
