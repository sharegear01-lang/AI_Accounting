# 计划：Flutter 移动端 App Demo（Android）

## Context（背景）

AIAcct 已有完整的 FastAPI 后端（LangGraph Agent + JWT 鉴权 + HITL 人工复核）
与 Vue3 Web 前端。用户提出：用 **Flutter** 做移动端 app demo，**平台选 Android 做试验**，
验证同一套后端 API 在移动端的可行性，产出可演示的移动端 Demo。

## 用户决策（已确认 2026-08-19）

| 问题 | 决策 |
|------|------|
| Q1 工具链安装 | **B. Android Studio 图形化安装**，安装到 **D 盘** |
| Q2 运行目标 | **Android 模拟器**（经 10.0.2.2 访问宿主机后端） |
| Q3 Demo 范围 | **完整版**：注册/登录 → 文本记账 → 图片记账 → 查询 → 修改/删除 + HITL |

## 环境搭建（D 盘布局与版本）

| 组件 | 版本 | 安装位置 |
|------|------|----------|
| Android Studio | 2026.1.3.8 (Quail 3 Patch 1) | D:\Android\Android Studio |
| Android SDK | cmdline-tools + platform-tools + emulator + system-image x86_64 | D:\Android\Sdk |
| Flutter SDK | 3.47.0 stable | D:\flutter |
| 模拟器 | Android 36 x86_64（google_apis） | AVD 目录默认 |

> 网络：本机经 Clash Verge 代理（127.0.0.1:7897）访问 Google 系站点，
> 所有下载均需 `-x http://127.0.0.1:7897`。Android Studio 自带 JBR，无需单独装 JDK。
> Android Studio 下载：https://redirector.gvt1.com/edgedl/android/studio/install/2026.1.3.8/android-studio-2026.1.3.8-windows.exe
> Flutter 下载：https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.47.0-stable.zip

## 现状盘点（已从代码/环境确认）

### 后端 API（直连 8000 端口，无 /api 前缀 —— /api 只是 Vite 代理约定）

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/register` | {username, password} | 注册（3-50 字符用户名，6-50 字符密码） |
| POST | `/login` | {username, password} | 返回 {access_token, token_type} |
| POST | `/chat` | {message, thread_id, image_base64?} | Bearer 鉴权，返回 {reply, thread_id} |
| POST | `/approve/{thread_id}` | - | Bearer 鉴权，批准 HITL 操作 |
| POST | `/reject/{thread_id}` | - | Bearer 鉴权，拒绝 HITL 操作 |
| GET | `/health` | - | 健康检查 |

### HITL 交互模式（前端关键逻辑，需复刻）

- 后端 chat 返回 `reply` 末尾带 `请回复"确认"批准操作，或回复"取消"拒绝。`
- Vue 前端检测该后缀 → 剥离后缀得 preview → 渲染 ApprovalCard → 点按钮调
  `/approve/{thread_id}` / `/reject/{thread_id}`
- 备选方案：直接发"确认"/"取消"文本消息也可恢复图执行

### 环境约束（重要）

- **本机无 Flutter、无 JDK、无 Android SDK、无 adb** —— 需先搭建工具链
- Docker + PostgreSQL 16 已运行（ai_acct_db 容器 healthy）
- 后端当前未启动；conda env `langgraph`（Python 3.13）已装 fastapi 0.135.1，`python main.py` 可启动
- 后端监听 `0.0.0.0:8000`：模拟器可经 `10.0.2.2:8000` 访问宿主机；真机需局域网 IP
- Android 9+ 默认禁止明文 HTTP → Manifest 需开 `usesCleartextTraffic`（dev 用）
- 磁盘余量 ~118GB，可容纳 Android SDK + 模拟器镜像

## Approach（推荐方案）

### 目录与命名

```
mobile/                    # 与 frontend/ 并列的 repo 子目录（flutter create 生成）
├── lib/
│   ├── main.dart          # 入口 + Provider 装配 + 路由
│   ├── api/
│   │   ├── client.dart    # dio 封装：baseUrl + JWT 拦截器 + 401 处理
│   │   └── api.dart       # register / login / chat / approve / reject
│   ├── models/            # ChatRequest/ChatResponse/TokenResponse 等
│   ├── providers/         # AuthProvider / ChatProvider（ChangeNotifier）
│   ├── screens/
│   │   ├── login_screen.dart   # 登录/注册切换（含服务器地址配置入口）
│   │   └── chat_screen.dart    # 聊天主界面
│   └── widgets/
│       ├── message_bubble.dart  # 用户/AI 气泡
│       ├── approval_card.dart   # HITL 确认卡（批准/拒绝）
│       └── typing_indicator.dart
└── android/               # flutter create 生成 + 少量配置修改
```

### 技术栈选型（demo 从简）

| 用途 | 选型 | 理由 |
|------|------|------|
| 状态管理 | Provider + ChangeNotifier | 官方推荐、无样板，demo 足够 |
| HTTP | dio | 拦截器模式与前端 axios 一致（JWT 附加 / 401 跳登录） |
| Markdown | flutter_markdown | AI 回复含表格等 markdown |
| 图片 | image_picker + image | 选图 + 压缩至 1280px 长边 / JPEG 0.85（与 web 端一致） |
| Token 存储 | shared_preferences | demo 足够（生产可换 flutter_secure_storage） |

### 核心交互设计

1. **服务器地址可配置**：登录页提供"服务器设置"入口，默认 `http://10.0.2.2:8000`
   （模拟器访问宿主机），真机改局域网 IP。避免每次改代码。
2. **图片记账**：image_picker 选图 → image 包压缩（1280px 长边 / JPEG 0.85）→
   base64 去前缀后随 chat 发送（与前端完全一致）。
3. **HITL 确认卡**：检测 reply 末尾 `请回复"确认"批准操作` 后缀 → 剥离 → 渲染
   确认卡（展示 preview）→ 批准/拒绝调对应端点 → 结果作为 AI 消息追加。
4. **会话 thread_id**：本地生成 `mobile_<timestamp>` 并持久化，跨重启保持。

### 环境搭建（一次性，写入脚本）

- JDK 17（Android Gradle Plugin 8.x 要求）+ Flutter SDK（stable）
- Android：cmdline-tools → platform-tools → emulator → system-image（x86_64）
  - 或用户选择安装 Android Studio 图形化
- `flutter doctor` 全绿 → `flutter emulators --create` 创建 AVD

## Files to modify

- 新增 `mobile/`（flutter create 脚手架 + 上述 lib 结构）
- `mobile/android/app/src/main/AndroidManifest.xml`：INTERNET 权限 + usesCleartextTraffic
- `.gitignore`：追加 mobile 构建产物（flutter create 自带 .gitignore，无需额外）

## Reuse（现有可复用）

- **API 契约**：`app/api/chat.py`、`app/api/auth.py`、`app/schemas/chat.py`、`app/schemas/auth.py`
  → Flutter models 直接照抄字段
- **HITL 检测/剥离逻辑**：`frontend/src/views/Chat.vue`（isApproval 检测 + approvalPreview 剥离正则）
- **API 封装模式**：`frontend/src/api/index.js`（JWT 拦截器 / 401 处理）
- **图片压缩参数**：`frontend/src/views/Chat.vue`（1280px / JPEG 0.85）
- **后端**：无需任何修改（API 已兼容）

## Steps（实施清单）

- [x] Step 0：环境搭建（JDK + Flutter + Android SDK + 模拟器）→ `flutter doctor` 通过
- [x] Step 1：`flutter create` 脚手架 + 依赖 + dio 封装 + token 存储 + 路由骨架
- [x] Step 2：登录/注册页（含服务器地址设置）
- [x] Step 3：聊天页（消息列表 / 建议词 / 打字指示器 / markdown 渲染）
- [x] Step 4：图片记账（选图 → 压缩 → base64 发送）
- [x] Step 5：HITL 确认卡（检测后缀 → 批准/拒绝 → 结果追加）
- [x] Step 6：联调验证（全流程跑通）+ `flutter analyze` / widget test

## 实施记录（2026-08-19 完成）

### 环境搭建（D 盘）

| 组件 | 版本 | 位置 | 备注 |
|------|------|------|------|
| Flutter | 3.47.0 stable | D:\flutter | zip 解压即用 |
| Android Studio | 2026.1.3.8 (Quail 3 P1) | D:\Android\android-studio | **zip 版**（NSIS 安装器两次失败：/D 参数被 git bash 转换丢失 + 退出码 1223） |
| Android SDK | platform-tools 37.0.1 / platforms;android-36 / build-tools;36.1.0 / emulator 37.1.11 | D:\Android\Sdk | cmdline-tools 22.0，JBR 来自 Android Studio |
| 模拟器 | aiacct_demo (Pixel 7 / Android 16 google_apis x86_64) | WHPX 加速可用 | Boot ~72s |

### 关键踩坑（复现可用）

1. **代理**：Google 系站点需经 Clash Verge（127.0.0.1:7897）。curl 下载加 `-x`；
   sdkmanager 用 `JAVA_TOOL_OPTIONS="-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=7897 ..."`；
   Gradle 在 `mobile/android/gradle.properties` 写 systemProp 代理（否则 maven.google.com 超时）。
2. **cmd 引号污染**：git bash 里 `cmd //c "sdkmanager.bat \"pkg\""` 会把引号传给包名 → 全部改用 PowerShell 传参（& 调用 + 单引号）。
3. **license 未接受**：sdkmanager 非交互模式跳过安装 → `yes | sdkmanager --licenses` 预接受。
4. **adb 路径转换**：git bash 下 `adb push /sdcard/...` 会被转成 C:/Program Files/Git/...
   → 本地路径用 Windows 格式（C:\...），远端路径加 `MSYS_NO_PATHCONV=1`。
5. **模拟器中文输入**：adb `input text` 不支持中文；LatinIME 无中文键盘。
   方案：安装 **ADBKeyboard**（不可见输入法），`ime set` 切换后广播 `ADB_INPUT_B64`（base64 UTF-8）注入中文，再切回 LatinIME。
6. **Flutter 键盘收起**：点击输入框外部不会自动收起软键盘（Flutter 默认行为），
   键盘弹出后输入栏上移（模拟器上至 y≈1422），自动化点击需先截图定位蓝色发送按钮。
7. **Android Studio 下载文件名**：2026.1.3.8 的 Windows 安装包实际名为 `android-studio-quail3-patch1-windows.exe`（非版本号命名），官方页面可查。

### 联调验证结果（全通过）

| # | 场景 | 结果 | 证据 |
|---|------|------|------|
| 1 | app 启动 → 登录页渲染 | ✅ | UI dump / 截图 |
| 2 | 注册 + 登录（JWT） | ✅ | 后端 POST /login 200 |
| 3 | 聊天发送 → AI 回复 | ✅ | POST /chat 200，回复渲染 |
| 4 | 图片记账（test_image1.jpg） | ✅ | 数据库记录 119：药店 ¥420.10 / 医疗 / 2026-08-19 |
| 5 | 删除 + HITL 确认卡（app 内中文指令） | ✅ | 确认卡 → 批准 → 数据库记录 119 消失 |
| 6 | 文本记账（API 层） | ✅ | 星巴克 ¥45 入库（记录 118，curl 验证） |

## Verification（2026-08-19 全部通过 ✅）

1. 后端启动：`python main.py`（conda env langgraph）→ /health 200
2. 模拟器安装 app（app-debug.apk）→ 注册新用户 → 登录（UI 实操 + 后端 POST /login 200）
3. 文本记账：API 层验证“昨天下午在星巴克花了45元买咖啡”→ 入库（记录 118）
4. 图片记账：模拟器相册选 test_image1.jpg → 压缩 → 发送 → OCR → 入库（记录 119：药店 ¥420.10 / 医疗）
5. 查询：chat 查询验证（记录可查）
6. 删除 + HITL：app 内中文指令“删除记录119”→ 确认卡 → 批准 → 数据库记录 119 消失（验证 OK）
7. `flutter analyze` 0 issues ✅；`flutter test` 全部通过 ✅
