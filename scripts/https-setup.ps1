# ============================================================
# 本地 HTTPS 开发证书生成脚本（openssl 版 mkcert 替代）
#
# 用途：前端 dev server (5173) 以 HTTPS 启动，消除浏览器在
#       密码输入框上的"不安全连接/密码泄露"警告。
#
# 依赖：openssl（Git for Windows / Miniconda 自带），无需管理员
#       （CA 安装到 CurrentUser 受信任根存储）。
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts\https-setup.ps1
#       然后 cd frontend; npm run dev，访问 https://localhost:5173
# ============================================================

param(
    [string]$CertsDir = (Join-Path $PSScriptRoot "..\frontend\certs"),
    [int]$Days = 825
)

$ErrorActionPreference = "Stop"

$openssl = Get-Command openssl -ErrorAction SilentlyContinue
if (-not $openssl) {
    Write-Error "未找到 openssl。请安装 Git for Windows 或 OpenSSL 后重试。"
    exit 1
}
$opensslPath = $openssl.Source
Write-Host "使用 openssl: $opensslPath"

New-Item -ItemType Directory -Force -Path $CertsDir | Out-Null

$caKey  = Join-Path $CertsDir "rootCA-key.pem"
$caCert = Join-Path $CertsDir "rootCA.pem"
$srvKey = Join-Path $CertsDir "localhost-key.pem"
$srvCert = Join-Path $CertsDir "localhost.pem"

# 1. 创建本地根 CA（仅首次）
if (-not (Test-Path $caCert)) {
    Write-Host "[1/4] 创建本地根 CA ..."
    & $opensslPath genrsa -out $caKey 2048
    & $opensslPath req -x509 -new -key $caKey -sha256 -days 3650 -subj "/CN=AI Acct Local Dev CA" -out $caCert
} else {
    Write-Host "[1/4] 根 CA 已存在，跳过。"
}

# 2. 生成服务器私钥 + 带 SAN 的证书（覆盖 localhost / 127.0.0.1 / ::1）
Write-Host "[2/4] 生成服务器证书 (localhost / 127.0.0.1 / ::1) ..."
& $opensslPath genrsa -out $srvKey 2048

$sanCfg = Join-Path $env:TEMP "ai_acct_openssl_san.cnf"
$csr    = Join-Path $env:TEMP "ai_acct_server.csr"
@"
[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1 = 127.0.0.1
IP.2 = ::1
"@ | Set-Content -Path $sanCfg -Encoding ASCII

& $opensslPath req -new -key $srvKey -out $csr -subj "/CN=localhost"
& $opensslPath x509 -req -in $csr -CA $caCert -CAkey $caKey -CAcreateserial `
    -days $Days -sha256 -extfile $sanCfg -extensions v3_req -out $srvCert

Remove-Item $sanCfg, $csr -ErrorAction SilentlyContinue

# 3. 安装根 CA 到 Windows 受信任根存储（CurrentUser 无需管理员；LocalMachine 尽力而为）
Write-Host "[3/4] 安装根 CA 到受信任根存储 ..."
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($caCert)

function Add-ToStore([string]$storeName, [string]$locationName) {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, $locationName)
    $store.Open("ReadWrite")
    $exists = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    if ($exists) {
        Write-Host "    $locationName\$storeName 已包含该 CA，跳过。"
    } else {
        $store.Add($cert)
        Write-Host "    CA 已安装到 $locationName\$storeName。"
    }
    $store.Close()
}

# CurrentUser（当前用户信任，无需管理员）
Add-ToStore "Root" "CurrentUser"

# LocalMachine（全机信任，需要管理员，失败可忽略）
try {
    Add-ToStore "Root" "LocalMachine"
} catch {
    Write-Host "    (可选) 安装到 LocalMachine 失败，不影响当前用户使用：$($_.Exception.Message)"
}

# 4. 完成
Write-Host "[4/4] 完成！"
Write-Host ""
Write-Host "    证书位置: $CertsDir"
Write-Host "    启动前端: cd frontend; npm run dev"
Write-Host "    访问地址: https://localhost:5173"
Write-Host ""
Write-Host "    提示: 浏览器首次访问若提示证书不受信任，请重启浏览器；"
Write-Host "          若仍不信任，请确认脚本第 3 步已成功安装 CA。"
