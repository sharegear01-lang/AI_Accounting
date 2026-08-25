# CI 流水线说明（供审阅）

> 配置文件：`.github/workflows/ci.yml`
> 触发事件：推送到 `main` 分支、任何 Pull Request
> 运行平台：GitHub Actions（ubuntu-latest，每次运行全新环境）

## 一、总体结构

```
push / pull_request
        │
        ▼
   ┌─────────┐    ┌─────────┐
   │ Backend │    │Frontend │   ← 两个 job 并行执行
   └─────────┘    └─────────┘
```

- **并发控制**：同一分支同时只跑一个流水线，新 push 自动取消旧 run（`concurrency` + `cancel-in-progress`），避免排队浪费。
- **两个 job 互相独立**，任一失败即整体失败（红叉），全部通过即绿钩。

---

## 二、Backend job（5 个步骤 + 环境准备）

### 环境准备

| 项 | 内容 | 说明 |
|----|------|------|
| Python | 3.12 | 与本地 3.13 差一个小版本，用于发现版本兼容问题 |
| PostgreSQL | 16-alpine（容器服务） | 每次运行起一个**全新空库**，测完即弃 |
| 环境变量 | 见下 | 模拟生产配置形状，但不含任何真实密钥 |

```yaml
DATABASE_URL: postgresql+psycopg://admin:secret@localhost:5432/ai_acct
DEEPSEEK_API_KEY: ""        # 占位——单测全 mock，不调真实 LLM
DASHSCOPE_API_KEY: ""       # 占位——不调真实 OCR
SECRET_KEY: ci-only-placeholder-secret
LANGSMITH_TRACING: "false"  # 关闭外部追踪上报
DEBUG: "false"              # 关闭热重载/调试模式
```

> 设计意图：CI 必须**不依赖任何外部服务**（DeepSeek / Dashscope / 真实数据库），
> 这样每次运行结果确定、可复现；真实 API 的联调由本地手动流程负责。

### 步骤 1：Lint（ruff）

```bash
pip install -r requirements.txt pytest ruff
ruff check . --exclude frontend mobile
```

- 规则：`pyproject.toml` 中 `E/F/I/UP/B/SIM/RUF/TRY/PIE`（含 B904 异常链等真问题），
  对中文项目做了豁免配置（全角标点、长行、logger.exception 风格等）。
- **失败含义**：代码有 lint 级问题（未定义引用、死代码、异常链断裂等）→ 直接红。
- 当前状态：全仓 0 告警。

### 步骤 2：迁移往返（fresh DB）

```bash
alembic upgrade head      # ① 空库 → 最新 schema
alembic downgrade base    # ② 全部回退 → 空库（验证迁移可逆、无数据残留）
alembic upgrade head      # ③ 再次建表（验证可重复执行）
```

- 三个命令都必须成功，验证的是**迁移脚本的完整性**：
  新库能建、旧版本能回退、回退后能重建。
- **失败含义**：某个迁移脚本有 bug（例如 downgrade 没写、upgrade 不可重入）。
- 注意：LangGraph 的 checkpoint 表**不在** Alembic 管理范围（由 checkpointer 自动创建），
  此步骤不触碰它们。

### 步骤 3：Schema 漂移检查

```bash
alembic check
```

- Alembic 1.9+ 内置命令：把**当前模型**（`app/models/`）与**迁移后的数据库**做对比，
  不一致即退出码非 0。
- **失败含义**：你改了 SQLAlchemy 模型（如给 `transactions` 加字段）但**忘了生成新迁移**
  ——这是 CI 里最重要的"防忘"门禁，逼着 schema 变更必须走迁移流程。

### 步骤 4：单元测试

```bash
pytest -v
```

- 只收集 `test_preprocess.py`（`pyproject.toml` 中 `testpaths` 限定），
  共 7 个用例，覆盖：OCR 成功/失败/超时/非法图片、纯文本透传、拦截回复、图片不进 checkpoint。
- 全部 **mock**（FakeLLM + AsyncMock 打桩 OCR），不碰数据库、不调外部 API。
- 其余 `test_*.py`（HITL、OCR、E2E 等）是**手动集成冒烟脚本**，依赖真实服务，CI 不跑。
- **失败含义**：图逻辑（preprocess 组装、防幻觉闸门、路由）有回归。

### 步骤 5：启动冒烟测试

```bash
python -m uvicorn main:app ... &    # 后台起服务
# 轮询 /health 最多 30 秒
curl -sf http://127.0.0.1:8000/health | grep -q '"ok"'
```

- 验证的是 **lifespan 全链路**：启动时自动跑 `alembic upgrade head` →
  初始化 PostgresSaver checkpointer（连真实 Postgres）→ FastAPI 起来 → `/health` 返回 `{"status":"ok"}`。
- **失败含义**：应用启动即崩（迁移失败、checkpointer 连不上、依赖缺失、路由注册炸）。
  这是"CI 全绿但部署必炸"的最后一道防线。

---

## 三、Frontend job（2 个步骤）

### 步骤 1：安装依赖

```bash
npm ci
```

- `npm ci` 按 `package-lock.json` **精确安装**（比 `npm install` 严格），
  保证 CI 与本地依赖树一致。
- 失败含义：锁文件与 `package.json` 不同步（改了依赖没提交 lock 文件）。

### 步骤 2：构建

```bash
npm run build   # vite build
```

- 验证 Vue3 代码能否生产构建：语法、import、模板、路由引用全部解析成功。
- **失败含义**：前端代码有编译级错误，或引用了不存在的模块/组件。
- 当前已知（非阻塞）告警：主 chunk 1.1MB > 500KB 阈值，属性能优化项，不影响通过。

---

## 四、本地等价验证命令（Windows 开发机）

CI 是 Ubuntu + 全新环境；本地复现命令如下（`DATABASE_URL` 指向临时库）：

```powershell
# 1. lint
ruff check . --exclude frontend mobile

# 2. 迁移往返（临时空库）
$env:DATABASE_URL = "postgresql+psycopg://admin:secret@localhost:5432/ai_acct_ci"
alembic upgrade head; alembic downgrade base; alembic upgrade head

# 3. 漂移检查
alembic check

# 4. 单测
pytest -v

# 5. 冒烟（注意 Windows 用 python main.py，Linux 才直接 uvicorn main:app）
$env:PORT = "8100"; python main.py   # 另开终端 curl http://127.0.0.1:8100/health

# 6. 前端
cd frontend; npm ci; npm run build
```

> Windows 差异提醒：CI 冒烟用 `python -m uvicorn main:app`（Ubuntu 默认事件循环没问题），
> 但 Windows 上必须 `python main.py`（已在 main.py 注释说明），这是平台差异不是 CI bug。

---

## 五、常见失败速查表

| 红在哪一步 | 最常见原因 | 修复动作 |
|-----------|-----------|---------|
| Lint | 新代码有 ruff 告警 | `ruff check --fix` 后提交 |
| 迁移往返 | 新迁移 downgrade 缺失/不可重入 | 补全迁移脚本，本地空库往返验证 |
| 漂移检查 | 改了模型忘了生成迁移 | `alembic revision --autogenerate -m "..."` 并 review 后提交 |
| 单元测试 | graph/节点逻辑改动破坏既有分支 | 跑 `pytest -v` 定位，修测试或修代码 |
| 冒烟 | 启动崩溃（依赖缺失/配置） | 看 `/tmp/uvicorn.log`，本地 `python main.py` 复现 |
| Frontend 构建 | 新增组件未提交 / lock 不同步 | `git status` 确认文件入库，`npm install` 后提交 lock |

---

## 六、当前边界与后续演进（审阅要点）

**CI 现在不做的**（有意为之）：
- ❌ 不调用真实 LLM / OCR / 任何外部 API
- ❌ 不跑集成冒烟脚本（test_hitl*.py 等，留给本地手动）
- ❌ 不部署（无 CD）——当前只保证"代码质量"，不保证"上线"

**建议的演进路线**（按优先级）：
1. **覆盖率门禁**：加 `pytest --cov` + 阈值（当前仅 7 个图级用例，覆盖面偏窄）
2. **集成测试 job**：用 mock API（如 `respx`/`vcr`）补 HITL 全链路测试，让 CI 能跑
3. **CD 阶段**：CI 绿后触发部署（阿里云 ECS）——需要先完成 deploy-prep 的
   Dockerfile / systemd / nginx 部分
4. **前端 lint**：接 ESLint + vue-tsc（当前只 build，不查代码风格）

---

*本文档与 `.github/workflows/ci.yml` 同步维护；改动 CI 时请一并更新。*
