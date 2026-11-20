import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 把 tests/ui-entry.js 打成可在 jsdom 里直接 import 的客户端包（非 SSR）
export default defineConfig({
  plugins: [vue()],
  logLevel: 'error',
  build: {
    lib: { entry: 'tests/ui-entry.js', formats: ['es'], fileName: () => 'bundle.mjs' },
    outDir: 'tests/.ui-dist',
    emptyOutDir: true,
    minify: false,
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
})
