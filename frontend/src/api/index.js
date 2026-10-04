import axios from 'axios'
import { ElMessage } from 'element-plus'
import { auth } from '../store/auth'
import router from '../router'

const api = axios.create({ baseURL: '/', timeout: 30000 })

api.interceptors.request.use((config) => {
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.message || err.message || '请求失败'
    if (status === 401) {
      auth.logout()
      router.push('/login')
    }
    ElMessage.error(msg)
    return Promise.reject(new Error(msg))
  }
)

export default api
