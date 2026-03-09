<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface FilterParams {
  data_type: string
  symbols: string[]
  start_date?: string
  end_date?: string
  dates?: string[]
  report_types?: string[]
  stock_list_code?: string
}

const props = withDefaults(defineProps<{
  queryButtonText?: string
  loading?: boolean
  showReportTypes?: boolean
  showDateRange?: boolean
}>(), {
  queryButtonText: '查询',
  loading: false,
  showReportTypes: false,
  showDateRange: true
})

const emit = defineEmits<{
  query: [params: FilterParams]
}>()

const panelCollapsed = ref(false)
const stockExpanded = ref(true)
const dateExpanded = ref(true)
const dataTypeExpanded = ref(true)

const dataTypes = [
  { value: 'stock_info', label: '股票基本信息', needDate: false },
  { value: 'quote', label: '最新行情', needDate: false },
  { value: 'historical_quote', label: '历史行情', needDate: true },
  { value: 'balance_sheet', label: '资产负债表', needDate: true },
  { value: 'income', label: '利润表', needDate: true },
  { value: 'cash_flow', label: '现金流量表', needDate: true },
  { value: 'dividend', label: '分红数据', needDate: true },
  { value: 'capital', label: '股本变动', needDate: true },
  { value: 'valuation', label: '估值数据', needDate: false },
  { value: 'main_business', label: '主营业务', needDate: true },
]

const stockMode = ref<'manual' | 'index'>('manual')
const dateMode = ref<'single' | 'range'>('range')
const selectedDataType = ref('stock_info')
const manualStocks = ref('')
const selectedList = ref('')
const singleDate = ref('')
const startDate = ref('')
const endDate = ref('')
const selectedReportTypes = ref<string[]>(['balance_sheet', 'income', 'cash_flow'])

const reportTypeOptions = [
  { value: 'balance_sheet', label: '资产负债表' },
  { value: 'income', label: '利润表' },
  { value: 'cash_flow', label: '现金流量表' },
  { value: 'dividend', label: '分红数据' },
]

const indexOptions = [
  { value: '000300', label: '沪深300' },
  { value: '000905', label: '中证500' },
  { value: '000852', label: '中证1000' },
  { value: '000016', label: '上证50' },
  { value: '399006', label: '创业板指' },
]

const today = new Date().toISOString().split('T')[0]

const selectedStocks = computed(() => {
  if (stockMode.value === 'index') {
    return []
  }
  return manualStocks.value
    .split(/[,\s\n]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0)
})

const currentDataType = computed(() => {
  return dataTypes.find(dt => dt.value === selectedDataType.value)
})

const needDateRange = computed(() => {
  return props.showDateRange
})

const isStatementType = computed(() => {
  return ['balance_sheet', 'income', 'cash_flow', 'dividend'].includes(selectedDataType.value)
})

watch(selectedDataType, () => {
  if (!needDateRange.value) {
    singleDate.value = ''
    startDate.value = ''
    endDate.value = ''
  }
})

watch(dateMode, () => {
  singleDate.value = ''
  startDate.value = ''
  endDate.value = ''
})

const handleQuery = () => {
  const params: FilterParams = {
    data_type: selectedDataType.value,
    symbols: [...selectedStocks.value],
    report_types: isStatementType.value && props.showReportTypes ? [...selectedReportTypes.value] : undefined,
  }
  
  if (needDateRange.value) {
    if (dateMode.value === 'single') {
      params.start_date = singleDate.value
      params.end_date = singleDate.value
    } else {
      params.start_date = startDate.value
      params.end_date = endDate.value
    }
  }
  
  if (stockMode.value === 'index' && selectedList.value) {
    params.stock_list_code = selectedList.value
  }
  
  emit('query', params)
}

const toggleReportType = (type: string) => {
  const idx = selectedReportTypes.value.indexOf(type)
  if (idx === -1) {
    selectedReportTypes.value.push(type)
  } else {
    selectedReportTypes.value.splice(idx, 1)
  }
}

defineExpose({
  selectedDataType,
  selectedStocks,
  startDate,
  endDate,
  singleDate,
  selectedReportTypes,
  stockMode,
  selectedList,
  dateMode
})
</script>

<template>
  <aside class="filter-panel" :class="{ collapsed: panelCollapsed }">
    <div class="panel-header">
      <span v-if="!panelCollapsed" class="panel-title">筛选条件</span>
      <button class="collapse-btn" @click="panelCollapsed = !panelCollapsed">
        {{ panelCollapsed ? '▶' : '◀' }}
      </button>
    </div>

    <div v-if="!panelCollapsed" class="panel-content">
      <section class="filter-section">
        <div class="section-header" @click="dataTypeExpanded = !dataTypeExpanded">
          <h4>数据类型</h4>
          <span class="toggle-icon">{{ dataTypeExpanded ? '▼' : '▶' }}</span>
        </div>
        <div v-if="dataTypeExpanded" class="section-content">
          <select v-model="selectedDataType">
            <option v-for="dt in dataTypes" :key="dt.value" :value="dt.value">
              {{ dt.label }}
            </option>
          </select>
        </div>
      </section>

      <section class="filter-section">
        <div class="section-header" @click="stockExpanded = !stockExpanded">
          <h4>股票选择</h4>
          <span class="toggle-icon">{{ stockExpanded ? '▼' : '▶' }}</span>
        </div>
        <div v-if="stockExpanded" class="section-content">
          <div class="radio-group">
            <label>
              <input type="radio" value="manual" v-model="stockMode" />
              指定股票
            </label>
            <label class="disabled-label" title="功能开发中">
              <input type="radio" value="index" v-model="stockMode" disabled />
              指数成分股
            </label>
          </div>
          
          <template v-if="stockMode === 'manual'">
            <textarea
              v-model="manualStocks"
              placeholder="例如: 000001, 600000&#10;留空采集全部"
              rows="3"
            />
            <div class="selection-count">
              {{ selectedStocks.length > 0 ? `已选 ${selectedStocks.length} 只` : '全部股票' }}
            </div>
          </template>
          
          <template v-else>
            <select v-model="selectedList" disabled class="disabled-select">
              <option value="">选择指数...</option>
              <option v-for="idx in indexOptions" :key="idx.value" :value="idx.value">
                {{ idx.label }} ({{ idx.value }})
              </option>
            </select>
            <div class="coming-soon">指数成分股功能开发中...</div>
          </template>
        </div>
      </section>

      <section v-if="needDateRange" class="filter-section">
        <div class="section-header" @click="dateExpanded = !dateExpanded">
          <h4>时间选择</h4>
          <span class="toggle-icon">{{ dateExpanded ? '▼' : '▶' }}</span>
        </div>
        <div v-if="dateExpanded" class="section-content">
          <div class="radio-group">
            <label>
              <input type="radio" value="single" v-model="dateMode" />
              固定日期
            </label>
            <label>
              <input type="radio" value="range" v-model="dateMode" />
              日期范围
            </label>
          </div>
          
          <template v-if="dateMode === 'single'">
            <input type="date" v-model="singleDate" :max="today" />
          </template>
          <template v-else>
            <div class="date-range">
              <input type="date" v-model="startDate" :max="today" />
              <span>至</span>
              <input type="date" v-model="endDate" :max="today" :min="startDate" />
            </div>
          </template>
        </div>
      </section>

      <section v-if="isStatementType && showReportTypes" class="filter-section">
        <div class="section-header">
          <h4>报表类型</h4>
        </div>
        <div class="section-content">
          <label 
            v-for="opt in reportTypeOptions" 
            :key="opt.value"
            class="checkbox-item"
          >
            <input 
              type="checkbox" 
              :checked="selectedReportTypes.includes(opt.value)"
              @change="toggleReportType(opt.value)"
            />
            <span>{{ opt.label }}</span>
          </label>
        </div>
      </section>

      <slot name="extra-filters"></slot>

      <div class="query-section">
        <button 
          @click="handleQuery"
          class="query-btn"
          :disabled="loading"
        >
          {{ loading ? '处理中...' : queryButtonText }}
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

.disabled-label {
  color: #999;
  cursor: not-allowed !important;
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

.disabled-select {
  background: #f5f5f5;
  color: #999;
  cursor: not-allowed;
}

.coming-soon {
  font-size: 0.75rem;
  color: #999;
  font-style: italic;
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

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0;
  cursor: pointer;
  font-size: 0.85rem;
}

.checkbox-item:hover {
  background: #f9f9f9;
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
