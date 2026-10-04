<template>
  <div class="my-bookings-page">
    <div class="page-header">我的预约</div>
    <el-table v-loading="loading" :data="bookings" border stripe size="default" class="booking-table">
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
      <el-table-column prop="review_note" label="审核意见" min-width="140" show-overflow-tooltip />
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'pending' || row.status === 'approved'"
            size="small"
            type="danger"
            @click="cancelBooking(row)"
          >取消</el-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const bookings = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const loading = ref(false)

function statusType(status) {
  const map = {
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    cancelled: 'info',
    used: 'primary',
  }
  return map[status] || 'info'
}

function statusText(status) {
  const map = {
    pending: '待审核',
    approved: '已通过',
    rejected: '已驳回',
    cancelled: '已取消',
    used: '已使用',
  }
  return map[status] || status
}

async function loadBookings() {
  loading.value = true
  try {
    const res = await api.get('/api/bookings/mine', {
      params: { page: page.value, size: size.value },
    })
    bookings.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function cancelBooking(row) {
  try {
    await ElMessageBox.confirm('确认取消该预约？', '提示', { type: 'warning' })
    await api.post(`/api/bookings/${row.id}/cancel`)
    ElMessage.success('取消成功')
    loadBookings()
  } catch {
    // ignore
  }
}

onMounted(loadBookings)
</script>

<style scoped>
.my-bookings-page {
  padding: 0;
}
.page-header {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
}
.booking-table {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
}
.pagination {
  margin-top: 20px;
  justify-content: center;
}
</style>
