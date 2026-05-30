import json

from django.core.management.base import BaseCommand, CommandError

from saa_collector.services.common.mfactor_readiness_service import MfactorReadinessService


class Command(BaseCommand):
    help = 'Check whether collector-owned data required by mfactor is present.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output machine-readable JSON.',
        )
        parser.add_argument(
            '--fail-on-error',
            action='store_true',
            dest='fail_on_error',
            help='Exit with an error if any required object is missing or empty.',
        )
        parser.add_argument(
            '--deep',
            action='store_true',
            help='Also run exact row counts and max-date checks for views. This can be slow.',
        )

    def handle(self, *args, **options):
        result = MfactorReadinessService(deep=options.get('deep', False)).check()
        if options.get('json'):
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            self.write_text_result(result)

        if options.get('fail_on_error') and result['status'] != 'OK':
            raise CommandError('mfactor readiness check failed')

    def write_text_result(self, result):
        summary = result['summary']
        self.stdout.write(
            'mfactor readiness: {} (ok={}, error={})'.format(
                result['status'],
                summary['ok'],
                summary['error'],
            )
        )
        for item in result['items']:
            self.stdout.write(
                '[{status}] {object} rows={row_count} max_date={max_date} type={object_type} {message}'.format(
                    **item,
                ).rstrip()
            )
