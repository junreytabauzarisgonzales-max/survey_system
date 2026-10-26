import { resolve } from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode}) => {
  const hosted = mode === 'hosted';
  const app = mode === 'app' || hosted;
  const env = loadEnv(mode, resolve(process.cwd(), '..'), '');
  const realtimeUrl = env.NEON_REALTIME_URL || process.env.NEON_REALTIME_URL || '';
  return {
    define: {__NEON_REALTIME_URL__: JSON.stringify(realtimeUrl)},
    plugins: [react(), {
      name: 'page-metadata',
      transformIndexHtml(html) {
        return app ? html.replace('<title>Student Survey Creator — Guides &amp; Downloads</title>', '<title>Student Survey Creator</title>') : html;
      },
    }],
    publicDir: app ? false : 'public',
    base: hosted ? '/app/' : '/',
    build: {outDir: hosted ? 'hosted-dist' : app ? 'app-dist' : 'dist'},
    server: app ? {proxy: {'/api': 'http://127.0.0.1:8000'}} : {},
  };
});
