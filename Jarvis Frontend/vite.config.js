import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'node:process'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    envDir: '.',
    plugins: [react()],
    server: {
      proxy: {
        '/api': env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
      },
    },
  }
})
