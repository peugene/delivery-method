import { defineConfig } from '@playwright/test';

// One suite for every implementation: only BASE_URL changes.
// APP_CMD (optional): the command that serves the application under test on BASE_URL.
// Playwright starts it, waits for BASE_URL, runs the tests, then stops it.
const baseURL = process.env.BASE_URL ?? 'http://localhost:3999';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1, // the harness resets shared data: one test at a time
  retries: 0, // a flaky test is a defect, not bad luck
  forbidOnly: !!process.env.CI,
  timeout: 30_000,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  webServer: process.env.APP_CMD
    ? {
        command: process.env.APP_CMD,
        url: baseURL,
        reuseExistingServer: false,
        timeout: Number(process.env.APP_START_TIMEOUT_MS ?? 180_000),
      }
    : undefined,
});
