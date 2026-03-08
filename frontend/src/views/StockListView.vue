<template>
  <div class="stock-list">
    <el-card>
      <template #header>
        <div class="card-header">
          <el-input
            v-model="keyword"
            placeholder="搜索股票代码或名称"
            style="width: 300px"
            clearable
            @keyup.enter="searchStocks"
          >
            <template #append>
              <el-button @click="searchStocks">搜索</el-button>
            </template>
          </el-input>
        </div>
      </template>
      <el-table :data="stocks" stripe v-loading="loading">
        <el-table-column prop="symbol" label="股票代码" width="120" />
        <el-table-column prop="name" label="股票名称" width="150" />
        <el-table-column prop="industry" label="行业" width="150">
          <template #default="{ row }">
            {{ row.industry || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="list_date" label="上市日期" width="120">
          <template #default="{ row }">
            {{ row.list_date || '-' }}
          </template>
        </el-table-column>
      </el-table>
      
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadStocks"
        @current-change="loadStocks"
        class="pagination"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchStocks, type Stock } from '@/utils/api'

const keyword = ref('')
const stocks = ref<Stock[]>([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const loadStocks = async () => {
  loading.value = true
  try {
    const response = await fetchStocks({
      keyword: keyword.value || undefined,
      page: currentPage.value,
      page_size: pageSize.value,
    })
    if (response.success && response.data) {
      stocks.value = response.data.results || []
      total.value = response.data.pagination?.total || 0
    }
  } catch (error) {
    console.error('Failed to load stocks:', error)
  } finally {
    loading.value = false
  }
}

const searchStocks = () => {
  currentPage.value = 1
  loadStocks()
}

onMounted(() => {
  loadStocks()
})
</script>

<style scoped>
.stock-list {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: flex-end;
}

.pagination {
  margin-top: 20px;
  justify-content: flex-end;
}
</style>
