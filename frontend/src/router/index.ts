import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import DataCheckView from '@/views/DataCheckView.vue'
import CollectView from '@/views/CollectView.vue'
import StockListView from '@/views/StockListView.vue'
import IntegrityReportsView from '@/views/IntegrityReportsView.vue'
import IntegrityReportDetailView from '@/views/IntegrityReportDetailView.vue'
import CollectPlansView from '@/views/CollectPlansView.vue'
import CollectPlanDetailView from '@/views/CollectPlanDetailView.vue'
import CollectPlanEditView from '@/views/CollectPlanEditView.vue'

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
      path: '/integrity-reports',
      name: 'integrity-reports',
      component: IntegrityReportsView
    },
    {
      path: '/integrity-reports/:id',
      name: 'integrity-report-detail',
      component: IntegrityReportDetailView,
      props: true
    },
    {
      path: '/collect',
      name: 'collect',
      component: CollectView
    },
    {
      path: '/collect-plans',
      name: 'collect-plans',
      component: CollectPlansView
    },
    {
      path: '/collect-plans/new',
      name: 'collect-plan-new',
      component: CollectPlanEditView
    },
    {
      path: '/collect-plans/:id',
      name: 'collect-plan-detail',
      component: CollectPlanDetailView,
      props: true
    },
    {
      path: '/collect-plans/:id/edit',
      name: 'collect-plan-edit',
      component: CollectPlanEditView,
      props: true
    },
    {
      path: '/stocks',
      name: 'stocks',
      component: StockListView
    },
  ]
})

export default router
