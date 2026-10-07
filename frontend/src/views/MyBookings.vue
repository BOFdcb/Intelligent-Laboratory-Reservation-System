<template>
  <div class="my-bookings-page">
    <div class="page-header">我的预约</div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- 实验室预约 -->
      <el-tab-pane label="实验室预约" name="lab">
        <el-table v-loading="loading" :data="bookings" border stripe size="default" class="booking-table">
          <el-table-column prop="lab.name" label="实验室" min-width="140" />
          <el-table-column prop="booking_date" label="日期" width="120" />
          <el-table-column label="时段" width="140">
            <template #default="{ row }">
              <span>{{ row.start_time?.slice(0, 5) }} - {{ row.end_time?.slice(0, 5) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="人数" width="90">
            <template #default="{ row }">
              <el-tooltip
                v-if="row.participant_count > 1"
                :content="`成员：我、${(row.members || []).join('、')}`"
                placement="top"
              >
                <el-tag size="small" type="primary">{{ row.participant_count }} 人</el-tag>
              </el-tooltip>
              <span v-else>1 人</span>
            </template>
          </el-table-column>
          <el-table-column prop="purpose" label="用途" min-width="160" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="130">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
              <el-tag v-if="row.auto_reviewed" type="success" size="small" effect="plain" class="ai-tag">AI</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="review_note" label="审核意见" min-width="130" show-overflow-tooltip />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'approved'"
                size="small"
                type="primary"
                @click="confirmBooking(row)"
              >签到</el-button>
              <el-button
                v-if="row.status === 'pending' || row.status === 'approved' || row.status === 'confirmed'"
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
        <div class="tab-tip">改约可在「AI 助手」对话中完成，例如：把我的 3 号预约改到明天下午。</div>
      </el-tab-pane>

      <!-- 设备预约 -->
      <el-tab-pane label="设备预约" name="equipment">
        <el-table v-loading="loading" :data="equipmentBookings" border stripe size="default" class="booking-table">
          <el-table-column label="设备" min-width="160">
            <template #default="{ row }">
              {{ row.equipment?.lab_name }} / {{ row.equipment?.name }}
              <span v-if="row.equipment?.model" class="equip-model">（{{ row.equipment.model }}）</span>
            </template>
          </el-table-column>
          <el-table-column prop="booking_date" label="日期" width="120" />
          <el-table-column label="时段" width="140">
            <template #default="{ row }">
              <span>{{ row.start_time }} - {{ row.end_time }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="purpose" label="用途" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === 'active' ? '有效' : '已取消' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'active'"
                size="small"
                type="danger"
                @click="cancelEquipmentBooking(row)"
              >取消</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="tab-tip">设备预约可在「AI 助手」对话中发起，例如：帮我预约明天上午 10 点到 12 点的示波器。</div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const activeTab = ref('lab')
const bookings = ref([])
const equipmentBookings = ref([])
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
    confirmed: 'primary',
    used: 'primary',
    released: 'danger',
  }
  return map[status] || 'info'
}

function statusText(status) {
  const map = {
    pending: '待审核',
    approved: '已通过',
    rejected: '已驳回',
    cancelled: '已取消',
    confirmed: '已签到',
    used: '已使用',
    released: '已释放',
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

async function loadEquipmentBookings() {
  loading.value = true
  try {
    const res = await api.get('/api/equipment-bookings/mine')
    equipmentBookings.value = res.data.items || []
  } finally {
    loading.value = false
  }
}

function onTabChange(name) {
  if (name === 'equipment') loadEquipmentBookings()
  else loadBookings()
}

async function cancelBooking(row) {
  try {
    await ElMessageBox.confirm('确认取消该预约？临期取消将扣除信用分。', '提示', { type: 'warning' })
    const res = await api.post(`/api/bookings/${row.id}/cancel`)
    ElMessage.success(res.message || '取消成功')
    loadBookings()
  } catch {
    // ignore
  }
}

async function confirmBooking(row) {
  try {
    const res = await api.post(`/api/bookings/${row.id}/confirm`)
    ElMessage.success(res.message || '签到成功')
    loadBookings()
  } catch {
    // 错误提示已由拦截器给出
  }
}

async function cancelEquipmentBooking(row) {
  try {
    await ElMessageBox.confirm('确认取消该设备预约？临期取消将扣除信用分。', '提示', { type: 'warning' })
    const res = await api.post(`/api/equipment-bookings/${row.id}/cancel`)
    ElMessage.success(res.message || '取消成功')
    loadEquipmentBookings()
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
.ai-tag {
  margin-left: 4px;
}
.equip-model {
  color: #909399;
  font-size: 12px;
}
.pagination {
  margin-top: 20px;
  justify-content: center;
}
.tab-tip {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
</style>
