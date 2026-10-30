from django.db import migrations, models


def preserve_mysql_insert_default(apps, schema_editor):
    # The legacy config column already uses JSON_OBJECT() on production MySQL.
    # Keep old worker inserts compatible after Django removes its temporary default.
    if schema_editor.connection.vendor == 'mysql':
        table = schema_editor.quote_name(apps.get_model('saa_collector', 'CollectJob')._meta.db_table)
        schema_editor.execute('ALTER TABLE {} ALTER COLUMN `result` SET DEFAULT (JSON_OBJECT())'.format(table))


class Migration(migrations.Migration):
    dependencies = [('saa_collector', '0004_canonicalize_collect_schedule_date_params')]
    operations = [
        migrations.AddField(
            model_name='collectjob', name='result',
            field=models.JSONField(default=dict, blank=True, verbose_name='执行结果'),
        ),
        migrations.RunPython(preserve_mysql_insert_default, migrations.RunPython.noop, atomic=False),
    ]
