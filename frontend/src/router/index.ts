import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import IntegrityReportsView from '@/views/IntegrityReportsView.vue'
import IntegrityReportDetailView from '@/views/IntegrityReportDetailView.vue'
import CollectSchedulesView from '@/views/CollectSchedulesView.vue'
import CollectScheduleDetailView from '@/views/CollectScheduleDetailView.vue'
import CollectScheduleEditView from '@/views/CollectScheduleEditView.vue'
import CollectPlansView from '@/views/CollectPlansView.vue'
import CollectPlanDetailView from '@/views/CollectPlanDetailView.vue'
import CollectPlanEditView from '@/views/CollectPlanEditView.vue'
import DataBrowseStockView from '@/views/DataBrowseStockView.vue'
import DataBrowseTypeView from '@/views/DataBrowseTypeView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView
    },
    {
      path: '/data-browse/stock',
      name: 'data-browse-stock',
      component: DataBrowseStockView
    },
    {
      path: '/data-browse/type',
      name: 'data-browse-type',
      component: DataBrowseTypeView
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
      path: '/collect-schedules',
      name: 'collect-schedules',
      component: CollectSchedulesView
    },
    {
      path: '/collect-schedules/new',
      name: 'collect-schedule-new',
      component: CollectScheduleEditView
    },
    {
      path: '/collect-schedules/:id',
      name: 'collect-schedule-detail',
      component: CollectScheduleDetailView,
      props: true
    },
    {
      path: '/collect-schedules/:id/edit',
      name: 'collect-schedule-edit',
      component: CollectScheduleEditView,
      props: true
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
  ]
})

export default router
