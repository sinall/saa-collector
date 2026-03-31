<script setup lang="ts">
import { ref, computed } from 'vue'

interface FilterParams {
  data_types: string[]
  frequency: string
  symbols: string[]
  start_date?: string
  end_date?: string
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

const panelCollapsed = ref(false)
const frequencyExpanded = ref(true)
const stockExpanded = ref(true)
const dateExpanded = ref(true)

const dataTypes = [
  { value: 'trade_days', label: '交易日' },
  { value: 'quote', label: '最新行情' },
  { value: 'historical_quote', label: '历史行情' },
  { value: 'balance_sheet', label: '资产负债表' },
  { value: 'income', label: '利润表' },
  { value: 'cash_flow', label: '现金流量表' },
  { value: 'dividend', label: '分红数据' },
  { value: 'capital', label: '股本变动' },
  { value: 'valuation_board', label: '板块估值' },
  { value: 'valuation_industry', label: '行业估值' },
  { value: 'main_business', label: '主营业务' },
]

const frequencies = [
  { value: 'daily', label: '日度' },
  { value: 'weekly', label: '周度' },
  { value: 'monthly', label: '月度' },
  { value: 'quarterly', label: '季度' },
  { value: 'yearly', label: '年度' },
]

const selectedDataTypes = ref<string[]>(['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow'])
const selectedFrequency = ref('monthly')
const stockMode = ref<'all' | 'manual'>('all')
const manualStocks = ref('')
const startDate = ref('2009-01-01')
const endDate = ref(new Date().toISOString().split('T')[0])

const today = new Date().toISOString().split('T')[0]

const selectedStocks = computed(() => {
  if (stockMode.value === 'all') {
    return []
  }
  return manualStocks.value
    .split(/[,\s\n]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0)
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
  selectedDataTypes.value = dataTypes.map(dt => dt.value)
}

const clearDataTypes = () => {
  selectedDataTypes.value = []
}

const handleQuery = () => {
  const params: FilterParams = {
    data_types: [...selectedDataTypes.value],
    frequency: selectedFrequency.value,
    symbols: stockMode.value === 'manual' ? [...selectedStocks.value] : [],
  }

  if (startDate.value) {
    params.start_date = startDate.value
  }
  if (endDate.value) {
    params.end_date = endDate.value
  }

  emit('query', params)
}
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
            v-for="dt in dataTypes"
            :key="dt.value"
            class="checkbox-item"
          >
            <input
              type="checkbox"
              :checked="selectedDataTypes.includes(dt.value)"
              @change="toggleDataType(dt.value)"
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
          <div class="radio-group">
            <label>
              <input type="radio" value="all" v-model="stockMode" />
              全部股票
            </label>
            <label>
              <input type="radio" value="manual" v-model="stockMode" />
              指定股票
            </label>
          </div>

          <template v-if="stockMode === 'manual'">
            <textarea
              v-model="manualStocks"
              placeholder="例如: 000001, 600000&#10;每行一个或逗号分隔"
              rows="3"
            />
            <div class="selection-count">
              {{ selectedStocks.length > 0 ? `已选 ${selectedStocks.length} 只` : '请输入股票代码' }}
            </div>
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
          :disabled="loading || selectedDataTypes.length === 0"
        >
          {{ loading ? '生成中...' : queryButtonText }}
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
