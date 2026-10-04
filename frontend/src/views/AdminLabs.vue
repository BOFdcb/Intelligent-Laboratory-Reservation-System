<template>
  <div class="admin-labs-page">
    <div class="page-header">
      <span>实验室管理</span>
      <el-button type="primary" @click="openAddDialog">新增实验室</el-button>
    </div>

    <el-table v-loading="loading" :data="labs" border stripe size="default">
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="location" label="位置" min-width="140" />
      <el-table-column prop="capacity" label="容量" width="90" />
      <el-table-column label="开放时间" width="160">
        <template #default="{ row }">
          {{ row.open_time?.slice(0, 5) }} - {{ row.close_time?.slice(0, 5) }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'enabled' ? 'success' : 'danger'" size="small">
            {{ row.status === 'enabled' ? '可用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openEditDialog(row)">编辑</el-button>
          <el-button size="small" @click="openEquipmentDialog(row)">设备</el-button>
          <el-button size="small" type="danger" @click="deleteLab(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="size"
      :total="total"
      layout="total, prev, pager, next"
      class="pagination"
      @current-change="loadLabs"
    />

    <!-- 新增/编辑 Dialog -->
    <el-dialog v-model="formVisible" :title="isEdit ? '编辑实验室' : '新增实验室'" width="540px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="请输入实验室名称" />
        </el-form-item>
        <el-form-item label="位置" required>
          <el-input v-model="form.location" placeholder="请输入位置" />
        </el-form-item>
        <el-form-item label="容量" required>
          <el-input-number v-model="form.capacity" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="开始时间" required>
          <el-time-picker
            v-model="form.open_time"
            value-format="HH:mm:ss"
            format="HH:mm:ss"
            placeholder="选择时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间" required>
          <el-time-picker
            v-model="form.close_time"
            value-format="HH:mm:ss"
            format="HH:mm:ss"
            placeholder="选择时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="使用规则">
          <el-input v-model="form.rules" type="textarea" :rows="3" placeholder="请输入使用规则（选填）" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch
            v-model="form.status"
            active-value="enabled"
            inactive-value="disabled"
            active-text="可用"
            inactive-text="停用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取 消</el-button>
        <el-button type="primary" :loading="formLoading" @click="submitForm">保 存</el-button>
      </template>
    </el-dialog>

    <!-- 设备管理 Dialog -->
    <el-dialog v-model="equipmentVisible" :title="`${currentLab?.name} - 设备管理`" width="680px">
      <div class="equip-toolbar">
        <el-button type="primary" size="small" @click="openEquipForm()">新增设备</el-button>
      </div>
      <el-table :data="equipmentList" border stripe size="small">
        <el-table-column prop="name" label="设备名称" />
        <el-table-column prop="model" label="型号" />
        <el-table-column prop="quantity" label="数量" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'normal' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="openEquipForm(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteEquipment(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog v-model="equipFormVisible" :title="isEquipEdit ? '编辑设备' : '新增设备'" width="440px" append-to-body>
        <el-form :model="equipForm" label-width="80px">
          <el-form-item label="名称" required>
            <el-input v-model="equipForm.name" placeholder="请输入设备名称" />
          </el-form-item>
          <el-form-item label="型号">
            <el-input v-model="equipForm.model" placeholder="请输入型号" />
          </el-form-item>
          <el-form-item label="数量" required>
            <el-input-number v-model="equipForm.quantity" :min="0" style="width: 100%" />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="equipForm.status" style="width: 100%">
              <el-option label="normal" value="normal" />
              <el-option label="maintenance" value="maintenance" />
              <el-option label="broken" value="broken" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="equipFormVisible = false">取 消</el-button>
          <el-button type="primary" :loading="equipFormLoading" @click="submitEquipForm">保 存</el-button>
        </template>
      </el-dialog>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const labs = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const loading = ref(false)

const formVisible = ref(false)
const formLoading = ref(false)
const isEdit = ref(false)
const currentLabId = ref(null)
const form = ref({
  name: '',
  location: '',
  capacity: 30,
  open_time: '',
  close_time: '',
  rules: '',
  status: 'enabled',
})

const equipmentVisible = ref(false)
const currentLab = ref(null)
const equipmentList = ref([])

const equipFormVisible = ref(false)
const equipFormLoading = ref(false)
const isEquipEdit = ref(false)
const currentEquipId = ref(null)
const equipForm = ref({ name: '', model: '', quantity: 1, status: 'normal' })

async function loadLabs() {
  loading.value = true
  try {
    const res = await api.get('/api/labs', { params: { page: page.value, size: size.value } })
    labs.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.value = {
    name: '',
    location: '',
    capacity: 30,
    open_time: '',
    close_time: '',
    rules: '',
    status: 'enabled',
  }
}

function openAddDialog() {
  isEdit.value = false
  currentLabId.value = null
  resetForm()
  formVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  currentLabId.value = row.id
  form.value = {
    name: row.name,
    location: row.location,
    capacity: row.capacity,
    open_time: row.open_time,
    close_time: row.close_time,
    rules: row.rules || '',
    status: row.status,
  }
  formVisible.value = true
}

async function submitForm() {
  const f = form.value
  if (!f.name || !f.location || !f.capacity || !f.open_time || !f.close_time) {
    return ElMessage.warning('请填写完整信息')
  }
  formLoading.value = true
  try {
    if (isEdit.value) {
      await api.put(`/api/labs/${currentLabId.value}`, f)
      ElMessage.success('修改成功')
    } else {
      await api.post('/api/labs', f)
      ElMessage.success('新增成功')
    }
    formVisible.value = false
    loadLabs()
  } finally {
    formLoading.value = false
  }
}

async function deleteLab(row) {
  try {
    await ElMessageBox.confirm(`确认删除实验室「${row.name}」？`, '提示', { type: 'warning' })
    await api.delete(`/api/labs/${row.id}`)
    ElMessage.success('删除成功')
    loadLabs()
  } catch {
    // ignore
  }
}

async function openEquipmentDialog(row) {
  currentLab.value = row
  equipmentVisible.value = true
  await loadEquipment()
}

async function loadEquipment() {
  try {
    const res = await api.get(`/api/labs/${currentLab.value.id}/equipment`)
    equipmentList.value = res.data
  } catch {
    equipmentList.value = []
  }
}

function openEquipForm(row = null) {
  if (row) {
    isEquipEdit.value = true
    currentEquipId.value = row.id
    equipForm.value = { name: row.name, model: row.model, quantity: row.quantity, status: row.status }
  } else {
    isEquipEdit.value = false
    currentEquipId.value = null
    equipForm.value = { name: '', model: '', quantity: 1, status: 'normal' }
  }
  equipFormVisible.value = true
}

async function submitEquipForm() {
  const f = equipForm.value
  if (!f.name || f.quantity === undefined || f.quantity === null) {
    return ElMessage.warning('请填写设备名称和数量')
  }
  equipFormLoading.value = true
  try {
    if (isEquipEdit.value) {
      await api.put(`/api/equipment/${currentEquipId.value}`, f)
      ElMessage.success('修改成功')
    } else {
      await api.post(`/api/labs/${currentLab.value.id}/equipment`, f)
      ElMessage.success('新增成功')
    }
    equipFormVisible.value = false
    loadEquipment()
  } finally {
    equipFormLoading.value = false
  }
}

async function deleteEquipment(row) {
  try {
    await ElMessageBox.confirm(`确认删除设备「${row.name}」？`, '提示', { type: 'warning' })
    await api.delete(`/api/equipment/${row.id}`)
    ElMessage.success('删除成功')
    loadEquipment()
  } catch {
    // ignore
  }
}

onMounted(loadLabs)
</script>

<style scoped>
.admin-labs-page {
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
.equip-toolbar {
  margin-bottom: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
