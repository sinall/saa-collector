<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useDataTypes, isDataTypeVisible } from '@/composables/useDataTypes'
import {
  fetchCompletenessHeatmapScopes,
  fetchCompletenessHeatmapScopeSymbols,
  type HeatmapScopeOption
} from '@/utils/api'

interface FilterParams {
  data_types: string[]
  frequency: string
  symbols: string[]
  stock_scope_key: string
  stock_scope_label: string
  start_date?: string
  end_date?: string
}

type StockScopeOption = HeatmapScopeOption | {
  key: 'manual'
  label: string
  type: 'manual'
}

const props = withDefaults(defineProps<{
  queryButtonText?: string
  loading?: boolean
}>(), {
  queryButtonText: '生成报告',
  loading: false
})

const emit = defineEmits<{
  query: [params: FilterParams]
}>()

const { dataTypes, loadDataTypes } = useDataTypes()
const reportDataTypes = computed(() => dataTypes.value.filter(dt => isDataTypeVisible(dt, 'integrity_report')))

const panelCollapsed = ref(false)
const frequencyExpanded = ref(true)
const stockExpanded = ref(true)
const dateExpanded = ref(true)
const resolvingScope = ref(false)

const frequencies = [
  { value: 'daily', label: '日度' },
  { value: 'weekly', label: '周度' },
  { value: 'monthly', label: '月度' },
  { value: 'quarterly', label: '季度' },
  { value: 'yearly', label: '年度' },
]

const selectedDataTypes = ref<string[]>(['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow'])
const selectedFrequency = ref('monthly')
const selectedStockScope = ref('all')
const scopeOptions = ref<HeatmapScopeOption[]>([
  { key: 'all', label: '全市场', type: 'all' }
])
const manualStocks = ref('')
const startDate = ref('2009-01-01')
const endDate = ref(new Date().toISOString().split('T')[0])

const today = new Date().toISOString().split('T')[0]

const selectedStocks = computed(() => {
  if (selectedStockScope.value !== 'manual') {
    return []
  }
  return manualStocks.value
    .split(/[,\s\n]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0)
})

const stockScopeOptions = computed<StockScopeOption[]>(() => [
  ...scopeOptions.value,
  { key: 'manual', label: '指定股票', type: 'manual' },
])

const selectedScopeOption = computed(() => {
  return stockScopeOptions.value.find(scope => scope.key === selectedStockScope.value)
})

const selectedScopeSummary = computed(() => {
  if (selectedStockScope.value === 'manual') {
    return selectedStocks.value.length > 0 ? `已选 ${selectedStocks.value.length} 只` : '请输入股票代码'
  }

  const option = selectedScopeOption.value
  if (!option || option.type !== 'index') {
    return '全市场'
  }

  const count = option.constituent_count ?? 0
  const dateText = option.latest_date ? `，${option.latest_date}` : ''
  return `${count} 只成分股${dateText}`
})

const toggleDataType = (type: string) => {
  const idx = selectedDataTypes.value.indexOf(type)
  if (idx === -1) {
    selectedDataTypes.value.push(type)
  } else {
    selectedDataTypes.value.splice(idx, 1)
  }
}

const selectAllDataTypes = () => {
  selectedDataTypes.value = reportDataTypes.value.map(dt => dt.key)
}

const clearDataTypes = () => {
  selectedDataTypes.value = []
}

const loadStockScopes = async () => {
  try {
    const response = await fetchCompletenessHeatmapScopes()
    if (response.success && response.data && response.data.length > 0) {
      scopeOptions.value = response.data
      if (!stockScopeOptions.value.some(scope => scope.key === selectedStockScope.value)) {
        selectedStockScope.value = 'all'
      }
    }
  } catch (error) {
    console.error('Failed to load stock scopes:', error)
  }
}

const resolveSymbolsForSelectedScope = async (): Promise<string[]> => {
  if (selectedStockScope.value === 'manual') {
    return [...selectedStocks.value]
  }
  if (selectedStockScope.value === 'all') {
    return []
  }

  resolvingScope.value = true
  try {
    const response = await fetchCompletenessHeatmapScopeSymbols(selectedStockScope.value)
    if (response.success && response.data) {
      return response.data.symbols
    }
    throw new Error(response.error || 'Failed to resolve stock scope')
  } finally {
    resolvingScope.value = false
  }
}

const handleQuery = async () => {
  let symbols: string[]
  try {
    symbols = await resolveSymbolsForSelectedScope()
  } catch (error) {
    console.error('Failed to resolve stock scope:', error)
    ElMessage.error('股票范围解析失败')
    return
  }

  const params: FilterParams = {
    data_types: [...selectedDataTypes.value],
    frequency: selectedFrequency.value,
    symbols,
    stock_scope_key: selectedStockScope.value,
    stock_scope_label: selectedScopeOption.value?.label || '全市场',
  }

  if (startDate.value) {
    params.start_date = startDate.value
  }
  if (endDate.value) {
    params.end_date = endDate.value
  }

  emit('query', params)
}

onMounted(() => {
  loadDataTypes()
  loadStockScopes()
})
</script>

<template>
  <aside class="filter-panel" :class="{ collapsed: panelCollapsed }">
    <div class="panel-header">
      <span v-if="!panelCollapsed" class="panel-title">报告条件</span>
      <button class="collapse-btn" @click="panelCollapsed = !panelCollapsed">
        {{ panelCollapsed ? '▶' : '◀' }}
      </button>
    </div>

    <div v-if="!panelCollapsed" class="panel-content">
      <section class="filter-section">
        <h4 class="section-title">数据类型</h4>
        <div class="checkbox-grid">
          <label
            v-for="dt in reportDataTypes"
            :key="dt.key"
            class="checkbox-item"
          >
            <input
              type="checkbox"
              :checked="selectedDataTypes.includes(dt.key)"
              @change="toggleDataType(dt.key)"
            />
            <span>{{ dt.label }}</span>
          </label>
        </div>
        <div class="tag-actions">
          <span class="selection-count">已选 {{ selectedDataTypes.length }} 种</span>
          <button class="quick-btn" @click="selectAllDataTypes">全选</button>
          <button class="quick-btn" @click="clearDataTypes">清空</button>
        </div>
      </section>

      <section class="filter-section">
        <h4 class="section-title">频度</h4>
        <select v-model="selectedFrequency" class="frequency-select">
          <option v-for="f in frequencies" :key="f.value" :value="f.value">
            {{ f.label }}
          </option>
        </select>
      </section>

      <section class="filter-section">
        <div class="section-header" @click="stockExpanded = !stockExpanded">
          <h4>股票选择</h4>
          <span class="toggle-icon">{{ stockExpanded ? '▼' : '▶' }}</span>
        </div>
        <div v-if="stockExpanded" class="section-content">
          <select v-model="selectedStockScope" class="scope-select">
            <option v-for="scope in stockScopeOptions" :key="scope.key" :value="scope.key">
              {{ scope.label }}
            </option>
          </select>
          <div class="selection-count">{{ selectedScopeSummary }}</div>

          <template v-if="selectedStockScope === 'manual'">
            <textarea
              v-model="manualStocks"
              placeholder="例如: 000001, 600000&#10;每行一个或逗号分隔"
              rows="3"
            />
          </template>
        </div>
      </section>

      <section class="filter-section">
        <div class="section-header" @click="dateExpanded = !dateExpanded">
          <h4>时间范围</h4>
          <span class="toggle-icon">{{ dateExpanded ? '▼' : '▶' }}</span>
        </div>
        <div v-if="dateExpanded" class="section-content">
          <div class="date-range">
            <input type="date" v-model="startDate" :max="today" />
            <span>至</span>
            <input type="date" v-model="endDate" :max="today" :min="startDate" />
          </div>
        </div>
      </section>

      <div class="query-section">
        <button
          @click="handleQuery"
          class="query-btn"
          :disabled="loading || resolvingScope || selectedDataTypes.length === 0"
        >
          {{ loading || resolvingScope ? '生成中...' : queryButtonText }}
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.filter-panel {
  width: 280px;
  min-width: 280px;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
}

.filter-panel.collapsed {
  width: 40px;
  min-width: 40px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #f5f5f5;
  border-bottom: 1px solid #e0e0e0;
}

.panel-title {
  font-weight: 600;
  color: #333;
}

.collapse-btn {
  background: none;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 0.25rem 0.5rem;
  cursor: pointer;
  font-size: 0.8rem;
  min-width: 28px;
}

.filter-panel.collapsed .panel-title {
  display: none;
}

.filter-panel.collapsed .panel-header {
  justify-content: center;
  padding: 0.5rem;
}

.filter-panel.collapsed .collapse-btn {
  width: 28px;
  padding: 0.25rem;
}

.panel-content {
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.filter-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.section-title {
  margin: 0;
  font-size: 0.9rem;
  color: #333;
  padding: 0.5rem 0;
  border-bottom: 1px solid #eee;
}

.checkbox-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.25rem 0.5rem;
  padding-top: 0.25rem;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.25rem;
  cursor: pointer;
  font-size: 0.8rem;
  border-radius: 3px;
  transition: background 0.15s;
}

.checkbox-item:hover {
  background: #f5f7fa;
}

.checkbox-item input[type="checkbox"] {
  margin: 0;
  cursor: pointer;
}

.checkbox-item span {
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.tag-actions .selection-count {
  flex: 1;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 0.5rem 0;
  border-bottom: 1px solid #eee;
  user-select: none;
}

.section-header:hover {
  background: #f9f9f9;
}

.section-header h4 {
  margin: 0;
  font-size: 0.9rem;
  color: #333;
}

.toggle-icon {
  font-size: 0.75rem;
  color: #888;
}

.section-content {
  padding-top: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.radio-group {
  display: flex;
  gap: 0.75rem;
  font-size: 0.85rem;
}

.radio-group label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  cursor: pointer;
}

input[type="text"],
input[type="date"],
select,
textarea {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.85rem;
  width: 100%;
}

textarea {
  resize: vertical;
  font-family: monospace;
}

.date-range {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.date-range input {
  flex: 1;
}

.date-range span {
  font-size: 0.8rem;
  color: #666;
}

.selection-count {
  font-size: 0.75rem;
  color: #888;
}

.quick-btn {
  padding: 0.15rem 0.4rem;
  font-size: 0.7rem;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 3px;
  cursor: pointer;
}

.quick-btn:hover {
  background: #e8e8e8;
}

.query-section {
  padding-top: 1rem;
  border-top: 1px solid #eee;
}

.query-btn {
  width: 100%;
  padding: 0.75rem;
  background: #409eff;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.2s;
}

.query-btn:hover:not(:disabled) {
  background: #337ecc;
}

.query-btn:disabled {
  background: #a0cfff;
  cursor: not-allowed;
}
</style>
