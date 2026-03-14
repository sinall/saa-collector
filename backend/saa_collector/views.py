import logging
import threading
from datetime import date, timedelta

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
            'saa_trade_days': 'date',
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
                    "SELECT symbol, name, industry, list_date FROM saa_stocks "
                    "WHERE symbol LIKE %s OR name LIKE %s "
                    "ORDER BY symbol LIMIT 100",
                    [f'%{keyword}%', f'%{keyword}%']
                )
            else:
                cursor.execute(
                    "SELECT symbol, name, industry, list_date FROM saa_stocks "
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
                "SELECT symbol, name, industry, list_date FROM saa_stocks "
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
            'historical_quote': ('saa_prices', 'date'),
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

    QUARTERLY_TYPES = {'balance_sheet', 'income', 'cash_flow', 'main_business'}
    YEARLY_TYPES = {'dividend', 'capital'}
    BATCH_SIZE = 500

    TABLE_MAPPING = {
        'quote': 'saa_latest_prices',
        'historical_quote': 'saa_prices',
        'balance_sheet': 'saa_raw_balance_sheet',
        'income': 'saa_raw_income_statement',
        'cash_flow': 'saa_raw_cash_flow_statement',
        'main_business': 'saa_raw_main_business',
        'dividend': 'saa_dividends',
        'capital': 'saa_capitals',
        'trade_days': 'saa_trade_days',
    }

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

        data_types = report.data_types if report.data_types else ['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'dividend', 'capital']

        for data_type in data_types:
            if data_type == 'trade_days':
                items = self._check_trade_days_missing(report)
            elif data_type == 'quote':
                items = self._check_quote_missing(report, stocks)
            elif data_type in self.TABLE_MAPPING:
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
        if data_type in self.QUARTERLY_TYPES:
            return 'quarterly'
        elif data_type in self.YEARLY_TYPES:
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

        table_name = self.TABLE_MAPPING['quote']
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
        table_name = self.TABLE_MAPPING.get(data_type)
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

        table_name = self.TABLE_MAPPING['trade_days']
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

        selected_items = report.items.filter(selected=True)
        if not selected_items.exists():
            return Response({
                'success': False,
                'error': '未选择任何缺失项'
            }, status=status.HTTP_400_BAD_REQUEST)

        plan = CollectPlan.objects.create(
            name=f"来自报告: {report.name}",
            source_report=report,
            execution_mode='PARALLEL'
        )

        data_type_items = {}
        for item in selected_items:
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
            job.complete(success=True, message='执行完成')
        except Exception as e:
            logger.exception(f"Job {job_id} execution failed: {e}")
            try:
                job = CollectJob.objects.get(id=job_id)
                job.complete(success=False, message=str(e))
            except:
                pass
