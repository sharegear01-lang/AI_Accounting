<template>
  <div class="dashboard">
    <!-- 本月统计卡片 -->
    <el-row :gutter="16">
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">本月支出</div>
          <div class="stat-value expense">¥{{ formatNum(stats.month_expense) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">本月收入</div>
          <div class="stat-value income">¥{{ formatNum(stats.month_income) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">本月结余</div>
          <div
            class="stat-value"
            :class="stats.month_income - stats.month_expense >= 0 ? 'income' : 'expense'"
          >
            ¥{{ formatNum(stats.month_income - stats.month_expense) }}
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">本月笔数</div>
          <div class="stat-value">{{ stats.month_count }} <span class="unit">笔</span></div>
        </div>
      </el-col>
    </el-row>

    <!-- 快捷操作 -->
    <div class="quick-actions">
      <el-button type="primary" @click="openAddDialog">＋ 记一笔</el-button>
      <el-button @click="$router.push('/transactions')">查看全部账单</el-button>
    </div>

    <el-row :gutter="16" class="content-row">
      <!-- 最近消费 -->
      <el-col :xs="24" :md="14">
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title">🕒 最近消费</span>
            <el-button link type="primary" @click="$router.push('/transactions')">全部账单 ›</el-button>
          </div>
          <el-table :data="stats.recent" size="small" empty-text="还没有消费记录，快用 AI 记一笔吧">
            <el-table-column prop="transaction_date" label="日期" width="100" />
            <el-table-column prop="merchant" label="商户" min-width="120" show-overflow-tooltip />
            <el-table-column prop="category" label="分类" width="90">
              <template #default="{ row }">
                <el-tag size="small" type="info">{{ row.category }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="金额" width="110" align="right">
              <template #default="{ row }">
                <span :class="row.amount > 0 ? 'expense' : 'income'">
                  {{ formatAmount(row.amount) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>

      <!-- 本月分类统计 -->
      <el-col :xs="24" :md="10">
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title">📊 本月分类统计</span>
            <span class="panel-sub">{{ stats.month }}</span>
          </div>
          <div v-if="expenseStats.length" class="cat-block">
            <div class="cat-block-title">支出</div>
            <div v-for="s in expenseStats" :key="'e' + s.category" class="cat-row">
              <div class="cat-info">
                <span class="cat-name">{{ s.category }}</span>
                <span class="cat-count">{{ s.count }} 笔</span>
              </div>
              <div class="cat-bar-wrap">
                <div
                  class="cat-bar expense-bar"
                  :style="{ width: pct(s.amount, maxExpense) + '%' }"
                />
              </div>
              <span class="cat-amount expense">¥{{ formatNum(s.amount) }}</span>
            </div>
          </div>
          <div v-if="incomeStats.length" class="cat-block">
            <div class="cat-block-title">收入</div>
            <div v-for="s in incomeStats" :key="'i' + s.category" class="cat-row">
              <div class="cat-info">
                <span class="cat-name">{{ s.category }}</span>
                <span class="cat-count">{{ s.count }} 笔</span>
              </div>
              <div class="cat-bar-wrap">
                <div
                  class="cat-bar income-bar"
                  :style="{ width: pct(Math.abs(s.amount), maxIncome) + '%' }"
                />
              </div>
              <span class="cat-amount income">¥{{ formatNum(Math.abs(s.amount)) }}</span>
            </div>
          </div>
          <el-empty
            v-if="!expenseStats.length && !incomeStats.length"
            description="本月暂无分类数据"
            :image-size="70"
          />
        </div>
      </el-col>
    </el-row>

    <!-- 记账弹窗 -->
    <TransactionFormDialog
      v-model="addDialogVisible"
      :transaction="null"
      @saved="loadStats"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../api'
import { formatAmount } from '../constants'
import TransactionFormDialog from '../components/TransactionFormDialog.vue'

const stats = reactive({
  month: '',
  month_expense: 0,
  month_income: 0,
  month_count: 0,
  total_expense: 0,
  total_count: 0,
  recent: [],
  category_stats: [],
})

const addDialogVisible = ref(false)

const expenseStats = computed(() =>
  stats.category_stats.filter((s) => s.amount > 0).sort((a, b) => b.amount - a.amount),
)
const incomeStats = computed(() =>
  stats.category_stats.filter((s) => s.amount < 0).sort((a, b) => a.amount - b.amount),
)
const maxExpense = computed(() => (expenseStats.value.length ? expenseStats.value[0].amount : 1))
const maxIncome = computed(() => (incomeStats.value.length ? Math.abs(incomeStats.value[0].amount) : 1))

function pct(val, max) {
  return max > 0 ? Math.max(6, Math.round((val / max) * 100)) : 0
}

function formatNum(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function openAddDialog() {
  addDialogVisible.value = true
}

async function loadStats() {
  try {
    const data = await api.transactions.stats()
    Object.assign(stats, data)
  } catch (e) {
    // 401 已由拦截器处理
  }
}

onMounted(loadStats)
</script>

<style scoped>
.dashboard {
  height: 100%;
  overflow: auto;
  padding: 20px;
}

/* ─── 统计卡片 ─── */
.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  margin-bottom: 16px;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.stat-value .unit {
  font-size: 13px;
  font-weight: 400;
  color: #909399;
}
.expense {
  color: #e64340;
}
.income {
  color: #18a058;
}

/* ─── 快捷操作 ─── */
.quick-actions {
  margin-bottom: 16px;
}

/* ─── 面板 ─── */
.content-row {
  margin-bottom: 20px;
}
.panel {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  margin-bottom: 16px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.panel-sub {
  font-size: 13px;
  color: #909399;
}

/* ─── 分类统计 ─── */
.cat-block {
  margin-bottom: 14px;
}
.cat-block-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
.cat-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.cat-info {
  width: 86px;
  flex-shrink: 0;
}
.cat-name {
  font-size: 14px;
  color: #303133;
}
.cat-count {
  font-size: 12px;
  color: #c0c4cc;
  margin-left: 4px;
}
.cat-bar-wrap {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: #f0f2f5;
  overflow: hidden;
}
.cat-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}
.expense-bar {
  background: linear-gradient(90deg, #f89898, #e64340);
}
.income-bar {
  background: linear-gradient(90deg, #7ed6a3, #18a058);
}
.cat-amount {
  width: 88px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
