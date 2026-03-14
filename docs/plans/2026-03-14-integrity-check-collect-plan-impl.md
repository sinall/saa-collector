# 完整性检查与采集计划实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 建立完整性检查 → 任务生成的完整工作流，包括 DataIntegrityReport、CollectPlan 数据模型及前后端实现。

**Architecture:** 新增 DataIntegrityReport/Item 和 CollectPlan 模型，扩展现有 CollectJob 模型添加 plan 外键。后端使用 DRF 实现 REST API，前端使用 Vue3 + Element Plus 实现页面。复用现有 CompoundServiceFactory 执行采集逻辑。

**Tech Stack:** Django REST Framework, Vue3, Element Plus, threading

---

## 数据类型特点说明

### 数据类型汇总表

| 数据类型 | 中文名 | 数据表 | 检查频率 | 数据保留策略 | 特殊说明 |
|---------|--------|--------|---------|-------------|---------|
| trade_days | 交易日 | saa_trade_days | 按报告频率 | 全量保留 | 无股票维度 |
| **quote** | 最新行情 | saa_latest_prices | **仅最新交易日** | **仅保留最新** | 不检查历史日期，只检查最新交易日是否有数据 |
| historical_quote | 历史行情 | saa_prices | 按报告频率 | 全量保留 | 历史日K线数据 |
| balance_sheet | 资产负债表 | saa_raw_balance_sheet | **强制季度** | 全量保留 | - |
| income | 利润表 | saa_raw_income_statement | **强制季度** | 全量保留 | - |
| cash_flow | 现金流量表 | saa_raw_cash_flow_statement | **强制季度** | 全量保留 | - |
| main_business | 主营业务 | saa_raw_main_business | **强制季度** | 全量保留 | - |
| dividend | 分红数据 | saa_dividends | **强制年度** | 全量保留 | - |
| capital | 股本变动 | saa_capitals | **强制年度** | 全量保留 | - |

### 检查逻辑说明

1. **quote (最新行情)** - 特殊处理
   - `saa_latest_prices` 表只存储最新交易日数据，不保留历史
   - 检查时只检查最新交易日是否有数据，不按报告频率检查历史
   - 缺失周期显示为最新交易日期（如 `2026-03-15`）

2. **财报类 (balance_sheet, income, cash_flow, main_business)** - 强制季度
   - 无论报告设置什么频率，都强制按季度检查
   - 周期格式：`2024-Q1`, `2024-Q2`, `2024-Q3`, `2024-Q4`

3. **年度类 (dividend, capital)** - 强制年度
   - 无论报告设置什么频率，都强制按年度检查
   - 周期格式：`2024`, `2025`

4. **其他类型** - 按报告频率
   - historical_quote: 按报告设置的频率检查
   - trade_days: 按报告设置的频率检查

### 代码中的分类常量

```python
QUARTERLY_TYPES = {'balance_sheet', 'income', 'cash_flow', 'main_business'}
YEARLY_TYPES = {'dividend', 'capital'}
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
```

---

## Task 1: 创建数据模型

**Files:**
- Modify: `backend/saa_collector/models.py`

**Step 1: 添加 DataIntegrityReport 和 DataIntegrityItem 模型**

在 `CollectJob` 模型后添加：

```python
class DataIntegrityReport(models.Model):
    STATUS_CHOICES = [
        ('GENERATING', '生成中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
    ]

    STOCK_SCOPE_CHOICES = [
        ('ALL', '全部股票'),
        ('SELECTED', '选定股票'),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField('报告名称', max_length=200)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='GENERATING')
    stock_scope = models.CharField('股票范围', max_length=20, choices=STOCK_SCOPE_CHOICES, default='ALL')
    stock_codes = models.JSONField('股票列表', default=list)
    date_start = models.DateField('开始日期', null=True, blank=True)
    date_end = models.DateField('结束日期', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)

    class Meta:
        db_table = 'collector_data_integrity_report'
        ordering = ['-created_at']
        verbose_name = '数据完整性报告'
        verbose_name_plural = '数据完整性报告'

    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"


class DataIntegrityItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    report = models.ForeignKey(DataIntegrityReport, on_delete=models.CASCADE, related_name='items')
    data_type = models.CharField('数据类型', max_length=50)
    stock_code = models.CharField('股票代码', max_length=20)
    missing_periods = models.JSONField('缺失周期', default=list)
    selected = models.BooleanField('已选择', default=False)

    class Meta:
        db_table = 'collector_data_integrity_item'
        verbose_name = '数据完整性项'
        verbose_name_plural = '数据完整性项'

    def __str__(self):
        return f"{self.stock_code} - {self.data_type}"
```

**Step 2: 添加 CollectPlan 模型**

在 `DataIntegrityItem` 后添加：

```python
class CollectPlan(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '待执行'),
        ('RUNNING', '执行中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
    ]

    EXECUTION_MODE_CHOICES = [
        ('PARALLEL', '并行执行'),
        ('SEQUENTIAL', '顺序执行'),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField('计划名称', max_length=200)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='PENDING')
    source_report = models.ForeignKey(DataIntegrityReport, on_delete=models.SET_NULL, null=True, blank=True, related_name='plans')
    execution_mode = models.CharField('执行模式', max_length=20, choices=EXECUTION_MODE_CHOICES, default='PARALLEL')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)

    class Meta:
        db_table = 'collector_collect_plan'
        ordering = ['-created_at']
        verbose_name = '采集计划'
        verbose_name_plural = '采集计划'

    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"
```

**Step 3: 扩展 CollectJob 模型添加 plan 外键**

在 `CollectJob` 类中添加 plan 字段（在 `created_at` 字段后）：

```python
    plan = models.ForeignKey(CollectPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')
```

注意：由于 CollectPlan 引用 CollectJob 需要在 CollectJob 之后定义，需要使用字符串引用或调整顺序。建议在 CollectJob 中使用字符串引用：

```python
    plan = models.ForeignKey('CollectPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')
```

**Step 4: 执行数据库迁移**

```bash
cd backend && python manage.py makemigrations saa_collector
cd backend && python manage.py migrate saa_collector
```

**Step 5: Commit**

```bash
git add backend/saa_collector/models.py backend/saa_collector/migrations/
git commit -m "feat: add DataIntegrityReport, DataIntegrityItem and CollectPlan models"
```

---

## Task 2: 创建 Serializers

**Files:**
- Modify: `backend/saa_collector/serializers.py`

**Step 1: 添加 DataIntegrityReport Serializers**

在文件末尾添加：

```python
from .models import DataIntegrityReport, DataIntegrityItem, CollectPlan


class DataIntegrityItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataIntegrityItem
        fields = ['id', 'data_type', 'stock_code', 'missing_periods', 'selected']
        read_only_fields = ['id', 'data_type', 'stock_code', 'missing_periods']


class DataIntegrityReportSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    stock_scope_display = serializers.CharField(source='get_stock_scope_display', read_only=True)
    items = DataIntegrityItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = DataIntegrityReport
        fields = [
            'id', 'name', 'status', 'status_display',
            'stock_scope', 'stock_scope_display', 'stock_codes',
            'date_start', 'date_end',
            'created_at', 'completed_at',
            'items', 'items_count'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'completed_at']

    def get_items_count(self, obj):
        return obj.items.count()


class DataIntegrityReportCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    stock_scope = serializers.ChoiceField(choices=['ALL', 'SELECTED'], default='ALL')
    stock_codes = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        default=list
    )
    date_start = serializers.DateField(required=False, allow_null=True)
    date_end = serializers.DateField(required=False, allow_null=True)


class DataIntegrityItemBulkUpdateSerializer(serializers.Serializer):
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text='要更新的 item ID 列表'
    )
    selected = serializers.BooleanField(help_text='选中状态')
```

**Step 2: 添加 CollectPlan Serializers**

继续添加：

```python
class CollectJobBriefSerializer(serializers.ModelSerializer):
    data_type_display = serializers.CharField(source='get_data_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CollectJob
        fields = [
            'id', 'data_type', 'data_type_display', 'symbols', 'params',
            'status', 'status_display', 'start_time', 'end_time', 'message'
        ]


class CollectPlanSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    execution_mode_display = serializers.CharField(source='get_execution_mode_display', read_only=True)
    jobs = CollectJobBriefSerializer(many=True, read_only=True)
    jobs_count = serializers.SerializerMethodField()
    source_report_name = serializers.CharField(source='source_report.name', read_only=True)

    class Meta:
        model = CollectPlan
        fields = [
            'id', 'name', 'status', 'status_display',
            'source_report', 'source_report_name',
            'execution_mode', 'execution_mode_display',
            'created_at', 'started_at', 'completed_at',
            'jobs', 'jobs_count'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'started_at', 'completed_at']

    def get_jobs_count(self, obj):
        return obj.jobs.count()


class CollectPlanCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    source_report = serializers.PrimaryKeyRelatedField(
        queryset=DataIntegrityReport.objects.all(),
        required=False,
        allow_null=True
    )
    execution_mode = serializers.ChoiceField(choices=['PARALLEL', 'SEQUENTIAL'], default='PARALLEL')


class CollectPlanUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    execution_mode = serializers.ChoiceField(choices=['PARALLEL', 'SEQUENTIAL'], required=False)
```

**Step 3: Commit**

```bash
git add backend/saa_collector/serializers.py
git commit -m "feat: add serializers for DataIntegrityReport and CollectPlan"
```

---

## Task 3: 创建 DataIntegrityReport API Views

**Files:**
- Modify: `backend/saa_collector/views.py`
- Modify: `backend/saa_collector/urls.py`

**Step 1: 在 views.py 中添加 DataIntegrityReport Views**

在文件末尾添加：

```python
from .models import CollectJob, DataIntegrityReport, DataIntegrityItem, CollectPlan
from .serializers import (
    CollectJobSerializer, CollectJobCreateSerializer,
    DataStatusSerializer, DataCompletenessSerializer,
    DataIntegrityReportSerializer, DataIntegrityReportCreateSerializer,
    DataIntegrityItemSerializer, DataIntegrityItemBulkUpdateSerializer,
    CollectPlanSerializer, CollectPlanCreateSerializer, CollectPlanUpdateSerializer,
    CollectJobBriefSerializer,
)


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
        reports = DataIntegrityReport.objects.all()
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

        for data_type in report.data_types:
            if data_type == 'trade_days':
                items = self._check_trade_days_missing(report)
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
            year, week = int(period[:4]), int(period[6:8])
            from datetime import datetime
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
            group_expr = "YEAR(date)"
        elif frequency == 'quarterly':
            select_expr = "CONCAT(YEAR(date), '-Q', QUARTER(date))"
            group_expr = "YEAR(date), QUARTER(date)"
        elif frequency == 'monthly':
            select_expr = "DATE_FORMAT(date, '%Y-%m')"
            group_expr = "DATE_FORMAT(date, '%Y-%m')"
        elif frequency == 'weekly':
            select_expr = "CONCAT(YEAR(date), '-W', LPAD(WEEK(date, 1), 2, '0'))"
            group_expr = "YEAR(date), WEEK(date, 1)"
        elif frequency == 'daily':
            select_expr = "date"
            group_expr = "date"

        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT symbol, {select_expr} as period
                FROM {table_name}
                WHERE symbol IN ({placeholders})
                  AND date BETWEEN %s AND %s
                GROUP BY symbol, {group_expr}
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
            elif frequency == 'daily':
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
            items_queryset = items_queryset.filter(data_type=data_type)

        stock_code = request.query_params.get('stock_code')
        if stock_code:
            items_queryset = items_queryset.filter(stock_code__icontains=stock_code)

        selected = request.query_params.get('selected')
        if selected is not None:
            if selected.lower() == 'true':
                items_queryset = items_queryset.filter(selected=True)
            elif selected.lower() == 'false':
                items_queryset = items_queryset.filter(selected=False)

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 100))

        items_count = items_queryset.count()
        start = (page - 1) * page_size
        end = start + page_size

        items = items_queryset[start:end]
        items_data = DataIntegrityItemSerializer(items, many=True).data

        report_data = DataIntegrityReportSerializer(report).data
        report_data['items'] = items_data
        report_data['items_count'] = items_count
        report_data['pagination'] = {
            'page': page,
            'page_size': page_size,
            'total': items_count,
            'total_pages': (items_count + page_size - 1) // page_size
        }

        return Response({'success': True, 'data': report_data})


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

        data_type = request.data.get('data_type')
        if data_type:
            items_queryset = items_queryset.filter(data_type=data_type)

        stock_code = request.data.get('stock_code')
        if stock_code:
            items_queryset = items_queryset.filter(stock_code__icontains=stock_code)

        selected = request.data.get('selected', True)

        updated = items_queryset.update(selected=selected)

        return Response({'success': True, 'data': {'updated_count': updated}})


class DataIntegrityReportGeneratePlanView(APIView):
    def post(self, request, pk):
        report = get_object_or_404(DataIntegrityReport, pk=pk)

        if report.status != 'COMPLETED':
            return Response({'error': '报告未完成'}, status=status.HTTP_400_BAD_REQUEST)

        selected_items = report.items.filter(selected=True)
        if not selected_items.exists():
            return Response({'error': '未选择任何缺失项'}, status=status.HTTP_400_BAD_REQUEST)

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

        return Response(CollectPlanSerializer(plan).data, status=status.HTTP_201_CREATED)
```

**Step 2: 在 urls.py 中添加路由**

```python
    path('integrity-reports/', views.DataIntegrityReportListView.as_view(), name='integrity-report-list'),
    path('integrity-reports/<int:pk>/', views.DataIntegrityReportDetailView.as_view(), name='integrity-report-detail'),
    path('integrity-reports/<int:pk>/items/', views.DataIntegrityReportItemsUpdateView.as_view(), name='integrity-report-items'),
    path('integrity-reports/<int:pk>/generate-plan/', views.DataIntegrityReportGeneratePlanView.as_view(), name='integrity-report-generate-plan'),
```

**Step 3: Commit**

```bash
git add backend/saa_collector/views.py backend/saa_collector/urls.py
git commit -m "feat: add DataIntegrityReport API views and urls"
```

---

## Task 4: 创建 CollectPlan API Views

**Files:**
- Modify: `backend/saa_collector/views.py`
- Modify: `backend/saa_collector/urls.py`

**Step 1: 在 views.py 中添加 CollectPlan Views**

```python
class CollectPlanListView(generics.ListCreateAPIView):
    queryset = CollectPlan.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CollectPlanCreateSerializer
        return CollectPlanSerializer

    def perform_create(self, serializer):
        serializer.save()


class CollectPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CollectPlan.objects.all()
    serializer_class = CollectPlanSerializer

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return CollectPlanUpdateSerializer
        return CollectPlanSerializer

    def update(self, request, *args, **kwargs):
        plan = self.get_object()
        if plan.status != 'PENDING':
            return Response({'error': '只能编辑待执行的计划'}, status=status.HTTP_400_BAD_REQUEST)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        plan = self.get_object()
        if plan.status != 'PENDING':
            return Response({'error': '只能删除待执行的计划'}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


class CollectPlanExecuteView(APIView):
    def post(self, request, pk):
        plan = get_object_or_404(CollectPlan, pk=pk)

        if plan.status != 'PENDING':
            return Response({'error': '计划状态不正确'}, status=status.HTTP_400_BAD_REQUEST)

        plan.status = 'RUNNING'
        plan.started_at = timezone.now()
        plan.save()

        thread = threading.Thread(target=self._execute_plan, args=(plan.id,))
        thread.start()

        return Response(CollectPlanSerializer(plan).data)

    def _execute_plan(self, plan_id):
        from django.db import connection
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
            try:
                plan = CollectPlan.objects.get(id=plan_id)
                plan.status = 'FAILED'
                plan.completed_at = timezone.now()
                plan.save()
            except:
                pass
        finally:
            connection.close()

    def _execute_job(self, job_id):
        try:
            job = CollectJob.objects.get(id=job_id)
            job.start()
            job.complete(success=True, message='执行完成')
        except Exception as e:
            try:
                job = CollectJob.objects.get(id=job_id)
                job.complete(success=False, message=str(e))
            except:
                pass
```

**Step 2: 在 urls.py 中添加路由**

```python
    path('collect-plans/', views.CollectPlanListView.as_view(), name='collect-plan-list'),
    path('collect-plans/<int:pk>/', views.CollectPlanDetailView.as_view(), name='collect-plan-detail'),
    path('collect-plans/<int:pk>/execute/', views.CollectPlanExecuteView.as_view(), name='collect-plan-execute'),
```

**Step 3: Commit**

```bash
git add backend/saa_collector/views.py backend/saa_collector/urls.py
git commit -m "feat: add CollectPlan API views and urls"
```

---

## Task 5: 更新前端路由

**Files:**
- Modify: `frontend/src/router/index.ts`

**Step 1: 添加新路由**

```typescript
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
```

**Step 2: Commit**

```bash
git add frontend/src/router/index.ts
git commit -m "feat: add routes for integrity reports and collect plans"
```

---

## Task 6: 更新导航栏

**Files:**
- Modify: `frontend/src/App.vue`

**Step 1: 添加新菜单项**

在 `<el-menu>` 中添加：

```vue
<el-menu-item index="/integrity-reports">
  <el-icon><Document /></el-icon>
  <span>完整性报告</span>
</el-menu-item>
```

在"数据采集"后添加：

```vue
<el-menu-item index="/collect-plans">
  <el-icon><List /></el-icon>
  <span>采集计划</span>
</el-menu-item>
```

需要导入 Document 图标：

```typescript
import { DataLine, DocumentChecked, Download, List, Document } from '@element-plus/icons-vue'
```

**Step 2: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: add navigation items for integrity reports and collect plans"
```

---

## Task 7: 创建完整性报告列表页

**Files:**
- Create: `frontend/src/views/IntegrityReportsView.vue`

**Step 1: 创建页面组件**

```vue
<template>
  <div class="integrity-reports">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>完整性报告</span>
          <el-button type="primary" @click="showCreateDialog">新建报告</el-button>
        </div>
      </template>

      <el-table :data="reports" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="报告名称" />
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="items_count" label="缺失项数" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewReport(row.id)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialogVisible" title="新建完整性报告" width="500px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="报告名称">
          <el-input v-model="createForm.name" />
        </el-form-item>
        <el-form-item label="股票范围">
          <el-radio-group v-model="createForm.stock_scope">
            <el-radio value="ALL">全部股票</el-radio>
            <el-radio value="SELECTED">选定股票</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createForm.stock_scope === 'SELECTED'" label="股票代码">
          <el-input v-model="stockCodesInput" type="textarea" placeholder="每行一个股票代码" />
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="createForm.date_start" type="date" />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="createForm.date_end" type="date" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createReport" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const reports = ref([])
const loading = ref(false)
const createDialogVisible = ref(false)
const creating = ref(false)
const stockCodesInput = ref('')

const createForm = ref({
  name: '',
  stock_scope: 'ALL',
  stock_codes: [],
  date_start: null,
  date_end: null
})

const fetchReports = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/integrity-reports/')
    reports.value = response.data
  } finally {
    loading.value = false
  }
}

const showCreateDialog = () => {
  createForm.value = {
    name: '',
    stock_scope: 'ALL',
    stock_codes: [],
    date_start: null,
    date_end: null
  }
  stockCodesInput.value = ''
  createDialogVisible.value = true
}

const createReport = async () => {
  creating.value = true
  try {
    const data = { ...createForm.value }
    if (data.stock_scope === 'SELECTED') {
      data.stock_codes = stockCodesInput.value.split('\n').map(s => s.trim()).filter(Boolean)
    }
    await axios.post('/api/integrity-reports/', data)
    createDialogVisible.value = false
    fetchReports()
  } finally {
    creating.value = false
  }
}

const viewReport = (id: number) => {
  router.push(`/integrity-reports/${id}`)
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'GENERATING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

onMounted(() => {
  fetchReports()
})
</script>

<style scoped>
.integrity-reports {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
```

**Step 2: Commit**

```bash
git add frontend/src/views/IntegrityReportsView.vue
git commit -m "feat: add IntegrityReportsView for listing reports"
```

---

## Task 8: 创建完整性报告详情页 (AG Grid 版本)

**Files:**
- Create: `frontend/src/views/IntegrityReportDetailView.vue`

**Step 1: 创建页面组件**

```vue
<template>
  <div class="integrity-report-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <el-button link @click="$router.back()">返回</el-button>
            <span style="margin-left: 16px; font-size: 18px;">{{ report?.name }}</span>
            <el-tag :type="getStatusType(report?.status)" style="margin-left: 8px;">
              {{ report?.status_display }}
            </el-tag>
          </div>
          <el-button
            type="primary"
            @click="generatePlan"
            :disabled="report?.status !== 'COMPLETED' || selectedCount === 0"
            :loading="generating"
          >
            生成采集计划
          </el-button>
        </div>
      </template>

      <div v-if="report?.status === 'GENERATING'" class="generating">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>报告生成中，请稍候...</span>
      </div>

      <div v-else>
        <div class="summary">
          <el-statistic title="缺失项总数" :value="report?.items_count || 0" />
          <el-statistic title="已选择" :value="selectedCount" />
        </div>

        <div class="toolbar">
          <el-button @click="selectAllFiltered" :disabled="!hasFilteredItems">
            全选当前筛选结果
          </el-button>
          <el-button @click="deselectAllFiltered" :disabled="!hasFilteredItems">
            取消选择当前筛选结果
          </el-button>
        </div>

        <ag-grid-vue
          class="ag-theme-quartz"
          :theme="gridTheme"
          :columnDefs="columnDefs"
          :rowData="rowData"
          :rowSelection="'multiple'"
          :pagination="true"
          :paginationPageSize="100"
          :defaultColDef="defaultColDef"
          :suppressRowClickSelection="true"
          @grid-ready="onGridReady"
          @selection-changed="onSelectionChanged"
          @filter-changed="onFilterChanged"
          @pagination-changed="onPaginationChanged"
          style="height: 500px; width: 100%; margin-top: 16px"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated, watch } from 'vue'
import { useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import { themeQuartz } from 'ag-grid-community'
import api from '@/utils/api'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{ id: string }>()
const router = useRouter()
const report = ref<any>(null)
const loading = ref(true)
const generating = ref(false)
let pollTimer: number | null = null

const gridApi = ref<any>(null)
const rowData = ref<any[]>([])
const selectedCount = ref(0)
const currentFilters = ref<{ data_type?: string; stock_code?: string }>({})

const hasFilteredItems = computed(() => {
  return Object.values(currentFilters.value).some(v => v)
})

const columnDefs = [
  {
    headerName: '选择',
    width: 70,
    pinned: 'left',
    checkboxSelection: true,
    headerCheckboxSelection: true,
    suppressMenu: true
  },
  {
    field: 'data_type',
    headerName: '数据类型',
    width: 150,
    filter: 'agSetColumnFilter',
    filterParams: {
    buttons: ['reset'],
    closeOnApply: true
  }
  },
  {
    field: 'stock_code',
    headerName: '股票代码',
    width: 120,
    filter: 'agTextColumnFilter',
    filterParams: {
    buttons: ['reset'],
    closeOnApply: true
  }
  },
  {
    field: 'missing_periods',
    headerName: '缺失周期',
    flex: 1,
    autoHeight: true,
    cellRenderer: (params: any) => params.value?.join(', ') || '',
    suppressMenu: true
  }
]

const defaultColDef = {
  sortable: true,
  resizable: true
}

const gridTheme = themeQuartz

const onGridReady = (params: any) => {
  gridApi.value = params.api
  loadItems()
}

const loadItems = async () => {
  if (!gridApi.value) return
  const params: any = {
    page: 1,
    page_size: 100
  }
  if (currentFilters.value.data_type) {
    params.data_type = currentFilters.value.data_type
  }
  if (currentFilters.value.stock_code) {
    params.stock_code = currentFilters.value.stock_code
  }
  try {
    const response = await api.get(`/integrity-reports/${props.id}/`, { params })
    if (response.data.success) {
      report.value = response.data.data
      rowData.value = response.data.data.items || []
      selectedCount.value = response.data.data.items?.filter((i: any) => i.selected).length || 0
    }
  } catch (error) {
    console.error('Failed to load items:', error)
    ElMessage.error('加载数据失败')
  }
}
const onSelectionChanged = (event: any) => {
  const selectedNodes = gridApi.value.getSelectedNodes()
  const itemIds = selectedNodes.map((node: any) => node.data.id)
  if (itemIds.length === 0) return
  try {
    await api.patch(`/integrity-reports/${props.id}/items/`, {
      item_ids: itemIds,
      selected: true
    })
    loadItems()
  } catch (error) {
    ElMessage.error('更新失败')
  }
}
const onFilterChanged = (event: any) => {
  const filterModel = gridApi.value.getFilterModel() || {}
  currentFilters.value = {}
  if (filterModel.data_type) {
    currentFilters.value.data_type = filterModel.data_type.filter
  }
  if (filterModel.stock_code) {
    currentFilters.value.stock_code = filterModel.stock_code.filter
  }
  loadItems()
}
const onPaginationChanged = (event: any) => {
}
const selectAllFiltered = async () => {
  try {
    const response = await api.post(
      `/integrity-reports/${props.id}/items/select-all/`,
      {
        ...currentFilters.value,
        selected: true
      }
    )
    ElMessage.success(`已选择 ${response.data.data.updated_count} 项`)
    loadItems()
  } catch (error) {
    ElMessage.error('全选失败')
  }
}
const deselectAllFiltered = async () => {
  try {
    const response = await api.post(
      `/integrity-reports/${props.id}/items/select-all/`,
      {
        ...currentFilters.value,
        selected: false
      }
    )
    ElMessage.success(`已取消选择 ${response.data.data.updated_count} 项`)
    loadItems()
  } catch (error) {
    ElMessage.error('取消选择失败')
  }
}
const fetchReport = async () => {
  try {
    const response = await api.get(`/integrity-reports/${props.id}/`)
    report.value = response.data.data
    return report.value.status
  } catch (error) {
    console.error('Failed to fetch report:', error)
    return null
  }
}
const pollReport = async () => {
  const status = await fetchReport()
  if (status === 'GENERATING') {
    pollTimer = window.setTimeout(pollReport, 3000)
  } else {
    loading.value = false
    loadItems()
  }
}
const generatePlan = async () => {
  generating.value = true
  try {
    const response = await api.post(`/integrity-reports/${props.id}/generate-plan/`)
    ElMessage.success('计划已生成')
    router.push(`/collect-plans/${response.data.data.id}/edit`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '生成失败')
  } finally {
    generating.value = false
  }
}
const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'GENERATING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}
onMounted(() => {
  pollReport()
})
onActivated(() => {
  loading.value = true
  pollReport()
})
onUnmounted(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
  }
})
</script>

<style scoped>
.integrity-report-detail {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.summary {
  display: flex;
  gap: 40px;
}
.toolbar {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
.generating {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: #909399;
}
</style>
```

**Step 2: Commit**

```bash
git add frontend/src/views/IntegrityReportDetailView.vue
git commit -m "feat: update IntegrityReportDetailView with AG Grid"
```

**Step 2: Commit**

```bash
git add frontend/src/views/IntegrityReportDetailView.vue
git commit -m "feat: add IntegrityReportDetailView for report details"
```

---

## Task 9: 创建采集计划列表页

**Files:**
- Create: `frontend/src/views/CollectPlansView.vue`

**Step 1: 创建页面组件**

```vue
<template>
  <div class="collect-plans">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>采集计划</span>
          <el-button type="primary" @click="$router.push('/collect-plans/new')">新建计划</el-button>
        </div>
      </template>

      <el-table :data="plans" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="计划名称" />
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="execution_mode_display" label="执行模式" width="100" />
        <el-table-column prop="jobs_count" label="作业数" width="80" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewPlan(row.id)">查看</el-button>
            <el-button
              link
              type="primary"
              v-if="row.status === 'PENDING'"
              @click="$router.push(`/collect-plans/${row.id}/edit`)"
            >编辑</el-button>
            <el-button
              link
              type="danger"
              v-if="row.status === 'PENDING'"
              @click="deletePlan(row.id)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const plans = ref([])
const loading = ref(false)

const fetchPlans = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/collect-plans/')
    plans.value = response.data
  } finally {
    loading.value = false
  }
}

const viewPlan = (id: number) => {
  router.push(`/collect-plans/${id}`)
}

const deletePlan = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定要删除该计划吗？', '提示', {
      type: 'warning'
    })
    await axios.delete(`/api/collect-plans/${id}/`)
    ElMessage.success('删除成功')
    fetchPlans()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

onMounted(() => {
  fetchPlans()
})
</script>

<style scoped>
.collect-plans {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
```

**Step 2: Commit**

```bash
git add frontend/src/views/CollectPlansView.vue
git commit -m "feat: add CollectPlansView for listing plans"
```

---

## Task 10: 创建采集计划详情页

**Files:**
- Create: `frontend/src/views/CollectPlanDetailView.vue`

**Step 1: 创建页面组件**

```vue
<template>
  <div class="collect-plan-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <el-button link @click="$router.back()">返回</el-button>
            <span style="margin-left: 16px; font-size: 18px;">{{ plan?.name }}</span>
            <el-tag :type="getStatusType(plan?.status)" style="margin-left: 8px;">
              {{ plan?.status_display }}
            </el-tag>
          </div>
          <div>
            <el-button
              v-if="plan?.status === 'PENDING'"
              @click="$router.push(`/collect-plans/${plan?.id}/edit`)"
            >编辑</el-button>
            <el-button
              type="primary"
              v-if="plan?.status === 'PENDING'"
              @click="executePlan"
              :loading="executing"
            >执行</el-button>
          </div>
        </div>
      </template>

      <el-descriptions :column="3" border>
        <el-descriptions-item label="计划名称">{{ plan?.name }}</el-descriptions-item>
        <el-descriptions-item label="执行模式">{{ plan?.execution_mode_display }}</el-descriptions-item>
        <el-descriptions-item label="来源报告">{{ plan?.source_report_name || '无' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ plan?.created_at }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ plan?.started_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ plan?.completed_at || '-' }}</el-descriptions-item>
      </el-descriptions>

      <h3 style="margin-top: 20px;">采集作业</h3>
      <el-table :data="plan?.jobs" style="margin-top: 12px;">
        <el-table-column prop="data_type_display" label="数据类型" width="150" />
        <el-table-column label="股票范围">
          <template #default="{ row }">
            <span>{{ row.symbols?.slice(0, 5).join(', ') }}{{ row.symbols?.length > 5 ? '...' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期范围" width="200">
          <template #default="{ row }">
            <span>{{ row.params?.start_date || '-' }} ~ {{ row.params?.end_date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getJobStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行时间" width="180">
          <template #default="{ row }">
            <span v-if="row.start_time">{{ row.start_time }}</span>
            <span v-if="row.end_time"> ~ {{ row.end_time }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="消息" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const props = defineProps<{ id: string }>()
const router = useRouter()
const plan = ref<any>(null)
const loading = ref(true)
const executing = ref(false)
let pollTimer: number | null = null

const fetchPlan = async () => {
  try {
    const response = await axios.get(`/api/collect-plans/${props.id}/`)
    plan.value = response.data
    return response.data.status
  } catch (error) {
    console.error('Failed to fetch plan:', error)
    return null
  }
}

const pollPlan = async () => {
  const status = await fetchPlan()
  if (status === 'RUNNING') {
    pollTimer = window.setTimeout(pollPlan, 3000)
  } else {
    loading.value = false
  }
}

const executePlan = async () => {
  executing.value = true
  try {
    await axios.post(`/api/collect-plans/${props.id}/execute/`)
    ElMessage.success('计划开始执行')
    loading.value = true
    pollPlan()
  } finally {
    executing.value = false
  }
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

const getJobStatusType = (status: string) => {
  const types: Record<string, string> = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'SUCCESS': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

onMounted(() => {
  fetchPlan().then(() => {
    loading.value = false
  })
})

onUnmounted(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
  }
})
</script>

<style scoped>
.collect-plan-detail {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
```

**Step 2: Commit**

```bash
git add frontend/src/views/CollectPlanDetailView.vue
git commit -m "feat: add CollectPlanDetailView for plan details"
```

---

## Task 11: 创建采集计划编辑页

**Files:**
- Create: `frontend/src/views/CollectPlanEditView.vue`

**Step 1: 创建页面组件**

```vue
<template>
  <div class="collect-plan-edit">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>{{ isEdit ? '编辑计划' : '新建计划' }}</span>
        </div>
      </template>

      <el-form :model="form" label-width="100px" style="max-width: 600px;">
        <el-form-item label="计划名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="执行模式">
          <el-radio-group v-model="form.execution_mode">
            <el-radio value="PARALLEL">并行执行</el-radio>
            <el-radio value="SEQUENTIAL">顺序执行</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-divider>采集作业</el-divider>

        <div v-for="(job, index) in form.jobs" :key="index" class="job-item">
          <el-card shadow="never">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="数据类型">
                  <el-select v-model="job.data_type">
                    <el-option label="交易日" value="trade_days" />
                    <el-option label="股票基本信息" value="stock_info" />
                    <el-option label="最新行情" value="quote" />
                    <el-option label="历史行情" value="historical_quote" />
                    <el-option label="资产负债表" value="balance_sheet" />
                    <el-option label="利润表" value="income" />
                    <el-option label="现金流量表" value="cash_flow" />
                    <el-option label="分红数据" value="dividend" />
                    <el-option label="主营业务" value="main_business" />
                    <el-option label="股本变动" value="capital" />
                    <el-option label="估值数据" value="valuation" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="开始日期">
                  <el-date-picker v-model="job.date_start" type="date" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="结束日期">
                  <el-date-picker v-model="job.date_end" type="date" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="股票代码">
              <el-input v-model="job.symbols_input" type="textarea" placeholder="每行一个股票代码，留空则全量" :rows="3" />
            </el-form-item>
            <el-button type="danger" link @click="removeJob(index)">删除此作业</el-button>
          </el-card>
        </div>

        <el-button type="primary" link @click="addJob" style="margin-top: 12px;">
          + 添加作业
        </el-button>

        <el-form-item style="margin-top: 24px;">
          <el-button type="primary" @click="savePlan" :loading="saving">保存</el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)

const isEdit = computed(() => !!route.params.id)

const form = ref({
  name: '',
  execution_mode: 'PARALLEL',
  jobs: [] as any[]
})

const addJob = () => {
  form.value.jobs.push({
    data_type: 'quote',
    symbols_input: '',
    date_start: null,
    date_end: null
  })
}

const removeJob = (index: number) => {
  form.value.jobs.splice(index, 1)
}

const fetchPlan = async () => {
  if (!route.params.id) return
  loading.value = true
  try {
    const response = await axios.get(`/api/collect-plans/${route.params.id}/`)
    const plan = response.data
    form.value.name = plan.name
    form.value.execution_mode = plan.execution_mode
    form.value.jobs = plan.jobs.map((job: any) => ({
      id: job.id,
      data_type: job.data_type,
      symbols_input: job.symbols?.join('\n') || '',
      date_start: job.params?.start_date || null,
      date_end: job.params?.end_date || null
    }))
  } finally {
    loading.value = false
  }
}

const savePlan = async () => {
  if (!form.value.name) {
    ElMessage.warning('请输入计划名称')
    return
  }

  saving.value = true
  try {
    const data = {
      name: form.value.name,
      execution_mode: form.value.execution_mode
    }

    if (isEdit.value) {
      await axios.patch(`/api/collect-plans/${route.params.id}/`, data)
      ElMessage.success('保存成功')
      router.push(`/collect-plans/${route.params.id}`)
    } else {
      const response = await axios.post('/api/collect-plans/', data)
      ElMessage.success('创建成功')
      router.push(`/collect-plans/${response.data.id}`)
    }
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (isEdit.value) {
    fetchPlan()
  } else {
    addJob()
  }
})
</script>

<style scoped>
.collect-plan-edit {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.job-item {
  margin-bottom: 16px;
}
</style>
```

**Step 2: Commit**

```bash
git add frontend/src/views/CollectPlanEditView.vue
git commit -m "feat: add CollectPlanEditView for creating/editing plans"
```

---

## Task 12: 集成测试与修复

**Step 1: 启动后端服务测试 API**

```bash
cd backend && python manage.py runserver
```

**Step 2: 启动前端服务测试页面**

```bash
cd frontend && npm run dev
```

**Step 3: 测试完整工作流**

1. 访问完整性报告页面，创建新报告
2. 查看报告详情，勾选缺失项
3. 生成采集计划
4. 编辑计划，执行计划
5. 查看执行进度

**Step 4: 修复发现的问题**

根据测试结果修复代码问题。

**Step 5: Commit**

```bash
git add -A
git commit -m "fix: fix issues found during integration testing"
```

---

## Summary

实现完成后，项目将具备：

1. **DataIntegrityReport** - 数据完整性报告模型及 API
2. **CollectPlan** - 采集计划模型及 API
3. **CollectJob** - 扩展支持归属计划
4. **前端页面** - 报告列表/详情、计划列表/详情/编辑
5. **执行机制** - 支持并行/顺序执行
