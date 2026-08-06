import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

// Frozen page-size baselines (shrink-only by convention). Measured during the
// SettingsPage phase-1 extraction. New pages use the default max-lines rules;
// listed offenders cannot grow past their pin without an intentional change.
// Soft target for new pages: ~500 lines. Hard ceiling for non-baseline: 800.
// ESLint max-lines supports one severity per matching rule entry, so the
// default is error@800; treat 500 as the review soft target.
const pageLineBaselines = {
  'src/pages/DecisionSignalsPage.tsx': 1513,
  'src/pages/PortfolioPage.tsx': 2291,
  'src/pages/SettingsPage.tsx': 2030,
  'src/pages/ChatPage.tsx': 1110,
  'src/pages/StockScreeningPage.tsx': 1699,
  'src/pages/ResearchAnalysisWorkbenchPage.tsx': 1406,
  'src/pages/BacktestPage.tsx': 1015,
  'src/pages/HomePage.tsx': 833,
}

const pageBaselineOverrides = Object.entries(pageLineBaselines).map(([file, max]) => ({
  files: [file],
  rules: {
    'max-lines': ['error', { max, skipBlankLines: false, skipComments: false }],
  },
}))

export default defineConfig([
  globalIgnores(['dist', 'playwright-report', 'test-results']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    // Default for pages not in the frozen baseline: warn at ~500, then the
    // next block raises a hard error at ~800. Because ESLint replaces the
    // rule entirely when a later matching config sets the same key, we keep
    // only the hard ceiling here and document the soft target above.
    // Practical dual signal: baselines are error-pinned; new pages error at 800.
    files: ['src/pages/**/*.{ts,tsx}'],
    ignores: [
      'src/pages/__tests__/**',
      ...Object.keys(pageLineBaselines),
    ],
    rules: {
      // Hard ceiling (~800). Soft target (~500) is the review convention.
      'max-lines': ['error', { max: 800, skipBlankLines: false, skipComments: false }],
    },
  },
  ...pageBaselineOverrides,
])
