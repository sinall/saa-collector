from django.db import migrations, models
import django.db.models.deletion

import saa_collector.constants


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='CollectJob',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('data_type', models.CharField(choices=saa_collector.constants.DATA_TYPE_CHOICES, max_length=50, verbose_name='数据类型')),
                ('config', models.JSONField(default=dict, verbose_name='任务配置')),
                ('status', models.CharField(choices=[('QUEUED', '排队中'), ('PENDING', '待执行'), ('RUNNING', '执行中'), ('SUCCESS', '成功'), ('FAILED', '失败')], default='PENDING', max_length=20, verbose_name='状态')),
                ('start_time', models.DateTimeField(blank=True, null=True, verbose_name='开始时间')),
                ('end_time', models.DateTimeField(blank=True, null=True, verbose_name='结束时间')),
                ('message', models.TextField(blank=True, null=True, verbose_name='消息')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
            ],
            options={
                'verbose_name': '采集任务',
                'verbose_name_plural': '采集任务',
                'db_table': 'collector_collect_job',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DataIntegrityReport',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200, verbose_name='报告名称')),
                ('status', models.CharField(choices=[('GENERATING', '生成中'), ('COMPLETED', '已完成'), ('FAILED', '失败')], default='GENERATING', max_length=20, verbose_name='状态')),
                ('filters', models.JSONField(default=dict, verbose_name='筛选条件')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='完成时间')),
            ],
            options={
                'verbose_name': '数据完整性报告',
                'verbose_name_plural': '数据完整性报告',
                'db_table': 'collector_data_integrity_report',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CollectPlan',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200, verbose_name='计划名称')),
                ('status', models.CharField(choices=[('QUEUED', '排队中'), ('PENDING', '待执行'), ('RUNNING', '执行中'), ('COMPLETED', '已完成'), ('FAILED', '失败')], default='PENDING', max_length=20, verbose_name='状态')),
                ('source', models.CharField(choices=[('MANUAL', '即时采集'), ('INTEGRITY', '修复计划'), ('SCHEDULE', '定时触发')], default='MANUAL', max_length=20, verbose_name='来源')),
                ('trigger_type', models.CharField(blank=True, choices=[('AUTO', '自动触发'), ('MANUAL', '手动触发')], max_length=20, null=True, verbose_name='触发类型')),
                ('source_schedule_id', models.IntegerField(blank=True, null=True, verbose_name='来源日程ID')),
                ('source_schedule_name', models.CharField(blank=True, max_length=200, null=True, verbose_name='来源日程名称')),
                ('execution_mode', models.CharField(choices=[('PARALLEL', '并行执行'), ('SEQUENTIAL', '顺序执行')], default='PARALLEL', max_length=20, verbose_name='执行模式')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('queued_at', models.DateTimeField(blank=True, null=True, verbose_name='入队时间')),
                ('queue_task_id', models.CharField(blank=True, max_length=100, null=True, verbose_name='队列任务ID')),
                ('started_at', models.DateTimeField(blank=True, null=True, verbose_name='开始时间')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='完成时间')),
                ('source_report', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='plans', to='saa_collector.dataintegrityreport')),
            ],
            options={
                'verbose_name': '采集计划',
                'verbose_name_plural': '采集计划',
                'db_table': 'collector_collect_plan',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='collectjob',
            name='plan',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs', to='saa_collector.collectplan'),
        ),
        migrations.CreateModel(
            name='CollectSchedule',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200, verbose_name='日程名称')),
                ('data_type', models.CharField(choices=saa_collector.constants.DATA_TYPE_CHOICES, max_length=50, verbose_name='数据类型')),
                ('symbols', models.JSONField(default=list, help_text='空列表表示全部股票', verbose_name='股票范围')),
                ('params', models.JSONField(default=dict, verbose_name='参数配置')),
                ('cron_expression', models.CharField(max_length=100, verbose_name='Cron表达式')),
                ('status', models.CharField(choices=[('ENABLED', '已启用'), ('DISABLED', '已禁用')], default='ENABLED', max_length=20, verbose_name='状态')),
                ('last_triggered_at', models.DateTimeField(blank=True, null=True, verbose_name='上次触发时间')),
                ('next_trigger_at', models.DateTimeField(blank=True, null=True, verbose_name='下次触发时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '采集日程',
                'verbose_name_plural': '采集日程',
                'db_table': 'collector_collect_schedule',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DataIntegrityItem',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('data_type', models.CharField(max_length=50, verbose_name='数据类型')),
                ('stock_code', models.CharField(blank=True, max_length=20, null=True, verbose_name='股票代码')),
                ('miss_period', models.CharField(blank=True, max_length=20, null=True, verbose_name='缺失周期')),
                ('selected', models.BooleanField(default=False, verbose_name='已选择')),
                ('status', models.CharField(choices=[('PENDING', '待修复'), ('FIXED', '已修复')], default='PENDING', max_length=20, verbose_name='修复状态')),
                ('fixed_at', models.DateTimeField(blank=True, null=True, verbose_name='修复时间')),
                ('fixed_by_plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='saa_collector.collectplan')),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='saa_collector.dataintegrityreport')),
            ],
            options={
                'verbose_name': '数据完整性项',
                'verbose_name_plural': '数据完整性项',
                'db_table': 'collector_data_integrity_item',
            },
        ),
    ]
