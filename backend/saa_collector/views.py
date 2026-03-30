import json
import logging
import threading
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.db import connection
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated

from django.db.models import Count
from django.shortcuts import get_object_or_404

from .models import CollectJob, DataIntegrityReport, DataIntegrityItem, CollectPlan
from .serializers import (
    CollectJobSerializer, CollectJobCreateSerializer,
    DataStatusSerializer, DataCompletenessSerializer,
    DataIntegrityReportSerializer, DataIntegrityReportCreateSerializer,
    DataIntegrityItemSerializer, DataIntegrityItemBulkUpdateSerializer,
    FlattenedIntegrityItemSerializer,
    CollectPlanSerializer, CollectPlanCreateSerializer, CollectPlanUpdateSerializer,
    CollectJobBriefSerializer,
)

logger = logging.getLogger(__name__)

from .constants import (
    DATA_TYPE_FREQUENCY,
    DATA_TYPE_CONFIG,
    TABLE_MAPPING,
    QUARTERLY_TYPES,
    YEARLY_TYPES,
    NON_STOCK_LEVEL_TYPES,
    A_STOCK_EARLIEST_DATE,
    EARLIEST_YEAR,
    EXPECTED_A_SHARE_STOCKS,
)


def calculate_expected_periods(earliest_date, latest_date, frequency):
    if not earliest_date or not latest_date or not frequency:
        return 0
    
    if frequency == 'daily':
        trading_days_per_year = 250
        days = (latest_date - earliest_date).days
        return max(1, int(days / 365 * trading_days_per_year))
    elif frequency == 'quarterly':
        quarters = (latest_date.year - earliest_date.year) * 4 + (latest_date.month - earliest_date.month) // 3 + 1
        return max(1, quarters)
    elif frequency == 'yearly':
        years = latest_date.year - earliest_date.year + 1
        return max(1, years)
    return 0


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
            ('trade_days', '交易日', 'saa_trade_days'),
            ('stock_info', '股票基本信息', 'saa_stocks'),
            ('quote', '最新行情', 'saa_latest_prices'),
            ('historical_quote', '历史行情', 'saa_prices_ex'),
            ('balance_sheet', '资产负债表', 'saa_raw_balance_sheet'),
            ('income', '利润表', 'saa_raw_income_statement'),
            ('cash_flow', '现金流量表', 'saa_raw_cash_flow_statement'),
            ('main_business', '主营业务', 'saa_raw_main_business'),
            ('capital', '股本变动', 'saa_capitals'),
            ('dividend', '分红数据', 'saa_dividends'),
            ('valuation_board', '板块估值', 'saa_board_valuation_levels'),
            ('valuation_industry', '行业估值', 'saa_industry_valuation_levels'),
        ]

        results = []
        with connection.cursor() as cursor:
            for data_type, display_name, table_name in data_types:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]

                    date_column = self._get_date_column(table_name)
                    frequency = DATA_TYPE_FREQUENCY.get(data_type)
                    completeness = None
                    
                    if date_column:
                        cursor.execute(
                            f"SELECT MIN({date_column}), MAX({date_column}) FROM {table_name} WHERE {date_column} >= %s",
                            [A_STOCK_EARLIEST_DATE]
                        )
                        row = cursor.fetchone()
                        earliest_date = row[0]
                        latest_date = row[1]
                        
                        if count == 0:
                            completeness = 0.0
                        elif frequency and earliest_date and latest_date:
                            cursor.execute(
                                f"SELECT COUNT(DISTINCT {date_column}) FROM {table_name} WHERE {date_column} >= %s",
                                [A_STOCK_EARLIEST_DATE]
                            )
                            actual_periods = cursor.fetchone()[0]
                            expected_periods = calculate_expected_periods(earliest_date, latest_date, frequency)
                            if expected_periods > 0:
                                completeness = min(1.0, actual_periods / expected_periods)
                    elif data_type == 'stock_info':
                        earliest_date = None
                        latest_date = None
                        if EXPECTED_A_SHARE_STOCKS > 0:
                            completeness = min(1.0, count / EXPECTED_A_SHARE_STOCKS)
                    else:
                        earliest_date = None
                        latest_date = None

                    results.append({
                        'data_type': data_type,
                        'data_type_display': display_name,
                        'count': count,
                        'earliest_date': earliest_date,
                        'latest_date': latest_date,
                        'frequency': frequency,
                        'completeness': completeness,
                    })
                except Exception as e:
                    logger.warning(f"Failed to get status for {table_name}: {e}")
                    results.append({
                        'data_type': data_type,
                        'data_type_display': display_name,
                        'count': 0,
                        'earliest_date': None,
                        'latest_date': None,
                        'frequency': DATA_TYPE_FREQUENCY.get(data_type),
                        'completeness': 0.0,
                    })

        serializer = DataStatusSerializer(results, many=True)
        return Response({'success': True, 'data': serializer.data})

    def _get_date_column(self, table_name):
        date_columns = {
            'saa_stocks': None,
            'saa_trade_days': 'date',
            'saa_latest_prices': 'date',
'saa_prices_ex': 'date',
            'saa_raw_balance_sheet': 'date',
            'saa_raw_income_statement': 'date',
            'saa_raw_cash_flow_statement': 'date',
            'saa_dividends': 'date',
            'saa_raw_main_business': 'date',
            'saa_capitals': 'date',
            'saa_board_valuation_levels': 'report_date',
            'saa_industry_valuation_levels': 'report_date',
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
                    "SELECT symbol, name, industry_classification_id, listing_time FROM saa_stocks "
                    "WHERE symbol LIKE %s OR name LIKE %s "
                    "ORDER BY symbol LIMIT 100",
                    [f'{keyword}%', f'%{keyword}%']
                )
            else:
                cursor.execute(
                    "SELECT symbol, name, industry_classification_id, listing_time FROM saa_stocks "
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
                "SELECT symbol, name, industry_classification_id, listing_time FROM saa_stocks "
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


class TypeBrowseDataView(APIView):
    permission_classes = [IsAuthenticated]

    TABLE_CONFIG = {
        'saa_stocks': {'date_column': None, 'order': 'symbol ASC'},
        'saa_latest_prices': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_prices_ex': {'date_column': 'date', 'order': 'code ASC, date DESC'},
        'saa_raw_balance_sheet': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_raw_income_statement': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_raw_cash_flow_statement': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_raw_main_business': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_capitals': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_dividends': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_trade_days': {'date_column': 'date', 'order': 'date DESC'},
    }

    NEEDS_STOCK_NAME = {
        'saa_latest_prices',
        'saa_prices_ex',
        'saa_raw_balance_sheet',
        'saa_raw_income_statement',
        'saa_raw_cash_flow_statement',
        'saa_raw_main_business',
        'saa_capitals',
        'saa_dividends',
    }

    def get(self, request, table_name):
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        offset = (page - 1) * page_size

        config = self.TABLE_CONFIG.get(table_name)
        if not config:
            return Response({'success': False, 'error': 'Invalid table name'}, status=400)

        date_column = config['date_column']
        order_clause = f"ORDER BY {config['order']}"

        with connection.cursor() as cursor:
            where_clauses = []
            params = []

            if date_column and start_date:
                where_clauses.append(f"t.{date_column} >= %s")
                params.append(start_date)
            if date_column and end_date:
                where_clauses.append(f"t.{date_column} <= %s")
                params.append(end_date)

            where_clause = " AND ".join(where_clauses)
            if where_clause:
                where_clause = "WHERE " + where_clause

            if table_name in self.NEEDS_STOCK_NAME:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} t {where_clause}",
                    params
                )
                total = cursor.fetchone()[0]

                cursor.execute(
                    f"""
                    SELECT t.*, s.name as stock_name
                    FROM {table_name} t
                    LEFT JOIN saa_stocks s ON t.symbol = s.symbol
                    {where_clause}
                    {order_clause}
                    LIMIT %s OFFSET %s
                    """,
                    params + [page_size, offset]
                )
            else:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} t {where_clause}",
                    params
                )
                total = cursor.fetchone()[0]

                cursor.execute(
                    f"SELECT t.* FROM {table_name} t {where_clause} {order_clause} LIMIT %s OFFSET %s",
                    params + [page_size, offset]
                )

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            results = [dict(zip(columns, row)) for row in rows]

            for row in results:
                for key, value in row.items():
                    if isinstance(value, date):
                        row[key] = value.strftime('%Y-%m-%d')
                    elif isinstance(value, Decimal):
                        row[key] = float(value)

        return Response({
            'success': True,
            'data': {
                'results': results,
                'total': total,
                'page': page,
                'page_size': page_size
            }
        })


@method_decorator(csrf_exempt, name='dispatch')
class DataCompletenessCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        data_type = request.data.get('data_type')
        symbols = request.data.get('symbols', [])
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        frequency = request.data.get('frequency', 'daily')
        page = int(request.data.get('page', 1))
        page_size = int(request.data.get('page_size', 100))

        if not all([data_type, start_date, end_date]):
            return Response({
                'success': False,
                'error': 'data_type, start_date, end_date are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if data_type == 'trade_days':
            missing_records, summary = self._check_trade_days_missing(start_date, end_date, frequency)
        else:
            trade_dates = self.get_trade_dates_by_frequency(start_date, end_date, frequency)

            if not trade_dates:
                expected_months = self._get_expected_months(start_date, end_date)
                summary = [{'period': m, 'expected': 0, 'missing': 0} for m in sorted(expected_months)]
                return Response({
                    'success': True,
                    'data': {
                        'total_missing': 0,
                        'missing_records': [],
                        'summary': summary,
                        'pagination': {'page': page, 'page_size': page_size, 'total': 0}
                    }
                })

            stocks = self.get_stocks_with_listing_date(symbols, start_date, end_date)

            if not stocks:
                expected_months = self._get_expected_months(start_date, end_date)
                summary = [{'period': m, 'expected': 0, 'missing': 0} for m in sorted(expected_months)]
                return Response({
                    'success': True,
                    'data': {
                        'total_missing': 0,
                        'missing_records': [],
                        'summary': summary,
                        'pagination': {'page': page, 'page_size': page_size, 'total': 0}
                    }
                })

            missing_records, summary = self.check_data_missing_batch(stocks, trade_dates, data_type, frequency, start_date, end_date)

        total = len(missing_records)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_records = missing_records[start_idx:end_idx]

        return Response({
            'success': True,
            'data': {
                'total_missing': total,
                'missing_records': paginated_records,
                'summary': summary,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size
                }
            }
        })

    def get_trade_dates_by_frequency(self, start_date, end_date, frequency):
        with connection.cursor() as cursor:
            if frequency == 'daily':
                cursor.execute("""
                    SELECT date FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                    ORDER BY date
                """, [start_date, end_date])
            elif frequency == 'weekly':
                cursor.execute("""
                    SELECT MAX(date) as date
                    FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                    GROUP BY YEARWEEK(date, 1)
                    ORDER BY date
                """, [start_date, end_date])
            elif frequency == 'monthly':
                cursor.execute("""
                    SELECT MAX(date) as date
                    FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                    GROUP BY YEAR(date), MONTH(date)
                    ORDER BY date
                """, [start_date, end_date])
            elif frequency == 'quarterly':
                cursor.execute("""
                    SELECT MAX(t.date) as date
                    FROM saa_trade_days t
                    INNER JOIN (
                        SELECT DISTINCT
                            YEAR(date) as yr,
                            QUARTER(date) as qtr,
                            CASE QUARTER(date)
                                WHEN 1 THEN DATE(CONCAT(YEAR(date), '-03-31'))
                                WHEN 2 THEN DATE(CONCAT(YEAR(date), '-06-30'))
                                WHEN 3 THEN DATE(CONCAT(YEAR(date), '-09-30'))
                                WHEN 4 THEN DATE(CONCAT(YEAR(date), '-12-31'))
                            END as quarter_end
                        FROM saa_trade_days
                        WHERE date BETWEEN %s AND %s
                    ) q ON t.date <= q.quarter_end
                    WHERE q.quarter_end BETWEEN %s AND %s
                    GROUP BY q.yr, q.qtr
                    ORDER BY date
                """, [start_date, end_date, start_date, end_date])
            elif frequency == 'yearly':
                cursor.execute("""
                    SELECT MAX(date) as date
                    FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                    GROUP BY YEAR(date)
                    ORDER BY date
                """, [start_date, end_date])
            else:
                return []

            rows = cursor.fetchall()
            return [row[0] for row in rows]

    def get_stocks_with_listing_date(self, symbols, start_date, end_date):
        with connection.cursor() as cursor:
            if symbols and len(symbols) > 0:
                symbol_map = {s.split('.')[0]: s for s in symbols}
                short_symbols = list(symbol_map.keys())
                placeholders = ','.join(['%s'] * len(short_symbols))
                cursor.execute(f"""
                    SELECT symbol, name, listing_time
                    FROM saa_stocks
                    WHERE symbol IN ({placeholders})
                      AND listing_time IS NOT NULL
                      AND listing_time <= %s
                """, short_symbols + [end_date])
            else:
                cursor.execute("""
                    SELECT symbol, name, listing_time
                    FROM saa_stocks
                    WHERE listing_time IS NOT NULL
                      AND listing_time <= %s
                """, [end_date])
                symbol_map = None

            stocks = []
            for row in cursor.fetchall():
                listing_time = row[2]
                if hasattr(listing_time, 'strftime'):
                    listing_date_str = listing_time.strftime('%Y-%m-%d')
                else:
                    listing_date_str = str(listing_time)

                short_symbol = row[0]
                full_symbol = symbol_map.get(short_symbol, short_symbol) if symbol_map else short_symbol

                stocks.append({
                    'symbol': full_symbol,
                    'name': row[1],
                    'listing_date': listing_date_str
                })

            return stocks

    def check_data_missing_batch(self, stocks, trade_dates, data_type, frequency, start_date=None, end_date=None):
        table_mapping = {
            'historical_quote': ('saa_prices_ex', 'date'),
            'balance_sheet': ('saa_raw_balance_sheet', 'date'),
            'income': ('saa_raw_income_statement', 'date'),
            'cash_flow': ('saa_raw_cash_flow_statement', 'date'),
            'dividend': ('saa_dividends', 'date'),
            'main_business': ('saa_raw_main_business', 'date'),
            'capital': ('saa_capitals', 'date'),
            'quote': ('saa_latest_prices', 'date'),
            'trade_days': ('saa_trade_days', 'date'),
        }

        if data_type not in table_mapping:
            return [], []

        if data_type == 'trade_days':
            return self._check_trade_days_missing(start_date, end_date, frequency)

        if data_type == 'quote':
            return self._check_quote_missing(stocks, trade_dates, frequency)

        table_name, date_column = table_mapping[data_type]
        missing_records = []

        data_type_display = dict(CollectJob.DATA_TYPE_CHOICES).get(data_type, data_type)

        frequency_display = {
            'daily': '日度',
            'weekly': '周度',
            'monthly': '月度',
            'quarterly': '季度'
        }.get(frequency, frequency)

        from collections import defaultdict
        period_stats = defaultdict(lambda: {'expected': 0, 'missing': 0})

        stock_expected = {}
        for stock in stocks:
            valid_dates = [
                d for d in trade_dates
                if str(d) >= stock['listing_date']
            ]
            if valid_dates:
                stock_expected[stock['symbol']] = {
                    'name': stock['name'],
                    'dates': valid_dates
                }
                for date in valid_dates:
                    period = str(date)[:7]
                    period_stats[period]['expected'] += 1

        if not stock_expected:
            return [], []

        all_symbols = list(stock_expected.keys())
        all_dates = list(set(d for info in stock_expected.values() for d in info['dates']))

        with connection.cursor() as cursor:
            symbol_placeholders = ','.join(['%s'] * len(all_symbols))
            date_placeholders = ','.join(['%s'] * len(all_dates))
            cursor.execute(f"""
                SELECT symbol, {date_column}
                FROM {table_name}
                WHERE symbol IN ({symbol_placeholders})
                  AND {date_column} IN ({date_placeholders})
            """, all_symbols + all_dates)

            existing_data = set((row[0], row[1]) for row in cursor.fetchall())

        for symbol, info in stock_expected.items():
            for date in info['dates']:
                if (symbol, date) not in existing_data:
                    period = str(date)[:7]
                    period_stats[period]['missing'] += 1
                    missing_records.append({
                        'symbol': symbol,
                        'name': info['name'],
                        'date': str(date),
                        'data_type': data_type_display,
                        'frequency': frequency_display
                    })

        summary = [
            {'period': period, 'expected': stats['expected'], 'missing': stats['missing']}
            for period, stats in sorted(period_stats.items())
        ]

        return missing_records, summary

    def _check_trade_days_missing(self, start_date, end_date, frequency):
        missing_records = []
        data_type_display = '交易日'
        frequency_display = {
            'daily': '日度',
            'weekly': '周度',
            'monthly': '月度',
            'quarterly': '季度'
        }.get(frequency, frequency)

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DATE_FORMAT(date, %s) as month
                FROM saa_trade_days
                WHERE date BETWEEN %s AND %s
                GROUP BY DATE_FORMAT(date, %s)
            """, ['%Y-%m', start_date, end_date, '%Y-%m'])
            existing_months = set(str(row[0]) for row in cursor.fetchall())

        expected_months = self._get_expected_months(start_date, end_date)
        missing_months = sorted(expected_months - existing_months)

        for month in missing_months:
            missing_records.append({
                'symbol': '-',
                'name': '-',
                'date': month,
                'data_type': data_type_display,
                'frequency': frequency_display
            })

        summary = []
        for month in sorted(expected_months):
            summary.append({
                'period': month,
                'expected': 1,
                'missing': 0 if month in existing_months else 1
            })

        return missing_records, summary

    def _check_quote_missing(self, stocks, trade_dates, frequency):
        from collections import defaultdict

        missing_records = []
        data_type_display = '最新行情'
        frequency_display = {
            'daily': '日度',
            'weekly': '周度',
            'monthly': '月度',
            'quarterly': '季度'
        }.get(frequency, frequency)

        if not trade_dates:
            return [], []

        period_stats = defaultdict(lambda: {'expected': 0, 'missing': 0})

        with connection.cursor() as cursor:
            for stock in stocks:
                short_symbol = stock['symbol'].split('.')[0]
                valid_dates = [
                    d for d in trade_dates
                    if str(d) >= stock['listing_date']
                ]

                if not valid_dates:
                    continue

                for date in valid_dates:
                    period = str(date)[:7]
                    period_stats[period]['expected'] += 1

                placeholders = ','.join(['%s'] * len(valid_dates))
                cursor.execute(f"""
                    SELECT DISTINCT date
                    FROM saa_latest_prices
                    WHERE symbol = %s
                      AND date IN ({placeholders})
                """, [short_symbol] + valid_dates)

                existing_dates = set(row[0] for row in cursor.fetchall())

                for date in valid_dates:
                    if date not in existing_dates:
                        period = str(date)[:7]
                        period_stats[period]['missing'] += 1
                        missing_records.append({
                            'symbol': stock['symbol'],
                            'name': stock['name'],
                            'date': str(date),
                            'data_type': data_type_display,
                            'frequency': frequency_display
                        })

        summary = [
            {'period': period, 'expected': stats['expected'], 'missing': stats['missing']}
            for period, stats in sorted(period_stats.items())
        ]

        return missing_records, summary

    def _get_expected_months(self, start_date, end_date):
        from datetime import datetime
        from calendar import monthrange

        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        months = set()
        current_year = start_date.year
        current_month = start_date.month

        while True:
            current_date = datetime(current_year, current_month, 1).date()
            if current_date > end_date:
                break
            months.add(current_date.strftime('%Y-%m'))
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

        return months


class DataIntegrityReportListView(APIView):
    permission_classes = [IsAuthenticated]

    BATCH_SIZE = 500

    def get(self, request):
        reports = DataIntegrityReport.objects.annotate(
            items_count=Count('items')
        ).order_by('-created_at')
        paginator = StandardPagination()
        page = paginator.paginate_queryset(reports, request, view=self)
        serializer = DataIntegrityReportSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = DataIntegrityReportCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        report = serializer.save()
        thread = threading.Thread(target=self._generate_report, args=(report.id,))
        thread.start()

        return Response({
            'success': True,
            'data': DataIntegrityReportSerializer(report).data
        }, status=status.HTTP_201_CREATED)

    def _generate_report(self, report_id):
        from django import db
        db.connections.close_all()

        try:
            report = DataIntegrityReport.objects.get(id=report_id)
            self._do_generate_report(report)
            report.status = 'COMPLETED'
            report.completed_at = timezone.now()
            report.save()
        except Exception as e:
            logger.exception(f"Report {report_id} generation failed: {e}")
            try:
                report = DataIntegrityReport.objects.get(id=report_id)
                report.status = 'FAILED'
                report.completed_at = timezone.now()
                report.save()
            except:
                pass

    def _do_generate_report(self, report):
        stocks = self._get_stocks_with_listing_dates(report)
        items_to_create = []

        data_types = report.data_types if report.data_types else ['trade_days', 'quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'dividend', 'capital']

        for data_type in data_types:
            if data_type == 'trade_days':
                items = self._check_trade_days_missing(report)
            elif data_type == 'quote':
                items = self._check_quote_missing(report, stocks)
            elif data_type in NON_STOCK_LEVEL_TYPES:
                items = self._check_non_stock_level_missing(report, data_type)
            elif data_type in TABLE_MAPPING:
                items = self._check_missing_periods_batch(report, stocks, data_type)
            else:
                items = []
            items_to_create.extend(items)

        if items_to_create:
            DataIntegrityItem.objects.bulk_create(items_to_create, batch_size=100)

    def _get_stocks_with_listing_dates(self, report):
        with connection.cursor() as cursor:
            if report.stock_scope == 'SELECTED' and report.stock_codes:
                symbols = report.stock_codes
                placeholders = ','.join(['%s'] * len(symbols))
                cursor.execute(f"""
                    SELECT symbol, listing_time FROM saa_stocks
                    WHERE symbol IN ({placeholders})
                      AND listing_time IS NOT NULL
                      AND listing_time <= %s
                """, symbols + [report.date_end])
            else:
                cursor.execute("""
                    SELECT symbol, listing_time FROM saa_stocks
                    WHERE listing_time IS NOT NULL
                      AND listing_time <= %s
                """, [report.date_end])

            return {row[0]: row[1] for row in cursor.fetchall()}

    def _get_check_frequency(self, data_type, report_frequency):
        if data_type in QUARTERLY_TYPES:
            return 'quarterly'
        elif data_type in YEARLY_TYPES:
            return 'yearly'
        return report_frequency

    def _get_latest_trade_date(self, max_date):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT MAX(date) FROM saa_trade_days
                WHERE date <= %s
            """, [max_date])
            result = cursor.fetchone()[0]
            return result

    def _check_quote_missing(self, report, stocks):
        latest_date = self._get_latest_trade_date(report.date_end)
        if not latest_date:
            return []

        symbols = list(stocks.keys())
        if not symbols:
            return []

        table_name = TABLE_MAPPING['quote']
        with connection.cursor() as cursor:
            placeholders = ','.join(['%s'] * len(symbols))
            cursor.execute(f"""
                SELECT DISTINCT symbol FROM {table_name}
                WHERE symbol IN ({placeholders})
            """, symbols)
            existing_symbols = set(row[0] for row in cursor.fetchall())

        missing_items = []
        missing_period = str(latest_date)
        for symbol, listing_date in stocks.items():
            if symbol not in existing_symbols:
                if listing_date and hasattr(listing_date, 'strftime'):
                    listing_date_str = listing_date.strftime('%Y-%m-%d')
                else:
                    listing_date_str = str(listing_date) if listing_date else None

                if listing_date_str and listing_date_str > missing_period:
                    continue

                missing_items.append(DataIntegrityItem(
                    report=report,
                    data_type='quote',
                    stock_code=symbol,
                    missing_periods=[missing_period],
                    selected=False
                ))

        return missing_items

    def _check_non_stock_level_missing(self, report, data_type):
        """检查非股票级别数据的缺失（如估值数据）"""
        config = DATA_TYPE_CONFIG.get(data_type)
        if not config:
            logger.warning(f"No config found for data_type: {data_type}")
            return []

        table_name = config['table']
        date_column = config['date_column']
        data_frequency = config.get('data_frequency', 'daily')

        check_frequency = self._get_check_frequency(data_type, report.frequency)
        expected = self._generate_periods(report.date_start, report.date_end, check_frequency)

        try:
            with connection.cursor() as cursor:
                if check_frequency == 'yearly':
                    select_expr = f"YEAR({date_column})"
                elif check_frequency == 'quarterly':
                    select_expr = f"CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column}))"
                elif check_frequency == 'monthly':
                    select_expr = f"DATE_FORMAT({date_column}, '%Y-%m')"
                elif check_frequency == 'weekly':
                    select_expr = f"CONCAT(YEAR({date_column}), '-W', LPAD(WEEK({date_column}, 1), 2, '0'))"
                else:
                    select_expr = date_column

                cursor.execute(f"""
                    SELECT DISTINCT {select_expr} as period
                    FROM {table_name}
                    WHERE {date_column} BETWEEN %s AND %s
                """, [report.date_start, report.date_end])

                existing = {str(row[0]) for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error checking {data_type} in table {table_name}: {e}")
            return []

        missing_periods = sorted(expected - existing)

        if not missing_periods:
            return []

        return [DataIntegrityItem(
            report=report,
            data_type=data_type,
            stock_code=None,
            missing_periods=missing_periods,
            selected=False
        )]

    def _generate_periods(self, start_date, end_date, frequency):
        periods = set()

        if frequency == 'yearly':
            year = start_date.year
            while year <= end_date.year:
                periods.add(str(year))
                year += 1

        elif frequency == 'quarterly':
            year, month = start_date.year, start_date.month
            q = (month - 1) // 3 + 1
            while True:
                period_date = date(year, (q - 1) * 3 + 1, 1)
                if period_date > end_date:
                    break
                periods.add(f"{year}-Q{q}")
                q += 1
                if q > 4:
                    q = 1
                    year += 1

        elif frequency == 'monthly':
            year, month = start_date.year, start_date.month
            while True:
                period_date = date(year, month, 1)
                if period_date > end_date:
                    break
                periods.add(f"{year}-{month:02d}")
                month += 1
                if month > 12:
                    month = 1
                    year += 1

        elif frequency == 'weekly':
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT
                        CONCAT(YEAR(date), '-W', LPAD(WEEK(date, 1), 2, '0'))
                    FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                """, [start_date, end_date])
                periods = set(row[0] for row in cursor.fetchall())

        elif frequency == 'daily':
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT date FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                """, [start_date, end_date])
                periods = set(str(row[0]) for row in cursor.fetchall())

        return periods

    def _get_period_start_date(self, period, frequency):
        if frequency == 'yearly':
            return date(int(period), 1, 1)
        elif frequency == 'quarterly':
            year, q = int(period[:4]), int(period[-1])
            return date(year, (q - 1) * 3 + 1, 1)
        elif frequency == 'monthly':
            return date(int(period[:4]), int(period[5:7]), 1)
        elif frequency == 'weekly':
            from datetime import datetime
            year, week = int(period[:4]), int(period[6:8])
            return datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w").date()
        elif frequency == 'daily':
            from datetime import datetime
            return datetime.strptime(period, '%Y-%m-%d').date()
        return date(1970, 1, 1)

    def _filter_periods_by_listing_date(self, periods, listing_date, frequency):
        if not listing_date:
            return periods

        filtered = set()
        for period in periods:
            period_start = self._get_period_start_date(period, frequency)
            if period_start >= listing_date:
                filtered.add(period)
        return filtered

    def _get_existing_periods_batch(self, symbols, data_type, start_date, end_date, frequency):
        table_name = TABLE_MAPPING.get(data_type)
        if not table_name:
            return {}

        result = {}

        for i in range(0, len(symbols), self.BATCH_SIZE):
            batch = symbols[i:i + self.BATCH_SIZE]
            batch_result = self._query_periods_batch(batch, table_name, start_date, end_date, frequency)

            for symbol, periods in batch_result.items():
                if symbol not in result:
                    result[symbol] = set()
                result[symbol].update(periods)

        return result

    def _query_periods_batch(self, symbols, table_name, start_date, end_date, frequency):
        placeholders = ','.join(['%s'] * len(symbols))

        if frequency == 'yearly':
            select_expr = "YEAR(date)"
        elif frequency == 'quarterly':
            select_expr = "CONCAT(YEAR(date), '-Q', QUARTER(date))"
        elif frequency == 'monthly':
            select_expr = "DATE_FORMAT(date, '%Y-%m')"
        elif frequency == 'weekly':
            select_expr = "CONCAT(YEAR(date), '-W', LPAD(WEEK(date, 1), 2, '0'))"
        else:
            select_expr = "date"

        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT DISTINCT symbol, {select_expr} as period
                FROM {table_name}
                WHERE symbol IN ({placeholders})
                  AND date BETWEEN %s AND %s
            """, list(symbols) + [start_date, end_date])

            result = {}
            for row in cursor.fetchall():
                symbol, period = row[0], str(row[1])
                if symbol not in result:
                    result[symbol] = set()
                result[symbol].add(period)
            return result

    def _check_trade_days_missing(self, report):
        frequency = self._get_check_frequency('trade_days', report.frequency)

        expected = self._generate_periods(report.date_start, report.date_end, frequency)

        table_name = TABLE_MAPPING['trade_days']
        with connection.cursor() as cursor:
            if frequency == 'yearly':
                select_expr = "YEAR(date)"
            elif frequency == 'quarterly':
                select_expr = "CONCAT(YEAR(date), '-Q', QUARTER(date))"
            elif frequency == 'monthly':
                select_expr = "DATE_FORMAT(date, '%Y-%m')"
            elif frequency == 'weekly':
                select_expr = "CONCAT(YEAR(date), '-W', LPAD(WEEK(date, 1), 2, '0'))"
            else:
                select_expr = "date"

            cursor.execute(f"""
                SELECT DISTINCT {select_expr} as period
                FROM {table_name}
                WHERE date BETWEEN %s AND %s
            """, [report.date_start, report.date_end])

            existing = set(str(row[0]) for row in cursor.fetchall())

        missing = expected - existing

        if missing:
            return [DataIntegrityItem(
                report=report,
                data_type='trade_days',
                stock_code='-',
                missing_periods=sorted(missing),
                selected=False
            )]
        return []

    def _check_missing_periods_batch(self, report, stocks, data_type):
        frequency = self._get_check_frequency(data_type, report.frequency)

        all_periods = self._generate_periods(report.date_start, report.date_end, frequency)

        symbols = list(stocks.keys())
        existing_data = self._get_existing_periods_batch(
            symbols, data_type, report.date_start, report.date_end, frequency
        )

        missing_items = []
        for symbol, listing_date in stocks.items():
            valid_periods = self._filter_periods_by_listing_date(
                all_periods, listing_date, frequency
            )

            existing = existing_data.get(symbol, set())
            missing = valid_periods - existing

            if missing:
                missing_items.append(DataIntegrityItem(
                    report=report,
                    data_type=data_type,
                    stock_code=symbol,
                    missing_periods=sorted(missing),
                    selected=False
                ))

        return missing_items


class DataIntegrityReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        items_queryset = DataIntegrityItem.objects.filter(report=report)

        data_type = request.query_params.get('data_type')
        if data_type:
            data_types = [dt.strip() for dt in data_type.split(',')]
            items_queryset = items_queryset.filter(data_type__in=data_types)

        stock_code = request.query_params.get('stock_code')
        if stock_code:
            items_queryset = items_queryset.filter(stock_code__icontains=stock_code)

        selected = request.query_params.get('selected')
        if selected is not None:
            if selected.lower() == 'true':
                items_queryset = items_queryset.filter(selected=True)
            elif selected.lower() == 'false':
                items_queryset = items_queryset.filter(selected=False)

        status_filter = request.query_params.get('status')
        if status_filter:
            items_queryset = items_queryset.filter(status=status_filter)

        period_filter = request.query_params.get('period')

        flattened_rows = self._flatten_items(items_queryset, period_filter)

        total_count = len(flattened_rows)
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 100))
        start = (page - 1) * page_size
        end = start + page_size
        paginated_rows = flattened_rows[start:end]

        serialized_rows = FlattenedIntegrityItemSerializer(paginated_rows, many=True).data

        selected_count = sum(1 for row in flattened_rows if row['selected'])

        report_data = DataIntegrityReportSerializer(report).data
        report_data['items'] = serialized_rows
        report_data['items_count'] = total_count
        report_data['selected_count'] = selected_count
        report_data['pagination'] = {
            'page': page,
            'page_size': page_size,
            'total': total_count,
            'total_pages': (total_count + page_size - 1) // page_size
        }

        return Response({'success': True, 'data': report_data})

    def _flatten_items(self, items_queryset, period_filter=None):
        flattened = []
        for item in items_queryset:
            for period in item.missing_periods:
                if period_filter and period_filter not in period:
                    continue
                flattened.append({
                    'id': item.id,
                    'data_type': item.data_type,
                    'stock_code': item.stock_code,
                    'period': period,
                    'selected': item.selected,
                    'status': item.status,
                    'status_display': item.get_status_display(),
                    'fixed_at': item.fixed_at,
                })
        return flattened


class DataIntegrityReportItemsUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)
        serializer = DataIntegrityItemBulkUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        item_ids = serializer.validated_data['item_ids']
        selected = serializer.validated_data['selected']
        updated = DataIntegrityItem.objects.filter(
            id__in=item_ids,
            report=report
        ).update(selected=selected)
        return Response({'success': True, 'data': {'updated_count': updated}})


class DataIntegrityReportItemsSelectAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        items_queryset = DataIntegrityItem.objects.filter(report=report)

        data_types = request.data.get('data_types')
        if data_types and len(data_types) > 0:
            items_queryset = items_queryset.filter(data_type__in=data_types)

        stock_code = request.data.get('stock_code')
        if stock_code:
            items_queryset = items_queryset.filter(stock_code__icontains=stock_code)

        period = request.data.get('period')
        if period:
            items_queryset = items_queryset.filter(missing_periods__contains=period)

        status_filter = request.data.get('status')
        if status_filter:
            items_queryset = items_queryset.filter(status=status_filter)

        selected = request.data.get('selected', True)
        updated = items_queryset.update(selected=selected)

        return Response({'success': True, 'data': {'updated_count': updated}})


class DataIntegrityReportGeneratePlanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        if report.status != 'COMPLETED':
            return Response({
                'success': False,
                'error': '报告未完成'
            }, status=status.HTTP_400_BAD_REQUEST)

        all_items = report.items.all()
        if not all_items.exists():
            return Response({
                'success': False,
                'error': '报告中没有缺失项'
            }, status=status.HTTP_400_BAD_REQUEST)

        plan = CollectPlan.objects.create(
            name=f"来自报告: {report.name}",
            source_report=report,
            execution_mode='PARALLEL'
        )

        data_type_items = {}
        for item in all_items:
            if item.data_type not in data_type_items:
                data_type_items[item.data_type] = {
                    'stock_codes': set(),
                    'periods': set()
                }
            data_type_items[item.data_type]['stock_codes'].add(item.stock_code)
            data_type_items[item.data_type]['periods'].update(item.missing_periods)

        for data_type, info in data_type_items.items():
            periods = sorted(info['periods'])
            date_start = periods[0] if periods else report.date_start
            date_end = periods[-1] if periods else report.date_end

            CollectJob.objects.create(
                plan=plan,
                data_type=data_type,
                symbols=list(info['stock_codes']),
                params={
                    'start_date': str(date_start) if date_start else None,
                    'end_date': str(date_end) if date_end else None,
                },
                status='PENDING'
            )

        return Response({
            'success': True,
            'data': CollectPlanSerializer(plan).data
        }, status=status.HTTP_201_CREATED)


class DataIntegrityReportRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        if report.status == 'GENERATING':
            return Response({
                'success': False,
                'error': '报告正在生成中'
            }, status=status.HTTP_400_BAD_REQUEST)

        report.items.all().delete()
        report.status = 'GENERATING'
        report.completed_at = None
        report.save()

        thread = threading.Thread(
            target=DataIntegrityReportListView()._generate_report,
            args=(report.id,)
        )
        thread.start()

        return Response({
            'success': True,
            'data': DataIntegrityReportSerializer(report).data
        })


class DataIntegrityReportHeatmapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from saa_collector.services.completeness_service import CompletenessService
        
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        if report.status != 'COMPLETED':
            return Response({
                'success': True,
                'data': {
                    'date_range': {'start': '', 'end': ''},
                    'frequency': report.frequency,
                    'data_types': [],
                    'periods': [],
                    'matrix': {},
                }
            })

        stock_codes = None
        if report.stock_scope == 'SELECTED' and report.stock_codes:
            stock_codes = report.stock_codes

        service = CompletenessService(
            stock_codes=stock_codes,
            date_end=report.date_end
        )
        
        periods = service.generate_periods(report.frequency, report.date_start, report.date_end)
        
        if not periods:
            return Response({
                'success': True,
                'data': {
                    'date_range': {'start': '', 'end': ''},
                    'frequency': report.frequency,
                    'data_types': [],
                    'periods': [],
                    'matrix': {},
                }
            })

        data_types = report.data_types or []
        result = service.calculate_all(data_types, periods, report.frequency)
        
        return Response({'success': True, 'data': result})

    def _calculate_trade_days_completeness(self, periods, start_date, end_date, frequency=None):
        """计算交易日完整度（非股票级别）"""
        if frequency is None:
            frequency = self.frequency if hasattr(self, 'frequency') else 'monthly'

        existing_periods = self._get_trade_days_periods(start_date, end_date, frequency)

        result = []
        for period in periods:
            if period in existing_periods:
                result.append(1.0)
            else:
                result.append(0.0)

        return result

    def _get_trade_days_periods(self, start_date, end_date, frequency=None):
        """获取交易日实际存在的 periods"""
        if frequency is None:
            frequency = self.frequency if hasattr(self, 'frequency') else 'monthly'
        date_format = self._get_date_format(frequency)
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT DATE_FORMAT(date, %s) as period
                FROM saa_trade_days
                WHERE date BETWEEN %s AND %s
            """, [date_format, start_date, end_date])
            
            periods = set()
            for row in cursor.fetchall():
                period = self._normalize_period(str(row[0]), frequency)
                periods.add(period)
            
            return periods

    def _calculate_quote_completeness(self, calculator, periods, date_end):
        """计算最新行情完整度（非周期性）"""
        latest_date = self._get_latest_trade_date(date_end)
        if not latest_date:
            return [-1] * len(periods)
        
        frequency = self.frequency if hasattr(self, 'frequency') else 'monthly'
        latest_period = calculator._convert_date_to_period(latest_date, frequency)
        
        total_stocks = calculator._get_total_stocks()
        
        with connection.cursor() as cursor:
            if calculator.stock_codes:
                cursor.execute("""
                    SELECT COUNT(DISTINCT symbol) FROM saa_latest_prices
                    WHERE symbol IN %s
                """, [calculator.stock_codes])
            else:
                cursor.execute("SELECT COUNT(DISTINCT symbol) FROM saa_latest_prices")
            
            data_count = cursor.fetchone()[0] or 0
        
        if total_stocks > 0:
            completeness = round(data_count / total_stocks, 2)
            completeness = min(1.0, max(0.0, completeness))
        else:
            completeness = -1
        
        result = []
        for period in periods:
            if period == latest_period:
                result.append(completeness)
            else:
                result.append(-1)
        
        return result

    def _get_latest_trade_date(self, max_date):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT MAX(date) FROM saa_trade_days
                WHERE date <= %s
            """, [max_date])
            result = cursor.fetchone()[0]
            return result

    def _get_date_format(self, frequency):
        if frequency == 'yearly':
            return '%Y'
        elif frequency == 'quarterly':
            return '%Y-%m'
        elif frequency == 'monthly':
            return '%Y-%m'
        elif frequency == 'weekly':
            return '%Y-%m-%d'
        else:
            return '%Y-%m-%d'

    def _get_period_start_date(self, period, frequency):
        if frequency == 'yearly':
            return date(int(period), 1, 1)
        elif frequency == 'quarterly':
            year = int(period[:4])
            q = int(period[-1])
            return date(year, (q - 1) * 3 + 1, 1)
        elif frequency == 'monthly':
            return date(int(period[:4]), int(period[5:7]), 1)
        elif frequency == 'weekly':
            from datetime import datetime
            year = int(period[:4])
            week = int(period[6:8])
            return datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w").date()
        elif frequency == 'daily':
            from datetime import datetime
            return datetime.strptime(period, '%Y-%m-%d').date()
        return date(1970, 1, 1)

    def _normalize_period(self, period_str, frequency):
        if not period_str:
            return period_str
        
        if frequency == 'quarterly':
            try:
                parts = period_str.split('-')
                if len(parts) == 2:
                    year = int(parts[0])
                    month = int(parts[1])
                    quarter = (month - 1) // 3 + 1
                    return f"{year}-Q{quarter}"
            except (ValueError, IndexError):
                pass
        
        return period_str

    def _generate_periods(self, start_date, end_date, frequency):
        periods = set()

        if not start_date or not end_date:
            return periods

        if frequency == 'yearly':
            year = start_date.year
            while year <= end_date.year:
                periods.add(str(year))
                year += 1

        elif frequency == 'quarterly':
            year, month = start_date.year, start_date.month
            q = (month - 1) // 3 + 1
            while True:
                period_date = date(year, (q - 1) * 3 + 1, 1)
                if period_date > end_date:
                    break
                periods.add(f"{year}-Q{q}")
                q += 1
                if q > 4:
                    q = 1
                    year += 1

        elif frequency == 'monthly':
            year, month = start_date.year, start_date.month
            while True:
                period_date = date(year, month, 1)
                if period_date > end_date:
                    break
                periods.add(f"{year}-{month:02d}")
                month += 1
                if month > 12:
                    month = 1
                    year += 1

        elif frequency == 'weekly':
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT
                        CONCAT(YEAR(date), '-W', LPAD(WEEK(date, 1), 2, '0'))
                    FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                """, [start_date, end_date])
                periods = set(row[0] for row in cursor.fetchall())

        elif frequency == 'daily':
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT date FROM saa_trade_days
                    WHERE date BETWEEN %s AND %s
                """, [start_date, end_date])
                periods = set(str(row[0]) for row in cursor.fetchall())

        return periods


DATA_TYPE_LABELS = {
    'quote': '最新行情',
    'historical_quote': '历史行情',
    'balance_sheet': '资产负债表',
    'income': '利润表',
    'cash_flow': '现金流量表',
    'dividend': '分红数据',
    'main_business': '主营业务',
    'capital': '股本变动',
    'trade_days': '交易日',
    'valuation_board': '板块估值',
    'valuation_industry': '行业估值',
}


def period_to_months(period, frequency):
    """
    将 period 字符串映射到 YYYY-MM 格式的集合。
    一个 period 可能对应多个月（如 quarterly, yearly）。
    """
    if not period:
        return set()

    if frequency == 'daily':
        if len(period) >= 7:
            return {period[:7]}
    elif frequency == 'weekly':
        try:
            year = int(period[:4])
            week = int(period[6:8]) if len(period) >= 8 else int(period[6:])
            from datetime import datetime
            d = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w").date()
            return {f"{d.year}-{d.month:02d}"}
        except (ValueError, IndexError):
            pass
    elif frequency == 'monthly':
        return {period}
    elif frequency == 'quarterly':
        try:
            year = int(period[:4])
            if 'Q' in period:
                q = int(period.split('Q')[1])
            else:
                q = int(period[-1])
            start_month = (q - 1) * 3 + 1
            return {f"{year}-{m:02d}" for m in range(start_month, start_month + 3)}
        except (ValueError, IndexError):
            pass
    elif frequency == 'yearly':
        try:
            year = int(period)
            return {f"{year}-{m:02d}" for m in range(1, 13)}
        except ValueError:
            pass
    return set()


class DataIntegrityReportSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        if report.status != 'COMPLETED':
            return Response({
                'success': True,
                'data': {
                    'by_data_type': [],
                    'by_period': [],
                    'total_missing': 0,
                    'total_stocks': 0,
                }
            })

        data_types_filter = request.query_params.get('data_types')
        stock_codes_filter = request.query_params.get('stock_codes')
        status_filter = request.query_params.get('status', 'PENDING')

        items_qs = DataIntegrityItem.objects.filter(report=report)

        if status_filter:
            items_qs = items_qs.filter(status=status_filter)

        if data_types_filter:
            data_types_list = [dt.strip() for dt in data_types_filter.split(',')]
            items_qs = items_qs.filter(data_type__in=data_types_list)

        if stock_codes_filter:
            stock_codes_list = [sc.strip() for sc in stock_codes_filter.split(',')]
            items_qs = items_qs.filter(stock_code__in=stock_codes_list)

        by_data_type = self._aggregate_by_data_type(items_qs)
        by_period = self._aggregate_by_period(items_qs, report.frequency)

        total_missing = sum(item['missing_count'] for item in by_data_type)
        total_stocks = len(set(
            item.stock_code for item in items_qs
            if item.stock_code
        ))

        return Response({
            'success': True,
            'data': {
                'by_data_type': by_data_type,
                'by_period': by_period,
                'total_missing': total_missing,
                'total_stocks': total_stocks,
            }
        })

    def _aggregate_by_data_type(self, items_qs):
        data_type_stats = {}
        for item in items_qs:
            if item.data_type not in data_type_stats:
                data_type_stats[item.data_type] = {
                    'missing_count': 0,
                    'stock_codes': set(),
                }
            data_type_stats[item.data_type]['missing_count'] += len(item.missing_periods or [])
            if item.stock_code:
                data_type_stats[item.data_type]['stock_codes'].add(item.stock_code)

        result = []
        for data_type, stats in data_type_stats.items():
            result.append({
                'data_type': data_type,
                'label': DATA_TYPE_LABELS.get(data_type, data_type),
                'missing_count': stats['missing_count'],
                'stock_count': len(stats['stock_codes']),
            })

        result.sort(key=lambda x: x['missing_count'], reverse=True)
        return result

    def _aggregate_by_period(self, items_qs, frequency):
        month_stats = {}

        for item in items_qs:
            for period in (item.missing_periods or []):
                months = period_to_months(period, frequency)
                for month in months:
                    if month not in month_stats:
                        month_stats[month] = 0
                    month_stats[month] += 1

        if not month_stats:
            return []

        year_data = {}
        for month_key, count in month_stats.items():
            year = int(month_key[:4])
            month = int(month_key[5:7])
            quarter = (month - 1) // 3 + 1

            if year not in year_data:
                year_data[year] = {
                    'missing_count': 0,
                    'quarters': {},
                }
            year_data[year]['missing_count'] += count

            if quarter not in year_data[year]['quarters']:
                year_data[year]['quarters'][quarter] = {
                    'missing_count': 0,
                    'months': {},
                }
            year_data[year]['quarters'][quarter]['missing_count'] += count
            year_data[year]['quarters'][quarter]['months'][month] = count

        result = []
        for year in sorted(year_data.keys(), reverse=True):
            year_entry = {
                'year': year,
                'missing_count': year_data[year]['missing_count'],
                'quarters': [],
            }
            for quarter in sorted(year_data[year]['quarters'].keys()):
                q_data = year_data[year]['quarters'][quarter]
                quarter_entry = {
                    'quarter': quarter,
                    'missing_count': q_data['missing_count'],
                    'months': [],
                }
                for month in sorted(q_data['months'].keys()):
                    quarter_entry['months'].append({
                        'month': month,
                        'missing_count': q_data['months'][month],
                    })
                year_entry['quarters'].append(quarter_entry)
            result.append(year_entry)

        return result


class DataIntegrityReportGeneratePlanByRangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        if report.status != 'COMPLETED':
            return Response({
                'success': False,
                'error': '报告未完成'
            }, status=status.HTTP_400_BAD_REQUEST)

        data_types = request.data.get('data_types', [])
        periods = request.data.get('periods', [])
        stock_scope = request.data.get('stock_scope', 'ALL')
        stock_codes = request.data.get('stock_codes', [])

        if not data_types:
            return Response({
                'success': False,
                'error': '请至少选择一个数据类型'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not periods:
            return Response({
                'success': False,
                'error': '请至少选择一个时间范围'
            }, status=status.HTTP_400_BAD_REQUEST)

        items_qs = DataIntegrityItem.objects.filter(
            report=report,
            data_type__in=data_types,
            status='PENDING'
        )

        if stock_scope == 'SELECTED' and stock_codes:
            items_qs = items_qs.filter(stock_code__in=stock_codes)

        selected_months = set()
        for period in periods:
            if len(period) == 4 and period.isdigit():
                year = int(period)
                for m in range(1, 13):
                    selected_months.add(f"{year}-{m:02d}")
            elif '-Q' in period:
                year = int(period[:4])
                q = int(period.split('Q')[1])
                start_month = (q - 1) * 3 + 1
                for m in range(start_month, start_month + 3):
                    selected_months.add(f"{year}-{m:02d}")
            else:
                selected_months.add(period)

        data_type_groups = {}

        logger.info(f"[generate-plan-by-range] report.frequency={report.frequency}, selected_months={selected_months}")

        for item in items_qs.iterator():
            matched = self._match_periods(item.missing_periods, selected_months, report.frequency)
            logger.info(f"[generate-plan-by-range] item.data_type={item.data_type}, missing_periods={item.missing_periods[:5] if item.missing_periods else []}, matched={matched}")
            if not matched:
                continue

            if item.data_type not in data_type_groups:
                data_type_groups[item.data_type] = {
                    'stock_codes': set(),
                    'periods': set(),
                }
            if item.stock_code:
                data_type_groups[item.data_type]['stock_codes'].add(item.stock_code)
            data_type_groups[item.data_type]['periods'].update(matched)

        logger.info(f"[generate-plan-by-range] data_type_groups periods: {[(k, sorted(v['periods'])) for k, v in data_type_groups.items()]}")

        if not data_type_groups:
            return Response({
                'success': False,
                'error': '没有找到匹配的缺失项'
            }, status=status.HTTP_400_BAD_REQUEST)

        plan = CollectPlan.objects.create(
            name=f"来自报告: {report.name}（按范围修复）",
            source_report=report,
            execution_mode='PARALLEL'
        )

        for data_type, info in data_type_groups.items():
            sorted_periods = sorted(info['periods'])
            start_month = sorted_periods[0] if sorted_periods else None
            end_month = sorted_periods[-1] if sorted_periods else None
            CollectJob.objects.create(
                plan=plan,
                data_type=data_type,
                symbols=list(info['stock_codes']),
                params={
                    'start_date': self._month_to_start_date(start_month),
                    'end_date': self._month_to_end_date(end_month),
                },
                status='PENDING'
            )

        return Response({
            'success': True,
            'data': {
                'id': plan.id,
                'name': plan.name,
                'jobs_count': len(data_type_groups),
            }
        }, status=status.HTTP_201_CREATED)

    def _month_to_start_date(self, year_month: str | None) -> str | None:
        """Convert YYYY-MM to YYYY-MM-01 (first day of month)"""
        if not year_month:
            return None
        return f"{year_month}-01"

    def _month_to_end_date(self, year_month: str | None) -> str | None:
        """Convert YYYY-MM to YYYY-MM-DD (last day of month)"""
        if not year_month:
            return None
        from calendar import monthrange
        year, month = map(int, year_month.split('-'))
        last_day = monthrange(year, month)[1]
        return f"{year_month}-{last_day:02d}"

    def _match_periods(self, missing_periods, selected_months, frequency):
        """
        返回 missing_periods 中与 selected_months 有交集的月份 (YYYY-MM 格式)。
        """
        if not missing_periods:
            return set()

        matched_months = set()
        for period in missing_periods:
            period_months = period_to_months(period, frequency)
            matched_months.update(period_months & selected_months)
        return matched_months


class DataIntegrityReportTreeSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        if report.status != 'COMPLETED':
            return Response({
                'success': True,
                'data': {'tree': []}
            })

        status_filter = request.query_params.get('status', 'PENDING')

        items_qs = DataIntegrityItem.objects.filter(report=report)

        if status_filter:
            items_qs = items_qs.filter(status=status_filter)

        tree = self._build_tree(items_qs, report.frequency)

        return Response({
            'success': True,
            'data': {'tree': tree}
        })

    def _build_tree(self, items_qs, report_frequency):
        data_type_period_stats = {}

        for item in items_qs:
            data_type = item.data_type
            if data_type not in data_type_period_stats:
                data_type_period_stats[data_type] = {}

            frequency = DATA_TYPE_FREQUENCY.get(data_type, report_frequency)

            for period in (item.missing_periods or []):
                if period not in data_type_period_stats[data_type]:
                    data_type_period_stats[data_type][period] = 0
                data_type_period_stats[data_type][period] += 1

        tree = []
        for data_type, period_stats in data_type_period_stats.items():
            frequency = DATA_TYPE_FREQUENCY.get(data_type, report_frequency)

            data_type_node = {
                'key': data_type,
                'label': DATA_TYPE_LABELS.get(data_type, data_type),
                'count': sum(period_stats.values()),
                'children': []
            }

            if frequency == 'yearly':
                year_data = {}
                for period, count in period_stats.items():
                    try:
                        year = int(period)
                        year_data[year] = year_data.get(year, 0) + count
                    except ValueError:
                        continue

                for year in sorted(year_data.keys(), reverse=True):
                    year_node = {
                        'key': f"{data_type}-{year}",
                        'label': f"{year}年",
                        'count': year_data[year],
                    }
                    data_type_node['children'].append(year_node)

            elif frequency == 'quarterly':
                year_data = {}
                for period, count in period_stats.items():
                    try:
                        year = int(period[:4])
                        if 'Q' in period:
                            q = int(period.split('Q')[1])
                        else:
                            q = int(period[-1])
                        if year not in year_data:
                            year_data[year] = {}
                        year_data[year][q] = year_data[year].get(q, 0) + count
                    except (ValueError, IndexError):
                        continue

                for year in sorted(year_data.keys(), reverse=True):
                    year_node = {
                        'key': f"{data_type}-{year}",
                        'label': f"{year}年",
                        'count': sum(year_data[year].values()),
                        'children': []
                    }

                    for quarter in sorted(year_data[year].keys()):
                        quarter_node = {
                            'key': f"{data_type}-{year}-Q{quarter}",
                            'label': f"Q{quarter}",
                            'count': year_data[year][quarter],
                        }
                        year_node['children'].append(quarter_node)

                    data_type_node['children'].append(year_node)

            else:
                month_stats = {}
                for period, count in period_stats.items():
                    months = period_to_months(period, frequency)
                    for month_key in months:
                        month_stats[month_key] = month_stats.get(month_key, 0) + count

                year_data = {}
                for month_key, count in month_stats.items():
                    try:
                        year = int(month_key[:4])
                        month = int(month_key[5:7])
                        quarter = (month - 1) // 3 + 1

                        if year not in year_data:
                            year_data[year] = {}
                        if quarter not in year_data[year]:
                            year_data[year][quarter] = {}
                        year_data[year][quarter][month] = count
                    except (ValueError, IndexError):
                        continue

                for year in sorted(year_data.keys(), reverse=True):
                    year_node = {
                        'key': f"{data_type}-{year}",
                        'label': f"{year}年",
                        'count': sum(
                            sum(quarter_data.values())
                            for quarter_data in year_data[year].values()
                        ),
                        'children': []
                    }

                    for quarter in sorted(year_data[year].keys()):
                        q_data = year_data[year][quarter]
                        quarter_node = {
                            'key': f"{data_type}-{year}-Q{quarter}",
                            'label': f"Q{quarter}",
                            'count': sum(q_data.values()),
                            'children': []
                        }

                        for month in sorted(q_data.keys()):
                            month_node = {
                                'key': f"{data_type}-{year}-{month:02d}",
                                'label': f"{month}月",
                                'count': q_data[month],
                            }
                            quarter_node['children'].append(month_node)

                        year_node['children'].append(quarter_node)

                    data_type_node['children'].append(year_node)

            tree.append(data_type_node)

        tree.sort(key=lambda x: x['count'], reverse=True)
        return tree


class CollectPlanListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plans = CollectPlan.objects.all()
        paginator = StandardPagination()
        page = paginator.paginate_queryset(plans, request, view=self)
        serializer = CollectPlanSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = CollectPlanCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        plan = serializer.save()
        return Response({
            'success': True,
            'data': CollectPlanSerializer(plan).data
        }, status=status.HTTP_201_CREATED)


class CollectPlanDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)
        serializer = CollectPlanSerializer(plan)
        return Response({'success': True, 'data': serializer.data})

    def patch(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)

        if plan.status != 'PENDING':
            return Response({
                'success': False,
                'error': '只能编辑待执行的计划'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = CollectPlanUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        for key, value in serializer.validated_data.items():
            setattr(plan, key, value)
        plan.save()

        return Response({'success': True, 'data': CollectPlanSerializer(plan).data})

    def delete(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)

        if plan.status != 'PENDING':
            return Response({
                'success': False,
                'error': '只能删除待执行的计划'
            }, status=status.HTTP_400_BAD_REQUEST)

        plan.delete()
        return Response({'success': True})


class CollectPlanExecuteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)

        if plan.status in ('COMPLETED', 'FAILED'):
            plan.status = 'PENDING'
            plan.started_at = None
            plan.completed_at = None
            plan.jobs.update(
                status='PENDING',
                start_time=None,
                end_time=None,
                message=None
            )

        if plan.status != 'PENDING':
            return Response({
                'success': False,
                'error': '计划状态不正确'
            }, status=status.HTTP_400_BAD_REQUEST)

        plan.status = 'RUNNING'
        plan.started_at = timezone.now()
        plan.save()

        thread = threading.Thread(target=self._execute_plan, args=(plan.id,))
        thread.start()

        return Response({'success': True, 'data': CollectPlanSerializer(plan).data})

    def _execute_plan(self, plan_id):
        from django import db
        db.connections.close_all()

        try:
            plan = CollectPlan.objects.get(id=plan_id)
            jobs = list(plan.jobs.all())

            if plan.execution_mode == 'PARALLEL':
                threads = []
                for job in jobs:
                    t = threading.Thread(target=self._execute_job, args=(job.id,))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()
            else:
                for job in jobs:
                    self._execute_job(job.id)

            plan.refresh_from_db()
            if plan.jobs.filter(status='FAILED').exists():
                plan.status = 'FAILED'
            else:
                plan.status = 'COMPLETED'
                self._update_report_items(plan)
            plan.completed_at = timezone.now()
            plan.save()
        except Exception as e:
            logger.exception(f"Plan {plan_id} execution failed: {e}")
            try:
                plan = CollectPlan.objects.get(id=plan_id)
                plan.status = 'FAILED'
                plan.completed_at = timezone.now()
                plan.save()
            except:
                pass

    def _execute_job(self, job_id):
        from django import db
        db.connections.close_all()

        try:
            job = CollectJob.objects.get(id=job_id)
            job.start()
            self._execute_collect(job)
            job.complete(success=True, message='执行完成')
        except Exception as e:
            logger.exception(f"Job {job_id} execution failed: {e}")
            try:
                job = CollectJob.objects.get(id=job_id)
                job.complete(success=False, message=str(e))
            except:
                pass

    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        from datetime import datetime

        factory = CompoundServiceFactory()
        data_type = job.data_type
        symbols = job.symbols if job.symbols else None
        start_date = job.params.get('start_date')
        end_date = job.params.get('end_date')

        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        if data_type == 'trade_days':
            service = factory.create_calendar_service()
            service.collect(start_date, end_date)
        elif data_type == 'stock_info':
            service = factory.create_stock_info_service()
            service.collect(symbols)
        elif data_type == 'quote':
            service = factory.create_quote_service()
            service.collect(symbols)
        elif data_type == 'historical_quote':
            service = factory.create_quote_service()
            service.collect_historical(symbols, start_date=start_date, end_date=end_date)
        elif data_type in ('balance_sheet', 'income', 'cash_flow', 'dividend'):
            service = factory.create_statement_service()
            report_types = job.params.get('report_types', [])
            if data_type == 'balance_sheet' or 'balance_sheet' in report_types:
                service.collect_balance_sheet(symbols, start_date)
            if data_type == 'income' or 'income' in report_types:
                service.collect_income(symbols, start_date)
            if data_type == 'cash_flow' or 'cash_flow' in report_types:
                service.collect_cash_flow(symbols, start_date)
            if data_type == 'dividend' or 'dividend' in report_types:
                service.collect_dividend(symbols, start_date)
        elif data_type == 'capital':
            service = factory.create_capital_service()
            service.collect(symbols, start_date)
        elif data_type == 'main_business':
            service = factory.create_statement_service()
            service.collect_main_business(symbols, start_date)
        elif data_type == 'valuation':
            from saa_collector.jobs.valuation_collect_job import ValuationCollectJob
            collect_job = ValuationCollectJob()
            collect_job()
        else:
            logger.warning(f"Unknown data type: {data_type}")

    def _update_report_items(self, plan):
        if not plan.source_report:
            return

        successful_jobs = plan.jobs.filter(status='SUCCESS')
        for job in successful_jobs:
            DataIntegrityItem.objects.filter(
                report=plan.source_report,
                data_type=job.data_type,
                stock_code__in=job.symbols,
                status='PENDING'
            ).update(
                status='FIXED',
                fixed_at=timezone.now(),
                fixed_by_plan=plan
            )


class DataCompletenessHeatmapView(APIView):
    permission_classes = [IsAuthenticated]

    DATA_TYPE_CONFIG = [
        ('trade_days', '交易日', 'saa_trade_days', 'date', 'daily'),
        ('stock_info', '股票基本信息', 'saa_stocks', None, None),
        ('quote', '最新行情', 'saa_latest_prices', 'date', None),
        ('historical_quote', '历史行情', 'saa_prices_ex', 'date', 'daily'),
        ('balance_sheet', '资产负债表', 'saa_raw_balance_sheet', 'date', 'quarterly'),
        ('income', '利润表', 'saa_raw_income_statement', 'date', 'quarterly'),
        ('cash_flow', '现金流量表', 'saa_raw_cash_flow_statement', 'date', 'quarterly'),
        ('main_business', '主营业务', 'saa_raw_main_business', 'date', 'quarterly'),
        ('capital', '股本变动', 'saa_capitals', 'date', 'yearly'),
        ('dividend', '分红数据', 'saa_dividends', 'date', 'yearly'),
        ('valuation_board', '板块估值', 'saa_board_valuation_level', 'report_date', 'daily'),
        ('valuation_industry', '行业估值', 'saa_industry_valuation_levels', 'report_date', 'daily'),
    ]

    def get(self, request):
        frequency = request.query_params.get('frequency', 'monthly')
        
        periods = self._generate_periods(frequency)
        if not periods:
            return Response({'success': False, 'error': 'Invalid frequency'}, status=400)

        data_types = [{'key': key, 'label': label, 'frequency': data_freq} for key, label, _, _, data_freq in self.DATA_TYPE_CONFIG]
        matrix = {}

        with connection.cursor() as cursor:
            for key, label, table_name, date_column, data_frequency in self.DATA_TYPE_CONFIG:
                if date_column is None:
                    matrix[key] = [1.0] * len(periods)
                    continue
                
                if data_frequency is None:
                    matrix[key] = self._calculate_point_completeness(cursor, table_name, date_column, len(periods))
                    continue
                
                try:
                    matrix[key] = self._calculate_completeness(
                        cursor, table_name, date_column, periods, frequency, data_frequency
                    )
                except Exception as e:
                    logger.warning(f"Failed to calculate completeness for {key}: {e}")
                    matrix[key] = [0.0] * len(periods)

        start_date = periods[0] if periods else ''
        end_date = periods[-1] if periods else ''

        return Response({
            'success': True,
            'data': {
                'date_range': {'start': start_date, 'end': end_date},
                'frequency': frequency,
                'periods': periods,
                'data_types': data_types,
                'matrix': matrix,
            }
        })

    def _generate_periods(self, frequency):
        periods = []
        today = date.today()
        
        if frequency == 'daily':
            start = today - timedelta(days=365)
            current = start
            while current <= today:
                periods.append(current.strftime('%Y-%m-%d'))
                current += timedelta(days=1)
        elif frequency == 'monthly':
            year, month = EARLIEST_YEAR, 1
            while date(year, month, 1) <= today:
                periods.append(f"{year}-{month:02d}")
                month += 1
                if month > 12:
                    month = 1
                    year += 1
        elif frequency == 'quarterly':
            year, quarter = EARLIEST_YEAR, 1
            while date(year, quarter * 3, 1) <= today:
                periods.append(f"{year}-Q{quarter}")
                quarter += 1
                if quarter > 4:
                    quarter = 1
                    year += 1
        elif frequency == 'yearly':
            year = EARLIEST_YEAR
            while year <= today.year:
                periods.append(str(year))
                year += 1
        else:
            return None
        
        return periods

    def _calculate_point_completeness(self, cursor, table_name, date_column, num_periods):
        cursor.execute(f"SELECT COUNT(DISTINCT symbol) FROM {table_name}")
        quote_count = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM saa_stocks")
        total_stocks = cursor.fetchone()[0] or 1
        
        ratio = round(quote_count / total_stocks, 2) if total_stocks > 0 else 0.0
        return [ratio] * num_periods

    def _calculate_completeness(self, cursor, table_name, date_column, periods, frequency, data_frequency):
        if not periods:
            return []
        
        need_aggregation = (
            (data_frequency == 'yearly' and frequency in ('quarterly', 'monthly')) or
            (data_frequency == 'quarterly' and frequency == 'monthly')
        )
        
        if need_aggregation:
            return self._calculate_completeness_aggregated(cursor, table_name, date_column, periods, frequency, data_frequency)
        
        result = []
        for period in periods:
            if not self._is_period_applicable(period, frequency, data_frequency):
                result.append(-1)
            else:
                result.append(None)
        
        applicable_indices = [i for i, v in enumerate(result) if v is None]
        if not applicable_indices:
            return result
        
        applicable_periods = [periods[i] for i in applicable_indices]
        start_date, end_date = self._get_period_range(applicable_periods[0], frequency)
        _, end_date = self._get_period_range(applicable_periods[-1], frequency)
        
        date_format = self._get_date_format(frequency)
        
        cursor.execute(f"""
            SELECT DATE_FORMAT({date_column}, %s) as period, COUNT(*) as cnt
            FROM {table_name}
            WHERE {date_column} >= %s AND {date_column} <= %s
            GROUP BY DATE_FORMAT({date_column}, %s)
        """, [date_format, start_date, end_date, date_format])
        
        period_counts = {self._get_period_key(row[0], frequency): row[1] for row in cursor.fetchall()}
        
        max_count = max(period_counts.values()) if period_counts else 1
        
        for i in applicable_indices:
            period = periods[i]
            period_key = self._get_period_key(period, frequency)
            count = period_counts.get(period_key, 0)
            result[i] = round(count / max_count, 2)
        
        return result

    def _calculate_completeness_aggregated(self, cursor, table_name, date_column, periods, frequency, data_frequency):
        aggregate_keys = {}
        for i, period in enumerate(periods):
            agg_key = self._get_aggregate_key(period, data_frequency)
            if agg_key not in aggregate_keys:
                aggregate_keys[agg_key] = []
            aggregate_keys[agg_key].append(i)
        
        start_date, end_date = self._get_period_range(periods[0], frequency)
        _, end_date = self._get_period_range(periods[-1], frequency)
        
        if data_frequency == 'yearly':
            cursor.execute(f"""
                SELECT YEAR({date_column}) as year, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s
                GROUP BY YEAR({date_column})
            """, [start_date, end_date])
            raw_counts = {str(row[0]): row[1] for row in cursor.fetchall()}
        else:
            cursor.execute(f"""
                SELECT DATE_FORMAT({date_column}, '%Y-%m') as month, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s
                GROUP BY DATE_FORMAT({date_column}, '%Y-%m')
            """, [start_date, end_date])
            raw_counts = {}
            for row in cursor.fetchall():
                month_str = row[0]
                year = month_str[:4]
                month = int(month_str[5:7])
                quarter = (month - 1) // 3 + 1
                quarter_key = f"{year}-Q{quarter}"
                if quarter_key not in raw_counts:
                    raw_counts[quarter_key] = 0
                raw_counts[quarter_key] += row[1]
        
        max_count = max(raw_counts.values()) if raw_counts else 1
        
        result = [0.0] * len(periods)
        for agg_key, indices in aggregate_keys.items():
            count = raw_counts.get(agg_key, 0)
            value = round(count / max_count, 2)
            for i in indices:
                result[i] = value
        
        return result

    def _get_aggregate_key(self, period, data_frequency):
        if data_frequency == 'yearly':
            return period[:4]
        elif data_frequency == 'quarterly':
            year = period[:4]
            month = int(period[5:7])
            quarter = (month - 1) // 3 + 1
            return f"{year}-Q{quarter}"
        return period

    def _get_period_key(self, period, frequency):
        if frequency == 'quarterly':
            if '-Q' in period:
                year = period[:4]
                quarter = int(period[6])
                end_month = quarter * 3
                return f"{year}-{end_month:02d}"
            return period
        return period

    def _is_period_applicable(self, period, frequency, data_frequency):
        if data_frequency is None or data_frequency == 'daily':
            return True
        
        if data_frequency == 'quarterly':
            if frequency == 'daily':
                return False
            if frequency == 'monthly':
                month = int(period[5:7])
                return month in (3, 6, 9, 12)
            return True
        
        if data_frequency == 'yearly':
            if frequency in ('daily', 'monthly'):
                return False
            if frequency == 'quarterly':
                quarter = int(period[6])
                return quarter == 4
            return True
        
        return True

    def _get_date_format(self, frequency):
        formats = {
            'daily': '%Y-%m-%d',
            'monthly': '%Y-%m',
            'quarterly': '%Y-%m',
            'yearly': '%Y',
        }
        return formats.get(frequency, '%Y-%m')

    def _get_period_range(self, period, frequency):
        if frequency == 'daily':
            return period, period
        elif frequency == 'monthly':
            year, month = int(period[:4]), int(period[5:7])
            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1) - timedelta(days=1)
            return f"{year}-{month:02d}-01", end.strftime('%Y-%m-%d')
        elif frequency == 'quarterly':
            year, quarter = int(period[:4]), int(period[6])
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            end_day = 31 if end_month in [3, 12] else 30 if end_month in [4, 6, 9, 11] else 28
            return f"{year}-{start_month:02d}-01", f"{year}-{end_month:02d}-{end_day}"
        elif frequency == 'yearly':
            year = int(period)
            return f"{year}-01-01", f"{year}-12-31"
        return period, period


class DisplayFieldConfigView(APIView):
    permission_classes = [IsAuthenticated]

    TABLE_LABEL_MAP = {
        'saa_stocks': '基本信息',
        'saa_latest_prices': '最新行情',
        'saa_prices_ex': '历史行情',
        'saa_raw_balance_sheet': '资产负债表',
        'saa_raw_income_statement': '利润表',
        'saa_raw_cash_flow_statement': '现金流量表',
        'saa_raw_main_business': '主营业务',
        'saa_capitals': '股本变动',
        'saa_dividends': '分红数据',
    }

    DATA_TYPE_GROUPS = [
        {
            'key': 'basic',
            'label': '基本信息',
            'items': [
                {'key': 'info', 'label': '基本信息', 'table': 'saa_stocks'},
            ]
        },
        {
            'key': 'quote',
            'label': '行情数据',
            'items': [
                {'key': 'quote', 'label': '最新行情', 'table': 'saa_latest_prices'},
                {'key': 'historical_quote', 'label': '历史行情', 'table': 'saa_prices_ex'},
            ]
        },
        {
            'key': 'statement',
            'label': '财务报表',
            'items': [
                {'key': 'balance_sheet', 'label': '资产负债表', 'table': 'saa_raw_balance_sheet'},
                {'key': 'income', 'label': '利润表', 'table': 'saa_raw_income_statement'},
                {'key': 'cash_flow', 'label': '现金流量表', 'table': 'saa_raw_cash_flow_statement'},
            ]
        },
        {
            'key': 'other',
            'label': '其他数据',
            'items': [
                {'key': 'main_business', 'label': '主营业务', 'table': 'saa_raw_main_business'},
                {'key': 'capital', 'label': '股本变动', 'table': 'saa_capitals'},
                {'key': 'dividend', 'label': '分红数据', 'table': 'saa_dividends'},
            ]
        },
    ]

    def get(self, request):
        table_name = request.query_params.get('table')
        
        with connection.cursor() as cursor:
            if table_name:
                cursor.execute(
                    "SELECT table_name, table_label, config FROM display_field_config WHERE table_name = %s",
                    [table_name]
                )
                row = cursor.fetchone()
                if row:
                    return Response({
                        'success': True,
                        'data': {
                            'table_name': row[0],
                            'table_label': row[1],
                            'config': json.loads(row[2]) if isinstance(row[2], str) else row[2]
                        }
                    })
                return Response({'success': False, 'error': 'Table not found'}, status=404)
            else:
                cursor.execute("SELECT table_name, table_label, config FROM display_field_config")
                configs = {}
                for row in cursor.fetchall():
                    configs[row[0]] = {
                        'table_label': row[1],
                        'config': json.loads(row[2]) if isinstance(row[2], str) else row[2]
                    }
                return Response({
                    'success': True,
                    'data': {
                        'groups': self.DATA_TYPE_GROUPS,
                        'configs': configs
                    }
                })

    def put(self, request):
        table_name = request.data.get('table_name')
        config = request.data.get('config')
        
        if not table_name or not config:
            return Response({'success': False, 'error': 'Missing table_name or config'}, status=400)
        
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE display_field_config SET config = %s WHERE table_name = %s",
                [json.dumps(config), table_name]
            )
            if cursor.rowcount == 0:
                return Response({'success': False, 'error': 'Table not found'}, status=404)
        
        return Response({'success': True})


class StockDataView(APIView):
    permission_classes = [IsAuthenticated]

    DATE_COLUMN_MAP = {
        'saa_stocks': None,
        'saa_latest_prices': 'date',
        'saa_prices_ex': 'date',
        'saa_raw_balance_sheet': 'date',
        'saa_raw_income_statement': 'date',
        'saa_raw_cash_flow_statement': 'date',
        'saa_raw_main_business': 'date',
        'saa_capitals': 'date',
        'saa_dividends': 'date',
    }

    NEEDS_STOCK_NAME = {
        'saa_latest_prices',
        'saa_prices_ex',
        'saa_raw_balance_sheet',
        'saa_raw_income_statement',
        'saa_raw_cash_flow_statement',
        'saa_raw_main_business',
        'saa_capitals',
        'saa_dividends',
    }

    def get(self, request, symbol, table_name):
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        offset = (page - 1) * page_size

        date_column = self.DATE_COLUMN_MAP.get(table_name, 'date')
        order_clause = f"ORDER BY t.{date_column} DESC" if date_column else ""

        with connection.cursor() as cursor:
            if table_name in self.NEEDS_STOCK_NAME:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE symbol = %s",
                    [symbol]
                )
                total = cursor.fetchone()[0]

                cursor.execute(
                    f"""
                    SELECT t.*, s.name as stock_name
                    FROM {table_name} t
                    LEFT JOIN saa_stocks s ON t.symbol = s.symbol
                    WHERE t.symbol = %s
                    {order_clause}
                    LIMIT %s OFFSET %s
                    """,
                    [symbol, page_size, offset]
                )
            else:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE symbol = %s",
                    [symbol]
                )
                total = cursor.fetchone()[0]

                order_clause_simple = f"ORDER BY {date_column} DESC" if date_column else ""
                cursor.execute(
                    f"SELECT * FROM {table_name} WHERE symbol = %s {order_clause_simple} LIMIT %s OFFSET %s",
                    [symbol, page_size, offset]
                )

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            results = [dict(zip(columns, row)) for row in rows]

            for row in results:
                for key, value in row.items():
                    if isinstance(value, date):
                        row[key] = value.strftime('%Y-%m-%d')
                    elif isinstance(value, Decimal):
                        row[key] = float(value)

        return Response({
            'success': True,
            'data': {
                'results': results,
                'total': total,
                'page': page,
                'page_size': page_size
            }
        })

