import axios from 'axios'

// 统一 axios 实例：请求走 /api 前缀，由 Vite 代理到后端
const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// 请求拦截器：自动附加 JWT token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 时跳转登录页
http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export const api = {
  // 鉴权
  register: (data) => http.post('/register', data),
  login: (data) => http.post('/login', data),

  // 聊天
  chat: (data) => http.post('/chat', data),

  // HITL 人工复核
  approve: (threadId) => http.post(`/approve/${threadId}`),
  reject: (threadId) => http.post(`/reject/${threadId}`),
}

export default http
