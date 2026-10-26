import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir:'./site-e2e', workers:1, timeout:60000,
  use:{baseURL:'http://127.0.0.1:4173',browserName:'chromium',channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true},
  webServer:{command:'npm run preview -- --port 4173 --strictPort',url:'http://127.0.0.1:4173',reuseExistingServer:false,timeout:30000},
});
