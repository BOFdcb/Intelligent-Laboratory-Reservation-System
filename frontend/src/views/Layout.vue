<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <span class="logo-icon">🔬</span>
        <span class="logo-text">智能实验室预约系统</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
        class="sidebar-menu"
      >
        <el-menu-item index="/labs">
          <el-icon><OfficeBuilding /></el-icon>
          <span>实验室</span>
        </el-menu-item>
        <el-menu-item index="/my-bookings">
          <el-icon><Calendar /></el-icon>
          <span>我的预约</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI 助手</span>
        </el-menu-item>
        <el-menu-item index="/profile">
          <el-icon><User /></el-icon>
          <span>个人中心</span>
        </el-menu-item>
        <template v-if="auth.user?.role === 'admin'">
          <el-menu-item index="/admin/bookings">
            <el-icon><DocumentChecked /></el-icon>
            <span>预约审核</span>
          </el-menu-item>
          <el-menu-item index="/admin/labs">
            <el-icon><Setting /></el-icon>
            <span>实验室管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/users">
            <el-icon><UserFilled /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/audit">
            <el-icon><Tickets /></el-icon>
            <span>工具调用审计</span>
          </el-menu-item>
          <el-menu-item index="/admin/analytics">
            <el-icon><DataAnalysis /></el-icon>
            <span>数据分析</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container class="main-wrapper">
      <el-header class="header">
        <div class="header-left">
          <span class="page-title">{{ route.meta.title || '' }}</span>
        </div>
        <div class="header-right">
          <el-popover
            placement="bottom-end"
            :width="380"
            trigger="click"
            @show="loadNotifications"
          >
            <template #reference>
              <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="notice-badge">
                <el-icon class="bell-icon"><Bell /></el-icon>
              </el-badge>
            </template>
            <div class="notice-panel">
              <div class="notice-panel-header">
                <span>站内消息</span>
                <el-button text type="primary" size="small" @click="readAll">全部已读</el-button>
              </div>
              <div v-loading="noticeLoading" class="notice-list">
                <div v-if="notifications.length === 0" class="notice-empty">暂无消息</div>
                <div
                  v-for="n in notifications"
                  :key="n.id"
                  class="notice-item"
                  :class="{ unread: !n.is_read }"
                  @click="openNotification(n)"
                >
                  <div class="notice-dot" v-if="!n.is_read"></div>
                  <div class="notice-body">
                    <div class="notice-title">{{ n.title }}</div>
                    <div class="notice-content">{{ n.content }}</div>
                    <div class="notice-time">{{ n.created_at }}</div>
                  </div>
                </div>
              </div>
            </div>
          </el-popover>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32" :src="auth.user?.avatar" class="user-avatar">
                {{ auth.user?.nickname?.charAt(0) || 'U' }}
              </el-avatar>
              <span class="nickname">{{ auth.user?.nickname || auth.user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  OfficeBuilding,
  Calendar,
  ChatDotRound,
  User,
  DocumentChecked,
  Setting,
  UserFilled,
  Tickets,
  DataAnalysis,
  Bell,
  ArrowDown,
} from '@element-plus/icons-vue'
import { auth } from '../store/auth'
import api from '../api'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => route.path)

// ---- 站内消息：进入页面轮询未读数，打开弹窗拉列表 ----
const unreadCount = ref(0)
const notifications = ref([])
const noticeLoading = ref(false)
let pollTimer = null

async function refreshUnread() {
  try {
    const res = await api.get('/api/notifications/unread-count')
    unreadCount.value = res.data.count
  } catch {
    // 轮询静默失败
  }
}

async function loadNotifications() {
  noticeLoading.value = true
  try {
    const res = await api.get('/api/notifications')
    notifications.value = res.data.items || []
    refreshUnread()
  } finally {
    noticeLoading.value = false
  }
}

async function readAll() {
  await api.post('/api/notifications/read-all')
  notifications.value.forEach((n) => { n.is_read = true })
  refreshUnread()
}

async function openNotification(n) {
  if (!n.is_read) {
    try {
      await api.post(`/api/notifications/${n.id}/read`)
      n.is_read = true
      refreshUnread()
    } catch {
      // ignore
    }
  }
  // 预约相关消息：管理员去审核页，学生去我的预约
  if (n.related_id) {
    router.push(auth.user?.role === 'admin' ? '/admin/bookings' : '/my-bookings')
  }
}

function handleCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'logout') {
    auth.logout()
    router.push('/login')
  }
}

onMounted(() => {
  refreshUnread()
  pollTimer = setInterval(refreshUnread, 60000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.layout-container {
  height: 100vh;
}
.sidebar {
  background-color: #304156;
  display: flex;
  flex-direction: column;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 12px;
  border-bottom: 1px solid #263445;
}
.logo-icon {
  font-size: 24px;
  margin-right: 8px;
}
.logo-text {
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
}
.sidebar-menu {
  border-right: none;
  flex: 1;
}
.main-wrapper {
  background-color: #f0f2f5;
}
.header {
  background-color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  padding: 0 20px;
  height: 60px;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 18px;
}
.notice-badge {
  cursor: pointer;
}
.bell-icon {
  font-size: 19px;
  color: #606266;
}
.bell-icon:hover {
  color: #409eff;
}
.notice-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 6px;
}
.notice-list {
  max-height: 360px;
  overflow-y: auto;
}
.notice-empty {
  text-align: center;
  color: #909399;
  font-size: 13px;
  padding: 24px 0;
}
.notice-item {
  display: flex;
  padding: 8px 6px;
  border-radius: 6px;
  cursor: pointer;
}
.notice-item:hover {
  background: #f5f7fa;
}
.notice-item.unread .notice-title {
  color: #303133;
  font-weight: 600;
}
.notice-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f56c6c;
  margin-top: 6px;
  margin-right: 8px;
  flex-shrink: 0;
}
.notice-body {
  flex: 1;
  min-width: 0;
}
.notice-title {
  font-size: 13px;
  color: #606266;
}
.notice-content {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin: 2px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notice-time {
  font-size: 11px;
  color: #c0c4cc;
}
.user-info {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 0 8px;
  outline: none;
}
.user-avatar {
  margin-right: 8px;
  background-color: #409eff;
  color: #fff;
}
.nickname {
  font-size: 14px;
  color: #606266;
  margin-right: 4px;
}
.main-content {
  padding: 20px;
  overflow-y: auto;
}
</style>
