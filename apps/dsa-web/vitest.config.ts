import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const testBase = {
  environment: 'jsdom' as const,
  globals: true,
  setupFiles: './src/setupTests.ts',
  exclude: [...configDefaults.exclude, 'e2e/**', 'playwright.config.ts'],
};

const reactCompilerPlugin = react({
  babel: {
    // Same plugin Vite production uses (vite.config.ts).
    plugins: [['babel-plugin-react-compiler']],
  },
});

export default defineConfig({
  test: {
    projects: [
      {
        plugins: [react()],
        test: {
          ...testBase,
          name: 'default',
        },
      },
      {
        plugins: [reactCompilerPlugin],
        test: {
          ...testBase,
          name: 'react-compiler',
          include: [
            'src/components/chat/__tests__/ChatThinkingDetails.test.tsx',
            'src/components/chat/__tests__/chatThinkingTrace.test.ts',
            'src/components/chat/__tests__/ChatMessageList.test.tsx',
          ],
        },
      },
    ],
  },
});
