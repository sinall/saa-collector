<template>
  <el-config-provider :locale="zhCn">
    <el-container class="app-container">
      <el-aside width="200px" class="sidebar">
        <div class="logo">
          <h2>SAA Collector</h2>
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
          
          <el-sub-menu index="data-browse">
            <template #title>
              <el-icon><FolderOpened /></el-icon>
              <span>数据浏览</span>
            </template>
            <el-menu-item index="/data-browse/stock">按股票</el-menu-item>
            <el-menu-item index="/data-browse/type">按类型</el-menu-item>
          </el-sub-menu>
          
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
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'

const route = useRoute()
const activeMenu = computed(() => route.path)
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
