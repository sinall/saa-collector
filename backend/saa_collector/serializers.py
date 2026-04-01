from rest_framework import serializers
from .models import CollectJob, DataIntegrityReport, DataIntegrityItem, CollectPlan
class CollectJobSerializer(serializers.ModelSerializer):
    data_type_display = serializers.CharField(source='get_data_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class Meta:
        model = CollectJob
        fields = [
            'id', 'data_type', 'data_type_display', 'config',
            'status', 'status_display', 'start_time', 'end_time',
            'message', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'start_time', 'end_time', 'message', 'created_at']
class CollectJobCreateSerializer(serializers.Serializer):
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        default=list,
        help_text='股票代码列表，为空则全量采集'
    )
    start_date = serializers.DateField(required=False, help_text='开始日期')
    end_date = serializers.DateField(required=False, help_text='结束日期')
    report_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
        help_text='报表类型列表 (balance_sheet, income, cash_flow, dividend)'
    )
class DataStatusSerializer(serializers.Serializer):
    data_type = serializers.CharField()
    data_type_display = serializers.CharField()
    count = serializers.IntegerField()
    latest_date = serializers.DateField(allow_null=True)
    earliest_date = serializers.DateField(allow_null=True)
    frequency = serializers.CharField(allow_null=True)
    completeness = serializers.FloatField(allow_null=True)
class DataCompletenessSerializer(serializers.Serializer):
    summary = serializers.DictField()
    by_stock = serializers.ListField()
    by_date = serializers.ListField()
    missing_details = serializers.ListField()
class DataIntegrityItemSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = DataIntegrityItem
        fields = ['id', 'data_type', 'stock_code', 'miss_period', 'selected', 'status', 'status_display', 'fixed_at']
        read_only_fields = ['id', 'data_type', 'stock_code', 'miss_period', 'status', 'status_display', 'fixed_at']
class FlattenedIntegrityItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    data_type = serializers.CharField()
    stock_code = serializers.CharField()
    period = serializers.CharField()
    selected = serializers.BooleanField()
    status = serializers.CharField()
    status_display = serializers.CharField()
    fixed_at = serializers.DateTimeField(allow_null=True)
class DataIntegrityReportSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    created_at_display = serializers.DateTimeField(
        source='created_at',
        format='%Y-%m-%d %H:%M:%S',
        read_only=True
    )
    completed_at_display = serializers.DateTimeField(
        source='completed_at',
        format='%Y-%m-%d %H:%M:%S',
        read_only=True,
        allow_null=True
    )
    stock_scope = serializers.SerializerMethodField()
    stock_codes = serializers.SerializerMethodField()
    data_types = serializers.SerializerMethodField()
    frequency = serializers.SerializerMethodField()
    date_start = serializers.SerializerMethodField()
    date_end = serializers.SerializerMethodField()

    class Meta:
        model = DataIntegrityReport
        fields = [
            'id', 'name', 'status', 'status_display',
            'filters',
            'stock_scope', 'stock_codes', 'data_types',
            'frequency', 'date_start', 'date_end',
            'created_at', 'created_at_display',
            'completed_at', 'completed_at_display',
            'items_count'
        ]
        read_only_fields = ['id', 'status', 'filters', 'created_at', 'completed_at']

    def get_stock_scope(self, obj):
        return obj.filters.get('stock_scope', 'ALL')

    def get_stock_codes(self, obj):
        return obj.filters.get('stock_codes', [])

    def get_data_types(self, obj):
        return obj.filters.get('data_types', [])

    def get_frequency(self, obj):
        return obj.filters.get('frequency', 'monthly')

    def get_date_start(self, obj):
        return obj.filters.get('date_start')

    def get_date_end(self, obj):
        return obj.filters.get('date_end')
class DataIntegrityReportCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    stock_scope = serializers.ChoiceField(choices=['ALL', 'SELECTED'], default='ALL')
    stock_codes = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        default=list
    )
    data_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list
    )
    frequency = serializers.ChoiceField(
        choices=['daily', 'weekly', 'monthly', 'quarterly', 'yearly'],
        default='monthly'
    )
    date_start = serializers.DateField(required=False, allow_null=True)
    date_end = serializers.DateField(required=False, allow_null=True)

    def create(self, validated_data):
        filters = {
            'stock_scope': validated_data.get('stock_scope', 'ALL'),
            'stock_codes': validated_data.get('stock_codes', []),
            'data_types': validated_data.get('data_types', []),
            'frequency': validated_data.get('frequency', 'monthly'),
            'date_start': str(validated_data['date_start']) if validated_data.get('date_start') else None,
            'date_end': str(validated_data['date_end']) if validated_data.get('date_end') else None,
        }
        return DataIntegrityReport.objects.create(
            name=validated_data['name'],
            filters=filters
        )
class DataIntegrityItemBulkUpdateSerializer(serializers.Serializer):
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text='要更新的 item ID 列表'
    )
    selected = serializers.BooleanField(help_text='选中状态')
class CollectJobBriefSerializer(serializers.ModelSerializer):
    data_type_display = serializers.CharField(source='get_data_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class Meta:
        model = CollectJob
        fields = [
            'id', 'data_type', 'data_type_display', 'config',
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
        if hasattr(obj, 'jobs_count'):
            return obj.jobs_count
        return len(obj.jobs.all()) if hasattr(obj, 'jobs') else 0
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
