// Vitest Configuration — Phase 4D Testing

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // page-mount audits load whole workspaces (and the chart engine on first use) while other files run in parallel
    testTimeout: 15_000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: ['node_modules/', 'src/test/setup.ts'],
    },
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
});
