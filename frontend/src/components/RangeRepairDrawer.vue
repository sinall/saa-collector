<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchIntegrityReportSummary,
  generatePlanByRange,
  type IntegrityReportSummary,
} from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps<{
  visible: boolean
  reportId: number
  reportFrequency: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'plan-created': [planId: number]
}>()

const router = useRouter()

const summaryData = ref<IntegrityReportSummary | null>(null)
const summaryLoading = ref(false)
const generating = ref(false)

const selectedDataTypes = ref<string[]>([])
const checkedPeriodKeys = ref<string[]>([])
const stockScope = ref<'ALL' | 'SELECTED'>('ALL')
const selectedStocks = ref<string[]>([])
const stockSearchInput = ref('')

const periodTreeRef = ref<any>(null)

interface PeriodTreeNode {
  id: string
  label: string
  count: number
  children?: PeriodTreeNode[]
}

const periodTreeData = computed<PeriodTreeNode[]>(() => {
  if (!summaryData.value?.by_period) return []
  return buildPeriodTree(summaryData.value.by_period)
})

const dataTypeOptions = computed(() => {
  if (!summaryData.value?.by_data_type) return []
  return summaryData.value.by_data_type.map(item => ({
    value: item.data_type,
    label: item.label,
    count: item.missing_count,
    stockCount: item.stock_count,
  }))
})

const estimatedCount = computed(() => {
  const months = expandCheckedToMonths(checkedPeriodKeys.value)
  let total = 0

  for (const year of summaryData.value?.by_period || []) {
    for (const quarter of year.quarters) {
      for (const month of quarter.months) {
        const monthKey = `${year.year}-${String(month.month).padStart(2, '0')}`
        if (months.includes(monthKey)) {
          total += month.missing_count
        }
      }
    }
  }

  if (selectedDataTypes.value.length > 0) {
    const selectedCount = selectedDataTypes.value.reduce((sum, dt) => {
      const item = summaryData.value?.by_data_type.find(d => d.data_type === dt)
      return sum + (item?.missing_count || 0)
    }, 0)
    const totalCount = summaryData.value?.total_missing || 1
    const ratio = totalCount > 0 ? selectedCount / totalCount : 0
    total = Math.round(total * ratio)
  }

  return total
})

const estimatedJobs = computed(() => {
  return selectedDataTypes.value.length
})

const canGenerate = computed(() => {
  return selectedDataTypes.value.length > 0 && checkedPeriodKeys.value.length > 0
})

function buildPeriodTree(byPeriod: IntegrityReportSummary['by_period']): PeriodTreeNode[] {
  return byPeriod.map(year => ({
    id: `${year.year}`,
    label: `${year.year}年`,
    count: year.missing_count,
    children: year.quarters.map(q => ({
      id: `${year.year}-Q${q.quarter}`,
      label: `Q${q.quarter}`,
      count: q.missing_count,
      children: q.months.map(m => ({
        id: `${year.year}-${String(m.month).padStart(2, '0')}`,
        label: `${m.month}月`,
        count: m.missing_count,
      })),
    })),
  }))
}

function expandCheckedToMonths(checkedKeys: string[]): string[] {
  const months = new Set<string>()

  for (const key of checkedKeys) {
    if (/^\d{4}$/.test(key)) {
      for (let m = 1; m <= 12; m++) {
        months.add(`${key}-${String(m).padStart(2, '0')}`)
      }
    } else if (/^\d{4}-Q\d$/.test(key)) {
      const year = key.slice(0, 4)
      const q = parseInt(key.slice(6))
      const startMonth = (q - 1) * 3 + 1
      for (let m = startMonth; m < startMonth + 3; m++) {
        months.add(`${year}-${String(m).padStart(2, '0')}`)
      }
    } else if (/^\d{4}-\d{2}$/.test(key)) {
      months.add(key)
    }
  }

  return Array.from(months).sort()
}

async function loadSummary() {
  if (!props.reportId) return

  summaryLoading.value = true
  try {
    const params: any = {}
    if (selectedDataTypes.value.length > 0) {
      params.data_types = selectedDataTypes.value.join(',')
    }
    if (stockScope.value === 'SELECTED' && selectedStocks.value.length > 0) {
      params.stock_codes = selectedStocks.value.join(',')
    }

    const response = await fetchIntegrityReportSummary(props.reportId, params)
    if (response.success && response.data) {
      summaryData.value = response.data
    } else {
      ElMessage.error(response.error || '加载统计数据失败')
    }
  } catch (error) {
    console.error('Failed to load summary:', error)
    ElMessage.error('加载统计数据失败')
  } finally {
    summaryLoading.value = false
  }
}

function handleDataTypeChange() {
  loadSummary()
}

function handleStockScopeChange() {
  if (stockScope.value === 'ALL') {
    selectedStocks.value = []
  }
  loadSummary()
}

function handleTreeCheck(_data: any, { checkedKeys }: { checkedKeys: string[] }) {
  checkedPeriodKeys.value = checkedKeys
}

function addStock() {
  const code = stockSearchInput.value.trim().toUpperCase()
  if (code && !selectedStocks.value.includes(code)) {
    selectedStocks.value.push(code)
    stockSearchInput.value = ''
    loadSummary()
  }
}

function removeStock(code: string) {
  const index = selectedStocks.value.indexOf(code)
  if (index > -1) {
    selectedStocks.value.splice(index, 1)
    loadSummary()
  }
}

function selectAllDataTypes() {
  selectedDataTypes.value = dataTypeOptions.value.map(dt => dt.value)
  loadSummary()
}

function invertDataTypes() {
  const allTypes = dataTypeOptions.value.map(dt => dt.value)
  selectedDataTypes.value = allTypes.filter(dt => !selectedDataTypes.value.includes(dt))
  loadSummary()
}

async function handleGenerate() {
  if (!canGenerate.value) {
    ElMessage.warning('请至少选择一个数据类型和时间范围')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定生成采集计划？预估影响 ${estimatedCount.value} 条缺失项，将创建 ${estimatedJobs.value} 个采集任务。`,
      '确认生成',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info',
      }
    )

    generating.value = true

    const periods = expandCheckedToMonths(checkedPeriodKeys.value)

    const response = await generatePlanByRange(props.reportId, {
      data_types: selectedDataTypes.value,
      periods,
      stock_scope: stockScope.value,
      stock_codes: stockScope.value === 'SELECTED' ? selectedStocks.value : undefined,
    })

    if (response.success && response.data) {
      ElMessage.success('采集计划已生成')
      emit('update:visible', false)
      emit('plan-created', response.data.id)
      router.push(`/collect-plans/${response.data.id}/edit`)
    } else {
      ElMessage.error(response.error || '生成失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to generate plan:', error)
      ElMessage.error('生成失败')
    }
  } finally {
    generating.value = false
  }
}

function handleClose() {
  emit('update:visible', false)
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadSummary()
  }
})

onMounted(() => {
  if (props.visible) {
    loadSummary()
  }
})
</script>

<template>
  <el-drawer
    :model-value="visible"
    @update:model-value="emit('update:visible', $event)"
    title="按范围生成采集计划"
    direction="rtl"
    size="480px"
    :close-on-click-modal="false"
  >
    <div class="drawer-content" v-loading="summaryLoading">
      <section class="section">
        <div class="section-header">
          <h3>数据类型</h3>
          <div class="header-actions">
            <el-button size="small" text @click="selectAllDataTypes">全选</el-button>
            <el-button size="small" text @click="invertDataTypes">反选</el-button>
          </div>
        </div>
        <div class="data-type-grid">
          <el-checkbox
            v-for="dt in dataTypeOptions"
            :key="dt.value"
            v-model="selectedDataTypes"
            :label="dt.value"
            @change="handleDataTypeChange"
          >
            <span class="data-type-label">
              {{ dt.label }}
              <span class="count">({{ dt.count.toLocaleString() }})</span>
            </span>
          </el-checkbox>
        </div>
      </section>

      <section class="section">
        <div class="section-header">
          <h3>时间范围</h3>
          <span class="hint">勾选年份/季度/月份</span>
        </div>
        <div class="period-tree-container">
          <el-tree
            ref="periodTreeRef"
            :data="periodTreeData"
            show-checkbox
            node-key="id"
            :default-expand-all="false"
            :expand-on-click-node="false"
            :check-on-click-node="true"
            :checked-keys="checkedPeriodKeys"
            @check="handleTreeCheck"
            :props="{
              label: 'label',
              children: 'children',
            }"
          >
            <template #default="{ node, data }">
              <span class="tree-node">
                <span class="node-label">{{ data.label }}</span>
                <span class="node-count">({{ data.count.toLocaleString() }})</span>
              </span>
            </template>
          </el-tree>
        </div>
      </section>

      <section class="section">
        <div class="section-header">
          <h3>股票范围</h3>
        </div>
        <el-radio-group v-model="stockScope" @change="handleStockScopeChange">
          <el-radio value="ALL">
            全部有缺失的股票
            <span v-if="summaryData" class="count">
              ({{ summaryData.total_stocks }}只)
            </span>
          </el-radio>
          <el-radio value="SELECTED">指定股票</el-radio>
        </el-radio-group>

        <div v-if="stockScope === 'SELECTED'" class="stock-input-area">
          <div class="stock-input-row">
            <el-input
              v-model="stockSearchInput"
              placeholder="输入股票代码后回车添加"
              @keyup.enter="addStock"
              style="flex: 1"
            />
            <el-button @click="addStock">添加</el-button>
          </div>
          <div class="selected-stocks">
            <el-tag
              v-for="code in selectedStocks"
              :key="code"
              closable
              @close="removeStock(code)"
              style="margin: 2px"
            >
              {{ code }}
            </el-tag>
            <span v-if="selectedStocks.length === 0" class="empty-hint">
              未添加股票
            </span>
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <div class="estimate-info">
          预估：约 <strong>{{ estimatedCount.toLocaleString() }}</strong> 条缺失项
          <template v-if="estimatedJobs > 0">
            → <strong>{{ estimatedJobs }}</strong> 个采集任务
          </template>
        </div>
        <div class="footer-actions">
          <el-button @click="handleClose">取消</el-button>
          <el-button
            type="primary"
            @click="handleGenerate"
            :disabled="!canGenerate"
            :loading="generating"
          >
            生成采集计划
          </el-button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.drawer-content {
  padding: 0 16px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.hint {
  font-size: 12px;
  color: #909399;
}

.count {
  font-size: 12px;
  color: #909399;
}

.data-type-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.data-type-label {
  display: flex;
  align-items: center;
  gap: 4px;
}

.data-type-label .count {
  color: #909399;
  font-size: 12px;
}

.period-tree-container {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 8px;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 4px;
}

.node-label {
  font-size: 13px;
}

.node-count {
  font-size: 11px;
  color: #909399;
}

.stock-input-area {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stock-input-row {
  display: flex;
  gap: 8px;
}

.selected-stocks {
  min-height: 32px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

.empty-hint {
  font-size: 12px;
  color: #909399;
}

.drawer-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
  border-top: 1px solid #e4e7ed;
}

.estimate-info {
  font-size: 13px;
  color: #606266;
}

.estimate-info strong {
  color: #409eff;
}

.footer-actions {
  display: flex;
  gap: 12px;
}

:deep(.el-tree-node__content) {
  height: 28px;
}

:deep(.el-checkbox__label) {
  font-size: 13px;
}
</style>
