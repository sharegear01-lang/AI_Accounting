# PLAN：招财猫吉祥物 —— 承载 AI 对话框的可交互卡通形象

## Context（背景）

给 AI 记账软件加一个"灵魂"：一只**会动的招财猫**承载 AI 能力。
点击招财猫唤出对话框；猫是活的存在——屏幕上走来走去、打哈欠、睡觉、
开心跳舞、摆经典招财动作，与对话状态实时联动。

## 已确认决策（用户拍板）

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 形态 | **A 浮动精灵**：猫在页面上自由走动，点击弹出聊天浮层 |
| 2 | 端范围 | 只做 Web（Vue3），作为测试；效果好后期转 3D |
| 3 | 美术 | **手绘 SVG 招财猫**（测试版，可缩放、动画可控、轻量） |
| 4 | 联动 | 全做：倾听/打哈欠/跳舞/瞪眼等确认/睡觉 zzz |
| 5 | 音效 | 暂不做（后期用户收集素材再加） |
| 6 | 登录页 | 也要放一只（简单循环动画） |

## 现状（已探索确认）

- 前端 Vue3 + Vite + Element Plus；路由 `/login`、`/chat`（`/` 重定向 `/chat`）
- `Chat.vue`（601 行）：整页聊天 = header + 消息列表 + 输入区 + HITL ApprovalCard
- API：`api.chat()` 返回 `{reply, thread_id, cancelled_confirmations}`；
  HITL 时 `{requires_confirmation, preview, expires_in_seconds}`
- **后端无"记账成功"结构化标记** → 前端从 reply 文本启发式判断
  （含 "✅"/"记账成功"/"已为您记账" 等 → dance）
- vite 代理 `/api` → `127.0.0.1:8000`

## 架构设计

### 页面形态（/chat 改造为"桌面"）

```
┌──────────────────────────────────────┐
│  桌面背景（记账主题：柔和渐变+装饰）        │
│                                      │
│              🐱 招财猫（自由走动）        │
│    点击 ──────► 弹出 ChatPanel 浮层     │
│                                      │
│   ┌─ ChatPanel（消息+输入+HITL）────┐  │
│   │  （可最小化/关闭）                │  │
│   └───────────────────────────────┘  │
└──────────────────────────────────────┘
```

### 组件拆分（关键：渲染与状态机解耦，为 3D 留接口）

```
frontend/src/
├── components/
│   ├── ManekiCat.vue      # 招财猫角色：SVG 绘制 + CSS 动画（纯渲染，props 驱动）
│   ├── ChatPanel.vue      # 聊天浮层面板（从 Chat.vue 抽取：消息/输入/图片/HITL）
│   └── ApprovalCard.vue   # 复用（不动）
├── composables/
│   └── useCatState.js     # 猫的状态机协调器（与渲染解耦 → 后期换 3D 渲染层保留状态机）
└── views/
    ├── Chat.vue           # 改造：桌面场景 + 猫 + 面板开关 + 状态驱动
    └── Login.vue          # 加招财猫装饰（wave/眨眼循环）
```

### 猫的状态机

| 状态 | 触发 | 动画表现 |
|------|------|----------|
| `idle` | 默认/回复后平静 | 呼吸起伏、偶尔眨眼 |
| `walk` | 随机（60% 概率）每 8~15s | 左右摇摆移动 + 脚步 bob，触边掉头（flipX） |
| `wave` | 用户点击猫；记账成功后 | 经典招财：右手臂上下摆动 |
| `listen` | 发送消息等待回复中 | 歪头 + 耳朵微动 + 专注眨眼 |
| `dance` | 收到回复且判定为记账成功 | 身体左右摆 + 手臂举起 + 小跳 |
| `happy` | 收到普通回复（非记账） | 快频率眨眼 + 轻微摇摆 |
| `wait_confirm` | HITL 确认卡存在且未处理 | 瞪大眼睛盯住（眨眼频率降低） |
| `yawn` | idle 超过 60s | 头后仰张嘴 + 眯眼 |
| `sleep` | idle 超过 180s | 眼睛闭合（弯线）+ 趴下 + zzz 上飘 |
| `wake` | 点击/新消息 | 伸懒腰过渡回 idle |

- **事件驱动**（优先级高，立即打断）：click / sending / reply / approval
- **随机驱动**（定时器）：walk 随机游走、idle→yawn→sleep 降级链
- 任何事件都重置闲置计时器

### SVG 招财猫设计（测试版）

经典形象：白猫 + 红项圈金铃铛 + 招财手臂 + 圆底座。

```
SVG 分组（每个 <g> 可独立 CSS transform，transform-origin 锚点）：
- base（金色圆垫底座，静止）
- body（蹲坐猫身 → 呼吸/趴下/跳舞旋转）
- tail（尾巴 → 开心时摇尾）
- head（头 → 歪头/后仰哈欠）
- ear-l / ear-r（内耳 → listen 微动）
- eye-l / eye-r（圆眼 + 高光 → 眨眼 scaleY、sleep 换弯线、wait 瞪大）
- mouth（嘴 → 微笑/哈欠张大/开心张嘴）
- blush（腮红）
- arm-l / arm-r（招财手臂 → wave 摆动、dance 举起）
- bell（金铃铛，随 body 动）
- zzz（睡觉气泡，CSS 上飘动画）
- 元宝/铜钱装饰（可选）
```

动画实现：CSS keyframes 控制各 `<g>` 的 transform（rotate/translate/scale），
状态切换 = 切 class；walk 的屏幕移动由父级容器 transform 驱动（transition 平滑）。

### 联动信号源（ChatPanel → 猫）

ChatPanel 通过 `@status-change` 事件上报，Chat.vue（或 useCatState）消费：
- `sending=true` → listen
- `assistant-reply` + 文本 → 含记账成功关键词 → dance，否则 happy
- `approval-pending`（isApproval 卡未处理）→ wait_confirm
- `approval-resolved` / `cancelled` / `expired` → 恢复 idle
- `user-message`（用户刚发消息）→ 唤醒 + listen

### 桌面走动逻辑

- 活动区域：整页可视区（避开 ChatPanel 展开区域，面板弹出时缩小活动区或猫停在面板旁）
- 移动：JS 定时器（每 500ms）更新目标 x/y + CSS transition（linear 3~6s）平滑
- 触边：flipX 掉头 + 换方向；随机停留 → idle
- 猫的尺寸 96~140px，z-index 高于背景、低于面板

## Files to modify（清单）

| 文件 | 动作 |
|------|------|
| `frontend/src/components/ManekiCat.vue` | **新增**：SVG 招财猫 + 动画 + 状态渲染 |
| `frontend/src/components/ChatPanel.vue` | **新增**：聊天浮层（从 Chat.vue 移植） |
| `frontend/src/composables/useCatState.js` | **新增**：状态机协调器（定时器 + 事件） |
| `frontend/src/views/Chat.vue` | **改造**：桌面场景 + 猫 + 面板集成 |
| `frontend/src/views/Login.vue` | **改造**：加招财猫装饰（wave/眨眼循环） |
| `frontend/package.json` | 不动（无新依赖，纯 CSS+SVG） |

## Reuse（可复用）

- `api.chat()`、`ApprovalCard.vue`：零改动
- `Chat.vue` 的消息渲染/图片压缩/HITL 处理：整体移植进 `ChatPanel.vue`

## Verification（验收）

- [ ] `npm run build` 通过
- [ ] 桌面场景：猫自由走动、触边掉头、随机停留
- [ ] 点击猫 → 弹出面板 + wave；再点/关闭按钮 → 收起
- [ ] 动画全状态：idle 眨眼 / walk / wave / listen / dance / happy /
      wait_confirm 瞪眼 / yawn / sleep zzz / wake
- [ ] 对话全流程在浮层内正常：文本记账、图片记账、HITL 同意/拒绝、记忆
- [ ] 联动验证：发消息→listen；记账成功回复→dance；HITL 卡→瞪眼；
      闲置 60s→yawn、180s→sleep；点猫/发消息→唤醒
- [ ] 登录页招财猫动画正常
- [ ] 窗口 resize 猫不跑出屏幕、面板不破版

## 后期展望（3D 转换预留）

- 状态机（useCatState）与渲染（ManekiCat.vue）解耦：状态枚举 + 事件接口已抽象
- 转 3D 时：渲染层换 Three.js / Rive（Rive 可直接承载同一状态机驱动骨骼动画），
  状态机、联动信号、页面骨架全部保留
- 音效：状态机预留 `onPlaySound(state)` 钩子，素材到位即接入

## 版本管理（已确认）

- **基线**：main @ 3b51c56（工具合并收尾已提交，基线干净）
- **分支**：全部开发在 `feat/maneki-cat`，main 零污染
- **颗粒提交**（每个 commit 即回滚点）：
  1. plans/maneki-cat.md 计划文档
  2. ManekiCat.vue（SVG + 动画 + 状态渲染）
  3. useCatState.js（状态机协调器）
  4. ChatPanel.vue（聊天浮层移植）
  5. Chat.vue 桌面场景集成
  6. Login.vue 招财猫装饰
  7. 验收修正 + 文档更新
- **回滚**：
  - 局部：`git revert <commit>` / `git checkout <commit> -- <file>`
  - 整体：`git checkout main`（main 未被污染）；效果差可
    `git branch -D feat/maneki-cat` 丢弃整个分支
- **存档**：验收通过后 `git tag v0.2.0-maneki-cat-demo`

## 待办

- [x] 确认 6 个决策点 → 细化方案
- [ ] 写 ManekiCat.vue（SVG 绘制 + 状态动画）
- [ ] 写 useCatState.js（状态机 + 定时器）
- [ ] 写 ChatPanel.vue（移植 Chat.vue 逻辑）
- [ ] 改造 Chat.vue（桌面 + 集成）
- [ ] 改造 Login.vue（招财猫装饰）
- [ ] 验收清单逐项通过
