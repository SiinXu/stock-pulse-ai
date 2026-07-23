// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  collectHardcodedUiStrings,
  findHardcodedUiStrings,
  findUnusedUiStringAllowances,
  type HardcodedUiStringAllowance,
  type HardcodedUiStringContext,
} from './hardcodedUiStringGuard';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

const exactAllowedStrings: HardcodedUiStringAllowance[] = [
  {
    file: 'components/StockAutocomplete/SuggestionsList.tsx',
    text: 'ETF',
    context: 'jsx-expression',
    purpose: 'Locale-independent exchange-traded-fund security-type acronym.',
  },
  {
    file: 'components/layout/SidebarNav.tsx',
    text: 'StockPulse',
    context: 'jsx-text',
    purpose: 'Product name in the navigation wordmark.',
  },
  {
    file: 'components/settings/GenerationBackendStatusPanel.tsx',
    text: 'JSON',
    context: 'jsx-text',
    purpose: 'Stable technical capability name returned by the generation backend.',
  },
  {
    file: 'components/settings/GenerationBackendStatusPanel.tsx',
    text: 'Stream',
    context: 'jsx-text',
    purpose: 'Stable technical capability name returned by the generation backend.',
  },
  {
    file: 'components/settings/NotificationTestPanel.tsx',
    text: 'ms',
    context: 'jsx-expression',
    purpose: 'SI-compatible milliseconds unit appended to a numeric latency.',
  },
  {
    file: 'components/settings/NotificationTestPanel.tsx',
    text: 'HTTP',
    context: 'jsx-text',
    purpose: 'Stable protocol acronym next to a numeric response status.',
  },
  {
    file: 'components/settings/NotificationTestPanel.tsx',
    text: 'ms',
    context: 'jsx-text',
    purpose: 'SI-compatible milliseconds unit next to a numeric latency.',
  },
  {
    file: 'components/settings/LLMConnectionModal.tsx',
    text: 'https://api.example.com/v1',
    context: 'placeholder',
    purpose: 'Protocol-neutral example URL rather than interface copy.',
  },
  {
    file: 'components/alerts/AlertRuleForm.tsx',
    text: '600519 / AAPL / hk00700',
    context: 'placeholder',
    purpose: 'Locale-independent examples of supported stock-code formats.',
  },
  {
    file: 'pages/AlertsPage.tsx',
    text: 'ms',
    context: 'jsx-expression',
    purpose: 'SI-compatible milliseconds unit appended to a numeric latency.',
  },
  {
    file: 'pages/ChatPage.tsx',
    text: 'U',
    context: 'jsx-expression',
    purpose: 'Locale-independent one-letter user avatar marker.',
  },
  {
    file: 'pages/ChatPage.tsx',
    text: 'AI',
    context: 'jsx-expression',
    purpose: 'Established technical acronym used as the assistant avatar marker.',
  },
  {
    file: 'pages/ChatPage.tsx',
    text: 'AI',
    context: 'jsx-text',
    purpose: 'Established technical acronym used as the loading assistant avatar marker.',
  },
  {
    file: 'pages/LoginPage.tsx',
    text: 'StockPulse',
    context: 'jsx-text',
    purpose: 'Product name in the login wordmark.',
  },
  {
    file: 'pages/PortfolioPage.tsx',
    text: 'CNY',
    context: 'jsx-expression',
    purpose: 'ISO 4217 fallback currency code from the portfolio data contract.',
  },
  {
    file: 'pages/SettingsPage.tsx',
    text: 'desktop.log',
    context: 'jsx-text',
    purpose: 'Literal diagnostic filename users must locate on disk.',
  },
  {
    file: 'pages/StockScreeningPage.tsx',
    text: 'LLM',
    context: 'jsx-text',
    purpose: 'Established technical acronym in a result-column heading.',
  },
];

function collectSourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry: { name: string; isDirectory: () => boolean; isFile: () => boolean }) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      return ['__tests__', '__stories__', 'generated'].includes(entry.name) ? [] : collectSourceFiles(fullPath);
    }
    if (!entry.isFile() || !/\.tsx?$/.test(entry.name)) return [];
    if (/\.(?:test|spec|stories|generated)\.tsx?$/.test(entry.name)) return [];
    return [fullPath];
  });
}

let productionCandidateCache: ReturnType<typeof collectHardcodedUiStrings> | null = null;

function productionCandidates(): ReturnType<typeof collectHardcodedUiStrings> {
  if (productionCandidateCache) {
    return productionCandidateCache;
  }
  productionCandidateCache = collectSourceFiles(sourceRoot).flatMap((filename) => {
    const relative = path.relative(sourceRoot, filename);
    return collectHardcodedUiStrings(relative, fs.readFileSync(filename, 'utf8'));
  });
  return productionCandidateCache;
}

describe('hardcoded UI string scanner', () => {
  it.each<[string, string, HardcodedUiStringContext]>([
    ['JSX text', 'const View = () => <p>Save changes</p>;', 'jsx-text'],
    ['JSX expression literal', "const View = () => <p>{'Save changes'}</p>;", 'jsx-expression'],
    ['JSX expression template', 'const View = ({ name }) => <p>{`Welcome ${name}`}</p>;', 'jsx-expression'],
    ['aria-label', 'const View = () => <button aria-label="Close dialog" />;', 'aria-label'],
    ['aria-description', 'const View = () => <button aria-description="Closes the dialog" />;', 'aria-description'],
    ['camelCase ariaLabel', 'const View = () => <IconButton ariaLabel="Close dialog" />;', 'ariaLabel'],
    ['image alt text', 'const View = () => <img alt="Market overview" />;', 'alt'],
    ['placeholder', "const View = () => <input placeholder={'Search stocks'} />;", 'placeholder'],
    ['title', 'const View = () => <button title={`Open settings`} />;', 'title'],
    ['custom-component label', 'const View = () => <Field label="Stock code" />;', 'label'],
    ['custom-component message', 'const View = () => <Alert message="Settings saved" />;', 'message'],
    ['custom-component description', 'const View = () => <EmptyState description="No reports yet" />;', 'description'],
    ['custom-component camelCase actionLabel', 'const View = () => <Alert actionLabel="Try again" />;', 'actionLabel'],
    ['custom-component emptyText', 'const View = () => <Select emptyText="No options" />;', 'emptyText'],
    ['custom-component searchPlaceholder', 'const View = () => <Select searchPlaceholder="Search models" />;', 'searchPlaceholder'],
    ['custom-component loadingText', 'const View = () => <Button loadingText="Saving settings" />;', 'loadingText'],
    ['error setter', "const fail = () => setError('Could not save settings');", 'error-call'],
    ['toast call', "const fail = () => toast.error('Could not save settings');", 'toast-call'],
    ['direct toast call', "const done = () => toast('Settings saved');", 'toast-call'],
    ['direct notify call', "const done = () => notify('Settings saved');", 'notice-call'],
    ['toast object', "const done = () => setToast({ type: 'success', message: 'Settings saved' });", 'toast-call'],
    ['banner object', "const done = () => setSaveBanner({ type: 'success', title: 'Settings saved' });", 'notice-call'],
    ['indirect toast copy', "const message = 'Settings saved'; const done = () => toast(message);", 'toast-call'],
    [
      'toast spread object',
      "const message = 'Settings saved'; const payload = { type: 'success', message }; const done = () => setToast({ ...payload });",
      'toast-call',
    ],
    [
      'banner spread object',
      "const title = 'Settings saved'; const payload = { type: 'success', title }; const done = () => setSaveBanner({ ...payload });",
      'notice-call',
    ],
    ['document title', "document.title = 'Settings';", 'document-title'],
    ['indirect document title', "const title = 'Settings'; document.title = title;", 'document-title'],
    ['Han text', 'const View = () => <p>保存设置</p>;', 'jsx-text'],
  ])('detects hardcoded user copy in %s', (_, sourceText, context) => {
    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([
      expect.objectContaining({ context }),
    ]);
  });

  it('does not treat imports, routes, classes, technical IDs, or translation keys as UI copy', () => {
    const sourceText = `
      import { Settings } from './Settings';
      const route = '/' + 'settings/model-access';
      const modelId = 'gpt-4o';
      const panelId = 'settings-panel';
      const panelClass = 'flex items-center';
      const View = () => (
        <Settings id={panelId} className={panelClass} data-testid={panelId}>
          {t('settings.title')}
        </Settings>
      );
    `;

    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([]);
  });

  it('resolves static const copy used indirectly in JSX text and user-facing attributes', () => {
    const sourceText = `
      const saveLabel = 'Save changes';
      const searchPlaceholder = 'Search stocks';
      const aliasedPlaceholder = searchPlaceholder;
      const View = () => (
        <label>
          {saveLabel}
          <input placeholder={aliasedPlaceholder} />
        </label>
      );
    `;

    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([
      expect.objectContaining({ context: 'jsx-expression', text: 'Save changes' }),
      expect.objectContaining({ context: 'placeholder', text: 'Search stocks' }),
    ]);
  });

  it('resolves aliased and nested const destructuring in user-facing attributes', () => {
    const sourceText = `
      const copy = {
        title: 'Delete report',
        dialog: {
          description: 'This action cannot be undone',
          actionLabel: 'Delete now',
        },
      };
      const {
        title: dialogTitle,
        dialog: { description: dialogDescription, actionLabel },
      } = copy;
      const View = () => (
        <Dialog
          title={dialogTitle}
          description={dialogDescription}
          actionLabel={actionLabel}
        />
      );
    `;

    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([
      expect.objectContaining({ context: 'title', text: 'Delete report' }),
      expect.objectContaining({ context: 'description', text: 'This action cannot be undone' }),
      expect.objectContaining({ context: 'actionLabel', text: 'Delete now' }),
    ]);
  });

  it('resolves destructured const objects supplied through JSX spreads', () => {
    const sourceText = `
      const copy = {
        dialog: {
          title: 'Delete report',
          description: 'This action cannot be undone',
        },
      };
      const { dialog: dialogProps } = copy;
      const View = () => <Dialog {...dialogProps} />;
    `;

    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([
      expect.objectContaining({ context: 'title', text: 'Delete report' }),
      expect.objectContaining({ context: 'description', text: 'This action cannot be undone' }),
    ]);
  });

  it('detects static destructuring defaults without treating a dynamic source as static', () => {
    const sourceText = `
      const { title: dialogTitle = 'Delete report' } = getDialogCopy();
      const { description } = getDialogCopy();
      const View = () => <Dialog title={dialogTitle} description={description} />;
    `;

    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([
      expect.objectContaining({ context: 'title', text: 'Delete report' }),
    ]);
  });

  it('does not follow mutable destructuring or recurse through cyclic const bindings', () => {
    const sourceText = `
      const copy = { title: 'Delete report' };
      let { title: mutableTitle } = copy;
      const { title: dynamicTitle } = getDialogCopy();
      const { title: cyclicTitle } = { title: cyclicTitle };
      const View = () => (
        <Dialog
          title={mutableTitle}
          label={dynamicTitle}
          description={cyclicTitle}
        />
      );
    `;

    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([]);
  });

  it('checks only user-facing properties supplied through JSX object spreads', () => {
    const title = 'Open settings';
    const sourceText = `
      const title = '${title}';
      const description = 'Review settings before continuing';
      const technicalProps = {
        id: 'settings-dialog',
        className: 'flex items-center',
        'data-testid': 'settings-dialog',
      };
      const dialogProps = {
        ...technicalProps,
        title,
        description,
        'aria-label': 'Settings dialog',
        actionLabel: 'Try again',
      };
      const View = () => (
        <Dialog {...dialogProps} {...{ emptyText: 'No options available' }} />
      );
    `;

    expect(findHardcodedUiStrings('fixture.tsx', sourceText)).toEqual([
      expect.objectContaining({ context: 'title', text: title }),
      expect.objectContaining({ context: 'description', text: 'Review settings before continuing' }),
      expect.objectContaining({ context: 'aria-label', text: 'Settings dialog' }),
      expect.objectContaining({ context: 'actionLabel', text: 'Try again' }),
      expect.objectContaining({ context: 'emptyText', text: 'No options available' }),
    ]);
  });

  it('requires an exact file, string, and context match for an allowance', () => {
    const sourceText = 'const View = () => <span>JSON</span>;';
    const allowance: HardcodedUiStringAllowance = {
      file: 'fixture.tsx',
      text: 'JSON',
      context: 'jsx-text',
      purpose: 'Stable wire-format name.',
    };

    expect(findHardcodedUiStrings('fixture.tsx', sourceText, [allowance])).toEqual([]);
    expect(findHardcodedUiStrings('other.tsx', sourceText, [allowance])).toHaveLength(1);
    expect(findHardcodedUiStrings('fixture.tsx', 'const View = () => <span>Stream</span>;', [allowance])).toHaveLength(1);
    expect(findHardcodedUiStrings('fixture.tsx', 'const View = () => <span title="JSON" />;', [allowance])).toHaveLength(1);
  });
});

describe('production hardcoded UI strings', () => {
  it('keeps hardcoded English and Chinese copy out of user-facing TSX contexts', () => {
    const failures = productionCandidates().filter((candidate) => !exactAllowedStrings.some((allowance) => (
      allowance.file === candidate.file
      && allowance.text === candidate.text
      && allowance.context === candidate.context
    )));

    expect(failures.map(({ file, line, context, text }) => (
      `${file}:${line} [${context}] ${JSON.stringify(text)}`
    ))).toEqual([]);
  });

  it('keeps every allowance documented, exact, and in use', () => {
    expect(exactAllowedStrings.every((allowance) => allowance.purpose.trim().length > 0)).toBe(true);
    expect(findUnusedUiStringAllowances(productionCandidates(), exactAllowedStrings)).toEqual([]);
  });
});
