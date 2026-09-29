import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Override with SEWERSENSE_API_TARGET to point the dev proxy at another backend port.
const apiTarget = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.SEWERSENSE_API_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true
      }
    }
  }
});
