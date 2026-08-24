<template>
  <div class="transactions">
    <div class="page-card">
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-date-picker
          v-model="filters.dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 260px"
          clearable
        />
        <el-select v-model="filters.category" placeholder="全部分类" clearable style="width: 140px">
          <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
        </el-select>
        <el-input
          v-model="filters.merchant"
          placeholder="搜索商户"
          clearable
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
        <div class="spacer" />
        <el-button type="success" @click="openAddDialog">＋ 记一笔</el-button>
      </div>

      <!-- 批量删除 -->
      <div v-if="selectedIds.length" class="batch-bar">
        <span>已选 {{ selectedIds.length }} 条</span>
        <el-button type="danger" size="small" @click="handleBatchDelete">批量删除</el-button>
      </div>

      <!-- 数据表 -->
      <el-table
        :data="rows"
        v-loading="loading"
        size="default"
        empty-text="没有符合条件的账单记录"
        @selection-change="(sel) => (selectedIds = sel.map((r) => r.id))"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="transaction_date" label="日期" width="110" />
        <el-table-column prop="merchant" label="商户" min-width="140" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <span :class="row.amount > 0 ? 'amount expense' : 'amount income'">
              {{ formatAmount(row.amount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadList"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <!-- 记账/编辑弹窗 -->
    <TransactionFormDialog
      v-model="dialogVisible"
      :transaction="editingRow"
      @saved="handleSaved"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { CATEGORIES, formatAmount } from '../constants'
import TransactionFormDialog from '../components/TransactionFormDialog.vue'

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const selectedIds = ref([])

const filters = reactive({
  dateRange: null,
  category: '',
  merchant: '',
})

const dialogVisible = ref(false)
const editingRow = ref(null)

async function loadList() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (filters.dateRange && filters.dateRange.length === 2) {
      params.start_date = filters.dateRange[0]
      params.end_date = filters.dateRange[1]
    }
    if (filters.category) params.category = filters.category
    if (filters.merchant.trim()) params.merchant = filters.merchant.trim()

    const data = await api.transactions.list(params)
    rows.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '查询失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadList()
}

function handleReset() {
  filters.dateRange = null
  filters.category = ''
  filters.merchant = ''
  handleSearch()
}

function handleSizeChange() {
  page.value = 1
  loadList()
}

function openAddDialog() {
  editingRow.value = null
  dialogVisible.value = true
}

function openEditDialog(row) {
  editingRow.value = row
  dialogVisible.value = true
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.merchant}」¥${Math.abs(Number(row.amount)).toFixed(2)} 这笔记录吗？删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return
  }
  try {
    await api.transactions.remove(row.id)
    ElMessage.success('删除成功')
    // 当前页删空则回退一页
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    loadList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function handleBatchDelete() {
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedIds.value.length} 条记录吗？删除后不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return
  }
  try {
    const count = selectedIds.value.length
    // 逐条删除（后端单条接口；也可在批量场景后续合并为批量接口）
    for (const id of selectedIds.value) {
      await api.transactions.remove(id)
    }
    ElMessage.success(`已删除 ${count} 条记录`)
    selectedIds.value = []
    // 当前页删空则回退一页
    if (rows.value.length === count && page.value > 1) page.value -= 1
    loadList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '批量删除失败')
  }
}

function handleSaved() {
  loadList()
}

onMounted(loadList)
</script>

<style scoped>
.transactions {
  height: 100%;
  overflow: auto;
  padding: 20px;
}

.page-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}
.spacer {
  flex: 1;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fef0f0;
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #e64340;
}

.amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.expense {
  color: #e64340;
}
.income {
  color: #18a058;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
