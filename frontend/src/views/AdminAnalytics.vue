<template>
  <div class="analytics-page">
    <div class="page-header">
      <span>数据分析 Agent</span>
      <span class="subtitle">自然语言提问 → 自动解析指标 → 聚合计算 → 图表化运营建议</span>
    </div>

    <div class="ask-bar">
      <el-input
        v-model="question"
        placeholder="例如：本周哪个实验室最忙？热门时段是几点？"
        clearable
        @keydown.enter="ask"
      />
      <el-button type="primary" :loading="loading" @click="ask">分析</el-button>
    </div>

    <div class="quick-list">
      <el-tag
        v-for="q in quickQuestions"
        :key="q"
        class="quick-tag"
        effect="plain"
        @click="useQuick(q)"
      >{{ q }}</el-tag>
    </div>

    <!-- 过程节点可见 -->
    <div v-if="activePlan || loading" class="process-line">
      <el-icon class="step-icon" :class="{ done: stepDone.parse }"><Search /></el-icon>
      <span class="step" :class="{ active: stepActive.parse, done: stepDone.parse }">问题解析</span>
      <el-tag v-if="activePlan" size="small" type="info" class="plan-tag">
        {{ metricLabel(activePlan.metric) }} · {{ rangeLabel(activePlan.range) }}
      </el-tag>
      <el-icon class="step-icon" :class="{ done: stepDone.compute }"><DataLine /></el-icon>
      <span class="step" :class="{ active: stepActive.compute, done: stepDone.compute }">数据计算</span>
      <el-icon class="step-icon" :class="{ done: stepDone.summarize }"><MagicStick /></el-icon>
      <span class="step" :class="{ active: stepActive.summarize, done: stepDone.summarize }">生成洞察</span>
    </div>

    <!-- 关键指标卡片 -->
    <div v-if="factItems.length" class="fact-grid">
      <div v-for="item in factItems" :key="item.key" class="fact-card">
        <div class="fact-value">{{ item.display }}</div>
        <div class="fact-label">{{ item.label }}</div>
      </div>
    </div>

    <!-- 洞察文本 -->
    <div v-if="summary" class="summary-card">
      <div class="summary-title">运营洞察与建议</div>
      <div class="summary-body">{{ summary }}</div>
    </div>

    <!-- 图表区 -->
    <div v-if="charts.length" class="chart-grid">
      <div v-for="chart in charts" :key="chart.key" class="chart-card">
        <div class="chart-title">{{ chart.title }}<span v-if="rangeLabelText" class="chart-range">{{ rangeLabelText }}</span></div>
        <div :id="`chart-${chart.key}`" class="chart-canvas"></div>
      </div>
    </div>

    <el-empty v-if="!loading && !charts.length && hasAsked" description="未查询到数据，换个时间范围或问题试试" />
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, DataLine, MagicStick } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { auth } from '../store/auth'

const question = ref('')
const loading = ref(false)
const hasAsked = ref(false)
const activePlan = ref(null)
const charts = ref([])
const facts = ref({})
const summary = ref('')
const rangeLabelText = ref('')

const stepActive = ref({ parse: false, compute: false, summarize: false })
const stepDone = ref({ parse: false, compute: false, summarize: false })

const quickQuestions = [
  '给我一份本周实验室运营综合看板',
  '本周哪个实验室最忙？使用率分别是多少？',
  '最近一周的热门使用时段是哪些？',
  '本周每天的预约量趋势如何？',
  '本月预约通过率和取消率是多少？',
]

const METRIC_LABELS = {
  overview: '综合看板', lab_usage: '实验室使用', hot_slots: '热门时段',
  daily_trend: '每日趋势', status_distribution: '状态分布',
}
const RANGE_LABELS = {
  today: '今天', this_week: '本周', last_week: '上周',
  this_month: '本月', last_7_days: '近7天', last_30_days: '近30天',
}
function metricLabel(m) { return METRIC_LABELS[m] || m }
function rangeLabel(r) { return RANGE_LABELS[r] || r }

const FACT_LABELS = {
  total_effective_bookings: '有效预约量',
  busiest_lab: '最忙实验室',
  busiest_lab_count: '最忙实验室预约数',
  average_utilization: '平均使用率',
  peak_slot: '热门时段',
  peak_slot_count: '热门时段次数',
  total_bookings: '预约总量',
  pending_count: '待审核数',
  effective_count: '有效预约数',
  approval_rate: '通过率',
  cancel_rate: '取消率',
  release_rate: '爽约释放率',
  peak_day: '高峰日期',
  peak_day_count: '高峰日预约数',
  average_per_day: '日均预约量',
}
const PERCENT_KEYS = new Set(['average_utilization', 'approval_rate', 'cancel_rate', 'release_rate'])

// 综合看板 facts 是嵌套结构，拍平成卡片
const factItems = computed(() => {
  const items = []
  const walk = (obj, prefix = '') => {
    for (const [k, v] of Object.entries(obj || {})) {
      const key = prefix ? `${prefix}_${k}` : k
      if (v && typeof v === 'object') {
        if (Array.isArray(v)) continue // ranking 列表不在卡片展示
        walk(v, key)
      } else if (FACT_LABELS[key]) {
        items.push({
          key,
          label: FACT_LABELS[key],
          display: PERCENT_KEYS.has(key) ? `${v}%` : String(v),
        })
      }
    }
  }
  walk(facts.value)
  return items.slice(0, 8)
})

function useQuick(q) {
  question.value = q
  ask()
}

async function ask() {
  const text = question.value.trim()
  if (!text || loading.value) return

  loading.value = true
  hasAsked.value = true
  activePlan.value = null
  charts.value = []
  facts.value = {}
  summary.value = ''
  rangeLabelText.value = ''
  stepActive.value = { parse: true, compute: false, summarize: false }
  stepDone.value = { parse: false, compute: false, summarize: false }
  disposeCharts()

  try {
    const resp = await fetch('/api/admin/analytics/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ question: text }),
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue
        try {
          handleEvent(JSON.parse(trimmed.slice(6)))
        } catch {
          // ignore malformed SSE
        }
      }
    }
  } catch (e) {
    ElMessage.error('请求失败：' + (e.message || '网络错误'))
  } finally {
    loading.value = false
    stepActive.value = { parse: false, compute: false, summarize: false }
  }
}

function handleEvent(ev) {
  if (ev.type === 'plan') {
    activePlan.value = ev.plan
    stepDone.value.parse = true
    stepActive.value = { parse: false, compute: true, summarize: false }
  } else if (ev.type === 'charts') {
    charts.value = ev.charts || []
    facts.value = ev.facts || {}
    rangeLabelText.value = ev.range ? `${ev.range.label}（${ev.range.from} ~ ${ev.range.to}）` : ''
    stepDone.value = { parse: true, compute: true, summarize: false }
    stepActive.value = { parse: false, compute: false, summarize: true }
    nextTick(renderCharts)
  } else if (ev.type === 'summary') {
    summary.value = ev.content || ''
    stepDone.value = { parse: true, compute: true, summarize: true }
    stepActive.value = { parse: false, compute: false, summarize: false }
  } else if (ev.type === 'error') {
    ElMessage.error(ev.content || '分析失败')
  }
}

// ---------------- ECharts 渲染 ----------------
const chartInstances = new Map()

function buildOption(chart) {
  const series = chart.series || []
  const isPie = series[0]?.type === 'pie'
  if (isPie) {
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{
        type: 'pie', radius: ['38%', '66%'], center: ['50%', '46%'],
        data: series[0].data || [],
        label: { formatter: '{b}: {c} ({d}%)' },
      }],
      color: ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9b59b6', '#1abc9c'],
    }
  }
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, type: 'scroll' },
    grid: { left: 48, right: 24, top: 28, bottom: 48 },
    xAxis: { type: 'category', data: chart.x_labels || [], axisLabel: { rotate: charts.length > 1 ? 0 : 0 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: series.map((s) => ({
      name: s.name, type: s.type === 'line' ? 'line' : 'bar',
      data: s.data || [],
      smooth: true,
      barMaxWidth: 36,
      areaStyle: s.area ? { opacity: 0.15 } : undefined,
      itemStyle: s.type === 'bar' ? { borderRadius: [4, 4, 0, 0] } : undefined,
    })),
    color: ['#409eff', '#67c23a'],
  }
}

function renderCharts() {
  charts.value.forEach((chart) => {
    const el = document.getElementById(`chart-${chart.key}`)
    if (!el) return
    let inst = chartInstances.get(chart.key)
    if (!inst) {
      inst = echarts.init(el)
      chartInstances.set(chart.key, inst)
    }
    inst.setOption(buildOption(chart), true)
    inst.resize()
  })
}

function disposeCharts() {
  chartInstances.forEach((inst) => inst.dispose())
  chartInstances.clear()
}

function onResize() {
  chartInstances.forEach((inst) => inst.resize())
}
window.addEventListener('resize', onResize)

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<style scoped>
.analytics-page {
  padding: 0;
}
.page-header {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}
.subtitle {
  font-size: 12px;
  color: #909399;
  font-weight: 400;
  margin-left: 10px;
}
.ask-bar {
  display: flex;
  gap: 10px;
  margin: 16px 0 10px;
}
.quick-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.quick-tag {
  cursor: pointer;
}
.quick-tag:hover {
  color: #409eff;
  border-color: #409eff;
}
.process-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #909399;
}
.step-icon {
  margin-left: 10px;
}
.step-icon.done {
  color: #67c23a;
}
.step.active {
  color: #409eff;
  font-weight: 600;
}
.step.done {
  color: #67c23a;
}
.plan-tag {
  margin-left: 4px;
}
.fact-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.fact-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}
.fact-value {
  font-size: 22px;
  font-weight: 700;
  color: #409eff;
}
.fact-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.summary-card {
  background: linear-gradient(135deg, #ecf5ff, #f0f9eb);
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
.summary-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.summary-body {
  font-size: 13px;
  line-height: 1.9;
  color: #606266;
  white-space: pre-line;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 16px;
}
.chart-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
}
.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}
.chart-range {
  font-size: 12px;
  color: #909399;
  font-weight: 400;
  margin-left: 10px;
}
.chart-canvas {
  width: 100%;
  height: 300px;
}
</style>
