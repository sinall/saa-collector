<template>
  <div class="data-browse-stock">
    <div class="page-header">
      <h3>{{ pageTitle }}</h3>
    </div>
    <el-row :gutter="20" class="content-row">
      <el-col :span="4">
        <el-card class="menu-card">
          <el-menu
            :default-active="activeDataType"
            @select="onDataTypeSelect"
            class="data-type-menu"
          >
            <template v-for="group in dataTypeGroups" :key="group.key">
              <el-sub-menu :index="group.key">
                <template #title>{{ group.label }}</template>
                <el-menu-item
                  v-for="item in group.items"
                  :key="item.key"
                  :index="item.key"
                >
                  {{ item.label }}
                </el-menu-item>
              </el-sub-menu>
            </template>
          </el-menu>
        </el-card>
      </el-col>
      
      <el-col :span="20">
        <el-card class="data-card">
          <div class="table-header">
            <span class="table-title">{{ currentTableLabel }}</span>
            <el-button @click="showColumnSettings = true" link>
              <el-icon><Setting /></el-icon>
              列设置
            </el-button>
          </div>
          
          <el-descriptions
            v-if="selectedStock && isBasicInfo"
            :column="2"
            border
            v-loading="dataLoading"
          >
            <el-descriptions-item
              v-for="col in visibleColumns"
              :key="col.name"
              :label="col.label"
              :span="col.width && col.width > 150 ? 2 : 1"
            >
              {{ formatValue(tableData[0]?.[col.name], col.format) }}
            </el-descriptions-item>
          </el-descriptions>

          <el-table
            v-else-if="selectedStock && !isBasicInfo"
            :data="tableData"
            stripe
            v-loading="dataLoading"
            max-height="500"
            border
          >
            <el-table-column
              v-for="col in visibleColumns"
              :key="col.name"
              :prop="col.name"
              :label="col.label"
              :width="col.width"
              :fixed="col.fixed ? 'left' : undefined"
              :align="isNumericFormat(col.format) ? 'right' : 'left'"
            >
              <template #default="{ row }">
                {{ formatValue(row[col.name], col.format) }}
              </template>
            </el-table-column>
          </el-table>
          
          <div v-if="selectedStock && !isBasicInfo && totalRecords > 0" class="pagination-container">
            <el-pagination
              v-model:current-page="currentPage"
              v-model:page-size="pageSize"
              :page-sizes="[20, 50, 100, 200]"
              :total="totalRecords"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="onPageSizeChange"
              @current-change="onPageChange"
            />
          </div>

          <el-empty v-else description="请搜索并选择一只股票" />
        </el-card>
      </el-col>
    </el-row>
    
    <el-dialog v-model="showColumnSettings" title="列设置" width="500px">
      <div class="column-settings">
        <div class="settings-header">
          <el-checkbox
            v-model="selectAllColumns"
            :indeterminate="isIndeterminate"
            @change="onSelectAllChange"
          >
            全选
          </el-checkbox>
          <el-button type="primary" link @click="resetColumnSettings">恢复默认</el-button>
        </div>
        
        <el-divider />
        
        <div class="column-list">
          <div
            v-for="col in allColumns"
            :key="col.name"
            class="column-item"
          >
            <el-checkbox
              v-model="col.visible"
              :disabled="col.fixed"
              @change="onColumnVisibilityChange"
            >
              {{ col.label }}
            </el-checkbox>
            <span v-if="col.fixed" class="fixed-tag">(固定)</span>
          </div>
        </div>
      </div>
      
      <template #footer>
        <el-button @click="showColumnSettings = false">取消</el-button>
        <el-button type="primary" @click="saveColumnSettings">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import {
  fetchDisplayConfig,
  saveDisplayConfig,
  fetchStockData,
  fetchStocks,
  type DataTypeGroup,
  type DisplayFieldConfig,
  type Stock,
} from '@/utils/api'

const router = useRouter()

const props = defineProps<{
  symbol?: string
  dataType?: string
}>()

const dataTypeGroups = ref<DataTypeGroup[]>([])
const displayConfigs = ref<Record<string, { table_label: string; config: { fields: DisplayFieldConfig[] } }>>({})

const activeDataType = ref('info')
const selectedStock = ref<Stock | null>(null)
const tableData = ref<Record<string, unknown>[]>([])
const dataLoading = ref(false)
const dataCache = ref<Map<string, { results: Record<string, unknown>[], total: number }>>(new Map())
const currentPage = ref(1)
const pageSize = ref(50)
const totalRecords = ref(0)

const showColumnSettings = ref(false)
const allColumns = ref<(DisplayFieldConfig & { visible: boolean })[]>([])

const pageTitle = computed(() => {
  if (selectedStock.value) {
    return `${selectedStock.value.name} (${selectedStock.value.symbol})`
  }
  return '个股信息'
})

const currentTable = computed(() => {
  for (const group of dataTypeGroups.value) {
    const item = group.items.find(i => i.key === activeDataType.value)
    if (item) return item.table
  }
  return 'saa_stocks'
})

const currentTableLabel = computed(() => {
  const config = displayConfigs.value[currentTable.value]
  return config?.table_label || '数据'
})

const currentConfig = computed(() => {
  return displayConfigs.value[currentTable.value]?.config
})

const visibleColumns = computed(() => {
  if (!currentConfig.value) return []
  return currentConfig.value.fields
    .filter(f => f.visible && f.name !== 'symbol' && f.name !== 'name' && f.name !== 'stock_code' && f.name !== 'stock_name')
    .sort((a, b) => a.order - b.order)
})

const isBasicInfo = computed(() => currentTable.value === 'saa_stocks')

const selectAllColumns = computed({
  get: () => allColumns.value.every(c => c.visible),
  set: () => {}
})

const isIndeterminate = computed(() => {
  const visibleCount = allColumns.value.filter(c => c.visible).length
  return visibleCount > 0 && visibleCount < allColumns.value.length
})

const loadDisplayConfig = async () => {
  const response = await fetchDisplayConfig()
  if (response.success && response.data) {
    const data = response.data as { groups: DataTypeGroup[]; configs: Record<string, { table_label: string; config: { fields: DisplayFieldConfig[] } }> }
    dataTypeGroups.value = data.groups
    displayConfigs.value = data.configs
  }
}

const onDataTypeSelect = (key: string) => {
  activeDataType.value = key
  currentPage.value = 1
  if (selectedStock.value) {
    router.push(`/stock/${selectedStock.value.symbol}/${key}`)
  }
}

const loadStockData = async () => {
  if (!selectedStock.value) return
  
  const cacheKey = `${selectedStock.value.symbol}:${currentTable.value}:${currentPage.value}:${pageSize.value}`
  if (dataCache.value.has(cacheKey)) {
    const cached = dataCache.value.get(cacheKey)!
    tableData.value = cached.results
    totalRecords.value = cached.total
    return
  }
  
  dataLoading.value = true
  try {
    const response = await fetchStockData(selectedStock.value.symbol, currentTable.value, currentPage.value, pageSize.value)
    if (response.success && response.data) {
      tableData.value = response.data.results
      totalRecords.value = response.data.total
      dataCache.value.set(cacheKey, { results: response.data.results, total: response.data.total })
    }
  } catch (error) {
    console.error('Failed to load stock data:', error)
  } finally {
    dataLoading.value = false
  }
}

const onPageSizeChange = (val: number) => {
  pageSize.value = val
  currentPage.value = 1
  loadStockData()
}

const onPageChange = (val: number) => {
  currentPage.value = val
  loadStockData()
}

const formatValue = (value: unknown, format?: string): string => {
  if (value === null || value === undefined) return '-'
  
  switch (format) {
    case 'price':
      return typeof value === 'number' ? value.toFixed(2) : String(value)
    case 'volume':
      if (typeof value !== 'number') return String(value)
      if (value >= 100000000) return (value / 100000000).toFixed(2) + '亿'
      if (value >= 10000) return (value / 10000).toFixed(2) + '万'
      return value.toLocaleString()
    case 'money':
      if (typeof value !== 'number') return String(value)
      if (value >= 100000000) return (value / 100000000).toFixed(2) + '亿'
      return (value / 10000).toFixed(2) + '万'
    case 'percent':
      return typeof value === 'number' ? (value * 100).toFixed(2) + '%' : String(value)
    case 'date':
      return String(value)
    default:
      return String(value)
  }
}

const isNumericFormat = (format?: string): boolean => {
  const numericFormats = ['price', 'volume', 'money', 'percent']
  return format ? numericFormats.includes(format) : false
}

const initColumnSettings = () => {
  if (!currentConfig.value) return
  allColumns.value = currentConfig.value.fields.map(f => ({ ...f, visible: f.visible }))
}

const onSelectAllChange = (val: boolean) => {
  allColumns.value.forEach(col => {
    if (!col.fixed) {
      col.visible = val
    }
  })
}

const onColumnVisibilityChange = () => {
  // Just update local state, will save on button click
}

const resetColumnSettings = () => {
  initColumnSettings()
}

const saveColumnSettings = async () => {
  if (!currentConfig.value) return
  
  const newFields = allColumns.value.map(({ visible, ...rest }) => ({
    ...rest,
    visible
  }))
  
  const response = await saveDisplayConfig(currentTable.value, { fields: newFields })
  
  if (response.success) {
    const existing = displayConfigs.value[currentTable.value]
    displayConfigs.value[currentTable.value] = {
      table_label: existing?.table_label ?? currentTable.value,
      config: { fields: newFields }
    }
  }
  
  showColumnSettings.value = false
}

watch(showColumnSettings, (val) => {
  if (val) {
    initColumnSettings()
  }
})

const getActiveDataType = (dataType?: string): string => {
  if (!dataType) return 'info'
  const validTypes = ['info', 'quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'main_business', 'capital', 'dividend']
  return validTypes.includes(dataType) ? dataType : 'info'
}

const loadStockBySymbol = async (symbol: string) => {
  const response = await fetchStocks({ keyword: symbol, page: 1, page_size: 1 })
  if (response.success && response.data) {
    const stocks = Array.isArray(response.data) ? response.data : response.data.results || []
    if (stocks.length > 0) {
      selectedStock.value = stocks[0]
      loadStockData()
    }
  }
}

watch([() => props.symbol, () => props.dataType], ([newSymbol, newDataType], [oldSymbol]) => {
  if (newSymbol) {
    if (newSymbol !== oldSymbol) {
      dataCache.value.clear()
      loadStockBySymbol(newSymbol)
    }
    activeDataType.value = getActiveDataType(newDataType)
    if (newSymbol === oldSymbol && selectedStock.value) {
      loadStockData()
    }
  }
}, { immediate: true })

onMounted(() => {
  loadDisplayConfig()
})
</script>

<style scoped>
.data-browse-stock {
  height: 100%;
}

.page-header {
  margin-bottom: 16px;
}

.page-header h3 {
  margin: 0;
  color: #303133;
}

.content-row {
  height: calc(100vh - 116px);
}

.menu-card {
  height: 100%;
}

.menu-card :deep(.el-card__body) {
  padding: 0;
  height: 100%;
  overflow: auto;
}

.data-type-menu {
  border-right: none;
  height: 100%;
}

.data-card {
  height: 100%;
}

.data-card :deep(.el-card__body) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.table-title {
  font-weight: 500;
  font-size: 15px;
}

.column-settings {
  max-height: 400px;
  overflow-y: auto;
}

.settings-header {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 16px;
}

.column-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.column-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fixed-tag {
  color: #909399;
  font-size: 12px;
}

.data-card :deep(.el-descriptions) {
  width: 100%;
}

.data-card :deep(.el-descriptions__label) {
  width: 140px;
  font-weight: 500;
}

.pagination-container {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
