from django.urls import path
from . import views

urlpatterns = [
    path('data-status/', views.DataStatusView.as_view(), name='data-status'),
    path('data-completeness/', views.DataCompletenessView.as_view(), name='data-completeness'),
    path('data-completeness/check/', views.DataCompletenessCheckView.as_view(), name='data-completeness-check'),
    
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
