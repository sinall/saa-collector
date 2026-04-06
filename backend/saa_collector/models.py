from django.db import models
from django.utils import timezone

from .constants import DATA_TYPE_CHOICES


class CollectJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '待执行'),
        ('RUNNING', '执行中'),
        ('SUCCESS', '成功'),
        ('FAILED', '失败'),
    ]

    DATA_TYPE_CHOICES = DATA_TYPE_CHOICES

    id = models.BigAutoField(primary_key=True)
    data_type = models.CharField('数据类型', max_length=50, choices=DATA_TYPE_CHOICES)
    config = models.JSONField('任务配置', default=dict)
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

    id = models.BigAutoField(primary_key=True)
    name = models.CharField('报告名称', max_length=200)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='GENERATING')
    filters = models.JSONField('筛选条件', default=dict)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)


    @property
    def stock_scope(self):
        return self.filters.get('stock_scope', 'ALL')

    @property
    def stock_codes(self):
        return self.filters.get('stock_codes', [])

    @property
    def data_types(self):
        return self.filters.get('data_types', [])

    @property
    def frequency(self):
        return self.filters.get('frequency', 'monthly')

    @property
    def date_start(self):
        return self.filters.get('date_start')

    @property
    def date_end(self):
        return self.filters.get('date_end')

    class Meta:
        db_table = 'collector_data_integrity_report'
        ordering = ['-created_at']
        verbose_name = '数据完整性报告'
        verbose_name_plural = '数据完整性报告'

    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"


class DataIntegrityItem(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '待修复'),
        ('FIXED', '已修复'),
    ]

    id = models.BigAutoField(primary_key=True)
    report = models.ForeignKey(DataIntegrityReport, on_delete=models.CASCADE, related_name='items')
    data_type = models.CharField('数据类型', max_length=50)
    stock_code = models.CharField('股票代码', max_length=20, null=True, blank=True)
    miss_period = models.CharField('缺失周期', max_length=20, null=True, blank=True)
    selected = models.BooleanField('已选择', default=False)
    status = models.CharField('修复状态', max_length=20, choices=STATUS_CHOICES, default='PENDING')
    fixed_at = models.DateTimeField('修复时间', null=True, blank=True)
    fixed_by_plan = models.ForeignKey('CollectPlan', on_delete=models.SET_NULL, null=True, blank=True)

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

    SOURCE_CHOICES = [
        ('MANUAL', '即时采集'),
        ('INTEGRITY', '修复计划'),
        ('SCHEDULE', '定时触发'),
    ]

    TRIGGER_TYPE_CHOICES = [
        ('AUTO', '自动触发'),
        ('MANUAL', '手动触发'),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField('计划名称', max_length=200)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='PENDING')
    source = models.CharField('来源', max_length=20, choices=SOURCE_CHOICES, default='MANUAL')
    trigger_type = models.CharField('触发类型', max_length=20, choices=TRIGGER_TYPE_CHOICES, null=True, blank=True)
    source_report = models.ForeignKey(DataIntegrityReport, on_delete=models.SET_NULL, null=True, blank=True, related_name='plans')
    source_schedule_id = models.IntegerField('来源日程ID', null=True, blank=True)
    source_schedule_name = models.CharField('来源日程名称', max_length=200, null=True, blank=True)
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


class CollectSchedule(models.Model):
    STATUS_CHOICES = [
        ('ENABLED', '已启用'),
        ('DISABLED', '已禁用'),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField('日程名称', max_length=200)
    data_type = models.CharField('数据类型', max_length=50, choices=DATA_TYPE_CHOICES)
    symbols = models.JSONField('股票范围', default=list, help_text='空列表表示全部股票')
    params = models.JSONField('参数配置', default=dict)
    cron_expression = models.CharField('Cron表达式', max_length=100)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='ENABLED')
    last_triggered_at = models.DateTimeField('上次触发时间', null=True, blank=True)
    next_trigger_at = models.DateTimeField('下次触发时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'collector_collect_schedule'
        ordering = ['-created_at']
        verbose_name = '采集日程'
        verbose_name_plural = '采集日程'

    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"
