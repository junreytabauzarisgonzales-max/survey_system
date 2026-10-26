import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode}) => {
  const app = mode === 'app';
  return {
    plugins: [react(), {
      name: 'page-metadata',
      transformIndexHtml(html) {
        return app ? html.replace('<title>Student Survey Creator — Guides &amp; Downloads</title>', '<title>Student Survey Creator</title>') : html;
      },
    }],
    publicDir: app ? false : 'public',
    build: {outDir: app ? 'app-dist' : 'dist'},
    server: app ? {proxy: {'/api': 'http://127.0.0.1:8000'}} : {},
  };
});
