import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/profile': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/learner': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/resources': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
