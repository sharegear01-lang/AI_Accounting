# Android 开发环境安装流程（Flutter 移动端 Demo）

> 2026-08-19 编写。适用于 Windows 10/11 64 位。
> 若沿用本机 D 盘已有工具，可直接跳到「三、直接复用本机 D 盘工具」。

---

## 一、前置条件

| 项目 | 要求 | 说明 |
|------|------|------|
| 网络代理 | Clash Verge `127.0.0.1:7897` | Google 系站点（下载/构建）必须走代理 |
| 磁盘 | D 盘 ≥ 15GB 可用 | 工具链约 10GB |
| 虚拟化 | BIOS 开启 VT-x/AMD-V | 模拟器加速需要（WHPX） |

---

## 二、从零安装步骤

### Step 1：Flutter SDK

1. 下载（约 1.9GB）：
   ```
   https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.47.0-stable.zip
   ```
2. 解压到 `D:\flutter`
3. 用户 PATH 追加 `D:\flutter\bin`
4. 验证：`flutter --version` → Flutter 3.47.0

### Step 2：Android Studio（推荐 zip 版，免安装）

> ⚠️ 不推荐 exe 安装器：NSIS 的 `/D` 参数在 shell 传递中易丢失/被转换，且静默安装可能被 UAC 取消（退出码 1223）。

1. 下载（约 1.5GB）：
   ```
   https://edgedl.me.gvt1.com/android/studio/ide-zips/2026.1.3.8/android-studio-quail3-patch1-windows.zip
   ```
2. 解压到 `D:\Android\android-studio`
3. 自带 JDK（JBR）：`D:\Android\android-studio\jbr`，无需单独装 JDK

### Step 3：Android SDK（命令行安装）

1. 下载 cmdline-tools（约 150MB）：
   ```
   https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip
   ```
2. 解压到 `D:\Android\Sdk\cmdline-tools\latest`（注意两层目录结构：cmdline-tools/latest/bin/sdkmanager.bat）
3. 设置**用户级**环境变量（PowerShell 管理员或 系统设置-环境变量）：
   ```
   ANDROID_HOME    = D:\Android\Sdk
   ANDROID_SDK_ROOT= D:\Android\Sdk
   JAVA_HOME       = D:\Android\android-studio\jbr
   PATH 追加: D:\Android\Sdk\platform-tools; D:\Android\Sdk\cmdline-tools\latest\bin
   ```
   新开终端生效。
4. 接受许可 + 安装组件（**必须用 PowerShell**，cmd 会污染引号）：
   ```powershell
   $env:JAVA_HOME='D:\Android\android-studio\jbr'
   # 下载走代理（关键）
   $env:JAVA_TOOL_OPTIONS='-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=7897 -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=7897'
   # 先接受许可（非交互模式必须，否则静默跳过安装）
   'y' * 20 | & 'D:\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat' --licenses
   # 安装组件
   & 'D:\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat' 'platform-tools' 'platforms;android-36' 'build-tools;36.1.0' 'emulator' 'system-images;android-36;google_apis;x86_64'
   ```

### Step 4：创建并启动模拟器

```powershell
# 创建 AVD（devices.xml 警告可忽略）
$env:JAVA_HOME='D:\Android\android-studio\jbr'
$env:ANDROID_HOME='D:\Android\Sdk'
'no' | & 'D:\Android\Sdk\cmdline-tools\latest\bin\avdmanager.bat' create avd -n aiacct_demo -k 'system-images;android-36;google_apis;x86_64' -d pixel_7

# 验证加速（应显示 WHPX 可用）
D:\Android\Sdk\emulator\emulator.exe -accel-check

# 启动（约 70 秒完成启动）
D:\Android\Sdk\emulator\emulator.exe -avd aiacct_demo -no-snapshot -no-audio -gpu swiftshader_indirect
```

### Step 5：验证

```
flutter doctor        # Android toolchain 应显示 √（SDK 36.1.0）
flutter devices       # 应看到 emulator-5554
```

---

## 三、直接复用本机 D 盘工具（更快）

本机 `D:\` 已有**完整可用**的工具（2026-08-19 清理后保留），无需重新下载：

| 工具 | 位置 | 状态 |
|------|------|------|
| Flutter 3.47.0 | `D:\flutter` | ✅ 完整 |
| Android Studio 2026.1.3.8 | `D:\Android\android-studio` | ✅ 完整（zip 版） |
| Android SDK 36 | `D:\Android\Sdk` | ✅ 完整（platform-tools/platforms/build-tools/emulator/系统镜像） |
| 安装包缓存 | `D:\Downloads\setup` | android-studio / flutter / cmdline-tools 安装包仍在 |

**只需**：
1. 确认环境变量（上文 Step 3.3，`ANDROID_HOME`/`JAVA_HOME`/PATH 当前已设置）
2. 重建模拟器（Step 4，AVD 已随清理删除）
3. 首次构建会重新生成 Gradle 缓存（`C:\Users\Administrator\.gradle`，约 4GB，属正常）

---

## 四、构建与运行 app

```bash
cd mobile
flutter pub get
flutter build apk --debug        # 首次构建约 10 分钟（下载 Gradle 依赖）
# 或直接部署：flutter run -d emulator-5554
```

> ⚠️ **Gradle 代理（必配）**：构建需访问 maven.google.com（被墙）。
> `mobile/android/gradle.properties` 已写入：
> ```
> systemProp.http.proxyHost=127.0.0.1
> systemProp.http.proxyPort=7897
> systemProp.https.proxyHost=127.0.0.1
> systemProp.https.proxyPort=7897
> ```
> 换机器/换代理端口时修改这里。

**后端联调**：
```bash
cd AI_Accounting
conda activate langgraph
python main.py        # 后端 0.0.0.0:8000
```
- 模拟器访问宿主机后端：app 登录页「服务器设置」→ `http://10.0.2.2:8000`（默认）
- 真机：改为局域网 IP（如 `http://192.168.x.x:8000`）

---

## 五、踩坑记录（重要）

| # | 坑 | 解决办法 |
|---|----|---------|
| 1 | git bash 调 Windows exe（robocopy 等）参数被 MSYS 转换破坏 | 改用 PowerShell 执行；或 `MSYS_NO_PATHCONV=1` |
| 2 | `cmd //c "sdkmanager \"pkg\""` 包名带字面引号 → Failed to find package | PowerShell `& sdkmanager.bat 'pkg'` 单引号传参 |
| 3 | sdkmanager 静默跳过安装（license 未接受） | 先 `'y'*20 | sdkmanager --licenses` |
| 4 | maven.google.com 超时 / 下载 404 | 全部走代理；gradle.properties 配 systemProp 代理 |
| 5 | adb push 远端路径被 git bash 转成 `C:/Program Files/Git/...` | 本地路径用 Windows 格式 + `MSYS_NO_PATHCONV=1` |
| 6 | Android 9+ 明文 HTTP 被禁 | Manifest 已配 `android:usesCleartextTraffic="true"` |
| 7 | 模拟器访问宿主机后端 | `10.0.2.2` = 宿主机 localhost |
| 8 | adb `input text` 不支持中文 | 装 ADBKeyboard（不可见输入法）：`ime set` 切换 → 广播 `ADB_INPUT_B64`（base64 UTF-8）→ 切回 |
| 9 | NSIS 安装器 `/D=路径` 失效（装到 C 盘）/ 退出码 1223 | 用官方 zip 版解压，位置完全可控 |
| 10 | `.gradle` 跨盘迁移卡文件锁 / robocopy 退出码 16 | 先杀 GradleDaemon（taskkill），用 PowerShell `Move-Item`，避免 robocopy |
| 11 | Android Studio 下载文件名非版本号命名 | 官方页面查实际名：`android-studio-quail3-patch1-windows.exe` |
| 12 | Flutter 点击输入框外不收起键盘 | 自动化点击需先截图定位输入栏（键盘弹出后布局上移） |

---

## 六、清理与卸载

| 目标 | 命令/位置 |
|------|----------|
| 构建产物（可再生） | `cd mobile && flutter clean`（删 build/ 约 2GB） |
| Gradle 缓存 | 删 `C:\Users\Administrator\.gradle`（约 4GB，下次构建重新下载） |
| 模拟器 | `avdmanager delete avd -n aiacct_demo`；数据在 `C:\Users\<用户>\.android\avd`（约 4GB） |
| 整个工具链 | 删 `D:\Android`、`D:\flutter`、撤销环境变量（ANDROID_HOME/ANDROID_SDK_ROOT/JAVA_HOME/PATH 中的 flutter/bin） |
| 下载缓存 | 删 `D:\Downloads\setup`（安装包约 5GB，留着可免重下） |
