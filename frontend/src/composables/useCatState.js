// 招财猫状态机协调器（与渲染解耦：ManekiCat.vue 只负责"画成什么样"，
// 这里负责"什么时候处于什么状态"。后期转 3D 时渲染层可整体替换，
// 状态机、事件接口、闲置降级链原样保留。）
import { ref, onUnmounted } from 'vue'

const IDLE_TO_YAWN = 60 * 1000   // 闲置 60s → 打哈欠
const IDLE_TO_SLEEP = 180 * 1000 // 闲置 180s → 睡觉
const WALK_MS = 4500              // 单次走动时长
const WAVE_MS = 1600
const DANCE_MS = 3600
const HAPPY_MS = 2600
const WAKE_MS = 1400
const YAWN_MS = 3400

const rand = (a, b) => a + Math.random() * (b - a)

export function useCatState() {
  const state = ref('idle')

  let stateTimer = null   // 事件状态的"到时回 idle"
  let idleTimer = null    // 闲置降级链
  let walkTimer = null    // 随机走动调度
  let listenActive = false

  function clearAll() {
    clearTimeout(stateTimer)
    clearTimeout(idleTimer)
    clearTimeout(walkTimer)
  }

  // 设置状态：holdMs 为 null 表示持续（由下一事件接管，如 listen/wait_confirm/sleep）
  function setState(next, holdMs = null) {
    state.value = next
    clearTimeout(stateTimer)
    if (holdMs) {
      stateTimer = setTimeout(() => {
        if (state.value === next) state.value = 'idle'
        resetIdle()
      }, holdMs)
    }
  }

  // 闲置降级链：idle → (60s) yawn → (120s) sleep
  function resetIdle() {
    clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      setState('yawn', YAWN_MS)
      idleTimer = setTimeout(() => {
        if (state.value === 'idle') setState('sleep')
      }, IDLE_TO_SLEEP - IDLE_TO_YAWN)
    }, IDLE_TO_YAWN)
  }

  // 唤醒：从 sleep/yawn 恢复
  function wake() {
    if (state.value === 'sleep' || state.value === 'yawn') {
      setState('wake', WAKE_MS)
    }
    resetIdle()
  }

  // 随机走动：仅在 idle 时进入，走一段回 idle
  function scheduleWalk() {
    clearTimeout(walkTimer)
    const next = () =>
      walkTimer = setTimeout(() => {
        if (state.value === 'idle') {
          setState('walk', WALK_MS)
          walkTimer = setTimeout(next, rand(9, 16) * 1000)
        } else {
          next()
        }
      }, rand(8, 15) * 1000)
    next()
  }

  // ─── 事件 API（ChatPanel / Chat.vue 调用）───
  function onUserClick() {
    wake()
    setState('wave', WAVE_MS)
  }

  // 发送消息、等待回复：持续 listen，直到回复到达
  function onSending() {
    wake()
    listenActive = true
    setState('listen')
  }

  // 收到 AI 回复：按内容判定 记账成功 → dance / 普通 → happy
  function onReply(text) {
    listenActive = false
    const success =
      /(✅|记账成功|已为您记账|已帮您记下|已为您记好|已记录|记账完成|已成功|已更新|已删除|已修改)/.test(
        text || '',
      )
    setState(success ? 'dance' : 'happy', success ? DANCE_MS : HAPPY_MS)
  }

  // 回复失败（网络错误等）：耷拉耳朵的低落态 → 用 happy 简化为低头
  function onError() {
    listenActive = false
    setState('happy', HAPPY_MS)
  }

  // HITL 确认卡出现：持续瞪眼等待，直到用户处理
  function onApprovalPending() {
    wake()
    setState('wait_confirm')
  }

  // HITL 卡片已处理（同意/拒绝/过期/取消）
  function onApprovalResolved() {
    setState('happy', HAPPY_MS)
  }

  // 用户输入/其他交互：轻唤醒
  function onUserInput() {
    wake()
  }

  resetIdle()
  scheduleWalk()

  onUnmounted(clearAll)

  return {
    state,
    onUserClick,
    onSending,
    onReply,
    onError,
    onApprovalPending,
    onApprovalResolved,
    onUserInput,
  }
}
