import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icons.svg'],
      manifest: {
        name: 'Naukri AI Agent Dashboard',
        short_name: 'Agent Dashboard',
        description: 'AI-powered job application agent for Naukri.com',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        orientation: 'portrait-primary',
        start_url: '/',
        icons: [
          { src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg}'],
        runtimeCaching: [
          {
            urlPattern: /^\/api\/stats/,
            handler: 'NetworkFirst',
            options: { cacheName: 'api-stats', expiration: { maxEntries: 10, maxAgeSeconds: 300 } },
          },
          {
            urlPattern: /^\/api\/(jobs|applications)/,
            handler: 'NetworkFirst',
            options: { cacheName: 'api-data', expiration: { maxEntries: 50, maxAgeSeconds: 600 } },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8005',
        changeOrigin: true,
      },
    },
  },
})
