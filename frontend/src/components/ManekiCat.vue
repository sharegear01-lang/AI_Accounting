<template>
  <div
    class="maneki-cat"
    :class="[`state-${state}`, { 'eyes-closed': forceClosed }]"
    :style="{ width: size + 'px' }"
    @click="$emit('click')"
  >
    <svg viewBox="0 0 200 220" class="cat-svg">
      <!-- ═══ 底座（金色圆垫）═══ -->
      <g id="base">
        <ellipse cx="100" cy="207" rx="64" ry="13" fill="url(#goldGrad)" stroke="#d99a2b" stroke-width="1.5" />
        <ellipse cx="100" cy="204" rx="50" ry="8" fill="rgba(255,255,255,0.35)" />
      </g>

      <!-- ═══ 尾巴 ═══ -->
      <g id="tail">
        <path
          d="M150,175 Q182,168 178,140 Q176,122 158,126"
          fill="none" stroke="#e8e8e8" stroke-width="12" stroke-linecap="round"
        />
        <path
          d="M150,175 Q182,168 178,140 Q176,122 158,126"
          fill="none" stroke="#ffffff" stroke-width="7" stroke-linecap="round"
        />
      </g>

      <!-- ═══ 身体（蹲坐）═══ -->
      <g id="body">
        <path
          d="M52,185 Q46,138 66,116 Q84,100 116,100 Q154,100 160,130 Q168,158 158,185 Q148,196 105,196 Q60,196 52,185 Z"
          fill="#ffffff" stroke="#d9d9d9" stroke-width="2"
        />
        <!-- 肚子阴影 -->
        <ellipse cx="100" cy="168" rx="36" ry="22" fill="#f7f7f7" />
      </g>

      <!-- ═══ 红项圈 + 金铃铛 ═══ -->
      <g id="bell-wrap">
        <path
          d="M60,118 Q100,132 140,118 L143,124 Q100,140 57,124 Z"
          fill="#e64545"
        />
        <circle cx="100" cy="130" r="9" fill="url(#goldGrad)" stroke="#d99a2b" stroke-width="1.5" />
        <line x1="100" y1="123" x2="100" y2="137" stroke="#d99a2b" stroke-width="1.5" />
        <circle cx="96" cy="127" r="1.8" fill="#fff" opacity="0.7" />
      </g>

      <!-- ═══ 招财手臂（左/右）═══ -->
      <g id="arm-l">
        <path
          d="M58,130 Q34,118 30,98 Q28,86 38,84 Q48,82 50,92 Q54,104 60,112 Z"
          fill="#ffffff" stroke="#d9d9d9" stroke-width="2"
        />
      </g>
      <g id="arm-r">
        <path
          d="M142,130 Q166,118 170,98 Q172,86 162,84 Q152,82 150,92 Q146,104 140,112 Z"
          fill="#ffffff" stroke="#d9d9d9" stroke-width="2"
        />
      </g>

      <!-- ═══ 头（含耳朵，整体可歪头/后仰）═══ -->
      <g id="head">
        <!-- 左耳 -->
        <g id="ear-l">
          <path d="M62,62 L52,22 L92,46 Z" fill="#ffffff" stroke="#d9d9d9" stroke-width="2" />
          <path d="M62,54 L57,32 L80,46 Z" fill="#ffb3ba" />
        </g>
        <!-- 右耳 -->
        <g id="ear-r">
          <path d="M138,62 L148,22 L108,46 Z" fill="#ffffff" stroke="#d9d9d9" stroke-width="2" />
          <path d="M138,54 L143,32 L120,46 Z" fill="#ffb3ba" />
        </g>
        <!-- 脸 -->
        <circle cx="100" cy="88" r="44" fill="#ffffff" stroke="#d9d9d9" stroke-width="2" />

        <g id="face">
          <!-- 左眼（睁） -->
          <g id="eye-l-open">
            <circle cx="81" cy="84" r="6.5" fill="#333" />
            <circle cx="83" cy="82" r="2.2" fill="#fff" />
          </g>
          <!-- 右眼（睁） -->
          <g id="eye-r-open">
            <circle cx="119" cy="84" r="6.5" fill="#333" />
            <circle cx="121" cy="82" r="2.2" fill="#fff" />
          </g>
          <!-- 闭眼（sleep/哈欠眯眼） -->
          <g id="eye-l-closed">
            <path d="M72,84 Q81,91 90,84" fill="none" stroke="#333" stroke-width="2.5" stroke-linecap="round" />
          </g>
          <g id="eye-r-closed">
            <path d="M110,84 Q119,91 128,84" fill="none" stroke="#333" stroke-width="2.5" stroke-linecap="round" />
          </g>
          <!-- 腮红 -->
          <ellipse id="blush-l" cx="68" cy="100" rx="7" ry="4.5" fill="#ffb3ba" opacity="0.7" />
          <ellipse id="blush-r" cx="132" cy="100" rx="7" ry="4.5" fill="#ffb3ba" opacity="0.7" />
          <!-- 嘴：微笑 / 哈欠张大 / 开心张嘴 -->
          <path id="mouth-smile" d="M93,104 Q100,111 107,104" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" />
          <ellipse id="mouth-open" cx="100" cy="104" rx="10" ry="12" fill="#8c4a3a" stroke="#666" stroke-width="1.5" />
          <!-- 胡须 -->
          <g id="whiskers" stroke="#bbb" stroke-width="1.5" stroke-linecap="round">
            <line x1="40" y1="92" x2="62" y2="96" />
            <line x1="40" y1="106" x2="62" y2="104" />
            <line x1="160" y1="92" x2="138" y2="96" />
            <line x1="160" y1="106" x2="138" y2="104" />
          </g>
        </g>
      </g>

      <!-- ═══ 头顶小金元宝 ═══ -->
      <g id="coin">
        <path d="M92,30 Q92,20 100,20 Q108,20 108,30 Q116,32 116,38 Q116,44 108,44 L92,44 Q84,44 84,38 Q84,32 92,30 Z" fill="url(#goldGrad)" stroke="#d99a2b" stroke-width="1.2" />
        <circle cx="100" cy="32" r="2" fill="#d99a2b" />
      </g>

      <!-- ═══ 睡觉 zzz ═══ -->
      <g id="zzz">
        <text x="150" y="52" class="zz z1">z</text>
        <text x="168" y="34" class="zz z2">z</text>
        <text x="186" y="18" class="zz z3">Z</text>
      </g>
    </svg>
  </div>
</template>

<script setup>
defineProps({
  state: { type: String, default: 'idle' },
  size: { type: Number, default: 120 },
  // 强制闭眼（sleep 用），优先于 CSS 眨眼动画
  forceClosed: { type: Boolean, default: false },
})
defineEmits(['click'])
</script>

<style scoped>
.maneki-cat {
  position: relative;
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
  transition: filter 0.2s;
}
.maneki-cat:hover {
  filter: brightness(1.04) drop-shadow(0 0 6px rgba(245, 185, 66, 0.5));
}
.cat-svg {
  width: 100%;
  height: auto;
  display: block;
  overflow: visible; /* zzz 可溢出 */
}

/* SVG 分组：以自身包围盒为基准做变换 */
#base, #tail, #body, #bell-wrap, #arm-l, #arm-r, #head, #coin, #zzz {
  transform-box: fill-box;
}
#arm-l, #arm-r, #head, #ear-l, #ear-r, #eye-l-open, #eye-r-open,
#eye-l-closed, #eye-r-closed, #mouth-smile, #mouth-open, #body {
  transform-box: fill-box;
}

/* ─── 眼睛睁开/闭合切换（sleep 用）─── */
#eye-l-closed, #eye-r-closed { opacity: 0; }
#eye-l-open, #eye-r-open { opacity: 1; transform-origin: center; }
.eyes-closed #eye-l-closed, .eyes-closed #eye-r-closed { opacity: 1; }
.eyes-closed #eye-l-open, .eyes-closed #eye-r-open { opacity: 0; }

/* ─── 嘴切换 ─── */
#mouth-open { opacity: 0; }
#mouth-smile { opacity: 1; }

/* ─── zzz（默认隐藏）─── */
#zzz { opacity: 0; }
.zz {
  font-size: 20px;
  font-weight: 700;
  fill: #b8956a;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ═══════════════ 状态动画 ═══════════════ */

/* 1) idle：呼吸 + 偶尔眨眼 */
.state-idle #body {
  animation: breathe 3s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-idle #eye-l-open, .state-idle #eye-r-open {
  animation: blink 5s infinite;
}
@keyframes breathe {
  0%, 100% { transform: scaleY(1); }
  50% { transform: scaleY(1.02); }
}
@keyframes blink {
  0%, 92%, 100% { transform: scaleY(1); }
  95%, 97% { transform: scaleY(0.12); }
}

/* 2) walk：身体上下颠 + 微摇（屏幕位移由父级控制） */
.state-walk #body {
  animation: walk-bob 0.45s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-walk #tail {
  animation: tail-sway 0.6s ease-in-out infinite;
  transform-origin: left bottom;
}
@keyframes walk-bob {
  0%, 100% { transform: translateY(0) rotate(-1.5deg); }
  50% { transform: translateY(-4px) rotate(1.5deg); }
}
@keyframes tail-sway {
  0%, 100% { transform: rotate(0deg); }
  50% { transform: rotate(8deg); }
}

/* 3) wave：经典招财，双臂上下摆 */
.state-wave #arm-l, .state-wave #arm-r {
  animation: wave-arm 0.5s ease-in-out infinite;
}
.state-wave #arm-l { transform-origin: top center; animation-delay: 0.1s; }
.state-wave #arm-r { transform-origin: top center; }
@keyframes wave-arm {
  0%, 100% { transform: rotate(14deg); }
  50% { transform: rotate(-18deg); }
}

/* 4) listen：歪头 + 耳朵微动 + 专注眨眼 */
.state-listen #head {
  animation: tilt-head 2.4s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-listen #ear-l, .state-listen #ear-r {
  animation: ear-twitch 1.2s ease-in-out infinite;
  transform-origin: bottom center;
}
.state-listen #ear-r { animation-delay: 0.3s; }
.state-listen #eye-l-open, .state-listen #eye-r-open {
  animation: blink 3.2s infinite;
}
@keyframes tilt-head {
  0%, 100% { transform: rotate(0deg); }
  30% { transform: rotate(8deg); }
  70% { transform: rotate(4deg); }
}
@keyframes ear-twitch {
  0%, 100% { transform: rotate(0deg); }
  50% { transform: rotate(-6deg); }
}

/* 5) dance：身体左右摆 + 小跳 + 双臂举起 */
.state-dance #body {
  animation: dance-body 0.7s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-dance #arm-l, .state-dance #arm-r {
  animation: dance-arm 0.7s ease-in-out infinite;
  transform-origin: top center;
}
.state-dance #arm-l { animation-delay: 0.15s; }
.state-dance #tail { animation: tail-sway 0.4s ease-in-out infinite; transform-origin: left bottom; }
.state-dance #eye-l-open, .state-dance #eye-r-open {
  animation: happy-blink 0.5s infinite;
}
@keyframes dance-body {
  0%, 100% { transform: translateY(0) rotate(-4deg); }
  50% { transform: translateY(-6px) rotate(4deg); }
}
@keyframes dance-arm {
  0%, 100% { transform: rotate(-25deg); }
  50% { transform: rotate(25deg); }
}
@keyframes happy-blink {
  0%, 100% { transform: scaleY(1); }
  50% { transform: scaleY(0.15); }
}

/* 6) happy：轻摆 + 快眨眼 */
.state-happy #body {
  animation: happy-sway 0.9s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-happy #eye-l-open, .state-happy #eye-r-open {
  animation: happy-blink 0.6s infinite;
}
@keyframes happy-sway {
  0%, 100% { transform: rotate(-2deg); }
  50% { transform: rotate(2deg); }
}

/* 7) wait_confirm：瞪大眼睛（眨眼变慢） */
.state-wait_confirm #eye-l-open, .state-wait_confirm #eye-r-open {
  animation: stare 6s infinite;
}
.state-wait_confirm #head {
  animation: tilt-head 4s ease-in-out infinite;
  transform-origin: center bottom;
}
@keyframes stare {
  0%, 90%, 100% { transform: scale(1.25); }
  94%, 96% { transform: scale(0.3); }
}

/* 8) yawn：头后仰 + 嘴张大 + 眯眼 */
.state-yawn #head {
  animation: yawn-head 3.2s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-yawn #mouth-open { opacity: 1; animation: yawn-mouth 3.2s ease-in-out infinite; transform-origin: center top; }
.state-yawn #mouth-smile { opacity: 0; }
.state-yawn #eye-l-open, .state-yawn #eye-r-open {
  animation: squint 3.2s ease-in-out infinite;
  transform-origin: center;
}
@keyframes yawn-head {
  0%, 100% { transform: rotate(0deg); }
  20% { transform: rotate(-6deg) translateY(-4px); }
  45% { transform: rotate(-6deg) translateY(-4px); }
  70% { transform: rotate(0deg); }
}
@keyframes yawn-mouth {
  0%, 100% { transform: scaleY(0.15); }
  30%, 55% { transform: scaleY(1); }
}
@keyframes squint {
  0%, 100% { transform: scaleY(1); }
  25%, 55% { transform: scaleY(0.35); }
}

/* 9) sleep：趴下 + 闭眼 + zzz */
.state-sleep #body {
  animation: sleep-breathe 4s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-sleep #head {
  animation: sleep-drop 4s ease-in-out infinite;
  transform-origin: center bottom;
}
.state-sleep #zzz { opacity: 1; }
.state-sleep .z1 { animation: zzz-float 2.6s ease-out infinite; }
.state-sleep .z2 { animation: zzz-float 2.6s ease-out 0.8s infinite; }
.state-sleep .z3 { animation: zzz-float 2.6s ease-out 1.6s infinite; }
@keyframes sleep-breathe {
  0%, 100% { transform: translateY(2px) scaleY(0.97); }
  50% { transform: translateY(0) scaleY(1); }
}
@keyframes sleep-drop {
  0%, 100% { transform: translateY(3px); }
  50% { transform: translateY(1px); }
}
@keyframes zzz-float {
  0% { opacity: 0; transform: translate(0, 6px) scale(0.6); }
  20% { opacity: 1; }
  100% { opacity: 0; transform: translate(10px, -22px) scale(1.15); }
}

/* 10) wake：伸懒腰过渡 */
.state-wake #body {
  animation: stretch 1.1s ease-in-out;
  transform-origin: center bottom;
}
.state-wake #arm-l, .state-wake #arm-r {
  animation: stretch-arms 1.1s ease-in-out;
  transform-origin: top center;
}
.state-wake #eye-l-open, .state-wake #eye-r-open {
  animation: blink 1.1s infinite;
}
@keyframes stretch {
  0% { transform: scaleY(0.95); }
  40% { transform: scaleY(1.12); }
  100% { transform: scaleY(1); }
}
@keyframes stretch-arms {
  0% { transform: rotate(0deg); }
  50% { transform: rotate(60deg); }
  100% { transform: rotate(0deg); }
}

/* 切换状态时平滑过渡关键组 */
#head, #body, #arm-l, #arm-r {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
</style>
