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
