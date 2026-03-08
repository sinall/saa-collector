import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import DataCheckView from '@/views/DataCheckView.vue'
import CollectView from '@/views/CollectView.vue'
import StockListView from '@/views/StockListView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView
    },
    {
      path: '/data-check',
      name: 'data-check',
      component: DataCheckView
    },
    {
      path: '/collect',
      name: 'collect',
      component: CollectView
    },
    {
      path: '/stocks',
      name: 'stocks',
      component: StockListView
    },
  ]
})

export default router
