import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('should load dashboard without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should have correct page title', async ({ page }) => {
    await expect(page).toHaveTitle(/SAA Collector/)
  })

  test('should display main content', async ({ page }) => {
    await waitForPageLoad(page)
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })

  test('should display dashboard content', async ({ page }) => {
    await waitForPageLoad(page)
    const app = page.locator('#app')
    await expect(app).toBeVisible()
  })
})
