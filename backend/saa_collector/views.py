import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.db import connection, transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from saa_collector.permissions import IsAuthenticatedInProduction

from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404

from .collect_job_config import build_collect_job_config
from .date_expressions import normalize_schedule_params, parse_schedule_date, resolve_collect_job_date_range
from .models import CollectJob, DataIntegrityReport, DataIntegrityItem, CollectPlan, CollectSchedule
from .task_dispatcher import (
    create_plan_from_schedule,
    dispatch_plan,
    reset_plan_for_dispatch,
    stop_plan_execution,
)
from .serializers import (
    CollectJobSerializer, CollectJobCreateSerializer,
    DataStatusSerializer, DataCompletenessSerializer,
    DataIntegrityReportSerializer, DataIntegrityReportCreateSerializer,
    DataIntegrityItemSerializer, DataIntegrityItemBulkUpdateSerializer,
    FlattenedIntegrityItemSerializer,
    CollectPlanSerializer, CollectPlanCreateSerializer, CollectPlanUpdateSerializer,
    CollectJobBriefSerializer,
    CollectScheduleSerializer, CollectScheduleCreateSerializer, CollectScheduleUpdateSerializer,
)

logger = logging.getLogger(__name__)

from .constants import (
    DATA_TYPE_FREQUENCY,
    DATA_TYPE_CONFIG,
    is_data_type_visible,
    TABLE_MAPPING,
    QUARTERLY_TYPES,
    YEARLY_TYPES,
    NON_STOCK_LEVEL_TYPES,
    A_STOCK_EARLIEST_DATE,
    EARLIEST_YEAR,
    EXPECTED_A_SHARE_STOCKS,
)


def parse_period_to_date(period_str):
    if not period_str:
        return None
    if 'Q' in period_str:
        try:
            year = int(period_str[:4])
            quarter = int(period_str.split('Q')[1])
            end_month = quarter * 3
            end_day = 31 if end_month in [3, 12] else 30 if end_month in [4, 6, 9, 11] else 28
            return datetime.strptime(f"{year}-{end_month:02d}-{end_day}", '%Y-%m-%d').date()
        except (ValueError, IndexError):
            pass
    return datetime.strptime(period_str, '%Y-%m-%d').date()


def resolve_collect_dates_from_job(job):
    params = normalize_schedule_params(job.config.get('params', {}))
    start_value = job.config.get('start_date')
    end_value = job.config.get('end_date')
    if start_value not in (None, ''):
        params = dict(params, start_date=start_value)
    if end_value not in (None, ''):
        params = dict(params, end_date=end_value)
    start_date, end_date, params = resolve_collect_job_date_range(params, today=timezone.localdate())
    return start_date, end_date, params


def can_edit_collect_plan(plan):
    return plan.source == 'MANUAL' and plan.status not in ('QUEUED', 'RUNNING')


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
        from .constants import DATA_TYPE_CONFIG

        data_types = [
            (key, config['label'], config['table'])
            for key, config in DATA_TYPE_CONFIG.items()
            if config.get('table')
        ]

        data_types.sort(key=lambda x: DATA_TYPE_CONFIG[x[0]].get('order', 99))

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
                    elif data_type in ('stock_info', 'securities'):
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
            'saa_securities': None,
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
            config=build_collect_job_config(
                symbols=serializer.validated_data.get('symbols', []),
                params={
                    'start_date': str(serializer.validated_data.get('start_date')) if serializer.validated_data.get('start_date') else None,
                    'end_date': str(serializer.validated_data.get('end_date')) if serializer.validated_data.get('end_date') else None,
                    'end_date_mode': serializer.validated_data.get('end_date_mode', 'EXECUTION_DAY'),
                    'report_types': serializer.validated_data.get('report_types', []),
                },
            )
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
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        service.collect(symbols)
        job.complete(success=True, message=f"Collected stock info for {len(job.config.get('symbols', [])) if job.config.get('symbols') else 'all'} symbols")


class CollectSecuritiesView(BaseCollectView):
    data_type = 'securities'

    def _execute_collect(self, job):
        from saa_collector.services.common.security_master_service import SecurityMasterRefreshService
        affected_rows = SecurityMasterRefreshService().refresh_from_stocks()
        job.complete(success=True, message=f"Refreshed securities master: {affected_rows} affected rows")


class CollectQuotesView(BaseCollectView):
    data_type = 'quote'

    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_quote_service()
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        service.collect(symbols)
        job.complete(success=True, message=f"Collected quotes for {len(job.config.get('symbols', [])) if job.config.get('symbols') else 'all'} symbols")


class CollectHistoricalQuotesView(BaseCollectView):
    data_type = 'historical_quote'

    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_quote_service()
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        start_date, end_date, _ = resolve_collect_dates_from_job(job)
        service.collect_historical(symbols, start_date=start_date, end_date=end_date)
        job.complete(success=True, message=f"Collected historical quotes")


class CollectStatementsView(BaseCollectView):
    data_type = 'balance_sheet'

    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory
        factory = CompoundServiceFactory()
        service = factory.create_statement_service()
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        start_date, _, params = resolve_collect_dates_from_job(job)

        report_types = params.get('report_types', [])

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
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        start_date, _, _ = resolve_collect_dates_from_job(job)
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
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        start_date, _, _ = resolve_collect_dates_from_job(job)
        service.collect_main_business(symbols, start_date)
        job.complete(success=True, message=f"Collected main business data")


class StockListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        keyword = request.query_params.get('keyword', '')

        with connection.cursor() as cursor:
            if keyword:
                cursor.execute(
                    "SELECT symbol, name, industry_classification_id, listing_date FROM saa_stocks "
                    "WHERE symbol LIKE %s OR name LIKE %s "
                    "ORDER BY symbol LIMIT 100",
                    [f'{keyword}%', f'%{keyword}%']
                )
            else:
                cursor.execute(
                    "SELECT symbol, name, industry_classification_id, listing_date FROM saa_stocks "
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
                "SELECT symbol, name, industry_classification_id, listing_date FROM saa_stocks "
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
        'saa_securities': {'date_column': None, 'order': 'code ASC', 'search_column': 'code'},
        'saa_latest_prices': {'date_column': 'date', 'order': 'symbol ASC, date DESC'},
        'saa_prices_ex': {'date_column': 'date', 'order': 'code ASC, date DESC'},
        'saa_index_quotes': {'date_column': 'date', 'order': 'code ASC, date DESC', 'search_column': 'code'},
        'saa_index_weights': {'date_column': 'date', 'order': '`index` ASC, date DESC', 'search_column': 'index', 'join_column': 'code'},
        'saa_industries': {'date_column': 'start_date', 'order': '`index` ASC, start_date DESC'},
        'saa_industry_stocks': {'date_column': 'date', 'order': 'industry_code ASC, date DESC', 'search_column': 'industry_code', 'join_column': 'code'},
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
        'saa_index_weights',
        'saa_industry_stocks',
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
        keyword = request.query_params.get('keyword', '').strip()
        offset = (page - 1) * page_size

        config = self.TABLE_CONFIG.get(table_name)
        if not config:
            return Response({'success': False, 'error': 'Invalid table name'}, status=400)

        date_column = config['date_column']
        order_clause = f"ORDER BY {config['order']}"
        search_column = config.get('search_column')
        join_column = config.get('join_column', 'symbol')

        with connection.cursor() as cursor:
            where_clauses = []
            params = []

            if date_column and start_date:
                where_clauses.append(f"t.{date_column} >= %s")
                params.append(start_date)
            if date_column and end_date:
                where_clauses.append(f"t.{date_column} <= %s")
                params.append(end_date)
            if keyword and search_column:
                if search_column == 'index':
                    where_clauses.append("t.`index` LIKE %s")
                else:
                    where_clauses.append(f"t.{search_column} LIKE %s")
                params.append(f"%{keyword}%")

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
                    LEFT JOIN saa_stocks s ON t.{join_column} = s.symbol
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
                    SELECT symbol, name, listing_date
                    FROM saa_stocks
                    WHERE symbol IN ({placeholders})
                      AND listing_date IS NOT NULL
                      AND listing_date <= %s
                """, short_symbols + [end_date])
            else:
                cursor.execute("""
                    SELECT symbol, name, listing_date
                    FROM saa_stocks
                    WHERE listing_date IS NOT NULL
                      AND listing_date <= %s
                """, [end_date])
                symbol_map = None

            stocks = []
            for row in cursor.fetchall():
                listing_date = row[2]
                if hasattr(listing_date, 'strftime'):
                    listing_date_str = listing_date.strftime('%Y-%m-%d')
                else:
                    listing_date_str = str(listing_date)

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
        report._date_start = datetime.strptime(report.date_start, '%Y-%m-%d').date() if report.date_start else None
        report._date_end = datetime.strptime(report.date_end, '%Y-%m-%d').date() if report.date_end else None

        stocks = self._get_stocks_with_listing_dates(report)
        items_to_create = []

        data_types = report.data_types if report.data_types else ['trade_days', 'quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'dividend', 'capital']
        data_types = [dt for dt in data_types if is_data_type_visible(dt, 'integrity_report')]

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
                    SELECT symbol, listing_date FROM saa_stocks
                    WHERE symbol IN ({placeholders})
                      AND listing_date IS NOT NULL
                      AND listing_date <= %s
                """, symbols + [report.date_end])
            else:
                cursor.execute("""
                    SELECT symbol, listing_date FROM saa_stocks
                    WHERE listing_date IS NOT NULL
                      AND listing_date <= %s
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
                    miss_period=missing_period,
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
        expected = self._generate_periods(report._date_start, report._date_end, check_frequency)

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

        items = []
        for period in missing_periods:
            items.append(DataIntegrityItem(
                report=report,
                data_type=data_type,
                stock_code=None,
                miss_period=period,
                selected=False
            ))
        return items

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

        from .constants import DATA_TYPE_CONFIG
        stock_column = DATA_TYPE_CONFIG.get(data_type, {}).get('stock_column', 'symbol')

        result = {}

        for i in range(0, len(symbols), self.BATCH_SIZE):
            batch = symbols[i:i + self.BATCH_SIZE]
            batch_result = self._query_periods_batch(batch, table_name, start_date, end_date, frequency, stock_column)

            for symbol, periods in batch_result.items():
                if symbol not in result:
                    result[symbol] = set()
                result[symbol].update(periods)

        return result

    def _query_periods_batch(self, symbols, table_name, start_date, end_date, frequency, stock_column='symbol'):
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
                SELECT DISTINCT {stock_column}, {select_expr} as period
                FROM {table_name}
                WHERE {stock_column} IN ({placeholders})
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

        expected = self._generate_periods(report._date_start, report._date_end, frequency)

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
            items = []
            for period in sorted(missing):
                items.append(DataIntegrityItem(
                    report=report,
                    data_type='trade_days',
                    stock_code='-',
                    miss_period=period,
                    selected=False
                ))
            return items
        return []

    def _check_missing_periods_batch(self, report, stocks, data_type):
        frequency = self._get_check_frequency(data_type, report.frequency)

        all_periods = self._generate_periods(report._date_start, report._date_end, frequency)

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

            for period in sorted(missing):
                missing_items.append(DataIntegrityItem(
                    report=report,
                    data_type=data_type,
                    stock_code=symbol,
                    miss_period=period,
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
        if period_filter:
            periods = [p.strip() for p in period_filter.split(',')]
        else:
            periods = None

        flattened_rows = self._flatten_items(items_queryset, periods)

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

    def _flatten_items(self, items_queryset, periods=None):
        flattened = []
        for item in items_queryset:
            if not item.miss_period:
                continue
            if periods and item.miss_period not in periods:
                continue
            flattened.append({
                'id': item.id,
                'data_type': item.data_type,
                'stock_code': item.stock_code,
                'period': item.miss_period,
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
            items_queryset = items_queryset.filter(miss_period__icontains=period)

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
            if item.miss_period:
                data_type_items[item.data_type]['periods'].add(item.miss_period)

        for data_type, info in data_type_items.items():
            periods = sorted(info['periods'])

            CollectJob.objects.create(
                plan=plan,
                data_type=data_type,
                config=build_collect_job_config(
                    symbols=[] if report.stock_scope == 'ALL' else list(info['stock_codes']),
                    start_date=str(report.date_start) if report.date_start else None,
                    end_date=str(report.date_end) if report.date_end else None,
                    miss_periods=periods,
                ),
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
    permission_classes = [IsAuthenticatedInProduction]

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

        date_start = datetime.strptime(report.date_start, '%Y-%m-%d').date() if report.date_start else None
        date_end = datetime.strptime(report.date_end, '%Y-%m-%d').date() if report.date_end else None

        service = CompletenessService(
            stock_codes=stock_codes,
            date_end=date_end
        )

        periods = service.generate_periods(report.frequency, date_start, date_end)

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

        data_types = [
            dt for dt in (report.data_types or [])
            if is_data_type_visible(dt, 'integrity_report')
        ]
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
        # 检测是否为季度格式（如资产负债表等季度数据）
        if 'Q' in period:
            try:
                year = int(period[:4])
                quarter = int(period.split('Q')[1])
                # 季度数据 → 转换为季度末月份（报告日所在月）
                # Q1→3月, Q2→6月, Q3→9月, Q4→12月
                end_month = quarter * 3
                return {f"{year}-{end_month:02d}"}
            except (ValueError, IndexError):
                # 格式错误时返回原值
                return {period}
        else:
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
            if item.miss_period:
                data_type_stats[item.data_type]['missing_count'] += 1
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
            if item.miss_period:
                period = item.miss_period
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

            if item.miss_period:
                period = item.miss_period
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
        plans = CollectPlan.objects.select_related('source_report').annotate(
            jobs_count=Count('jobs')
        ).prefetch_related(
            Prefetch('jobs', queryset=CollectJob.objects.all().order_by('-created_at'))
        ).order_by('-created_at')
        source = request.query_params.get('source')
        if source:
            plans = plans.filter(source=source)
        plan_status = request.query_params.get('status')
        if plan_status:
            plans = plans.filter(status=plan_status)
        trigger_type = request.query_params.get('trigger_type')
        if trigger_type:
            plans = plans.filter(trigger_type=trigger_type)
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

        if not can_edit_collect_plan(plan):
            return Response({
                'success': False,
                'error': '只能编辑手动创建且未执行中的计划'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = CollectPlanUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        validated_data = dict(serializer.validated_data)
        jobs_data = validated_data.pop('jobs', None)

        existing_jobs = {}
        if jobs_data is not None:
            existing_jobs = {job.id: job for job in plan.jobs.all()}
            for job_data in jobs_data:
                job_id = job_data.get('id')
                if job_id and job_id not in existing_jobs:
                    return Response({
                        'success': False,
                        'error': '计划作业不存在或不属于当前计划'
                    }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for key, value in validated_data.items():
                setattr(plan, key, value)
            plan.save()

            if jobs_data is not None:
                kept_job_ids = set()

                for job_data in jobs_data:
                    job_id = job_data.get('id')
                    if job_id:
                        job = existing_jobs[job_id]
                    else:
                        job = CollectJob(plan=plan)

                    existing_config = job.config or {}
                    existing_params = existing_config.get('params') or {}
                    params = dict(existing_params)

                    if 'start_date' in job_data:
                        params['start_date'] = str(job_data['start_date']) if job_data.get('start_date') else None
                    if 'end_date' in job_data:
                        params['end_date'] = str(job_data['end_date']) if job_data.get('end_date') else None
                    if 'report_types' in job_data:
                        params['report_types'] = job_data.get('report_types') or []
                    if 'skip_existing' in job_data:
                        params['skip_existing'] = job_data.get('skip_existing', False)
                    if 'data_frequency' in job_data:
                        params['data_frequency'] = job_data.get('data_frequency', 'daily')
                    if 'end_date_mode' in job_data:
                        params['end_date_mode'] = job_data.get('end_date_mode', 'EXECUTION_DAY')
                    if 'stock_scope' in job_data:
                        params['stock_scope'] = job_data.get('stock_scope', 'ALL')
                    if 'stock_list_code' in job_data:
                        params['stock_list_code'] = job_data.get('stock_list_code') or None

                    job.data_type = job_data['data_type']
                    job.config = build_collect_job_config(
                        symbols=job_data.get('symbols', existing_config.get('symbols', [])),
                        params=params,
                        stock_scope=job_data.get('stock_scope', existing_config.get('stock_scope', 'ALL')),
                        stock_list_code=job_data.get('stock_list_code', existing_config.get('stock_list_code')),
                    )
                    job.save()
                    kept_job_ids.add(job.id)

                plan.jobs.exclude(id__in=kept_job_ids).delete()

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

        reset_plan_for_dispatch(plan)

        if plan.status != 'PENDING':
            return Response({
                'success': False,
                'error': '计划状态不正确'
            }, status=status.HTTP_400_BAD_REQUEST)

        dispatch_plan(plan)
        plan.refresh_from_db()

        return Response({'success': True, 'data': CollectPlanSerializer(plan).data})


class CollectPlanStopView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)

        try:
            stop_plan_execution(plan)
        except ValueError as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

        plan.refresh_from_db()
        return Response({'success': True, 'data': CollectPlanSerializer(plan).data})


class CollectPlanContinueView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)

        if plan.status != 'STOPPED':
            return Response({
                'success': False,
                'error': '只能继续已停止的计划'
            }, status=status.HTTP_400_BAD_REQUEST)

        resume_jobs = plan.jobs.exclude(status='SUCCESS')
        dispatch_plan(plan, jobs_queryset=resume_jobs)
        plan.refresh_from_db()
        return Response({'success': True, 'data': CollectPlanSerializer(plan).data})


class CollectPlanResetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)

        if plan.status == 'RUNNING':
            return Response({
                'success': False,
                'error': '执行中的计划不能直接重置，请先停止'
            }, status=status.HTTP_400_BAD_REQUEST)

        reset_plan_for_dispatch(plan)
        plan.refresh_from_db()
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
                from .services.heatmap_cache import invalidate_heatmap_cache
                invalidate_heatmap_cache()
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
            logger.exception(f"[Job {job_id}] Execution failed: {e}")
            try:
                job = CollectJob.objects.get(id=job_id)
                job.complete(success=False, message=str(e))
            except:
                pass

    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory

        factory = CompoundServiceFactory()
        data_type = job.data_type
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        start_date, end_date, params = resolve_collect_dates_from_job(job)

        logger.info(f"[Job {job.id}] Collecting: data_type={data_type}, symbols={symbols}, "
                    f"start_date={start_date}, end_date={end_date}")

        if data_type == 'trade_days':
            service = factory.create_calendar_service()
            service.collect(start_date, end_date)
        elif data_type == 'stock_info':
            service = factory.create_stock_info_service()
            service.collect(symbols)
        elif data_type == 'securities':
            from saa_collector.services.common.security_master_service import SecurityMasterRefreshService
            SecurityMasterRefreshService().refresh_from_stocks()
        elif data_type == 'quote':
            service = factory.create_quote_service()
            service.collect(symbols)
        elif data_type == 'historical_quote':
            service = factory.create_quote_service()
            service.collect_historical(symbols, start_date=start_date, end_date=end_date)
        elif data_type == 'financial_statements':
            service = factory.create_statement_service()
            service.produce(symbols, start_date)
        elif data_type in ('balance_sheet', 'income', 'cash_flow', 'dividend'):
            service = factory.create_statement_service()
            report_types = params.get('report_types', [])
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
        elif data_type == 'csrc_industry_classifications':
            from saa_collector.services.common.industry_classification_service import CsrcIndustryClassificationService
            service = CsrcIndustryClassificationService()
            service.collect()
        elif data_type == 'tick':
            from saa_collector.jobs.tick_job import TickJob
            collect_job = TickJob()
            collect_job()
        else:
            logger.warning(f"[Job {job.id}] Unknown data type: {data_type}")

    def _update_report_items(self, plan):
        if not plan.source_report:
            return

        successful_jobs = plan.jobs.filter(status='SUCCESS')
        for job in successful_jobs:
            symbols = job.config.get('symbols', [])
            miss_periods = job.config.get('miss_periods', [])

            if not symbols:
                continue

            if not miss_periods:
                DataIntegrityItem.objects.filter(
                    report=plan.source_report,
                    data_type=job.data_type,
                    stock_code__in=symbols,
                    status='PENDING'
                ).update(
                    status='FIXED',
                    fixed_at=timezone.now(),
                    fixed_by_plan=plan
                )
                logger.info(f"[Job {job.id}] Marked all items as FIXED for data_type={job.data_type}")
                continue

            fixed_count = 0
            for symbol in symbols:
                for period in miss_periods:
                    if self._verify_data_exists(job.data_type, symbol, period):
                        updated = DataIntegrityItem.objects.filter(
                            report=plan.source_report,
                            data_type=job.data_type,
                            stock_code=symbol,
                            miss_period=period,
                            status='PENDING'
                        ).update(
                            status='FIXED',
                            fixed_at=timezone.now(),
                            fixed_by_plan=plan
                        )
                        if updated > 0:
                            fixed_count += 1
                            logger.info(f"[Job {job.id}] Verified and fixed: {symbol} - {period}")
                    else:
                        logger.warning(f"[Job {job.id}] Data not found in DB: {symbol} - {period}, skip marking as FIXED")

            logger.info(f"[Job {job.id}] Fixed {fixed_count} items after verification")

    def _verify_data_exists(self, data_type, symbol, period):
        if data_type not in DATA_TYPE_CONFIG:
            logger.warning(f"Unknown data_type: {data_type}")
            return False

        config = DATA_TYPE_CONFIG[data_type]
        table_name = config['table']
        date_column = config['date_column']
        stock_column = config.get('stock_column', 'symbol')

        if not date_column:
            return False

        period_date = parse_period_to_date(period)
        if not period_date:
            logger.warning(f"Invalid period format: {period}")
            return False

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} "
                    f"WHERE {stock_column} = %s AND {date_column} = %s",
                    [symbol, period_date]
                )
                count = cursor.fetchone()[0]
                exists = count > 0
                if not exists:
                    logger.debug(f"No data found in {table_name}: {stock_column}={symbol}, {date_column}={period_date}")
                return exists
        except Exception as e:
            logger.exception(f"Error verifying data existence: {e}")
            return False


class DataCompletenessHeatmapView(APIView):
    permission_classes = [IsAuthenticated]
    CACHE_TIMEOUT_SECONDS = 6 * 60 * 60
    LATEST_CACHE_TIMEOUT_SECONDS = 24 * 60 * 60

    INDEX_SCOPE_LABELS = {
        '000906': '中证800',
    }

    def get(self, request):
        from .services.completeness_service import CompletenessService
        from .services.heatmap_cache import build_heatmap_cache_keys
        from .constants import DATA_TYPE_CONFIG

        frequency = request.query_params.get('frequency', 'monthly')
        scope_key = request.query_params.get('scope', 'all')
        force_refresh = request.query_params.get('refresh') in ('1', 'true', 'yes', 'on')
        scope = self._resolve_scope(scope_key)
        if scope is None:
            return Response({'success': False, 'error': 'Invalid scope'}, status=400)

        cache_key, latest_cache_key = build_heatmap_cache_keys(
            frequency,
            scope['key'],
            timezone.localdate().isoformat(),
        )
        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.info("heatmap request cache_hit frequency=%s scope=%s", frequency, scope['key'])
                return Response({
                    'success': True,
                    'data': cached_result,
                    'meta': {'cached': True, 'cache': 'daily'},
                })

            latest_result = cache.get(latest_cache_key)
            if latest_result is not None:
                logger.info("heatmap request latest_cache_hit frequency=%s scope=%s", frequency, scope['key'])
                return Response({
                    'success': True,
                    'data': latest_result,
                    'meta': {'cached': True, 'cache': 'latest'},
                })

        service = CompletenessService(
            stock_codes=scope['stock_codes'],
            index_code=scope['index_code'],
        )
        periods = service.generate_periods(frequency)

        if not periods:
            return Response({'success': False, 'error': 'Invalid frequency'}, status=400)

        data_types = [
            key for key, config in DATA_TYPE_CONFIG.items()
            if config.get('show_completeness') and is_data_type_visible(key, 'dashboard')
        ]
        started_at = time.monotonic()
        logger.info(
            "heatmap request start frequency=%s scope=%s periods=%s data_types=%s",
            frequency,
            scope['key'],
            len(periods),
            len(data_types),
        )
        result = service.calculate_all(data_types, periods, frequency)
        result['scope'] = {
            'key': scope['key'],
            'label': scope['label'],
        }
        cache.set(cache_key, result, timeout=self.CACHE_TIMEOUT_SECONDS)
        cache.set(latest_cache_key, result, timeout=self.LATEST_CACHE_TIMEOUT_SECONDS)
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "heatmap request done frequency=%s scope=%s periods=%s data_types=%s elapsed_ms=%s",
            frequency,
            scope['key'],
            len(periods),
            len(data_types),
            elapsed_ms,
        )

        return Response({
            'success': True,
            'data': result,
            'meta': {'cached': False, 'cache': 'refresh' if force_refresh else 'miss'},
        })

    def _resolve_scope(self, scope_key):
        if scope_key in (None, '', 'all'):
            return {
                'key': 'all',
                'label': '全市场',
                'stock_codes': None,
                'index_code': None,
            }

        if not scope_key.startswith('index:'):
            return None

        index_code = scope_key.split(':', 1)[1].strip()
        if not index_code:
            return None

        with connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT COUNT(DISTINCT code)
                    FROM saa_index_weights
                    WHERE `index` = %s
                      AND date = (
                          SELECT MAX(date)
                          FROM saa_index_weights
                          WHERE `index` = %s
                      )
                    ORDER BY code
                """,
                [index_code, index_code],
            )
            row = cursor.fetchone()
            constituent_count = row[0] if row else 0

        if not constituent_count:
            return None

        label = self.INDEX_SCOPE_LABELS.get(index_code, index_code)
        return {
            'key': f'index:{index_code}',
            'label': label,
            'stock_codes': None,
            'index_code': index_code,
        }


class DataCompletenessHeatmapScopesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scopes = [
            {
                'key': 'all',
                'label': '全市场',
                'type': 'all',
            }
        ]

        with connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT w.`index`, latest.max_date, COUNT(DISTINCT w.code) AS constituent_count
                    FROM saa_index_weights w
                    JOIN (
                        SELECT `index`, MAX(date) AS max_date
                        FROM saa_index_weights
                        GROUP BY `index`
                    ) latest
                      ON latest.`index` = w.`index`
                     AND latest.max_date = w.date
                    GROUP BY w.`index`, latest.max_date
                    ORDER BY w.`index`
                """
            )
            rows = cursor.fetchall()

        for index_code, latest_date, constituent_count in rows:
            scopes.append({
                'key': f'index:{index_code}',
                'label': DataCompletenessHeatmapView.INDEX_SCOPE_LABELS.get(index_code, index_code),
                'type': 'index',
                'index': index_code,
                'latest_date': latest_date.isoformat() if hasattr(latest_date, 'isoformat') else latest_date,
                'constituent_count': constituent_count,
            })

        return Response({
            'success': True,
            'data': scopes,
        })


class DataCompletenessHeatmapScopeSymbolsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scope_key = request.query_params.get('scope', 'all')
        if scope_key in (None, '', 'all'):
            return Response({
                'success': True,
                'data': {
                    'key': 'all',
                    'label': '全市场',
                    'type': 'all',
                    'constituent_count': 0,
                    'symbols': [],
                },
            })

        if not scope_key.startswith('index:'):
            return Response({'success': False, 'error': 'Invalid scope'}, status=400)

        index_code = scope_key.split(':', 1)[1].strip()
        if not index_code:
            return Response({'success': False, 'error': 'Invalid scope'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT DISTINCT w.code, latest.max_date
                    FROM saa_index_weights w
                    JOIN (
                        SELECT MAX(date) AS max_date
                        FROM saa_index_weights
                        WHERE `index` = %s
                    ) latest
                      ON latest.max_date = w.date
                    WHERE w.`index` = %s
                    ORDER BY w.code
                """,
                [index_code, index_code],
            )
            rows = cursor.fetchall()

        if not rows:
            return Response({'success': False, 'error': 'Invalid scope'}, status=400)

        latest_date = rows[0][1]
        symbols = [row[0] for row in rows]
        return Response({
            'success': True,
            'data': {
                'key': f'index:{index_code}',
                'label': DataCompletenessHeatmapView.INDEX_SCOPE_LABELS.get(index_code, index_code),
                'type': 'index',
                'index': index_code,
                'latest_date': latest_date.isoformat() if hasattr(latest_date, 'isoformat') else latest_date,
                'constituent_count': len(symbols),
                'symbols': symbols,
            },
        })


class DisplayFieldConfigView(APIView):
    permission_classes = [IsAuthenticated]

    TABLE_LABEL_MAP = {
        'saa_stocks': '基本信息',
        'saa_securities': '证券主数据',
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
                {'key': 'securities', 'label': '证券主数据', 'table': 'saa_securities'},
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
        'saa_securities': None,
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


class DataTypesConfigView(APIView):
    """
    返回所有数据类型配置

    这是系统的单一数据源，前端应该从此API获取所有数据类型信息
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .constants import DATA_TYPE_CONFIG, DATA_TYPE_GROUPS

        data_types = []
        for key, config in DATA_TYPE_CONFIG.items():
            data_types.append({
                'key': key,
                'label': config['label'],
                'table': config['table'],
                'frequency': config.get('data_frequency'),
                'completeness_model': config.get('completeness_model'),
                'stock_level': config.get('stock_level', True),
                'group': config.get('group'),
                'show_completeness': config.get('show_completeness', True),
                'visibility': config.get('visibility', {}),
                'need_date': config.get('need_date', True),
                'stock_column': config.get('stock_column'),
                'supports_integrity_check': config.get('supports_integrity_check', True),
                'order': config.get('order', 99),
            })

        data_types.sort(key=lambda x: x['order'])

        return Response({
            'data_types': data_types,
            'groups': sorted(DATA_TYPE_GROUPS, key=lambda x: x['order']),
        })


class CollectScheduleListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        schedules = CollectSchedule.objects.all().order_by('-created_at')
        serializer = CollectScheduleSerializer(schedules, many=True)
        return Response({'success': True, 'data': serializer.data})

    def post(self, request):
        serializer = CollectScheduleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        schedule = serializer.save()

        if schedule.status == 'ENABLED':
            from .tasks import get_next_schedule_fire_time
            schedule.next_trigger_at = get_next_schedule_fire_time(schedule, timezone.now())
            schedule.save(update_fields=['next_trigger_at'])

        return Response({
            'success': True,
            'data': CollectScheduleSerializer(schedule).data
        }, status=status.HTTP_201_CREATED)


class CollectScheduleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            schedule = CollectSchedule.objects.get(pk=pk)
        except CollectSchedule.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Schedule not found'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CollectScheduleSerializer(schedule)
        return Response({'success': True, 'data': serializer.data})

    def put(self, request, pk):
        try:
            schedule = CollectSchedule.objects.get(pk=pk)
        except CollectSchedule.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Schedule not found'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CollectScheduleUpdateSerializer(schedule, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        schedule = serializer.save()
        if schedule.status == 'ENABLED':
            from .tasks import get_next_schedule_fire_time
            schedule.next_trigger_at = get_next_schedule_fire_time(schedule, timezone.now())
        else:
            schedule.next_trigger_at = None
        schedule.save(update_fields=['next_trigger_at'])

        return Response({
            'success': True,
            'data': CollectScheduleSerializer(schedule).data
        })

    def delete(self, request, pk):
        try:
            schedule = CollectSchedule.objects.get(pk=pk)
        except CollectSchedule.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Schedule not found'
            }, status=status.HTTP_404_NOT_FOUND)

        schedule.delete()

        return Response({'success': True})


class CollectScheduleTriggerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            schedule = CollectSchedule.objects.get(pk=pk)
        except CollectSchedule.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Schedule not found'
            }, status=status.HTTP_404_NOT_FOUND)

        schedule.last_triggered_at = timezone.now()
        schedule.save()
        plan = create_plan_from_schedule(schedule, trigger_type='MANUAL')
        dispatch_plan(plan)
        plan.refresh_from_db()

        return Response({
            'success': True,
            'data': {
                'plan_id': plan.id,
                'plan': CollectPlanSerializer(plan).data,
                'message': f'已创建采集计划: {plan.name}'
            }
        })

    def _execute_plan(self, plan_id):
        from django import db
        db.connections.close_all()

        try:
            plan = CollectPlan.objects.get(id=plan_id)
            plan.status = 'RUNNING'
            plan.started_at = timezone.now()
            plan.save()

            all_success = True
            for job in plan.jobs.all():
                try:
                    job.start()
                    self._execute_collect(job)
                    job.complete(success=True, message='执行完成')
                except Exception as e:
                    logger.exception(f"Job {job.id} failed: {e}")
                    job.complete(success=False, message=str(e))
                    all_success = False

            plan.status = 'COMPLETED' if all_success else 'FAILED'
            plan.completed_at = timezone.now()
            plan.save()
            if plan.status == 'COMPLETED':
                from .services.heatmap_cache import invalidate_heatmap_cache
                invalidate_heatmap_cache()
        except Exception as e:
            logger.exception(f"Plan {plan_id} failed: {e}")
            try:
                plan = CollectPlan.objects.get(id=plan_id)
                plan.status = 'FAILED'
                plan.completed_at = timezone.now()
                plan.save()
            except:
                pass

    def _execute_collect(self, job):
        from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory

        factory = CompoundServiceFactory()
        data_type = job.data_type
        symbols = job.config.get('symbols') if job.config.get('symbols') else None
        start_date, end_date, params = resolve_collect_dates_from_job(job)

        logger.info(f"[Job {job.id}] Triggered execution: data_type={data_type}, symbols={symbols}")

        if data_type == 'trade_days':
            service = factory.create_calendar_service()
            service.collect(start_date, end_date)
        elif data_type == 'stock_info':
            service = factory.create_stock_info_service()
            service.collect(symbols)
        elif data_type == 'securities':
            from saa_collector.services.common.security_master_service import SecurityMasterRefreshService
            SecurityMasterRefreshService().refresh_from_stocks()
        elif data_type == 'quote':
            service = factory.create_quote_service()
            service.collect(symbols)
        elif data_type == 'historical_quote':
            service = factory.create_quote_service()
            service.collect_historical(symbols, start_date=start_date, end_date=end_date)
        elif data_type == 'financial_statements':
            service = factory.create_statement_service()
            service.produce(symbols, start_date)
        elif data_type in ('balance_sheet', 'income', 'cash_flow', 'dividend'):
            service = factory.create_statement_service()
            report_types = params.get('report_types', [])
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
        elif data_type == 'csrc_industry_classifications':
            from saa_collector.services.common.industry_classification_service import CsrcIndustryClassificationService
            service = CsrcIndustryClassificationService()
            service.collect()
        elif data_type == 'tick':
            from saa_collector.jobs.tick_job import TickJob
            collect_job = TickJob()
            collect_job()
        else:
            logger.warning(f"[Job {job.id}] Unknown data type: {data_type}")


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        if not username or not password:
            return Response({'error': '请输入用户名和密码'}, status=400)

        uc_api = getattr(settings, 'UC_API', '') or ''
        uc_admin_users = getattr(settings, 'UC_ADMIN_USERS', [])

        if not uc_api:
            if username == 'admin' and password == 'admin':
                user, _ = User.objects.get_or_create(
                    username='admin',
                    defaults={'is_staff': True, 'is_superuser': True}
                )
                token, _ = Token.objects.get_or_create(user=user)
                return Response({'token': token.key, 'username': user.username, 'avatar_url': ''})
            return Response({'error': '用户名或密码错误'}, status=401)

        from ucenter import UCenterClient, UCenterError

        try:
            client = UCenterClient(
                api_url=uc_api,
                key=settings.UC_KEY,
                appid=settings.UC_APPID,
            )
            result = client.login(username, password)
        except UCenterError as e:
            logger.error(f'UCenter login error: {e}')
            return Response({'error': '认证服务暂时不可用'}, status=503)

        uid = result.get('uid', -1)
        if uid <= 0:
            return Response({'error': '用户名或密码错误'}, status=401)

        if username not in uc_admin_users:
            return Response({'error': '无权访问此系统'}, status=403)

        user, _ = User.objects.get_or_create(
            username=username,
            defaults={'email': result.get('email', '')}
        )
        token, _ = Token.objects.get_or_create(user=user)

        avatar_url = f"{uc_api.rstrip('/')}/avatar.php?uid={uid}&size=middle"

        logger.info(f'User {username} logged in via UCenter (uid={uid})')
        return Response({
            'token': token.key,
            'username': user.username,
            'avatar_url': avatar_url,
        })
