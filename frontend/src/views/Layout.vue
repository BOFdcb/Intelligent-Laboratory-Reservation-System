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
        </template>
      </el-menu>
    </el-aside>
    <el-container class="main-wrapper">
      <el-header class="header">
        <div class="header-left">
          <span class="page-title">{{ route.meta.title || '' }}</span>
        </div>
        <div class="header-right">
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
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  OfficeBuilding,
  Calendar,
  ChatDotRound,
  User,
  DocumentChecked,
  Setting,
  UserFilled,
  ArrowDown,
} from '@element-plus/icons-vue'
import { auth } from '../store/auth'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => route.path)

function handleCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
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
