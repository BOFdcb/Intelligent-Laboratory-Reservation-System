<template>
  <div class="admin-bookings-page">
    <div class="page-header">
      <span>预约审核</span>
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 160px" @change="page = 1; loadBookings()">
        <el-option label="全部" value="" />
        <el-option label="待审核" value="pending" />
        <el-option label="已通过" value="approved" />
        <el-option label="已驳回" value="rejected" />
        <el-option label="已取消" value="cancelled" />
        <el-option label="已使用" value="used" />
      </el-select>
    </div>

    <el-table v-loading="loading" :data="bookings" border stripe size="default">
      <el-table-column prop="user.nickname" label="预约人" width="120" />
      <el-table-column prop="lab.name" label="实验室" min-width="140" />
      <el-table-column prop="booking_date" label="日期" width="120" />
      <el-table-column label="时段" width="140">
        <template #default="{ row }">
          <span>{{ row.start_time?.slice(0, 5) }} - {{ row.end_time?.slice(0, 5) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="purpose" label="用途" min-width="180" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" @click="approveBooking(row)">通过</el-button>
            <el-button size="small" type="danger" @click="openRejectDialog(row)">驳回</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="size"
      :total="total"
      layout="total, prev, pager, next"
      class="pagination"
      @current-change="loadBookings"
    />

    <el-dialog v-model="rejectVisible" title="驳回预约" width="480px">
      <el-form label-width="90px">
        <el-form-item label="审核意见" required>
          <el-input v-model="reviewNote" type="textarea" :rows="3" placeholder="请输入驳回原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectVisible = false">取 消</el-button>
        <el-button type="primary" :loading="rejectLoading" @click="submitReject">确认驳回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const bookings = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const loading = ref(false)
const filterStatus = ref('')

const rejectVisible = ref(false)
const rejectLoading = ref(false)
const reviewNote = ref('')
const currentBooking = ref(null)

function statusType(status) {
  const map = { pending: 'warning', approved: 'success', rejected: 'danger', cancelled: 'info', used: 'primary' }
  return map[status] || 'info'
}

function statusText(status) {
  const map = { pending: '待审核', approved: '已通过', rejected: '已驳回', cancelled: '已取消', used: '已使用' }
  return map[status] || status
}

function formatDate(str) {
  if (!str) return '-'
  const d = new Date(str)
  if (isNaN(d.getTime())) return str
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function loadBookings() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filterStatus.value) params.status = filterStatus.value
    const res = await api.get('/api/bookings', { params })
    bookings.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function approveBooking(row) {
  try {
    await api.post(`/api/bookings/${row.id}/approve`)
    ElMessage.success('审核通过')
    loadBookings()
  } catch {
    // ignore
  }
}

function openRejectDialog(row) {
  currentBooking.value = row
  reviewNote.value = ''
  rejectVisible.value = true
}

async function submitReject() {
  if (!reviewNote.value.trim()) {
    return ElMessage.warning('请输入驳回原因')
  }
  rejectLoading.value = true
  try {
    await api.post(`/api/bookings/${currentBooking.value.id}/reject`, { review_note: reviewNote.value })
    ElMessage.success('已驳回')
    rejectVisible.value = false
    loadBookings()
  } finally {
    rejectLoading.value = false
  }
}

onMounted(loadBookings)
</script>

<style scoped>
.admin-bookings-page {
  padding: 0;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.pagination {
  margin-top: 20px;
  justify-content: center;
}
</style>
