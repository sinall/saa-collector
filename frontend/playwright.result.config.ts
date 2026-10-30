import { defineConfig, devices } from '@playwright/test'

// All API requests in this suite are intercepted; no collector backend is used.
export default defineConfig({
  testDir: './e2e/pages',
  testMatch: 'collect-job-result.spec.ts',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:43184', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 43184 --strictPort',
    // Wait for our own server, not a proxy/WSL response on an unopened port.
    wait: { stdout: /Local:/ },
    reuseExistingServer: false,
  },
})
