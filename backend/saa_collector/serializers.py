from rest_framework import serializers
from .models import CollectJob


class CollectJobSerializer(serializers.ModelSerializer):
    data_type_display = serializers.CharField(source='get_data_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = CollectJob
        fields = [
            'id', 'data_type', 'data_type_display', 'symbols', 'params',
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


class DataCompletenessSerializer(serializers.Serializer):
    summary = serializers.DictField()
    by_stock = serializers.ListField()
    by_date = serializers.ListField()
    missing_details = serializers.ListField()
