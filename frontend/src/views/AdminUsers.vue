<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <span class="card-title">用户管理</span>
      </template>
      <el-table :data="users" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="头像" width="80">
          <template #default="{ row }">
            <el-avatar :size="32" :src="row.avatar">{{ (row.nickname || row.username)?.charAt(0) }}</el-avatar>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="nickname" label="昵称" width="140" />
        <el-table-column prop="email" label="邮箱" min-width="160" show-overflow-tooltip />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'">
              {{ row.role === 'admin' ? '管理员' : '学生' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="信用分" width="170">
          <template #default="{ row }">
            <div class="credit-cell">
              <el-input-number
                v-model="creditDraft[row.id]"
                :min="0"
                :max="100"
                :step="5"
                size="small"
                controls-position="right"
                style="width: 100px"
              />
              <el-button size="small" type="primary" plain @click="saveCredit(row)">保存</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="size"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const users = ref([])
const loading = ref(false)
const page = ref(1)
const size = 20
const total = ref(0)
// 每行一个信用分草稿：{ [userId]: score }
const creditDraft = reactive({})

function formatTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN') : '-'
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/api/users', { params: { page: page.value, size } })
    users.value = res.data.items
    users.value.forEach((u) => {
      creditDraft[u.id] = u.credit_score ?? 100
    })
  } finally {
    loading.value = false
  }
}

async function saveCredit(row) {
  const score = creditDraft[row.id]
  try {
    const res = await api.post(`/api/users/${row.id}/credit`, { credit_score: score })
    ElMessage.success(res.message || '已更新')
  } catch {
    // 拦截器已提示错误
  }
}

onMounted(load)
</script>

<style scoped>
.card-title { font-size: 16px; font-weight: 600; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
.credit-cell { display: flex; align-items: center; gap: 6px; }
</style>
