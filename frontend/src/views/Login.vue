<template>
  <div class="login-page">
    <div class="login-card">
      <!-- 招财猫吉祥物：idle / wave / happy 循环 -->
      <div class="cat-stage">
        <ManekiCat :state="catState" :size="110" />
      </div>
      <h1 class="title">🧾 AI 会计助手</h1>
      <p class="subtitle">自然语言记账 · 截图识别 · AI 智能问答</p>

      <el-tabs v-model="activeTab" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form ref="loginFormRef" :model="loginForm" :rules="rules" label-position="top">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="loginForm.username" placeholder="请输入用户名" size="large" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                size="large"
                show-password
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="handleLogin">
              登 录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules" label-position="top">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="registerForm.username" placeholder="3-50 个字符" size="large" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="registerForm.password"
                type="password"
                placeholder="至少 6 位"
                size="large"
                show-password
              />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input
                v-model="registerForm.confirmPassword"
                type="password"
                placeholder="再次输入密码"
                size="large"
                show-password
                @keyup.enter="handleRegister"
              />
            </el-form-item>
            <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="handleRegister">
              注 册
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import ManekiCat from '../components/ManekiCat.vue'

const router = useRouter()
const activeTab = ref('login')
const loading = ref(false)

// 招财猫循环：idle → wave → happy → idle...
const catState = ref('idle')
let catTimer = null
const CAT_CYCLE = [
  { s: 'wave', ms: 2200 },
  { s: 'happy', ms: 1600 },
  { s: 'idle', ms: 2600 },
  { s: 'idle', ms: 1600 },
]
function catLoop() {
  const step = CAT_CYCLE[catStep]
  catState.value = step.s
  catTimer = setTimeout(() => {
    catStep = (catStep + 1) % CAT_CYCLE.length
    catLoop()
  }, step.ms)
}
let catStep = 0
onMounted(catLoop)
onUnmounted(() => clearTimeout(catTimer))

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', confirmPassword: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度 3-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 50, message: '密码长度至少 6 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

async function handleLogin() {
  loading.value = true
  try {
    const data = await api.login({ username: loginForm.username, password: loginForm.password })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('username', loginForm.username)
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败，请检查用户名和密码')
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  loading.value = true
  try {
    await api.register({ username: registerForm.username, password: registerForm.password })
    ElMessage.success('注册成功，请登录')
    // 自动填入登录表单并切换
    loginForm.username = registerForm.username
    loginForm.password = registerForm.password
    activeTab.value = 'login'
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.title {
  text-align: center;
  font-size: 26px;
  color: #303133;
  margin-bottom: 8px;
}

.cat-stage {
  display: flex;
  justify-content: center;
  margin-bottom: 4px;
  cursor: pointer;
}
.cat-stage:hover .maneki-cat {
  transform: scale(1.06);
}

.subtitle {
  text-align: center;
  color: #909399;
  font-size: 13px;
  margin-bottom: 24px;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
}
</style>
