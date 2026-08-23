<template>
  <div ref="desktopRef" class="desktop">
    <!-- 背景装饰（记账主题，低干扰） -->
    <div class="bg-decor" aria-hidden="true">
      <span class="deco d1">💰</span>
      <span class="deco d2">🧾</span>
      <span class="deco d3">📊</span>
      <span class="deco d4">¥</span>
      <span class="deco d5">🧮</span>
    </div>
    <div class="bg-msg">点击招财猫开始记账</div>

    <!-- 右上角：用户信息 + 退出 -->
    <div class="top-right">
      <span class="username">👤 {{ username }}</span>
      <el-button text type="danger" size="small" @click="handleLogout">退出登录</el-button>
    </div>

    <!-- 招财猫（浮动精灵） -->
    <div
      class="cat-float"
      :class="{ flipped: catPos.flip }"
      :style="{ left: catPos.x + 'px', top: catPos.y + 'px' }"
      @click="handleCatClick"
    >
      <ManekiCat
        :state="cat.state"
        :size="CAT_SIZE"
        :force-closed="cat.state === 'sleep'"
      />
      <!-- 点击提示（首次） -->
      <div v-if="showHint" class="hint-bubble">点我记账 🐱</div>
    </div>

    <!-- 聊天面板 -->
    <transition name="panel-pop">
      <div v-show="panelOpen" class="panel-wrap">
        <ChatPanel
          :thread-id="threadId"
          @close="panelOpen = false"
          @minimize="panelOpen = false"
          @sending="cat.onSending()"
          @reply="cat.onReply"
          @error="cat.onError()"
          @approval="cat.onApprovalPending()"
          @approval-resolved="cat.onApprovalResolved()"
          @user-input="cat.onUserInput()"
        />
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import ManekiCat from '../components/ManekiCat.vue'
import ChatPanel from '../components/ChatPanel.vue'
import { useCatState } from '../composables/useCatState'

const router = useRouter()
const username = localStorage.getItem('username') || '用户'

// 会话线程 ID：首次访问生成并持久化
const threadId = localStorage.getItem('thread_id') || `web_${Date.now()}`
localStorage.setItem('thread_id', threadId)

const cat = useCatState()
const desktopRef = ref(null)
const panelOpen = ref(false)
const showHint = ref(true)
const CAT_SIZE = 120
const PANEL_W = 420

// ─── 招财猫位置控制（走动/触边掉头/避让面板）───
const catPos = reactive({ x: 60, y: 80, flip: false })
let moveTimer = null

const rand = (a, b) => a + Math.random() * (b - a)

function viewport() {
  const el = desktopRef.value
  return el ? { w: el.clientWidth, h: el.clientHeight } : { w: 1200, h: 700 }
}

function moveCat() {
  const { w, h } = viewport()
  const margin = 20
  const maxX = w - CAT_SIZE - margin
  const maxY = h - CAT_SIZE - 30 // 底部留一点
  const minX = margin
  const minY = margin
  let tx = rand(minX, Math.max(minX, maxX))
  let ty = rand(minY, Math.max(minY, maxY))
  // 面板展开时：活动区收窄到面板左侧，避免猫走到面板下面
  if (panelOpen.value) {
    const limitX = w - PANEL_W - CAT_SIZE - 48
    tx = rand(minX, Math.max(minX, Math.min(maxX, limitX)))
  }
  catPos.flip = tx >= catPos.x
  catPos.x = tx
  catPos.y = ty
}

// 猫进入 walk 状态 → 移动到随机目标（过渡由 CSS 驱动）
watch(
  () => cat.state.value,
  (s) => {
    if (s === 'walk') moveCat()
  },
)

function handleCatClick() {
  showHint.value = false
  cat.onUserClick()
  panelOpen.value = !panelOpen.value
  if (!panelOpen.value) {
    // 收起面板后猫有更大地盘
    moveCat()
  }
}

// 面板展开时若猫在面板区域，把它挪走
watch(panelOpen, (open) => {
  if (open) moveCat()
})

function handleLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  router.push('/login')
}

function onResize() {
  const { w, h } = viewport()
  catPos.x = Math.min(catPos.x, w - CAT_SIZE - 20)
  catPos.y = Math.min(catPos.y, h - CAT_SIZE - 30)
}

onMounted(() => {
  moveCat()
  // 首次提示 6s 后消失
  moveTimer = setTimeout(() => { showHint.value = false }, 6000)
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  clearTimeout(moveTimer)
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
.desktop {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: linear-gradient(160deg, #fff8ec 0%, #ffeecb 45%, #ffdf9e 100%);
  user-select: none;
}

/* ─── 背景装饰 ─── */
.bg-decor {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.deco {
  position: absolute;
  font-size: 42px;
  opacity: 0.12;
}
.d1 { top: 12%; left: 8%; transform: rotate(-12deg); }
.d2 { top: 22%; right: 12%; transform: rotate(10deg); }
.d3 { bottom: 18%; left: 16%; transform: rotate(6deg); }
.d4 { bottom: 30%; right: 22%; font-size: 64px; font-weight: 700; color: #b8956a; }
.d5 { top: 60%; left: 46%; transform: rotate(-8deg); }

.bg-msg {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 15px;
  color: rgba(122, 92, 30, 0.35);
  letter-spacing: 2px;
  white-space: nowrap;
}

/* ─── 右上角 ─── */
.top-right {
  position: absolute;
  top: 14px;
  right: 18px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 30;
}
.username {
  font-size: 14px;
  color: #7a5c1e;
  background: rgba(255, 255, 255, 0.6);
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid rgba(240, 180, 41, 0.4);
}

/* ─── 招财猫 ─── */
.cat-float {
  position: absolute;
  z-index: 20;
  cursor: pointer;
  transition: left 4.5s linear, top 4.5s linear;
  will-change: left, top;
}
.cat-float.flipped {
  transform: scaleX(-1);
  transition: left 4.5s linear, top 4.5s linear, transform 0.4s ease;
}
.cat-float:hover {
  filter: drop-shadow(0 4px 10px rgba(184, 149, 106, 0.35));
}

.hint-bubble {
  position: absolute;
  top: -34px;
  left: 50%;
  transform: translateX(-50%);
  background: #fff;
  border: 1px solid #f0b429;
  color: #7a5c1e;
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 12px;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  animation: hint-bob 1.6s ease-in-out infinite;
}
.hint-bubble::after {
  content: '';
  position: absolute;
  bottom: -6px;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: #f0b429;
  border-bottom: none;
}
@keyframes hint-bob {
  0%, 100% { transform: translateX(-50%) translateY(0); }
  50% { transform: translateX(-50%) translateY(-5px); }
}

/* ─── 聊天面板 ─── */
.panel-wrap {
  position: absolute;
  right: 22px;
  bottom: 22px;
  width: 420px;
  height: min(620px, calc(100vh - 60px));
  z-index: 40;
}
.panel-pop-enter-active,
.panel-pop-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.panel-pop-enter-from,
.panel-pop-leave-to {
  opacity: 0;
  transform: scale(0.92) translateY(10px);
}
</style>
