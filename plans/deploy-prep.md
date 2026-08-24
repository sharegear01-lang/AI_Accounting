# 阿里云部署准备计划（AIAcct → 阿里云 ECS）

## Context（背景）

用户已在阿里云部署一台 ECS（Ubuntu 22.04.5 LTS），准备将 AIAcct（FastAPI + LangGraph + PostgreSQL + Vue3）部署上去"看看效果、练练手"。

**已确认的约束（用户回答）**：
- 无域名、无 ICP 备案（备案尚未开始）
- 数据库未定 → 已确认：**直接在服务器上装**（推荐 Docker PG）
- 规模小、实验状态
- HTTPS：最终需要，但受限于无域名

**服务器现状**：
- Ubuntu 22.04.5 LTS，磁盘 39GB（用 6.8%），内存使用 25%（总量待确认，方案按 ≥2GB 设计），内网 IP 172.26.253.66（对外走公网 IP）
- 0 更新待装，系统较新

## 部署架构（最终形态，单机）

```
[浏览器] → 公网 IP:80 → Nginx → /              → frontend/dist (静态文件)
                              /api → 127.0.0.1:8000 → uvicorn (FastAPI)
                                                        ├→ PostgreSQL 16 (Docker, 仅 localhost)
                                                        ├→ DeepSeek API (外网)
                                                        └→ Dashscope OCR (外网)
```

- 前端 `npm run build` 产物由 Nginx 托管，`/api` 反代到后端 —— 与现有 Vite 代理路径一致，前端代码零改动
- 数据库不暴露公网（不映射 5432 端口）
- HTTPS 留作 Phase 6（域名 + 备案完成后切换）

## 部署方式决策（为什么这么选）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 数据库 | Docker 跑 postgres:16-alpine（复用现有 docker-compose.yml） | 与开发环境一致、配置零迁移、清理方便 |
| 后端 | 原生进程 + systemd 守护 | 实验阶段免 Dockerfile，调试简单；LangGraph checkpoint 在 PG，单机无冲突 |
| 前端 | 服务器上 npm run build | 代码从 git 拉取后原地构建，无需传 dist |
| 代码传输 | git pull（GitHub） | 需先提交本地未推送的 8 个 commit + 未提交修改 |
| Web 服务器 | Nginx | 静态托管 + 反代 + 未来 HTTPS 终结 |
| 访问方式 | IP + HTTP（Phase 0-5）→ 域名 + HTTPS（Phase 6） | 无域名无法签发受信任证书，练手阶段 HTTP 够用 |

## Files to modify / 新建

| 文件 | 操作 | 说明 |
|------|------|------|
| `.env` | 修改（服务器上新建，不入库） | 生产值：DEBUG=False、新 SECRET_KEY、DB 密码、LangSmith 处置 |
| `docker-compose.yml` | 修改 | 数据库强密码、取消 5432 端口对外暴露（仅 localhost） |
| `main.py` | 修改 | `reload` 参数化（生产 False），或由启动命令控制 |
| `deploy/aiacct.service` | 新建 | systemd unit：uvicorn 守护 + 开机自启 |
| `deploy/nginx.conf` | 新建 | 静态托管 + /api 反代 |
| `scripts/deploy.sh` | 新建（可选） | 服务器上一键拉取+构建+重启 |
| `.gitignore` | 确认 | `.env` 已忽略；`frontend/dist` 已忽略（服务器上构建无需入库） |

## Steps（实施清单）

### Phase 0 — 本地代码收尾（现在，本地电脑做）
- [ ] 处理未提交修改 `app/agent/nodes.py`（提交或还原，需确认内容）
- [ ] 处理未跟踪文件（.langgraph_api/、frontend/certs/、test_image*.jpg 等按需忽略）
- [ ] 提交本地领先的 8 个 commit 并 `git push` 到 origin/main
- [ ] 确认 GitHub 仓库访问方式（HTTPS token 或 SSH key，服务器上需要）

### Phase 1 — 服务器基础准备
- [ ] 阿里云控制台：安全组放行 **22 / 80**（443 留到 Phase 6；5432 不放行）
- [ ] SSH 登录，`sudo apt update && apt upgrade`（含 3 个 ESM 安全更新评估）
- [ ] 创建非 root 部署用户 `aiacct`，配置 SSH key 登录
- [ ] 安装：Docker + docker compose plugin、Nginx、git
- [ ] 确认 Python 3.11+（Ubuntu 22.04 默认 3.10 → 需装 ppa:deadsnakes 或改用 Docker 后端；**待定方案**）
- [ ] 安装 Node.js 18+（nvm 或 nodesource）

### Phase 2 — 数据库（Docker PG）
- [ ] 修改 `docker-compose.yml`：强密码、`127.0.0.1:5432:5432`（不暴露公网）
- [ ] 服务器上 `docker compose up -d` 启动 PG
- [ ] 验证 `pg_isready` / 端口仅本机可连

### Phase 3 — 后端
- [ ] 克隆仓库到 `~/aiacct`（或 /opt/aiacct）
- [ ] 创建生产 `.env`：DEBUG=False、DATABASE_URL 指向 localhost、**新 SECRET_KEY**、DeepSeek/Dashscope key、**LangSmith 处置**（国内访问 api.smith.langchain.com 不稳定 → 建议 LANGSMITH_TRACING=false，或实测后决定）
- [ ] 创建 venv，`pip install -r requirements.txt`
- [ ] `main.py` 生产启动参数化（reload=False，由环境或命令行控制）
- [ ] 写 `deploy/aiacct.service`（systemd：`uvicorn main:app --host 127.0.0.1 --port 8000`，仅本机监听）+ 开机自启
- [ ] 手动 `curl http://127.0.0.1:8000/health` 验证

### Phase 4 — 前端 + Nginx
- [ ] `cd frontend && npm install && npm run build`
- [ ] 写 `deploy/nginx.conf`：80 端口托管 dist + `/api` 反代 127.0.0.1:8000（含 `proxy_set_header` 转发、长超时——chat 请求可能超 60s）
- [ ] Nginx 语法检查 `nginx -t` 并启用

### Phase 5 — 端到端验证
- [ ] 浏览器访问 `http://公网IP` → 登录页正常
- [ ] 注册 → 登录 → 文本记账 → 查询 → 修改/删除（HITL 确认卡片）全链路
- [ ] 图片记账（Qwen3-OCR）验证
- [ ] 重启服务器 → 服务自动恢复（systemd + Docker restart policy）
- [ ] 验证 5432 公网不可达、80/22 可达

### Phase 6 — 后续（正式使用前，非本次部署阻塞项）
- [ ] 购买域名 → 阿里云 ICP 备案（约 1~2 周，可并行进行）
- [ ] 备案通过 → 域名解析 → 阿里云免费 SSL 证书 → Nginx 切 HTTPS（443 + 80 跳转）
- [ ] 数据库定时备份（pg_dump + cron，如 每日 03:00，保留 7 天）
- [ ] 生产 API key 独立（当前 .env 的 key 为开发用，正式用建议换新）
- [ ] 评估多 worker（uvicorn --workers 2）+ 前端 dist 走 CDN（可选）

## Verification（验收标准）

1. `curl http://127.0.0.1:8000/health` → `{"status":"ok",...}`
2. 浏览器公网 IP 访问：登录/注册/记账/查询/图片记账/HITL 全部可用
3. 服务重启自恢复
4. 公网仅暴露 80/22（后期 443）
5. `systemctl status aiacct` 与 `docker ps` 均正常

## 已知限制 / 风险

- ~~无 Alembic 迁移~~：✅ 已引入（启动时自动 `alembic upgrade head`，初始迁移幂等兼容旧库）
- **Python 版本**：Ubuntu 22.04 默认 3.10，项目要求 3.11+（deadSnakes PPA 或 Docker 化后端，需在 Phase 1 决策）
- **LangSmith**：国内网络访问不稳定，开启可能拖慢/超时，需实测决定
- **HTTP 明文**：练手阶段密码走 HTTP 有风险，建议仅个人实验用，正式使用必须走 Phase 6 HTTPS
- **git 传输**：服务器需能访问 GitHub（token 或 SSH）
