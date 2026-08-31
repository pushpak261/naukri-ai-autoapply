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
            handler: 'NetworkOnly',
          },
          {
            urlPattern: /^\/api\/(jobs|applications)/,
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8005',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    cssCodeSplit: true,
    // Enable minification and optimize chunk sizes
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true, // Remove console.log in production
        drop_debugger: true,
      },
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // Better chunk splitting for improved caching
            if (id.includes('recharts') || id.includes('d3-')) return 'charts';
            if (id.includes('@xyflow')) return 'flow';
            if (id.includes('@tanstack')) return 'react-query';
            if (id.includes('@reduxjs') || id.includes('react-redux')) return 'redux';
            if (id.includes('lucide-react')) return 'icons';
            if (id.includes('react-router')) return 'router';
            // Core React libraries
            if (id.includes('react') && !id.includes('react-dom')) return 'react-core';
            if (id.includes('react-dom')) return 'react-dom';
          }
        },
        // Improve chunk naming for better caching
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
    // Optimize chunk size threshold
    chunkSizeWarningLimit: 1000,
  },
})
