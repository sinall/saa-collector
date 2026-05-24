from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('saa_collector', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalApiCacheEntry',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('provider', models.CharField(max_length=50, verbose_name='数据源')),
                ('api_name', models.CharField(max_length=100, verbose_name='API名称')),
                ('cache_key', models.CharField(max_length=64, unique=True, verbose_name='缓存键')),
                ('canonical_call_json', models.JSONField(verbose_name='规范化调用')),
                ('params_json', models.JSONField(default=dict, verbose_name='调用参数')),
                ('fields', models.TextField(blank=True, default='', verbose_name='请求字段')),
                ('response_json', models.JSONField(default=list, verbose_name='原始响应')),
                ('raw_response_schema_version', models.CharField(max_length=50, verbose_name='原始响应Schema版本')),
                ('expires_at', models.DateTimeField(verbose_name='过期时间')),
                ('hit_count', models.PositiveIntegerField(default=0, verbose_name='命中次数')),
                ('last_hit_at', models.DateTimeField(blank=True, null=True, verbose_name='最后命中时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '外部API缓存',
                'verbose_name_plural': '外部API缓存',
                'db_table': 'collector_external_api_cache',
                'indexes': [
                    models.Index(fields=['provider', 'api_name'], name='collector_ex_provider_e840d2_idx'),
                    models.Index(fields=['expires_at'], name='collector_ex_expires_eb7359_idx'),
                ],
            },
        ),
    ]
