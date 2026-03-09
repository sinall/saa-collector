import logging
import threading
from datetime import date, timedelta

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.db import connection
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import CollectJob
from .serializers import (
    CollectJobSerializer, CollectJobCreateSerializer,
    DataStatusSerializer, DataCompletenessSerializer
)

logger = logging.getLogger(__name__)


def health_check(request):
    return HttpResponse('OK', content_type='text/plain')


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class DataStatusView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        data_types = [
            ('stock_info', '股票基本信息', 'saa_stocks'),
            ('quote', '最新行情', 'saa_latest_prices'),
            ('historical_quote', '历史行情', 'saa_prices'),
            ('balance_sheet', '资产负债表', 'saa_raw_balance_sheet'),
            ('income', '利润表', 'saa_raw_income_statement'),
            ('cash_flow', '现金流量表', 'saa_raw_cash_flow_statement'),
            ('dividend', '分红数据', 'saa_dividends'),
            ('main_business', '主营业务', 'saa_raw_main_business'),
            ('capital', '股本变动', 'saa_capitals'),
        ]
        
        results = []
        with connection.cursor() as cursor:
            for data_type, display_name, table_name in data_types:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    
                    date_column = self._get_date_column(table_name)
                    if date_column:
                        cursor.execute(f"SELECT MIN({date_column}), MAX({date_column}) FROM {table_name}")
                        row = cursor.fetchone()
                        earliest_date = row[0]
                        latest_date = row[1]
                    else:
                        earliest_date = None
                        latest_date = None
                    
                    results.append({
                        'data_type': data_type,
                        'data_type_display': display_name,
                        'count': count,
                        'earliest_date': earliest_date,
                        'latest_date': latest_date,
                    })
                except Exception as e:
                    logger.warning(f"Failed to get status for {table_name}: {e}")
                    results.append({
                        'data_type': data_type,
                        'data_type_display': display_name,
                        'count': 0,
                        'earliest_date': None,
                        'latest_date': None,
                    })
        
        serializer = DataStatusSerializer(results, many=True)
        return Response({'success': True, 'data': serializer.data})
    
    def _get_date_column(self, table_name):
        date_columns = {
            'saa_stocks': None,
            'saa_latest_prices': 'date',
            'saa_prices': 'date',
            'saa_raw_balance_sheet': 'date',
            'saa_raw_income_statement': 'date',
            'saa_raw_cash_flow_statement': 'date',
            'saa_dividends': 'date',
            'saa_raw_main_business': 'date',
            'saa_capitals': 'date',
        }
        return date_columns.get(table_name)


class DataCompletenessView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        data_type = request.query_params.get('data_type')
        symbols = request.query_params.getlist('symbols')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not all([data_type, start_date, end_date]):
            return Response({
                'success': False,
                'error': 'data_type, start_date, end_date are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        summary = {'total': 0, 'existing': 0, 'missing': 0, 'rate': 0}
        by_stock = []
        by_date = []
        missing_details = []
        
        return Response({
            'success': True,
            'data': {
                'summary': summary,
                'by_stock': by_stock,
                'by_date': by_date,
                'missing_details': missing_details,
            }
        })


class CollectJobListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        jobs = CollectJob.objects.all()
        
        data_type = request.query_params.get('data_type')
        if data_type:
            jobs = jobs.filter(data_type=data_type)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            jobs = jobs.filter(status=status_filter)
        
        paginator = StandardPagination()
        page = paginator.paginate_queryset(jobs, request, view=self)
        serializer = CollectJobSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CollectJobDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        try:
            job = CollectJob.objects.get(pk=pk)
        except CollectJob.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Job not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = CollectJobSerializer(job)
        return Response({'success': True, 'data': serializer.data})


class BaseCollectView(APIView):
    permission_classes = [IsAuthenticated]
    data_type = None
    
    def post(self, request):
        serializer = CollectJobCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        job = CollectJob.objects.create(
            data_type=self.data_type,
            symbols=serializer.validated_data.get('symbols', []),
            params={
                'start_date': str(serializer.validated_data.get('start_date')) if serializer.validated_data.get('start_date') else None,
                'end_date': str(serializer.validated_data.get('end_date')) if serializer.validated_data.get('end_date') else None,
                'report_types': serializer.validated_data.get('report_types', []),
            }
        )
        
        thread = threading.Thread(target=self._run_job, args=(job.id,))
        thread.start()
        
        return Response({
            'success': True,
            'data': CollectJobSerializer(job).data
        }, status=status.HTTP_201_CREATED)
    
    def _run_job(self, job_id):
        from django import db
        db.connections.close_all()
        
        job = CollectJob.objects.get(id=job_id)
        job.start()
        
        try:
            self._execute_collect(job)
            job.complete(success=True)
        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            job.complete(success=False, message=str(e))
    
    def _execute_collect(self, job):
        pass


class CollectStockInfoView(BaseCollectView):
    data_type = 'stock_info'
    
    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_stock_info_service()
        symbols = job.symbols if job.symbols else None
        service.collect(symbols)
        job.complete(success=True, message=f"Collected stock info for {len(job.symbols) if job.symbols else 'all'} symbols")


class CollectQuotesView(BaseCollectView):
    data_type = 'quote'
    
    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_quote_service()
        symbols = job.symbols if job.symbols else None
        service.collect(symbols)
        job.complete(success=True, message=f"Collected quotes for {len(job.symbols) if job.symbols else 'all'} symbols")


class CollectHistoricalQuotesView(BaseCollectView):
    data_type = 'historical_quote'
    
    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_quote_service()
        symbols = job.symbols if job.symbols else None
        start_date = job.params.get('start_date')
        end_date = job.params.get('end_date')
        service.collect_historical(symbols, start_date=start_date, end_date=end_date)
        job.complete(success=True, message=f"Collected historical quotes")


class CollectStatementsView(BaseCollectView):
    data_type = 'balance_sheet'
    
    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_statement_service()
        symbols = job.symbols if job.symbols else None
        start_date = job.params.get('start_date')
        if start_date:
            from datetime import datetime
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        report_types = job.params.get('report_types', [])
        
        if 'balance_sheet' in report_types or not report_types:
            service.collect_balance_sheet(symbols, start_date)
        if 'income' in report_types or not report_types:
            service.collect_income(symbols, start_date)
        if 'cash_flow' in report_types or not report_types:
            service.collect_cash_flow(symbols, start_date)
        if 'dividend' in report_types:
            service.collect_dividend(symbols, start_date)
        
        job.complete(success=True, message=f"Collected statements")


class CollectCapitalView(BaseCollectView):
    data_type = 'capital'
    
    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_capital_service()
        symbols = job.symbols if job.symbols else None
        start_date = job.params.get('start_date')
        if start_date:
            from datetime import datetime
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        service.collect(symbols, start_date)
        job.complete(success=True, message=f"Collected capital changes")


class CollectValuationView(BaseCollectView):
    data_type = 'valuation'
    
    def _execute_collect(self, job):
        from saa_collector.jobs.valuation_collect_job import ValuationCollectJob
        collect_job = ValuationCollectJob()
        collect_job()
        job.complete(success=True, message=f"Collected valuation data")


class CollectMainBusinessView(BaseCollectView):
    data_type = 'main_business'
    
    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_statement_service()
        symbols = job.symbols if job.symbols else None
        start_date = job.params.get('start_date')
        if start_date:
            from datetime import datetime
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        service.collect_main_business(symbols, start_date)
        job.complete(success=True, message=f"Collected main business data")


class StockListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        keyword = request.query_params.get('keyword', '')
        
        with connection.cursor() as cursor:
            if keyword:
                cursor.execute(
                    "SELECT symbol, name, industry, list_date FROM stock_info "
                    "WHERE symbol LIKE %s OR name LIKE %s "
                    "ORDER BY symbol LIMIT 100",
                    [f'%{keyword}%', f'%{keyword}%']
                )
            else:
                cursor.execute(
                    "SELECT symbol, name, industry, list_date FROM stock_info "
                    "ORDER BY symbol LIMIT 100"
                )
            
            stocks = []
            for row in cursor.fetchall():
                stocks.append({
                    'symbol': row[0],
                    'name': row[1],
                    'industry': row[2],
                    'list_date': str(row[3]) if row[3] else None,
                })
        
        return Response({
            'success': True,
            'data': stocks
        })


class StockDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, symbol):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT symbol, name, industry, list_date FROM stock_info "
                "WHERE symbol = %s",
                [symbol]
            )
            row = cursor.fetchone()
            if not row:
                return Response({
                    'success': False,
                    'error': 'Stock not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            return Response({
                'success': True,
                'data': {
                    'symbol': row[0],
                    'name': row[1],
                    'industry': row[2],
                    'list_date': str(row[3]) if row[3] else None,
                }
            })
