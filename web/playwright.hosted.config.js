import {defineConfig} from '@playwright/test';

const python=process.env.HOSTED_TEST_PYTHON||'python';
export default defineConfig({
  testDir:'./hosted-e2e',workers:1,timeout:90000,
  use:{baseURL:'http://127.0.0.1:8766',browserName:'chromium',channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true},
  webServer:{command:`"${python}" -m backend.hosted_test_server`,cwd:'..',url:'http://127.0.0.1:8766/api/health',reuseExistingServer:false,timeout:60000},
});
