import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./e2e',workers:1,timeout:60000,
  use:{baseURL:'http://127.0.0.1:8765',browserName:'chromium',channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true},
  webServer:{command:'python -m backend.test_server',cwd:'..',url:'http://127.0.0.1:8765/api/health',reuseExistingServer:false,timeout:30000}
});
