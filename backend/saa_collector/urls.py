from django.urls import path
from . import views

urlpatterns = [
    path('data-status/', views.DataStatusView.as_view(), name='data-status'),
    path('data-completeness/', views.DataCompletenessView.as_view(), name='data-completeness'),
    path('data-completeness/check/', views.DataCompletenessCheckView.as_view(), name='data-completeness-check'),

    path('integrity-reports/', views.DataIntegrityReportListView.as_view(), name='integrity-report-list'),
    path('integrity-reports/<int:pk>/', views.DataIntegrityReportDetailView.as_view(), name='integrity-report-detail'),
    path('integrity-reports/<int:pk>/items/', views.DataIntegrityReportItemsUpdateView.as_view(), name='integrity-report-items'),
    path('integrity-reports/<int:pk>/items/select-all/', views.DataIntegrityReportItemsSelectAllView.as_view(), name='integrity-report-items-select-all'),
    path('integrity-reports/<int:pk>/generate-plan/', views.DataIntegrityReportGeneratePlanView.as_view(), name='integrity-report-generate-plan'),

    path('collect-plans/', views.CollectPlanListView.as_view(), name='collect-plan-list'),
    path('collect-plans/<int:pk>/', views.CollectPlanDetailView.as_view(), name='collect-plan-detail'),
    path('collect-plans/<int:pk>/execute/', views.CollectPlanExecuteView.as_view(), name='collect-plan-execute'),

    path('collect/stock-info/', views.CollectStockInfoView.as_view(), name='collect-stock-info'),
    path('collect/quotes/', views.CollectQuotesView.as_view(), name='collect-quotes'),
    path('collect/historical-quotes/', views.CollectHistoricalQuotesView.as_view(), name='collect-historical-quotes'),
    path('collect/statements/', views.CollectStatementsView.as_view(), name='collect-statements'),
    path('collect/capital/', views.CollectCapitalView.as_view(), name='collect-capital'),
    path('collect/valuation/', views.CollectValuationView.as_view(), name='collect-valuation'),
    path('collect/main-business/', views.CollectMainBusinessView.as_view(), name='collect-main-business'),

    path('collect/jobs/', views.CollectJobListView.as_view(), name='collect-jobs'),
    path('collect/jobs/<int:pk>/', views.CollectJobDetailView.as_view(), name='collect-job-detail'),

    path('stocks/', views.StockListView.as_view(), name='stock-list'),
    path('stocks/<str:symbol>/', views.StockDetailView.as_view(), name='stock-detail'),
]
