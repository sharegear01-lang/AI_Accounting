import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// ─── 本地 HTTPS ─────────────────────────────────────────────────────────────
// 若 frontend/certs/ 下存在证书（由 scripts/https-setup.ps1 生成），则以 HTTPS
// 启动 dev server，消除浏览器在密码输入框上的"不安全连接/密码泄露"警告；
// 未生成证书时回退为 HTTP，不影响原有开发流程。
const certDir = fileURLToPath(new URL('./certs/', import.meta.url))
const hasCerts =
  fs.existsSync(path.join(certDir, 'localhost.pem')) &&
  fs.existsSync(path.join(certDir, 'localhost-key.pem'))

const server = {
  port: 5173,
  proxy: {
    // 将 API 请求代理到 FastAPI 后端
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
}

if (hasCerts) {
  server.https = {
    key: fs.readFileSync(path.join(certDir, 'localhost-key.pem')),
    cert: fs.readFileSync(path.join(certDir, 'localhost.pem')),
  }
  console.log('[vite] 检测到本地证书，已启用 HTTPS: https://localhost:5173')
}

export default defineConfig({
  plugins: [vue()],
  server,
})
