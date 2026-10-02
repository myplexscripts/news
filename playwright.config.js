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
    { name: 'iphone-standalone', use: { browserName: 'webkit', viewport: { width: 430, height: 932 }, isMobile: true, hasTouch: true, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1' } },
    { name: 'mobile-webkit', use: { browserName: 'webkit', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } }
  ],
  webServer: { command: 'npm run preview -- --host 127.0.0.1 --port 4173', url: `http://127.0.0.1:4173${base}/`, reuseExistingServer: !process.env.CI },
  reporter: [['list'], ['html', { open: 'never' }]]
});
