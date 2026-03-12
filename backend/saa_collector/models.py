from django.db import models
from django.utils import timezone


class CollectJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '待执行'),
        ('RUNNING', '执行中'),
        ('SUCCESS', '成功'),
        ('FAILED', '失败'),
    ]
    
    DATA_TYPE_CHOICES = [
        ('trade_days', '交易日'),
        ('stock_info', '股票基本信息'),
        ('quote', '最新行情'),
        ('historical_quote', '历史行情'),
        ('balance_sheet', '资产负债表'),
        ('income', '利润表'),
        ('cash_flow', '现金流量表'),
        ('dividend', '分红数据'),
        ('main_business', '主营业务'),
        ('capital', '股本变动'),
        ('valuation', '估值数据'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    data_type = models.CharField('数据类型', max_length=50, choices=DATA_TYPE_CHOICES)
    symbols = models.JSONField('股票列表', default=list)
    params = models.JSONField('其他参数', default=dict)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='PENDING')
    start_time = models.DateTimeField('开始时间', null=True, blank=True)
    end_time = models.DateTimeField('结束时间', null=True, blank=True)
    message = models.TextField('消息', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    
    class Meta:
        db_table = 'collector_collect_job'
        ordering = ['-created_at']
        verbose_name = '采集任务'
        verbose_name_plural = '采集任务'
    
    def __str__(self):
        return f"{self.get_data_type_display()} - {self.status}"
    
    def start(self):
        self.status = 'RUNNING'
        self.start_time = timezone.now()
        self.save()
    
    def complete(self, success=True, message=None):
        self.status = 'SUCCESS' if success else 'FAILED'
        self.end_time = timezone.now()
        if message:
            self.message = message
        self.save()
