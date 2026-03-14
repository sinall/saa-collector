<template>
  <div class="data-browse-stock">
    <div class="page-header">
      <h3>数据浏览 - 按股票</h3>
      <router-link to="/data-browse/type">
        <el-button type="primary" link>切换到按类型浏览</el-button>
      </router-link>
    </div>
    
    <el-row :gutter="20" class="content-row">
      <el-col :span="6">
        <el-card class="stock-list-card">
          <template #header>
            <div class="card-header">
              <span>股票列表</span>
            </div>
          </template>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索股票代码/名称"
            clearable
            @keyup.enter="searchStocks"
            class="search-input"
          >
            <template #append>
              <el-button @click="searchStocks">搜索</el-button>
            </template>
          </el-input>
          
          <div class="stock-list" v-loading="stockLoading">
            <div
              v-for="stock in stocks"
              :key="stock.symbol"
              class="stock-item"
              :class="{ active: selectedStock?.symbol === stock.symbol }"
              @click="selectStock(stock)"
            >
              <span class="stock-code">{{ stock.symbol }}</span>
              <span class="stock-name">{{ stock.name }}</span>
            </div>
          </div>
          
          <el-pagination
            v-model:current-page="stockPage"
            :page-size="stockPageSize"
            :total="stockTotal"
            layout="prev, pager, next"
            small
            @current-change="loadStocks"
            class="stock-pagination"
          />
        </el-card>
      </el-col>
      
      <el-col :span="18">
        <el-card class="stock-detail-card" v-if="selectedStock">
          <template #header>
            <div class="card-header">
              <span>{{ selectedStock.symbol }} - {{ selectedStock.name }}</span>
            </div>
          </template>
          
          <el-tabs v-model="activeTab" @tab-change="onTabChange">
            <el-tab-pane label="基本信息" name="info">
              <el-descriptions :column="2" border v-loading="infoLoading">
                <el-descriptions-item label="股票代码">{{ stockDetail?.symbol }}</el-descriptions-item>
                <el-descriptions-item label="股票名称">{{ stockDetail?.name }}</el-descriptions-item>
                <el-descriptions-item label="所属行业">{{ stockDetail?.industry || '-' }}</el-descriptions-item>
                <el-descriptions-item label="上市日期">{{ stockDetail?.list_date || '-' }}</el-descriptions-item>
              </el-descriptions>
            </el-tab-pane>
            
            <el-tab-pane label="历史行情" name="historical_quote">
              <el-table :data="historicalQuotes" stripe v-loading="quoteLoading" max-height="400">
                <el-table-column prop="trade_date" label="交易日期" width="120" />
                <el-table-column prop="open" label="开盘价" width="100" />
                <el-table-column prop="high" label="最高价" width="100" />
                <el-table-column prop="low" label="最低价" width="100" />
                <el-table-column prop="close" label="收盘价" width="100" />
                <el-table-column prop="volume" label="成交量" width="120">
                  <template #default="{ row }">
                    {{ formatNumber(row.volume) }}
                  </template>
                </el-table-column>
                <el-table-column prop="amount" label="成交额" width="120">
                  <template #default="{ row }">
                    {{ formatNumber(row.amount) }}
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            
            <el-tab-pane label="资产负债表" name="balance_sheet">
              <el-table :data="balanceSheets" stripe v-loading="balanceLoading" max-height="400">
                <el-table-column prop="report_period" label="报告期" width="120" />
                <el-table-column prop="report_date" label="报告日期" width="120" />
                <el-table-column prop="total_assets" label="资产总计" width="150">
                  <template #default="{ row }">
                    {{ formatMoney(row.total_assets) }}
                  </template>
                </el-table-column>
                <el-table-column prop="total_liabilities" label="负债合计" width="150">
                  <template #default="{ row }">
                    {{ formatMoney(row.total_liabilities) }}
                  </template>
                </el-table-column>
                <el-table-column prop="total_equity" label="所有者权益" width="150">
                  <template #default="{ row }">
                    {{ formatMoney(row.total_equity) }}
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-card>
        
        <el-card v-else class="stock-detail-card empty-card">
          <el-empty description="请从左侧选择一只股票" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  fetchStocksMock,
  fetchStockDetailMock,
  fetchStockHistoricalQuotesMock,
  fetchStockBalanceSheetsMock,
  type Stock,
  type StockDetail,
  type StockHistoricalQuote,
  type StockBalanceSheet,
} from '@/utils/api'

const searchKeyword = ref('')
const stocks = ref<Stock[]>([])
const stockLoading = ref(false)
const stockPage = ref(1)
const stockPageSize = ref(20)
const stockTotal = ref(0)
const selectedStock = ref<Stock | null>(null)

const activeTab = ref('info')
const stockDetail = ref<StockDetail | null>(null)
const historicalQuotes = ref<StockHistoricalQuote[]>([])
const balanceSheets = ref<StockBalanceSheet[]>([])
const infoLoading = ref(false)
const quoteLoading = ref(false)
const balanceLoading = ref(false)

const loadStocks = async () => {
  stockLoading.value = true
  try {
    const response = await fetchStocksMock({
      keyword: searchKeyword.value || undefined,
      page: stockPage.value,
      page_size: stockPageSize.value,
    })
    if (response.success && response.data) {
      stocks.value = response.data.results || []
      stockTotal.value = response.data.pagination?.total || 0
    }
  } catch (error) {
    console.error('Failed to load stocks:', error)
  } finally {
    stockLoading.value = false
  }
}

const searchStocks = () => {
  stockPage.value = 1
  loadStocks()
}

const selectStock = (stock: Stock) => {
  selectedStock.value = stock
  activeTab.value = 'info'
  loadStockDetail()
}

const loadStockDetail = async () => {
  if (!selectedStock.value) return
  
  infoLoading.value = true
  try {
    const response = await fetchStockDetailMock(selectedStock.value.symbol)
    if (response.success && response.data) {
      stockDetail.value = response.data
    }
  } catch (error) {
    console.error('Failed to load stock detail:', error)
  } finally {
    infoLoading.value = false
  }
}

const onTabChange = (tab: string) => {
  if (!selectedStock.value) return
  
  if (tab === 'historical_quote') {
    loadHistoricalQuotes()
  } else if (tab === 'balance_sheet') {
    loadBalanceSheets()
  }
}

const loadHistoricalQuotes = async () => {
  if (!selectedStock.value) return
  
  quoteLoading.value = true
  try {
    const response = await fetchStockHistoricalQuotesMock(selectedStock.value.symbol)
    if (response.success && response.data) {
      historicalQuotes.value = response.data
    }
  } catch (error) {
    console.error('Failed to load historical quotes:', error)
  } finally {
    quoteLoading.value = false
  }
}

const loadBalanceSheets = async () => {
  if (!selectedStock.value) return
  
  balanceLoading.value = true
  try {
    const response = await fetchStockBalanceSheetsMock(selectedStock.value.symbol)
    if (response.success && response.data) {
      balanceSheets.value = response.data
    }
  } catch (error) {
    console.error('Failed to load balance sheets:', error)
  } finally {
    balanceLoading.value = false
  }
}

const formatNumber = (num: number | null): string => {
  if (num === null) return '-'
  if (num >= 100000000) return (num / 100000000).toFixed(2) + '亿'
  if (num >= 10000) return (num / 10000).toFixed(2) + '万'
  return num.toLocaleString()
}

const formatMoney = (num: number | null): string => {
  if (num === null) return '-'
  return (num / 100000000).toFixed(2) + '亿'
}

onMounted(() => {
  loadStocks()
})
</script>

<style scoped>
.data-browse-stock {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h3 {
  margin: 0;
  color: #303133;
}

.content-row {
  height: calc(100vh - 160px);
}

.stock-list-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.stock-list-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.search-input {
  margin-bottom: 12px;
}

.stock-list {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 12px;
}

.stock-item {
  padding: 10px 12px;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  transition: background-color 0.2s;
}

.stock-item:hover {
  background-color: #f5f7fa;
}

.stock-item.active {
  background-color: #ecf5ff;
  color: #409eff;
}

.stock-code {
  font-weight: 500;
}

.stock-name {
  color: #909399;
  font-size: 13px;
}

.stock-pagination {
  justify-content: center;
}

.stock-detail-card {
  height: 100%;
}

.stock-detail-card :deep(.el-card__body) {
  height: calc(100% - 56px);
  overflow: auto;
}

.empty-card {
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
