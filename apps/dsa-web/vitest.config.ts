import { readFileSync } from 'node:fs';
import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import {
  getWebUnitTestTimeoutMs,
  isVitestCoverageCliEnabled,
  WEB_VITEST_COVERAGE_FLAG,
  WEB_VITEST_COVERAGE_FLAG_VALUE,
} from './src/test-utils/coverageTimeouts';

const coverageEnabled = isVitestCoverageCliEnabled();

type CoverageBaseline = {
  provider: 'v8';
  all: boolean;
  reportsDirectory: string;
  reporters: Array<'text' | 'json' | 'json-summary' | 'html' | 'lcov' | 'clover' | 'cobertura'>;
  include: string[];
  exclude: string[];
  thresholds: {
    lines: number;
    functions: number;
    statements: number;
    branches: number;
  };
};

const coverageBaseline = JSON.parse(
  readFileSync(new URL('./scripts/web-coverage-baseline.json', import.meta.url), 'utf8'),
) as CoverageBaseline;

const testBase = {
  environment: 'jsdom' as const,
  globals: true,
  setupFiles: './src/setupTests.ts',
  exclude: [...configDefaults.exclude, 'e2e/**', 'playwright.config.ts'],
  // Coverage instrumentation makes production-source glob/AST scans slower than
  // the 5s default. Keep the default for `npm run test`; raise only for coverage.
  // Testing Library findBy/waitFor is configured separately in setupTests.ts.
  // Fork workers do not see `--coverage` on argv; inject one explicit flag.
  testTimeout: getWebUnitTestTimeoutMs(),
  env: {
    [WEB_VITEST_COVERAGE_FLAG]: coverageEnabled ? WEB_VITEST_COVERAGE_FLAG_VALUE : '',
  },
};

const reactCompilerPlugin = react({
  babel: {
    // Same plugin Vite production uses (vite.config.ts).
    plugins: [['babel-plugin-react-compiler']],
  },
});

export default defineConfig({
  test: {
    coverage: {
      provider: coverageBaseline.provider,
      all: coverageBaseline.all,
      reportsDirectory: coverageBaseline.reportsDirectory,
      reporter: coverageBaseline.reporters,
      reportOnFailure: true,
      include: coverageBaseline.include,
      exclude: [...configDefaults.coverage.exclude, ...coverageBaseline.exclude],
      thresholds: coverageBaseline.thresholds,
    },
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
