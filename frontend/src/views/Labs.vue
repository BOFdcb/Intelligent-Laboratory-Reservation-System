<template>
  <div class="labs-page">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索实验室名称或位置"
        clearable
        style="width: 300px"
        :prefix-icon="Search"
        @input="handleSearch"
        @clear="loadLabs"
      />
    </div>

    <div v-loading="loading" class="labs-grid">
      <div
        v-for="lab in labs"
        :key="lab.id"
        class="lab-card"
        @click="showDetail(lab)"
      >
        <div class="lab-header">
          <h3 class="lab-name">{{ lab.name }}</h3>
          <el-tag :type="lab.status === 'enabled' ? 'success' : 'danger'" size="small">
            {{ lab.status === 'enabled' ? '可用' : '停用' }}
          </el-tag>
        </div>
        <div class="lab-info">
          <div class="info-item">
            <el-icon><Location /></el-icon>
            <span>{{ lab.location }}</span>
          </div>
          <div class="info-item">
            <el-icon><User /></el-icon>
            <span>容量：{{ lab.capacity }} 人</span>
          </div>
          <div class="info-item">
            <el-icon><Clock /></el-icon>
            <span>{{ lab.open_time?.slice(0, 5) }} - {{ lab.close_time?.slice(0, 5) }}</span>
          </div>
        </div>
        <div v-if="lab.rules" class="lab-rules">规则：{{ lab.rules }}</div>
      </div>
      <el-empty v-if="!loading && labs.length === 0" description="暂无实验室" />
    </div>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="size"
      :total="total"
      layout="total, prev, pager, next"
      class="pagination"
      @current-change="loadLabs"
    />

    <!-- 详情 Dialog -->
    <el-dialog v-model="detailVisible" :title="currentLab?.name" width="640px" class="detail-dialog">
      <div class="detail-section">
        <div class="detail-row"><span class="label">位置：</span>{{ currentLab?.location }}</div>
        <div class="detail-row"><span class="label">容量：</span>{{ currentLab?.capacity }} 人</div>
        <div class="detail-row">
          <span class="label">开放时间：</span>{{ currentLab?.open_time?.slice(0, 5) }} - {{ currentLab?.close_time?.slice(0, 5) }}
        </div>
        <div class="detail-row"><span class="label">状态：</span>
          <el-tag :type="currentLab?.status === 'enabled' ? 'success' : 'danger'" size="small">
            {{ currentLab?.status === 'enabled' ? '可用' : '停用' }}
          </el-tag>
        </div>
        <div v-if="currentLab?.rules" class="detail-row"><span class="label">使用规则：</span>{{ currentLab?.rules }}</div>
      </div>

      <div class="equipment-section">
        <h4>设备列表</h4>
        <el-table :data="equipmentList" size="small" border max-height="260">
          <el-table-column prop="name" label="设备名称" />
          <el-table-column prop="model" label="型号" />
          <el-table-column prop="quantity" label="数量" width="80" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'normal' ? 'success' : 'warning'" size="small">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="detailVisible = false">关 闭</el-button>
        <el-button
          type="primary"
          :disabled="currentLab?.status !== 'enabled'"
          @click="openBookingDialog"
        >立即预约</el-button>
      </template>
    </el-dialog>

    <!-- 预约 Dialog -->
    <el-dialog v-model="bookingVisible" title="预约实验室" width="480px">
      <el-form :model="bookingForm" label-width="90px">
        <el-form-item label="实验室">
          <el-input :model-value="currentLab?.name" disabled />
        </el-form-item>
        <el-form-item label="预约日期" required>
          <el-date-picker
            v-model="bookingForm.booking_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            :disabled-date="disabledDate"
          />
        </el-form-item>
        <el-form-item label="开始时间" required>
          <el-time-picker
            v-model="bookingForm.start_time"
            value-format="HH:mm"
            format="HH:mm"
            placeholder="选择时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间" required>
          <el-time-picker
            v-model="bookingForm.end_time"
            value-format="HH:mm"
            format="HH:mm"
            placeholder="选择时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="用途">
          <el-input
            v-model="bookingForm.purpose"
            type="textarea"
            :rows="3"
            placeholder="请简述预约用途"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bookingVisible = false">取 消</el-button>
        <el-button type="primary" :loading="bookingLoading" @click="submitBooking">提交预约</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Location, User, Clock } from '@element-plus/icons-vue'
import api from '../api'

const labs = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(12)
const keyword = ref('')
const loading = ref(false)

const detailVisible = ref(false)
const currentLab = ref(null)
const equipmentList = ref([])

const bookingVisible = ref(false)
const bookingLoading = ref(false)
const bookingForm = ref({
  booking_date: '',
  start_time: '',
  end_time: '',
  purpose: '',
})

let searchTimer = null
function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadLabs()
  }, 400)
}

async function loadLabs() {
  loading.value = true
  try {
    const res = await api.get('/api/labs', {
      params: { page: page.value, size: size.value, keyword: keyword.value },
    })
    labs.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function showDetail(lab) {
  currentLab.value = lab
  detailVisible.value = true
  try {
    const res = await api.get(`/api/labs/${lab.id}`)
    currentLab.value = res.data
    equipmentList.value = res.data.equipment || []
  } catch {
    equipmentList.value = []
  }
}

function openBookingDialog() {
  bookingForm.value = { booking_date: '', start_time: '', end_time: '', purpose: '' }
  bookingVisible.value = true
}

function disabledDate(time) {
  return time.getTime() < Date.now() - 8.64e7
}

async function submitBooking() {
  const f = bookingForm.value
  if (!f.booking_date || !f.start_time || !f.end_time) {
    return ElMessage.warning('请完整填写预约日期和时间段')
  }
  if (f.start_time >= f.end_time) {
    return ElMessage.warning('结束时间必须晚于开始时间')
  }
  bookingLoading.value = true
  try {
    await api.post('/api/bookings', {
      lab_id: currentLab.value.id,
      booking_date: f.booking_date,
      start_time: f.start_time,
      end_time: f.end_time,
      purpose: f.purpose,
    })
    ElMessage.success('预约提交成功，请等待审核')
    bookingVisible.value = false
    detailVisible.value = false
  } finally {
    bookingLoading.value = false
  }
}

onMounted(loadLabs)
</script>

<style scoped>
.labs-page {
  padding: 0;
}
.toolbar {
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}
.labs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  min-height: 200px;
}
.lab-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: all 0.3s;
}
.lab-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}
.lab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.lab-name {
  margin: 0;
  font-size: 17px;
  color: #303133;
}
.lab-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.info-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
  font-size: 14px;
}
.lab-rules {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pagination {
  margin-top: 20px;
  justify-content: center;
}
.detail-section {
  margin-bottom: 16px;
}
.detail-row {
  margin-bottom: 8px;
  font-size: 14px;
  color: #606266;
}
.detail-row .label {
  color: #909399;
}
.equipment-section h4 {
  margin: 0 0 10px;
  color: #303133;
  font-size: 15px;
}
</style>
