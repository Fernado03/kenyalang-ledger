import { defineConfig, devices } from '@playwright/test'

const API_URL = 'http://127.0.0.1:8010'
const WEB_URL = 'http://localhost:5183'

/** Windows venv layout; the repo only supports these two shapes. */
const PYTHON = process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'

/**
 * E2E owns port 8010 + 5183 and a throwaway SQLite file, so destructive
 * review/export specs never touch the demo database. The API command reseeds
 * before uvicorn boots.
 */
export default defineConfig({
  testDir: './e2e',
  // Evidence shots are generated output, not a behaviour gate: only the
  // explicit `test:e2e:evidence` invocation collects them.
  testIgnore: process.argv.some((arg) => arg.includes('09-evidence')) ? [] : ['**/09-evidence.spec.ts'],
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: WEB_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${PYTHON} seed_e2e.py && ${PYTHON} -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --log-level warning`,
      cwd: '../backend',
      url: `${API_URL}/api/health/live`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        DATABASE_URL: 'sqlite:///kenyalang-e2e.db',
        KENYALANG_STORAGE_ROOT: 'storage-e2e',
        KENYALANG_ENV: 'local',
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      command: 'npm run dev -- --host localhost --port 5183 --strictPort',
      cwd: '.',
      url: WEB_URL,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VITE_API_PROXY: API_URL },
    },
  ],
})
