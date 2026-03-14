import { FullConfig } from '@playwright/test'

async function globalSetup(config: FullConfig) {
  console.log('🚀 Starting E2E tests...')
  console.log('📍 Base URL:', config.projects[0]?.use?.baseURL || 'http://localhost:3001')
  console.log('📁 Test directory:', config.rootDir)
}

export default globalSetup
