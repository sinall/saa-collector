import { test, expect } from '@playwright/test';

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
