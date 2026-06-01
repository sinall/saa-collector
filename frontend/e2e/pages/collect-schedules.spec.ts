import { test, expect } from '@playwright/test';

test('collect-schedules page should explain cron expressions', async ({ page }) => {
  await page.route('**/api/data-types/', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          { key: 'valuation', label: '估值数据' },
        ],
        groups: [],
      }),
    })
  })

  await page.route('**/api/collect-schedules/', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [
          {
            id: 3,
            name: '估值数据采集',
            data_type: 'valuation',
            symbols: [],
            params: {},
            cron_expression: '5 0 7 5 *',
            status: 'ENABLED',
            next_trigger_at: '2026-05-07T00:05:00+08:00',
          },
        ],
      }),
    })
  })

  await page.goto('/admin/collector/collect-schedules')

  await expect(page.getByRole('columnheader', { name: '说明' })).toBeVisible()
  await expect(page.getByText('5 0 7 5 *')).toBeVisible()
  await expect(page.getByText('每年 5月7日 00:05', { exact: true })).toBeVisible()
})

test('collect-schedules page should display schedules from API', async ({ page }) => {
  await page.goto('http://localhost:3000/collect-schedules');
  
  await page.waitForTimeout(2000);
  
  const tableBody = page.locator('.el-table__body');
  await expect(tableBody).toBeVisible();
  
  const rows = page.locator('.el-table__body tbody tr');
  const rowCount = await rows.count();
  console.log(`Found ${rowCount} schedule rows`);
  
  expect(rowCount).toBeGreaterThan(0);
  
  const firstRow = rows.first();
  await expect(firstRow).toContainText('Tick');
  
  const errors: string[] = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  
  if (errors.length > 0) {
    console.log('Console errors:', errors);
  }
});

test('collect-schedules page should refresh after creating a schedule', async ({ page }) => {
  let schedulesCallCount = 0

  await page.route('**/api/data-types/', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          { key: 'trade_days', label: '交易日', need_date: true },
        ],
        groups: [],
      }),
    })
  })

  await page.route('**/api/collect-schedules/', async route => {
    if (route.request().method() === 'GET') {
      schedulesCallCount += 1
      const schedules = schedulesCallCount === 1
        ? [
            {
              id: 1,
              name: '旧日程',
              data_type: 'trade_days',
              symbols: [],
              params: {},
              cron_expression: '0 9 * * 1-5',
              status: 'ENABLED',
              next_trigger_at: '2026-06-01T09:00:00+08:00',
            },
          ]
        : [
            {
              id: 1,
              name: '旧日程',
              data_type: 'trade_days',
              symbols: [],
              params: {},
              cron_expression: '0 9 * * 1-5',
              status: 'ENABLED',
              next_trigger_at: '2026-06-01T09:00:00+08:00',
            },
            {
              id: 2,
              name: '新建日程',
              data_type: 'trade_days',
              symbols: [],
              params: { start_date: 'today', end_date: 'today' },
              cron_expression: '0 10 * * 1',
              status: 'ENABLED',
              next_trigger_at: '2026-06-08T10:00:00+08:00',
            },
          ]

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: schedules,
        }),
      })
      return
    }

    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: 2,
            name: '新建日程',
            data_type: 'trade_days',
            symbols: [],
            params: { start_date: 'today', end_date: 'today' },
            cron_expression: '0 10 * * 1',
            status: 'ENABLED',
            next_trigger_at: '2026-06-08T10:00:00+08:00',
          },
        }),
      })
    }
  })

  await page.goto('/admin/collector/collect-schedules')
  await expect(page.getByText('旧日程')).toBeVisible()
  await expect(page.getByText('新建日程')).toHaveCount(0)

  await page.getByRole('button', { name: '新建' }).click()
  await expect(page).toHaveURL(/\/collect-schedules\/new$/)

  await page.getByLabel('日程名称').fill('新建日程')
  await page.getByText('请选择数据类型').click()
  await page.locator('.el-select-dropdown__item').filter({ hasText: '交易日' }).click()
  await page.getByLabel('Cron表达式').fill('0 10 * * 1')
  await page.getByRole('button', { name: '创建' }).click()

  await expect(page).toHaveURL(/\/collect-schedules$/)
  await expect(page.getByText('新建日程')).toBeVisible()
  await expect(page.locator('.el-table__body tbody tr')).toHaveCount(2)
})
