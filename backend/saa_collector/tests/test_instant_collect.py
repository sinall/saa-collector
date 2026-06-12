from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User

from saa_collector.models import CollectJob, CollectPlan
from saa_collector.tasks import execute_collect_plan


class InstantCollectAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    def test_create_plan_with_single_job(self):
        """Test creating a plan with a single collection job"""
        response = self.client.post('/api/collect-plans/', {
            'name': '即时采集-测试',
            'execution_mode': 'PARALLEL',
            'jobs': [{
                'data_type': 'quote',
                'symbols': ['000001', '000002'],
                'start_date': '2024-01-01',
                'end_date': '2024-12-31'
            }]
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['name'], '即时采集-测试')
        self.assertEqual(len(response.data['data']['jobs']), 1)
        self.assertEqual(response.data['data']['jobs'][0]['data_type'], 'quote')

    def test_create_plan_job_persists_skip_existing(self):
        response = self.client.post('/api/collect-plans/', {
            'name': '跳过已有数据计划',
            'execution_mode': 'PARALLEL',
            'jobs': [{
                'data_type': 'historical_quote',
                'stock_scope': 'ALL',
                'symbols': ['000001', '000002'],
                'data_frequency': 'monthly',
                'start_date': '2024-01-01',
                'end_date': '2024-12-31',
                'skip_existing': True,
            }]
        }, format='json')

        self.assertEqual(response.status_code, 201)
        job_config = response.data['data']['jobs'][0]['config']
        self.assertTrue(job_config['params']['skip_existing'])
        self.assertEqual(job_config['params']['data_frequency'], 'monthly')
        self.assertEqual(job_config['stock_scope'], 'ALL')
        self.assertTrue(CollectJob.objects.get().config['params']['skip_existing'])

    def test_create_plan_job_persists_index_scope(self):
        response = self.client.post('/api/collect-plans/', {
            'name': '指数范围计划',
            'execution_mode': 'PARALLEL',
            'jobs': [{
                'data_type': 'quote',
                'stock_scope': 'INDEX',
                'stock_list_code': '000906',
                'symbols': [],
                'data_frequency': 'daily',
            }]
        }, format='json')

        self.assertEqual(response.status_code, 201)
        job_config = response.data['data']['jobs'][0]['config']
        self.assertEqual(job_config['stock_scope'], 'INDEX')
        self.assertEqual(job_config['stock_list_code'], '000906')
        self.assertEqual(job_config['params']['data_frequency'], 'daily')

    def test_create_plan_without_jobs(self):
        """Test creating a plan without jobs (backward compatibility)"""
        response = self.client.post('/api/collect-plans/', {
            'name': '空计划',
            'execution_mode': 'PARALLEL'
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['name'], '空计划')
        self.assertEqual(len(response.data['data']['jobs']), 0)

    def test_reject_plan_job_when_end_date_is_before_start_date(self):
        response = self.client.post('/api/collect-plans/', {
            'name': '非法日期计划',
            'execution_mode': 'PARALLEL',
            'jobs': [{
                'data_type': 'quote',
                'start_date': '2026-06-01',
                'end_date': '2026-05-01',
            }]
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
        self.assertEqual(CollectPlan.objects.filter(name='非法日期计划').count(), 0)

    def test_update_pending_plan_persists_job_date_config(self):
        plan = CollectPlan.objects.create(name='日期编辑测试')
        job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            config={'symbols': ['000001'], 'params': {}}
        )

        response = self.client.patch(f'/api/collect-plans/{plan.id}/', {
            'name': '日期编辑测试-已更新',
            'execution_mode': 'SEQUENTIAL',
            'jobs': [{
                'id': job.id,
                'data_type': 'quote',
                'stock_scope': 'ALL',
                'symbols': ['000001'],
                'data_frequency': 'daily',
                'start_date': '2024-01-01',
                'end_date': '2024-12-31',
            }]
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['name'], '日期编辑测试-已更新')
        self.assertEqual(response.data['data']['jobs'][0]['config']['params']['start_date'], '2024-01-01')
        self.assertEqual(response.data['data']['jobs'][0]['config']['params']['end_date'], '2024-12-31')
        self.assertEqual(response.data['data']['jobs'][0]['config']['params']['data_frequency'], 'daily')

        job.refresh_from_db()
        self.assertEqual(job.config['params']['start_date'], '2024-01-01')
        self.assertEqual(job.config['params']['end_date'], '2024-12-31')

    def test_update_pending_plan_persists_skip_existing(self):
        plan = CollectPlan.objects.create(name='跳过已有数据编辑测试')
        job = CollectJob.objects.create(
            plan=plan,
            data_type='historical_quote',
            config={'symbols': ['000001'], 'params': {'skip_existing': False}}
        )

        response = self.client.patch(f'/api/collect-plans/{plan.id}/', {
            'jobs': [{
                'id': job.id,
                'data_type': 'historical_quote',
                'symbols': ['000001'],
                'data_frequency': 'monthly',
                'skip_existing': True,
            }]
        }, format='json')

        self.assertEqual(response.status_code, 200)
        job.refresh_from_db()
        self.assertTrue(job.config['params']['skip_existing'])

    def test_update_pending_plan_persists_index_scope(self):
        plan = CollectPlan.objects.create(name='指数范围编辑测试')
        job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            config={'symbols': [], 'params': {}}
        )

        response = self.client.patch(f'/api/collect-plans/{plan.id}/', {
            'jobs': [{
                'id': job.id,
                'data_type': 'quote',
                'stock_scope': 'INDEX',
                'stock_list_code': '000906',
                'symbols': [],
            }]
        }, format='json')

        self.assertEqual(response.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.config['stock_scope'], 'INDEX')
        self.assertEqual(job.config['stock_list_code'], '000906')

    @patch('saa_collector.tasks.execute_collect_plan.delay')
    def test_execute_plan_always_queues_with_celery(self, delay):
        delay.return_value.id = 'celery-task-1'
        plan = CollectPlan.objects.create(name='Celery执行测试')
        CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            config={'symbols': ['000001'], 'params': {}}
        )

        response = self.client.post(f'/api/collect-plans/{plan.id}/execute/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'QUEUED')
        self.assertEqual(plan.jobs.get().status, 'QUEUED')
        self.assertEqual(plan.queue_task_id, 'celery-task-1')
        self.assertIsNotNone(plan.queued_at)
        delay.assert_called_once_with(plan.id)

    @patch('saa_collector.tasks.execute_plan')
    def test_celery_task_passes_task_id_to_executor(self, execute_plan):
        result = execute_collect_plan.apply(args=(123,), task_id='celery-task-1')

        execute_plan.assert_called_once_with(123, task_id='celery-task-1')
        self.assertEqual(result.get(), {'plan_id': 123, 'task_id': 'celery-task-1'})

    @patch('saa_collector.tasks.execute_plan')
    def test_celery_task_propagates_executor_failure(self, execute_plan):
        execute_plan.side_effect = RuntimeError('collect failed')

        result = execute_collect_plan.apply(args=(123,), task_id='celery-task-1')

        execute_plan.assert_called_once_with(123, task_id='celery-task-1')
        self.assertTrue(result.failed())
        with self.assertRaises(RuntimeError):
            result.get()
