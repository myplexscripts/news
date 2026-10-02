import { defineConfig } from '@playwright/test';
const base = process.env.BASE_PATH || '';
export default defineConfig({
  testDir: './tests/browser',
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: `http://127.0.0.1:4173${base}/`, serviceWorkers: 'block', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1363, height: 900 } } },
    { name: 'laptop', use: { browserName: 'chromium', viewport: { width: 1024, height: 768 } } },
    { name: 'tablet', use: { browserName: 'chromium', viewport: { width: 820, height: 1180 } } },
    { name: 'mobile', use: { browserName: 'chromium', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: 'mobile-webkit', use: { browserName: 'webkit', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } }
  ],
  webServer: { command: 'npm run preview -- --host 127.0.0.1 --port 4173', url: `http://127.0.0.1:4173${base}/`, reuseExistingServer: !process.env.CI },
  reporter: [['list'], ['html', { open: 'never' }]]
});
