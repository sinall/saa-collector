import hashlib
import json

from django.db import migrations, models


def migrate_response_json_to_body(apps, schema_editor):
    ExternalApiCacheEntry = apps.get_model('saa_collector', 'ExternalApiCacheEntry')
    for entry in ExternalApiCacheEntry.objects.all().iterator():
        response_json = getattr(entry, 'response_json', None)
        response_body = json.dumps(
            response_json,
            ensure_ascii=False,
            separators=(',', ':'),
        ).encode('utf-8')
        entry.response_body = response_body
        entry.response_content_type = 'application/json'
        entry.response_encoding = 'utf-8'
        entry.response_headers_json = {}
        entry.response_sha256 = hashlib.sha256(response_body).hexdigest()
        entry.save(update_fields=[
            'response_body',
            'response_content_type',
            'response_encoding',
            'response_headers_json',
            'response_sha256',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('saa_collector', '0002_external_api_cache_entry'),
    ]

    operations = [
        migrations.AddField(
            model_name='externalapicacheentry',
            name='request_method',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name='请求方法'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='request_url',
            field=models.TextField(blank=True, default='', verbose_name='请求URL'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='request_body',
            field=models.TextField(blank=True, default='', verbose_name='请求Body'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='response_status_code',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='响应状态码'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='response_headers_json',
            field=models.JSONField(default=dict, verbose_name='响应头'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='response_content_type',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='响应Content-Type'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='response_encoding',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='响应编码'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='response_filename',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='响应文件名'),
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='response_body',
            field=models.BinaryField(default=b'', verbose_name='原始响应Body'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='externalapicacheentry',
            name='response_sha256',
            field=models.CharField(blank=True, default='', max_length=64, verbose_name='响应SHA256'),
        ),
        migrations.RunPython(migrate_response_json_to_body, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='externalapicacheentry',
            name='response_json',
        ),
    ]
