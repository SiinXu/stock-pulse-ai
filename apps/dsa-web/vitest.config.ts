import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react({
      babel: {
        // Match production vite.config.ts so live-append memoization is tested.
        plugins: [['babel-plugin-react-compiler']],
      },
    }),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    exclude: [...configDefaults.exclude, 'e2e/**', 'playwright.config.ts'],
  },
});
