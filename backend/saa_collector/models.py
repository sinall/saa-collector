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
    plan = models.ForeignKey('CollectPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')
    
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
    
    FREQUENCY_CHOICES = [
        ('daily', '日度'),
        ('weekly', '周度'),
        ('monthly', '月度'),
        ('quarterly', '季度'),
        ('yearly', '年度'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    name = models.CharField('报告名称', max_length=200)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='GENERATING')
    stock_scope = models.CharField('股票范围', max_length=20, choices=STOCK_SCOPE_CHOICES, default='ALL')
    stock_codes = models.JSONField('股票列表', default=list)
    data_types = models.JSONField('数据类型列表', default=list)
    frequency = models.CharField('频度', max_length=20, choices=FREQUENCY_CHOICES, default='monthly')
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
