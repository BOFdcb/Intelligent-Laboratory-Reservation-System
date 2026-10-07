import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../store/auth'

const routes = [
  { path: '/login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/labs',
    children: [
      { path: 'labs', component: () => import('../views/Labs.vue'), meta: { title: '实验室' } },
      { path: 'my-bookings', component: () => import('../views/MyBookings.vue'), meta: { title: '我的预约' } },
      { path: 'chat', component: () => import('../views/Chat.vue'), meta: { title: 'AI 助手' } },
      { path: 'profile', component: () => import('../views/Profile.vue'), meta: { title: '个人中心' } },
      { path: 'admin/bookings', component: () => import('../views/AdminBookings.vue'), meta: { title: '预约审核', admin: true } },
      { path: 'admin/labs', component: () => import('../views/AdminLabs.vue'), meta: { title: '实验室管理', admin: true } },
      { path: 'admin/users', component: () => import('../views/AdminUsers.vue'), meta: { title: '用户管理', admin: true } },
      { path: 'admin/audit', component: () => import('../views/AdminAudit.vue'), meta: { title: '工具调用审计', admin: true } },
      { path: 'admin/analytics', component: () => import('../views/AdminAnalytics.vue'), meta: { title: '数据分析', admin: true } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (to.path !== '/login' && !auth.token) return '/login'
  if (to.meta.admin && auth.user?.role !== 'admin') return '/labs'
  return true
})

export default router
