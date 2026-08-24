<template>
  <div class="layout">
    <!-- 顶部导航栏 -->
    <header class="navbar">
      <div class="brand" @click="$router.push('/dashboard')">🧾 AI 会计助手</div>
      <el-menu
        mode="horizontal"
        :default-active="activeMenu"
        router
        class="nav-menu"
        :ellipsis="false"
      >
        <el-menu-item index="/dashboard">🏠 首页</el-menu-item>
        <el-menu-item index="/transactions">📋 账单明细</el-menu-item>
        <el-menu-item index="/chat">🤖 AI 记账</el-menu-item>
      </el-menu>
      <div class="nav-right">
        <span class="username">👤 {{ username }}</span>
        <el-button text type="danger" size="small" @click="handleLogout">退出登录</el-button>
      </div>
    </header>

    <!-- 内容区：各页面自行管理滚动 -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const username = localStorage.getItem('username') || '用户'

const activeMenu = computed(() => {
  // 高亮当前路由对应的菜单项
  const p = route.path
  if (p.startsWith('/transactions')) return '/transactions'
  if (p.startsWith('/chat')) return '/chat'
  return '/dashboard'
})

function handleLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ─── 导航栏 ─── */
.navbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  background: #fff;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08);
  z-index: 100;
}

.brand {
  font-size: 18px;
  font-weight: 700;
  color: #7a5c1e;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}

.nav-menu {
  flex: 1;
  border-bottom: none !important;
  background: transparent;
}
.nav-menu :deep(.el-menu-item) {
  font-size: 15px;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.username {
  font-size: 14px;
  color: #606266;
  background: #f5f7fa;
  padding: 4px 12px;
  border-radius: 20px;
}

/* ─── 内容区 ─── */
.main-content {
  flex: 1;
  overflow: hidden;
  background: #f0f2f5;
}
</style>
