<template>
  <div class="chat-page">
    <!-- 顶部导航栏 -->
    <header class="chat-header">
      <div class="header-left">
        <span class="logo">🧾</span>
        <span class="app-title">AI 会计助手</span>
      </div>
      <div class="header-right">
        <span class="username">👤 {{ username }}</span>
        <el-button text type="danger" @click="handleLogout">退出登录</el-button>
      </div>
    </header>

    <!-- 消息列表 -->
    <main ref="messageListRef" class="message-list" @scroll.passive>
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">💰</div>
        <p class="empty-title">开始记账吧！</p>
        <p class="empty-subtitle">支持文字描述或截图上传，例如：</p>
        <div class="suggestion-list">
          <el-tag
            v-for="s in suggestions"
            :key="s"
            class="suggestion"
            effect="plain"
            @click="sendText(s)"
          >
            {{ s }}
          </el-tag>
        </div>
      </div>

      <div v-for="(msg, index) in messages" :key="index" class="message-row" :class="msg.role">
        <div class="avatar">{{ msg.role === 'user' ? '🧑' : '🤖' }}</div>
        <div class="bubble-wrapper">
          <div class="bubble" :class="msg.role">
            <!-- 用户消息：普通文本 -->
            <template v-if="msg.role === 'user'">
              <span v-if="msg.hasImage" class="msg-image">
                <img :src="msg.image" alt="图片" />
              </span>
              <span class="msg-text">{{ msg.content }}</span>
            </template>

            <!-- AI 消息：markdown / HITL 卡片 / 加载中 -->
            <template v-else>
              <!-- HITL 确认卡片 -->
              <ApprovalCard
                v-if="msg.isApproval"
                :thread-id="threadId"
                :preview="msg.approvalPreview"
                @resolved="handleResolved"
              />
              <!-- 加载指示 -->
              <div v-else-if="msg.loading" class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
              <!-- 普通 AI 回复（markdown 渲染） -->
              <div v-else class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
            </template>
          </div>
        </div>
      </div>
    </main>

    <!-- 底部输入区 -->
    <footer class="chat-footer">
      <div v-if="pendingImage" class="image-preview-bar">
        <div class="preview-item">
          <img :src="pendingImage" alt="待发送图片" />
          <el-icon class="remove-icon" @click="clearImage"><CircleCloseFilled /></el-icon>
        </div>
        <span class="preview-tip">将随消息一起发送，自动压缩至 1280px</span>
      </div>

      <div class="input-area">
        <el-upload
          :show-file-list="false"
          :before-upload="handleImageSelect"
          accept="image/*"
        >
          <el-button class="upload-btn" circle>
            <el-icon><PictureFilled /></el-icon>
          </el-button>
        </el-upload>

        <el-input
          v-model="inputText"
          class="message-input"
          type="textarea"
          :rows="1"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="输入记账内容，如：昨天在星巴克花了45元买咖啡"
          resize="none"
          @keydown.enter.exact.prevent="sendMessage"
        />

        <el-button
          type="primary"
          class="send-btn"
          :loading="sending"
          :disabled="sending"
          @click="sendMessage"
        >
          发送
        </el-button>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { PictureFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { api } from '../api'
import ApprovalCard from '../components/ApprovalCard.vue'

const router = useRouter()
const username = localStorage.getItem('username') || '用户'

// 会话线程 ID：首次访问生成并持久化
const threadId = localStorage.getItem('thread_id') || `web_${Date.now()}`
localStorage.setItem('thread_id', threadId)

const inputText = ref('')
const sending = ref(false)
const pendingImage = ref('') // base64 待发送图片
const messageListRef = ref(null)

const suggestions = [
  '昨天下午在星巴克花了45元买咖啡',
  '看看最近的账单',
  '帮我删除最新一笔记录',
]

const messages = reactive([
  {
    role: 'assistant',
    content: '你好！我是你的 AI 记账助手 📊\n\n可以这样使用我：\n- **记一笔账**：直接描述消费，如"中午吃了麦当劳花了35元"\n- **传图记账**：点击左下角图片按钮上传订单截图\n- **查询账单**：问我"这个月吃饭花了多少钱"\n- **修改/删除**：我会先展示预览，经你确认后才会执行',
    loading: false,
    isApproval: false,
    hasImage: false,
  },
])

function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text)
}

async function scrollToBottom() {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

function addMessage(msg) {
  messages.push(msg)
  scrollToBottom()
}

// ─── 图片处理：长边归一化至 1280px（OCR 准确率与延迟的平衡点）───
function handleImageSelect(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    const img = new Image()
    img.onload = () => {
      // 长边上限：低于此值保持原尺寸，避免不必要的重编码
      const MAX = 1280
      let { width, height } = img
      if (width > MAX || height > MAX) {
        const ratio = Math.min(MAX / width, MAX / height)
        width = Math.round(width * ratio)
        height = Math.round(height * ratio)
      }
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0, width, height)
      // JPEG 质量 0.85：清晰度优先，体积不是延迟瓶颈
      pendingImage.value = canvas.toDataURL('image/jpeg', 0.85)
      ElMessage.success('图片已就绪，可随消息发送')
    }
    img.src = e.target.result
  }
  reader.readAsDataURL(file)
  return false // 阻止自动上传
}

function clearImage() {
  pendingImage.value = ''
}

// ─── 发送消息 ───
function sendText(text) {
  inputText.value = text
  sendMessage()
}

async function sendMessage() {
  const text = inputText.value.trim()
  const image = pendingImage.value
  if (!text && !image) return
  if (sending.value) return

  // 用户消息入列
  addMessage({
    role: 'user',
    content: text || '(图片记账)',
    hasImage: !!image,
    image: image || '',
  })
  inputText.value = ''
  pendingImage.value = ''

  // AI 占位（加载中）
  addMessage({ role: 'assistant', content: '', loading: true, isApproval: false, hasImage: false })

  sending.value = true
  try {
    const data = await api.chat({
      message: text || '请识别图片并完成记账',
      thread_id: threadId,
      image_base64: image ? image.split(',')[1] : null, // 去掉 data:image/jpeg;base64, 前缀
    })
    // 移除加载占位
    const loadingIdx = messages.findIndex((m) => m.loading)
    if (loadingIdx !== -1) messages.splice(loadingIdx, 1)

    const reply = data.reply || ''
    // 检测 HITL interrupt 预览
    const isApproval = reply.includes('请回复"确认"批准操作')
    addMessage({
      role: 'assistant',
      content: reply,
      loading: false,
      isApproval,
      approvalPreview: isApproval ? reply.replace(/\n*请回复"确认"批准操作，或回复"取消"拒绝。\s*$/, '') : '',
      hasImage: false,
    })
  } catch (e) {
    const loadingIdx = messages.findIndex((m) => m.loading)
    if (loadingIdx !== -1) messages.splice(loadingIdx, 1)
    addMessage({
      role: 'assistant',
      content: `❌ 请求失败：${e.response?.data?.detail || e.message || '未知错误'}`,
      loading: false,
      isApproval: false,
      hasImage: false,
    })
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

// HITL 批准/拒绝完成后，将结果作为 AI 消息追加
function handleResolved(reply) {
  if (reply) {
    addMessage({
      role: 'assistant',
      content: reply,
      loading: false,
      isApproval: false,
      hasImage: false,
    })
  }
}

function handleLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  router.push('/login')
}

onMounted(scrollToBottom)
</script>

<style scoped>
.chat-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  max-width: 900px;
  margin: 0 auto;
  background: #fff;
  box-shadow: 0 0 30px rgba(0, 0, 0, 0.08);
}

/* 顶部 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo {
  font-size: 22px;
}

.app-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  color: #606266;
  font-size: 14px;
}

/* 消息列表 */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  background: #f7f8fa;
}

.empty-state {
  text-align: center;
  padding: 80px 0;
}

.empty-icon {
  font-size: 56px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 18px;
  color: #303133;
  margin-bottom: 8px;
}

.empty-subtitle {
  color: #909399;
  font-size: 13px;
  margin-bottom: 20px;
}

.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}

.suggestion {
  cursor: pointer;
  padding: 6px 16px;
  font-size: 13px;
  transition: all 0.2s;
}

.suggestion:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

/* 消息行 */
.message-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.message-row.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background: #e4e7ed;
  flex-shrink: 0;
}

.bubble-wrapper {
  max-width: 75%;
  display: flex;
  flex-direction: column;
}

.bubble {
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.bubble.user {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 2px;
}

.bubble.assistant {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-top-left-radius: 2px;
}

.msg-image {
  display: block;
  margin-bottom: 8px;
}

.msg-image img {
  max-width: 220px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

/* Markdown 表格等样式 */
.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f5f7fa;
}

.markdown-body :deep(pre) {
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
}

.markdown-body :deep(code) {
  background: #f5f7fa;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 12px;
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 5px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
  animation: blink 1.4s infinite both;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes blink {
  0%, 80%, 100% { opacity: 0.3; }
  40% { opacity: 1; }
}

/* 底部输入区 */
.chat-footer {
  border-top: 1px solid #e4e7ed;
  padding: 12px 24px 20px;
  background: #fff;
}

.image-preview-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 8px;
}

.preview-item {
  position: relative;
}

.preview-item img {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 6px;
}

.remove-icon {
  position: absolute;
  top: -6px;
  right: -6px;
  font-size: 18px;
  color: #f56c6c;
  cursor: pointer;
  background: #fff;
  border-radius: 50%;
}

.preview-tip {
  color: #909399;
  font-size: 12px;
}

.input-area {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.upload-btn {
  flex-shrink: 0;
}

.message-input {
  flex: 1;
}

.message-input :deep(.el-textarea__inner) {
  box-shadow: none;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 14px;
}

.send-btn {
  flex-shrink: 0;
  height: 36px;
  padding: 0 22px;
}
</style>
