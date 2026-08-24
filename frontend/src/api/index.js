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

  // 聊天（含 HITL 按钮决策：approve=True/False 时直接恢复被 interrupt 暂停的图）
  chat: (data) => http.post('/chat', data),

  // 交易记录（直接 CRUD，不经 Agent）
  transactions: {
    // 分页查询：{ start_date, end_date, category, merchant, page, page_size }
    list: (params) => http.get('/transactions', { params }),
    // 首页统计汇总
    stats: () => http.get('/transactions/stats'),
    // 新增一笔
    create: (data) => http.post('/transactions', data),
    // 修改一笔
    update: (id, data) => http.put(`/transactions/${id}`, data),
    // 删除一笔
    remove: (id) => http.delete(`/transactions/${id}`),
  },
}

export default http
