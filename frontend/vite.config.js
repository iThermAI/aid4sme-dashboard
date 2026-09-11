import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The capture PC may run Windows 7, where Chrome stops at version 109.
// Keep both targets at chrome109 while any Windows 7 capture PC is in use.
export default defineConfig({
  plugins: [vue()],
  build: {
    target: 'chrome109',
    cssTarget: 'chrome109',
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 800
  },
  // `npm run dev` on a development PC, talking to a running backend:
  //   BACKEND=http://<capture-pc-ip>:8000 npm run dev
  server: {
    host: true,
    proxy: { '/api': { target: process.env.BACKEND || 'http://localhost:8000', changeOrigin: true } }
  }
})
