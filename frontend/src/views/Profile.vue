<template>
  <div class="profile-page">
    <el-card class="profile-card">
      <template #header>
        <div class="card-header">个人中心</div>
      </template>
      <div class="profile-content">
        <div class="avatar-section">
          <img v-if="auth.user?.avatar" :src="auth.user.avatar" class="avatar-img" />
          <div v-else class="avatar-placeholder">{{ auth.user?.nickname?.charAt(0) || 'U' }}</div>
          <el-upload
            class="avatar-uploader"
            action=""
            :show-file-list="false"
            :http-request="uploadAvatar"
            accept="image/*"
          >
            <el-button type="primary" size="small" plain>更换头像</el-button>
          </el-upload>
        </div>
        <div class="info-section">
          <div class="info-row">
            <span class="info-label">用户名</span>
            <span class="info-value">{{ auth.user?.username }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">角色</span>
            <span class="info-value">{{ auth.user?.role === 'admin' ? '管理员' : '普通用户' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">信用分</span>
            <span class="info-value">
              <el-tag :type="creditType(auth.user?.credit_score)" size="small">
                {{ auth.user?.credit_score ?? 100 }}
              </el-tag>
              <span class="credit-tip">初始 100 分，临期取消扣 5 分，低于 60 分将限制预约</span>
            </span>
          </div>
          <el-form :model="form" label-width="80px" class="edit-form">
            <el-form-item label="昵称">
              <el-input v-model="form.nickname" placeholder="请输入昵称" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="form.email" placeholder="请输入邮箱" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveProfile">保存修改</el-button>
            </el-form-item>
          </el-form>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { auth } from '../store/auth'
import api from '../api'

const form = ref({ nickname: '', email: '' })
const saving = ref(false)

function initForm() {
  form.value.nickname = auth.user?.nickname || ''
  form.value.email = auth.user?.email || ''
}

function creditType(score) {
  const s = score ?? 100
  if (s < 60) return 'danger'
  if (s < 90) return 'warning'
  return 'success'
}

async function refreshProfile() {
  // 登录时缓存的 user 可能没有 credit_score 等新字段，挂载时拉取最新资料
  try {
    const me = await api.get('/api/users/me')
    auth.setUser(me.data)
    initForm()
  } catch {
    // ignore
  }
}

async function saveProfile() {
  saving.value = true
  try {
    await api.put('/api/users/me', form.value)
    const me = await api.get('/api/users/me')
    auth.setUser(me.data)
    ElMessage.success('保存成功')
  } finally {
    saving.value = false
  }
}

async function uploadAvatar({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await api.post('/api/users/me/avatar', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const me = await api.get('/api/users/me')
    auth.setUser(me.data)
    ElMessage.success('头像更新成功')
  } catch {
    // ignore
  }
}

onMounted(refreshProfile)
</script>

<style scoped>
.profile-page {
  padding: 0;
}
.profile-card {
  border-radius: 12px;
}
.card-header {
  font-size: 17px;
  font-weight: 600;
  color: #303133;
}
.profile-content {
  display: flex;
  gap: 40px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  min-width: 120px;
}
.avatar-img {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #ebeef5;
}
.avatar-placeholder {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  font-weight: 600;
}
.info-section {
  flex: 1;
  min-width: 260px;
}
.info-row {
  display: flex;
  align-items: center;
  margin-bottom: 14px;
  font-size: 14px;
}
.info-label {
  width: 80px;
  color: #909399;
  flex-shrink: 0;
}
.info-value {
  color: #303133;
  font-weight: 500;
}
.edit-form {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px dashed #ebeef5;
}
.credit-tip {
  margin-left: 10px;
  font-size: 12px;
  color: #909399;
}
</style>
