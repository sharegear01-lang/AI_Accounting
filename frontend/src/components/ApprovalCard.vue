<template>
  <div class="approval-card">
    <div class="approval-header">
      <el-icon color="#e6a23c"><WarningFilled /></el-icon>
      <span class="approval-title">需要您的确认</span>
    </div>

    <pre class="approval-preview">{{ preview }}</pre>

    <div v-if="!resolved" class="approval-actions">
      <el-button type="success" :loading="loading" @click="handleApprove">
        ✅ 批准操作
      </el-button>
      <el-button type="danger" :loading="loading" @click="handleReject">
        ❌ 拒绝操作
      </el-button>
    </div>

    <div v-else class="approval-result">
      <el-tag :type="approved ? 'success' : 'danger'" size="large">
        {{ approved ? '✅ 已批准' : '❌ 已拒绝' }}
      </el-tag>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const props = defineProps({
  threadId: { type: String, required: true },
  preview: { type: String, required: true },
})

const emit = defineEmits(['resolved'])

const loading = ref(false)
const resolved = ref(false)
const approved = ref(false)

async function handleApprove() {
  await doAction(true)
}

async function handleReject() {
  await doAction(false)
}

async function doAction(isApprove) {
  loading.value = true
  try {
    const data = isApprove
      ? await api.approve(props.threadId)
      : await api.reject(props.threadId)
    approved.value = isApprove
    resolved.value = true
    ElMessage.success(data.reply || (isApprove ? '操作已批准' : '操作已拒绝'))
    // 将结果追加到消息流
    emit('resolved', data.reply)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.approval-card {
  margin-top: 8px;
  border: 1px solid #e6a23c;
  border-radius: 8px;
  padding: 12px 16px;
  background: #fdf6ec;
  max-width: 100%;
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

.approval-result {
  text-align: center;
  padding: 8px 0;
}
</style>
