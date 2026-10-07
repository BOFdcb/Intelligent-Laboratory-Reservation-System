<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">Agent 工具调用审计</span>
          <div class="filters">
            <el-select v-model="toolName" placeholder="全部工具" clearable size="small" style="width: 200px" @change="reload">
              <el-option v-for="t in toolOptions" :key="t" :label="t" :value="t" />
            </el-select>
            <el-select v-model="successFilter" placeholder="全部结果" clearable size="small" style="width: 130px" @change="reload">
              <el-option label="成功" value="true" />
              <el-option label="失败/拒绝" value="false" />
            </el-select>
            <el-button size="small" @click="reload">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table :data="logs" v-loading="loading" border stripe size="small">
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column label="用户" width="150">
          <template #default="{ row }">
            {{ row.username }}
            <el-tag size="small" :type="row.role === 'admin' ? 'danger' : 'info'">{{ row.role === 'admin' ? '管理员' : '学生' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="tool_name" label="工具" width="190" />
        <el-table-column label="参数" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.arguments }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono" :class="{ 'result-error': !row.success }">{{ row.result_summary }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'" size="small">
              {{ row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
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
import { ref, onMounted } from 'vue'
import api from '../api'

const logs = ref([])
const loading = ref(false)
const page = ref(1)
const size = 20
const total = ref(0)
const toolName = ref('')
const successFilter = ref('')

const toolOptions = [
  'list_labs', 'get_lab_equipment', 'check_availability', 'search_rules',
  'search_equipment', 'create_booking', 'update_booking', 'cancel_booking',
  'list_my_bookings', 'book_equipment', 'cancel_equipment_booking',
  'list_my_equipment_bookings',
  'admin_list_bookings', 'admin_approve_booking', 'admin_reject_booking',
]

async function load() {
  loading.value = true
  try {
    const res = await api.get('/api/admin/audit-logs', {
      params: {
        page: page.value, size,
        tool_name: toolName.value || '',
        success: successFilter.value || '',
      },
    })
    logs.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}

onMounted(load)
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title { font-size: 16px; font-weight: 600; }
.filters { display: flex; gap: 10px; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
.mono {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #606266;
}
.result-error { color: #f56c6c; }
</style>
