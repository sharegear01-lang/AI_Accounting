<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑账单' : '记一笔'"
    width="480px"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
      <el-form-item label="商户名称" prop="merchant">
        <el-input
          v-model="form.merchant"
          placeholder="如：星巴克、美团外卖、公司工资"
          maxlength="200"
          clearable
        />
      </el-form-item>

      <el-form-item label="金额" prop="amount">
        <el-input-number
          v-model="form.amount"
          :precision="2"
          :step="10"
          :min="-99999999.99"
          :max="99999999.99"
          controls-position="right"
          style="width: 100%"
          placeholder="正数=支出，负数=收入"
        />
        <div class="amount-tip">正数为支出，负数为收入（如工资 -8000）</div>
      </el-form-item>

      <el-form-item label="分类" prop="category">
        <el-select v-model="form.category" filterable allow-create style="width: 100%">
          <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
        </el-select>
      </el-form-item>

      <el-form-item label="日期" prop="transaction_date">
        <el-date-picker
          v-model="form.transaction_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="备注" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="2"
          maxlength="2000"
          placeholder="补充描述（可选）"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEdit ? '保存修改' : '确认记账' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { CATEGORIES } from '../constants'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // null / undefined = 新增；传对象 = 编辑该记录
  transaction: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const isEdit = computed(() => !!props.transaction)
const formRef = ref(null)
const submitting = ref(false)

const form = reactive({
  merchant: '',
  amount: null,
  category: '餐饮',
  transaction_date: '',
  description: '',
})

// 打开时预填（编辑）或重置（新增）
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    if (props.transaction) {
      form.merchant = props.transaction.merchant || ''
      form.amount = Number(props.transaction.amount)
      form.category = props.transaction.category || '其他'
      form.transaction_date = props.transaction.transaction_date
      form.description = props.transaction.description || ''
    } else {
      resetForm()
      // 默认今天
      const d = new Date()
      const pad = (n) => String(n).padStart(2, '0')
      form.transaction_date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    }
  },
)

function resetForm() {
  form.merchant = ''
  form.amount = null
  form.category = '餐饮'
  form.transaction_date = ''
  form.description = ''
  formRef.value?.clearValidate()
}

const rules = {
  merchant: [{ required: true, message: '请输入商户名称', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  transaction_date: [{ required: true, message: '请选择日期', trigger: 'change' }],
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    const payload = {
      merchant: form.merchant.trim(),
      amount: form.amount,
      category: form.category || '其他',
      transaction_date: form.transaction_date,
      description: form.description?.trim() || '',
    }
    if (isEdit.value) {
      await api.transactions.update(props.transaction.id, payload)
      ElMessage.success('修改成功')
    } else {
      await api.transactions.create(payload)
      ElMessage.success('记账成功')
    }
    emit('update:modelValue', false)
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || (isEdit.value ? '修改失败' : '记账失败'))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.amount-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;
}
</style>
