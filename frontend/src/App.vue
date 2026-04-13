<template>
  <el-config-provider :locale="zhCn">
    <el-container class="app-container">
      <el-aside width="200px" class="sidebar">
        <div class="sidebar-user" v-if="username">
          <el-avatar :size="36" :src="avatarUrl || undefined">
            {{ username.charAt(0).toUpperCase() }}
          </el-avatar>
          <div class="sidebar-user-info">
            <span class="sidebar-user-name">{{ username }}</span>
            <span class="sidebar-user-logout" @click="handleLogout">退出</span>
          </div>
        </div>
        <div class="logo" v-else>
          <h2>SAA Collector</h2>
        </div>
        <div class="stock-search">
          <el-autocomplete
            v-model="stockSearchKeyword"
            :fetch-suggestions="searchStocks"
            placeholder="搜索股票代码/名称"
            @select="onStockSelect"
            clearable
            value-key="label"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-autocomplete>
        </div>
        <el-menu
          :default-active="activeMenu"
          router
          class="sidebar-menu"
        >
          <el-menu-item index="/">
            <el-icon><DataLine /></el-icon>
            <span>仪表盘</span>
          </el-menu-item>
          
          <el-menu-item index="/data-browse">
            <el-icon><FolderOpened /></el-icon>
            <span>数据浏览</span>
          </el-menu-item>
          
          <el-menu-item index="/integrity-reports">
            <el-icon><DocumentChecked /></el-icon>
            <span>数据检查</span>
          </el-menu-item>
          
          <el-sub-menu index="collect-manage">
            <template #title>
              <el-icon><Download /></el-icon>
              <span>采集管理</span>
            </template>
            <el-menu-item index="/collect-schedules">采集日程</el-menu-item>
            <el-menu-item index="/collect-plans">采集计划</el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-aside>
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-config-provider>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, DataLine, FolderOpened, DocumentChecked, Download } from '@element-plus/icons-vue'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import { fetchStocks, type Stock } from '@/utils/api'
import { useDataTypes } from '@/composables/useDataTypes'
import auth from '@/utils/auth'

const route = useRoute()
const router = useRouter()
const activeMenu = computed(() => route.path)

const username = ref(auth.getUsername())
const avatarUrl = ref(auth.getAvatarUrl())

// 登录后路由变化时刷新用户信息
watch(() => route.path, () => {
  username.value = auth.getUsername()
  avatarUrl.value = auth.getAvatarUrl()
})

const handleLogout = () => {
  auth.logout()
  username.value = ''
  avatarUrl.value = ''
  router.push('/login')
}

const stockSearchKeyword = ref('')

const { loadDataTypes } = useDataTypes()

onMounted(async () => {
  try {
    await loadDataTypes()
  } catch (error) {
    console.error('Failed to load data types config on app startup:', error)
  }
})

const searchStocks = async (query: string, cb: (results: { value: string; label: string; stock: Stock }[]) => void) => {
  if (!query) {
    cb([])
    return
  }
  
  const response = await fetchStocks({ keyword: query, page: 1, page_size: 10 })
  if (response.success && response.data) {
    const stocks = Array.isArray(response.data) ? response.data : response.data.results || []
    cb(stocks.map(s => ({
      value: s.symbol,
      label: `${s.symbol} - ${s.name}`,
      stock: s
    })))
  } else {
    cb([])
  }
}

const onStockSelect = (item: { value: string; label: string; stock: Stock }) => {
  stockSearchKeyword.value = ''
  router.push(`/stock/${item.stock.symbol}`)
}
</script>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
}

.app-container {
  height: 100vh;
}

.sidebar {
  background-color: #304156;
  color: #fff;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  border-bottom: 1px solid #3a4a5b;
}

.logo h2 {
  margin: 0;
  font-size: 16px;
}

.sidebar-user {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 10px;
  border-bottom: 1px solid #3a4a5b;
}

.sidebar-user .el-avatar {
  flex-shrink: 0;
  background-color: #409eff;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}

.sidebar-user-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.sidebar-user-name {
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-user-logout {
  color: #6b7a8a;
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s;
}

.sidebar-user-logout:hover {
  color: #409eff;
}

.stock-search {
  padding: 16px 12px;
  border-bottom: 1px solid #3a4a5b;
}

.stock-search :deep(.el-autocomplete) {
  width: 100%;
}

.stock-search :deep(.el-input__wrapper) {
  background-color: #263445;
  border-radius: 18px;
  box-shadow: none;
  border: 1px solid transparent;
  padding: 1px 12px;
  transition: all 0.3s;
}

.stock-search :deep(.el-input__wrapper:hover) {
  background-color: #2d3d50;
}

.stock-search :deep(.el-input__wrapper.is-focus) {
  background-color: #2d3d50;
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.stock-search :deep(.el-input__inner) {
  color: #bfcbd9;
  font-size: 13px;
}

.stock-search :deep(.el-input__inner::placeholder) {
  color: #6b7a8a;
}

.stock-search :deep(.el-input__prefix) {
  color: #6b7a8a;
}

.stock-search :deep(.el-input__suffix) {
  color: #6b7a8a;
}

.stock-search :deep(.el-input__clear) {
  color: #6b7a8a;
}

.stock-search :deep(.el-input__clear:hover) {
  color: #bfcbd9;
}

.sidebar-menu {
  border-right: none;
  background-color: #304156;
}

.sidebar-menu .el-menu-item {
  color: #bfcbd9;
}

.sidebar-menu .el-menu-item:hover,
.sidebar-menu .el-menu-item.is-active {
  background-color: #263445;
  color: #409eff;
}

.sidebar-menu .el-sub-menu__title {
  color: #bfcbd9 !important;
}

.sidebar-menu .el-sub-menu__title:hover {
  background-color: #263445 !important;
  color: #409eff !important;
}

.sidebar-menu .el-sub-menu .el-menu-item {
  background-color: #1f2d3d;
  color: #bfcbd9;
}

.sidebar-menu .el-sub-menu .el-menu-item:hover,
.sidebar-menu .el-sub-menu .el-menu-item.is-active {
  background-color: #263445;
  color: #409eff;
}

.main-content {
  background-color: #f0f2f5;
  padding: 20px;
}
</style>
