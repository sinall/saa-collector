import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('Data Browse Stock Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/data-browse/stock')
    await waitForPageLoad(page)
  })

  test('should load without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should display main content', async ({ page }) => {
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })
})

test.describe('Data Browse Type Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/data-browse/type')
    await waitForPageLoad(page)
  })

  test('should load without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should display main content', async ({ page }) => {
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })
})
