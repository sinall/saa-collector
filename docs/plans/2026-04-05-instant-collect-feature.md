# Instant Collect Feature Implementation Plan

> 历史实现计划。本文记录即时采集功能的实施步骤；当前即时采集和 schedule-triggered plan 规范见 `../../openspec/specs/collector-schedules/spec.md`。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement "即时采集" (Instant Collect) feature that allows users to create a collection plan with tasks in a single API call from the frontend dialog.

**Architecture:** 
- Backend: Extend `CollectPlanCreateSerializer` to support nested `jobs` array, creating plan and associated tasks atomically
- Frontend: Update instant collect dialog to call the API properly instead of showing placeholder message
- Use existing `CollectJobCreateSerializer` structure for job configuration

**Tech Stack:**
- Backend: Django REST Framework, serializers, threading
- Frontend: Vue 3, TypeScript, Element Plus
- Testing: Playwright E2E tests

---

## Task 1: Backend - Add InstantCollectJobSerializer

**Files:**
- Modify: `backend/saa_collector/serializers.py` (after line 28)

**Step 1: Add new serializer for instant collect job**

Add after `CollectJobCreateSerializer` (line 28):

```python
class InstantCollectJobSerializer(serializers.Serializer):
    data_type = serializers.CharField(max_length=50, help_text='Data type to collect')
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        default=list,
        help_text='Stock codes list, empty for all stocks'
    )
    start_date = serializers.DateField(required=False, help_text='Start date')
    end_date = serializers.DateField(required=False, help_text='End date')
    report_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
        help_text='Report types (balance_sheet, income, cash_flow, dividend)'
    )
```

**Step 2: Commit**

```bash
git add backend/saa_collector/serializers.py
git commit -m "feat(serializers): add InstantCollectJobSerializer for instant collect"
```

---

## Task 2: Backend - Extend CollectPlanCreateSerializer

**Files:**
- Modify: `backend/saa_collector/serializers.py` (lines 177-184)

**Step 1: Add jobs field and create method**

Replace `CollectPlanCreateSerializer` (lines 177-184) with:

```python
class CollectPlanCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    source_report = serializers.PrimaryKeyRelatedField(
        queryset=DataIntegrityReport.objects.all(),
        required=False,
        allow_null=True
    )
    execution_mode = serializers.ChoiceField(choices=['PARALLEL', 'SEQUENTIAL'], default='PARALLEL')
    jobs = serializers.ListField(
        child=InstantCollectJobSerializer(),
        required=False,
        allow_empty=True,
        help_text='List of collection jobs to create'
    )

    def create(self, validated_data):
        plan = CollectPlan.objects.create(
            name=validated_data['name'],
            source_report=validated_data.get('source_report'),
            execution_mode=validated_data.get('execution_mode', 'PARALLEL')
        )

        jobs_data = validated_data.get('jobs', [])
        for job_data in jobs_data:
            CollectJob.objects.create(
                plan=plan,
                data_type=job_data['data_type'],
                config={
                    'symbols': job_data.get('symbols', []),
                    'params': {
                        'start_date': str(job_data['start_date']) if job_data.get('start_date') else None,
                        'end_date': str(job_data['end_date']) if job_data.get('end_date') else None,
                        'report_types': job_data.get('report_types', []),
                    }
                }
            )

        return plan
```

**Step 2: Commit**

```bash
git add backend/saa_collector/serializers.py
git commit -m "feat(serializers): extend CollectPlanCreateSerializer to support jobs creation"
```

---

## Task 3: Backend - Add API test

**Files:**
- Create: `backend/saa_collector/tests/test_instant_collect.py`

**Step 1: Create test file**

```python
import json
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User


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
```

**Step 2: Run test to verify it passes**

Run: `cd backend && python manage.py test saa_collector.tests.test_instant_collect`

Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/saa_collector/tests/test_instant_collect.py
git commit -m "test(backend): add API tests for instant collect feature"
```

---

## Task 4: Frontend - Update API client

**Files:**
- Modify: `frontend/src/utils/api.ts` (line 924)

**Step 1: Update createCollectPlan function**

Replace `createCollectPlan` function (lines 924-931) with:

```typescript
export const createCollectPlan = async (params: {
  name: string
  source_report?: number
  execution_mode?: 'PARALLEL' | 'SEQUENTIAL'
  jobs?: Array<{
    data_type: string
    symbols?: string[]
    start_date?: string
    end_date?: string
    report_types?: string[]
  }>
}): Promise<ApiResponse<CollectPlan>> => {
  const response = await api.post('/collect-plans/', params)
  return response.data
}
```

**Step 2: Commit**

```bash
git add frontend/src/utils/api.ts
git commit -m "feat(api): update createCollectPlan to support jobs parameter"
```

---

## Task 5: Frontend - Update instant collect dialog

**Files:**
- Modify: `frontend/src/views/CollectPlansView.vue` (lines 293-322)

**Step 1: Update createInstantPlan function**

Replace `createInstantPlan` function (lines 293-322) with:

```typescript
const createInstantPlan = async () => {
  if (!instantForm.value.data_type) {
    ElMessage.warning('请选择数据类型')
    return
  }

  creating.value = true
  try {
    const dataTypeName = getLabel(instantForm.value.data_type)
    const name = instantForm.value.name || `即时采集-${dataTypeName}-${new Date().toISOString().split('T')[0]}`
    
    const params: any = {
      name,
      execution_mode: 'PARALLEL',
      jobs: [{
        data_type: instantForm.value.data_type,
        symbols: instantForm.value.symbols,
      }]
    }

    if (instantForm.value.dateRange && instantForm.value.dateRange.length === 2) {
      params.jobs[0].start_date = instantForm.value.dateRange[0].toISOString().split('T')[0]
      params.jobs[0].end_date = instantForm.value.dateRange[1].toISOString().split('T')[0]
    }
    
    const response = await createCollectPlan(params)
    if (response.success) {
      ElMessage.success('即时采集计划创建成功')
      instantCollectVisible.value = false
      fetchPlans()
    } else {
      ElMessage.error(response.error || '创建失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '创建失败')
  } finally {
    creating.value = false
  }
}
```

**Step 2: Add import for createCollectPlan**

Add to imports (line 129):

```typescript
import {
  fetchCollectPlans,
  executeCollectPlan,
  deleteCollectPlan,
  createCollectPlan
} from '@/utils/api'
```

**Step 3: Commit**

```bash
git add frontend/src/views/CollectPlansView.vue
git commit -m "feat(frontend): implement instant collect dialog functionality"
```

---

## Task 6: Frontend - Add E2E test

**Files:**
- Create: `frontend/e2e/pages/instant-collect.spec.ts`

**Step 1: Create E2E test**

```typescript
import { test, expect } from '@playwright/test'

test.describe('Instant Collect Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.click('button[type="submit"]')
    await page.waitForURL('/')
  })

  test('should create instant collect plan successfully', async ({ page }) => {
    await page.goto('/collect-plans')
    
    await page.click('button:has-text("即时采集")')
    
    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('.el-dialog .el-dialog__title')).toContainText('即时采集')
    
    await page.click('.el-dialog .el-select')
    await page.click('.el-select-dropdown__item:has-text("最新行情")')
    
    await page.click('.el-dialog button:has-text("创建并执行")')
    
    await expect(page.locator('.el-message--success')).toBeVisible()
    await expect(page.locator('.el-message--success')).toContainText('创建成功')
    
    await expect(page.locator('.el-dialog')).not.toBeVisible()
  })

  test('should show validation error when data type not selected', async ({ page }) => {
    await page.goto('/collect-plans')
    
    await page.click('button:has-text("即时采集")')
    
    await page.click('.el-dialog button:has-text("创建并执行")')
    
    await expect(page.locator('.el-message--warning')).toBeVisible()
    await expect(page.locator('.el-message--warning')).toContainText('请选择数据类型')
  })
})
```

**Step 2: Run test**

Run: `cd frontend && npm run test:e2e:chromium`

Expected: All tests pass

**Step 3: Commit**

```bash
git add frontend/e2e/pages/instant-collect.spec.ts
git commit -m "test(e2e): add instant collect feature tests"
```

---

## Task 7: Integration testing

**Step 1: Manual test via browser**

1. Start backend: `cd backend && python manage.py runserver`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to `http://localhost:3000/collect-plans`
4. Click "即时采集" button
5. Fill in form:
   - Data type: "最新行情"
   - Symbols: (leave empty for all stocks)
   - Date range: 2024-01-01 to 2024-12-31
6. Click "创建并执行"
7. Verify:
   - Success message appears
   - Dialog closes
   - New plan appears in list with source "即时采集"
   - Plan has 1 job

**Step 2: Verify plan can be executed**

1. Click "查看" on the new plan
2. Click "执行" button
3. Verify plan status changes to "执行中" then "已完成"

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete instant collect feature implementation"
```

---

## Notes

- **Backward Compatibility**: The `jobs` field is optional, existing API calls without jobs will continue to work
- **Single Job**: Current implementation supports single job per instant collect (as per requirements)
- **No Auto-Execute**: Plan is created in PENDING status, user must manually execute it
- **Naming**: Uses "即时采集" (Instant Collect) in UI, "MANUAL" as source identifier in code
