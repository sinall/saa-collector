import { createRouter, createWebHistory } from 'vue-router'
import auth from '@/utils/auth'
import { getBasePath } from '@/utils/path-detector'
import DashboardView from '@/views/DashboardView.vue'
import LoginView from '@/views/LoginView.vue'
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
  history: createWebHistory(getBasePath()),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView
    },
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView
    },
    {
      path: '/stock/:symbol/:dataType?',
      name: 'stock-detail',
      component: DataBrowseStockView,
      props: true
    },
    {
      path: '/data-browse/:type?',
      name: 'data-browse',
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

router.beforeEach((to, _from, next) => {
  const isDev = import.meta.env.DEV && import.meta.env.VITE_DEV_TOKEN

  if (isDev) {
    next()
    return
  }

  if (to.path !== '/login' && !auth.isAuthenticated()) {
    next('/login')
  } else if (to.path === '/login' && auth.isAuthenticated()) {
    next('/')
  } else {
    next()
  }
})

export default router
