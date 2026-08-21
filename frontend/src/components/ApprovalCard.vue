<template>
  <div class="approval-card" :class="{ 'is-cancelled': cancelled }">
    <div class="approval-header">
      <el-icon color="#e6a23c"><WarningFilled /></el-icon>
      <span class="approval-title">需要您的确认</span>
      <el-tag v-if="cancelled" type="info" size="small" effect="plain" class="countdown">
        已取消
      </el-tag>
      <el-tag v-else-if="!resolved && !expired && remaining > 0" type="warning" size="small" effect="plain" class="countdown">
        {{ remaining }}s
      </el-tag>
      <el-tag v-else-if="expired" type="info" size="small" effect="plain" class="countdown">
        已超时
      </el-tag>
    </div>

    <pre class="approval-preview">{{ preview }}</pre>

    <!-- 已取消：用户改发新消息导致后端自动取消了本次确认 -->
    <div v-if="cancelled" class="approval-cancelled">
      ❌ 该操作已被您的新消息打断，自动取消，未执行。
    </div>

    <!-- 正常待确认：同意/拒绝 两个按钮 -->
    <div v-else-if="!resolved && !expired" class="approval-actions">
      <el-button type="success" :loading="loading" :disabled="loading || disabled" @click="handleApprove">
        ✅ 同意
      </el-button>
      <el-button type="danger" :loading="loading" :disabled="loading || disabled" @click="handleReject">
        ❌ 拒绝
      </el-button>
    </div>

    <!-- 本地倒计时归零 -->
    <div v-else-if="expired" class="approval-expired">
      ⏰ 确认超时，该操作已自动取消。
    </div>

    <!-- 用户已做出选择 -->
    <div v-else class="approval-result">
      <el-tag :type="approved ? 'success' : 'danger'" size="large">
        {{ approved ? '✅ 已同意' : '❌ 已拒绝' }}
      </el-tag>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const props = defineProps({
  threadId: { type: String, required: true },
  preview: { type: String, required: true },
  // 确认剩余有效秒数（后端返回 expires_in_seconds；无倒计时则为 null）
  expiresIn: { type: Number, default: null },
  // 已被新消息打断/取消（后端返回 cancelled_confirmations > 0 时由父组件置位）
  cancelled: { type: Boolean, default: false },
  // 请求在途时禁用按钮（避免与新消息请求竞态）
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['resolved', 'expired'])

const loading = ref(false)
const resolved = ref(false)
const approved = ref(false)
const expired = ref(false)
const remaining = ref(props.expiresIn)

let timer = null

function stopCountdown() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

// 倒计时：超时后禁用按钮（后端也会在超时后自动按拒绝处理，这里是前端同步展示）
function startCountdown() {
  stopCountdown()
  if (!props.expiresIn || props.expiresIn <= 0) return
  remaining.value = props.expiresIn
  timer = setInterval(() => {
    remaining.value -= 1
    if (remaining.value <= 0) {
      stopCountdown()
      expired.value = true
      emit('expired')
    }
  }, 1000)
}

// 卡片被标记取消（用户发新消息）→ 停止倒计时，不再允许操作
watch(
  () => props.cancelled,
  (val) => {
    if (val) stopCountdown()
  },
)

async function doAction(isApprove) {
  if (loading.value || props.disabled) return
  loading.value = true
  try {
    // 按钮点击直接带 approve 字段请求 /chat，后端恢复被 interrupt 暂停的图
    const data = await api.chat({
      thread_id: props.threadId,
      message: '',
      approve: isApprove,
    })
    stopCountdown()
    approved.value = isApprove
    resolved.value = true
    ElMessage.success(data.reply || (isApprove ? '操作已执行' : '操作已取消'))
    emit('resolved', data.reply)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败，请重试')
  } finally {
    loading.value = false
  }
}

function handleApprove() {
  doAction(true)
}

function handleReject() {
  doAction(false)
}

onMounted(startCountdown)
onUnmounted(stopCountdown)
</script>

<style scoped>
.approval-card {
  margin-top: 8px;
  border: 1px solid #e6a23c;
  border-radius: 8px;
  padding: 12px 16px;
  background: #fdf6ec;
  max-width: 100%;
  transition: opacity 0.2s;
}

.approval-card.is-cancelled {
  border-color: #dcdfe6;
  background: #f5f7fa;
  opacity: 0.85;
}

.approval-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.approval-title {
  font-weight: 600;
  color: #e6a23c;
}

.is-cancelled .approval-title {
  color: #909399;
}

.countdown {
  margin-left: auto;
}

.approval-preview {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
  font-family: inherit;
}

.approval-actions {
  display: flex;
  gap: 12px;
}

.approval-expired,
.approval-cancelled {
  font-size: 13px;
  color: #909399;
  text-align: center;
  padding: 8px 0;
}

.approval-result {
  text-align: center;
  padding: 8px 0;
}
</style>
