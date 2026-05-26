from django.db import migrations


def canonicalize_collect_schedule_params(apps, schema_editor):
    CollectSchedule = apps.get_model('saa_collector', 'CollectSchedule')

    for schedule in CollectSchedule.objects.all().iterator():
        params = dict(schedule.params or {})
        start_value = params.get('start_date')
        if start_value in (None, ''):
            start_value = params.get('date_start')
        end_value = params.get('end_date')
        if end_value in (None, ''):
            end_value = params.get('date_end')

        changed = False

        if params.pop('date_start', None) is not None:
            changed = True
        if params.pop('date_end', None) is not None:
            changed = True

        if start_value in (None, ''):
            if params.pop('start_date', None) is not None:
                changed = True
        else:
            if params.get('start_date') != start_value:
                params['start_date'] = start_value
                changed = True

        if end_value in (None, ''):
            if params.pop('end_date', None) is not None:
                changed = True
        else:
            if params.get('end_date') != end_value:
                params['end_date'] = end_value
                changed = True

        if changed:
            schedule.params = params
            schedule.save(update_fields=['params'])


def reverse_canonicalize_collect_schedule_params(apps, schema_editor):
    CollectSchedule = apps.get_model('saa_collector', 'CollectSchedule')

    for schedule in CollectSchedule.objects.all().iterator():
        params = dict(schedule.params or {})
        start_value = params.get('start_date')
        end_value = params.get('end_date')

        if start_value in (None, '') and end_value in (None, ''):
            continue

        if start_value not in (None, ''):
            params['date_start'] = start_value
        else:
            params.pop('date_start', None)

        if end_value not in (None, ''):
            params['date_end'] = end_value
        else:
            params.pop('date_end', None)

        schedule.params = params
        schedule.save(update_fields=['params'])


class Migration(migrations.Migration):
    dependencies = [
        ('saa_collector', '0003_external_api_cache_raw_response_body'),
    ]

    operations = [
        migrations.RunPython(
            canonicalize_collect_schedule_params,
            reverse_canonicalize_collect_schedule_params,
        ),
    ]
