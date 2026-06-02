from rest_framework import serializers
from .constants import DATA_TYPE_CONFIG, is_data_type_visible
from .collect_job_config import build_collect_job_config
from .date_expressions import normalize_schedule_params, validate_schedule_params
from .models import CollectJob, DataIntegrityReport, DataIntegrityItem, CollectPlan, CollectSchedule
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
class InstantCollectJobSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    data_type = serializers.CharField(max_length=50, help_text='Data type to collect')
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        default=list,
        help_text='Stock codes list, empty for all stocks'
    )
    start_date = serializers.DateField(required=False, allow_null=True, help_text='Start date')
    end_date = serializers.DateField(required=False, allow_null=True, help_text='End date')
    report_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
        help_text='Report types (balance_sheet, income, cash_flow, dividend)'
    )

    def validate(self, attrs):
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError('结束日期不能早于开始日期')
        return attrs
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
        data_types = obj.filters.get('data_types', [])
        return [dt for dt in data_types if is_data_type_visible(dt, 'integrity_report')]

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

    def validate_data_types(self, value):
        filtered = [dt for dt in value if is_data_type_visible(dt, 'integrity_report')]
        if not filtered:
            raise serializers.ValidationError('请选择至少一种可用于完整性报告的数据类型')
        return filtered

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
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    source_schedule_id = serializers.IntegerField(read_only=True, allow_null=True)
    source_schedule_name = serializers.CharField(read_only=True)
    trigger_type_display = serializers.CharField(source='get_trigger_type_display', read_only=True)
    class Meta:
        model = CollectPlan
        fields = [
            'id', 'name', 'status', 'status_display',
            'source', 'source_display', 'trigger_type', 'trigger_type_display',
            'source_report', 'source_report_name',
            'source_schedule_id', 'source_schedule_name',
            'execution_mode', 'execution_mode_display',
            'created_at', 'queued_at', 'queue_task_id', 'started_at', 'completed_at',
            'jobs', 'jobs_count'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'queued_at', 'queue_task_id', 'started_at', 'completed_at']
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
    jobs = serializers.ListField(
        child=InstantCollectJobSerializer(),
        required=False,
        allow_empty=True,
        help_text='List of collection jobs to create'
    )

    def create(self, validated_data):
        plan = CollectPlan.objects.create(
            name=validated_data['name'],
            source_report=validated_data.get('source_report'),
            execution_mode=validated_data.get('execution_mode', 'PARALLEL')
        )

        jobs_data = validated_data.get('jobs', [])
        for job_data in jobs_data:
            CollectJob.objects.create(
                plan=plan,
                data_type=job_data['data_type'],
                config=build_collect_job_config(
                    symbols=job_data.get('symbols', []),
                    params={
                        'start_date': str(job_data['start_date']) if job_data.get('start_date') else None,
                        'end_date': str(job_data['end_date']) if job_data.get('end_date') else None,
                        'report_types': job_data.get('report_types', []),
                    },
                )
            )

        return plan
class CollectPlanUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    execution_mode = serializers.ChoiceField(choices=['PARALLEL', 'SEQUENTIAL'], required=False)
    jobs = serializers.ListField(
        child=InstantCollectJobSerializer(),
        required=False,
        allow_empty=True,
        help_text='Full list of collection jobs to keep on the plan'
    )


class CollectScheduleSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    data_type_display = serializers.CharField(source='get_data_type_display', read_only=True)

    class Meta:
        model = CollectSchedule
        fields = [
            'id', 'name', 'data_type', 'data_type_display',
            'symbols', 'params', 'cron_expression',
            'status', 'status_display',
            'last_triggered_at', 'next_trigger_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_triggered_at', 'next_trigger_at', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['params'] = normalize_schedule_params(data.get('params'))
        return data


class CollectScheduleCreateSerializer(serializers.ModelSerializer):
    def validate_params(self, value):
        try:
            return validate_schedule_params(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    class Meta:
        model = CollectSchedule
        fields = ['name', 'data_type', 'symbols', 'params', 'cron_expression', 'status']
        extra_kwargs = {
            'status': {'default': 'ENABLED'},
            'symbols': {'default': list},
            'params': {'default': dict},
        }


class CollectScheduleUpdateSerializer(serializers.ModelSerializer):
    def validate_params(self, value):
        try:
            return validate_schedule_params(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    class Meta:
        model = CollectSchedule
        fields = ['name', 'data_type', 'symbols', 'params', 'cron_expression', 'status']
