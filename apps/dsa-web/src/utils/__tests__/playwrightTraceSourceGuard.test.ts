/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  findPlaywrightTraceSourceViolations,
  findPlaywrightTraceSourceGraphViolations,
  hasOnlyRuntimePolicyOwnedConfigTrace,
} from './playwrightTraceSourceGuard';

function readSourceTree(root: string): Record<string, string> {
  const sources: Record<string, string> = {};
  const ignoredDirectories = new Set(['node_modules', 'test-results', 'dist', '.git']);
  const visit = (directory: string): void => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const filename = `${directory}/${entry.name}`;
      if (entry.isDirectory()) {
        if (ignoredDirectories.has(entry.name)) continue;
        visit(filename);
      } else if (/\.(?:m?js|tsx?)$/.test(entry.name)) {
        sources[filename] = fs.readFileSync(filename, 'utf8');
      }
    }
  };
  visit(root);
  return sources;
}

function configWithProjectOverride(override: string): string {
  return `export default defineConfig({
    use: {
      trace: requestedTraceMode === 'off' ? 'off' : {
        mode: 'retain-on-failure' as const,
        screenshots: false,
        snapshots: true,
        sources: true,
        attachments: false,
      },
    },
    projects: [{ name: 'chromium', use: { ${override} } }],
  });`;
}

describe('Playwright credential-bearing trace source guard', () => {
  it('accepts the current production E2E sources without false positives', () => {
    const sources = readSourceTree('.');
    const e2eEntries = Object.keys(sources).filter((filename) => filename.startsWith('./e2e/'));
    const violations = findPlaywrightTraceSourceGraphViolations(
      sources,
      e2eEntries,
    );

    expect(violations).toEqual([]);
  });

  it('allows only a literal trace-off option and ignores comments and string content', () => {
    const source = `
      // test.use({ trace: 'on' });
      const documentation = "browserContext.tracing.start()";
      test.use({ trace: ('off' as const) });
    `;

    expect(findPlaywrightTraceSourceViolations('safe.spec.ts', source)).toEqual([]);
  });

  it('allows unrelated business trace fields and tracing APIs', () => {
    const source = `
      const payload = { trace: 'server-span' };
      await telemetry.tracing.flush();
      const { tracing } = applicationDiagnostics;
      expect(payload.trace).toBe('server-span');
      expect(tracing).toBeDefined();
    `;

    expect(findPlaywrightTraceSourceViolations('business.spec.ts', source)).toEqual([]);
  });

  it('rejects an aliased tracing destructuring access', () => {
    const source = 'const { tracing: capture } = browserContext; await capture.start();';

    expect(findPlaywrightTraceSourceViolations('alias.spec.ts', source)).toEqual([
      { file: 'alias.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects direct manual tracing access', () => {
    const source = 'await browserContext.tracing.start({ screenshots: false });';

    expect(findPlaywrightTraceSourceViolations('manual.spec.ts', source)).toEqual([
      { file: 'manual.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects manual tracing through a simple const BrowserContext alias', () => {
    const source = 'const ctx = browserContext; await ctx.tracing.start();';

    expect(findPlaywrightTraceSourceViolations('context-alias.spec.ts', source)).toEqual([
      { file: 'context-alias.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects plain tracing destructuring access', () => {
    const source = 'const { tracing } = browserContext; await tracing.start();';

    expect(findPlaywrightTraceSourceViolations('destructure.spec.ts', source)).toEqual([
      { file: 'destructure.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects computed string-literal manual tracing access', () => {
    const source = "await browserContext['tracing'].start();";

    expect(findPlaywrightTraceSourceViolations('manual-computed.spec.ts', source)).toEqual([
      { file: 'manual-computed.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects a computed string-literal trace option', () => {
    const source = "test.use({ ['trace']: 'on' });";

    expect(findPlaywrightTraceSourceViolations('computed.spec.ts', source)).toEqual([
      { file: 'computed.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a computed no-substitution template trace option', () => {
    const source = "test.use({ [`trace`]: 'on' });";

    expect(findPlaywrightTraceSourceViolations('template.spec.ts', source)).toEqual([
      { file: 'template.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a conditional trace value even when one branch is off', () => {
    const source = "test.use({ trace: 'off' ? 'on' : 'off' });";

    expect(findPlaywrightTraceSourceViolations('conditional.spec.ts', source)).toEqual([
      { file: 'conditional.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects an indirect trace options object', () => {
    const source = "const options = { trace: 'on' }; test.use(options);";

    expect(findPlaywrightTraceSourceViolations('indirect.spec.ts', source)).toEqual([
      { file: 'indirect.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects trace options passed through a const alias of test.use', () => {
    const source = `
      import { test } from '@playwright/test';
      const applyOptions = test.use;
      applyOptions({ trace: 'on' });
    `;

    expect(findPlaywrightTraceSourceViolations('use-alias.spec.ts', source)).toEqual([
      { file: 'use-alias.spec.ts', line: 4, rule: 'trace-option' },
    ]);
  });

  it('rejects trace options passed through a destructured alias of test.use', () => {
    const source = `
      import { test } from '@playwright/test';
      const { use: applyOptions } = test;
      applyOptions({ trace: 'on' });
    `;

    expect(findPlaywrightTraceSourceViolations('use-destructure.spec.ts', source)).toEqual([
      { file: 'use-destructure.spec.ts', line: 4, rule: 'trace-option' },
    ]);
  });

  it('rejects a trace option assigned after the options object is created', () => {
    const source = `
      import { test } from '@playwright/test';
      const options: Record<string, unknown> = {};
      options.trace = 'on';
      test.use(options);
    `;

    expect(findPlaywrightTraceSourceViolations('assigned.spec.ts', source)).toEqual([
      { file: 'assigned.spec.ts', line: 4, rule: 'trace-option' },
    ]);
  });

  it('rejects a trace option assigned through a local options alias', () => {
    const source = `
      import { test } from '@playwright/test';
      const options: Record<string, unknown> = {};
      const alias = options;
      alias.trace = 'on';
      test.use(options);
    `;

    expect(findPlaywrightTraceSourceViolations('assigned-alias.spec.ts', source)).toEqual([
      { file: 'assigned-alias.spec.ts', line: 5, rule: 'trace-option' },
    ]);
  });

  it('rejects a statically named trace entry constructed with Object.fromEntries', () => {
    const source = `
      import { test } from '@playwright/test';
      const options = Object.fromEntries([['trace', 'on']]);
      test.use(options);
    `;

    expect(findPlaywrightTraceSourceViolations('from-entries.spec.ts', source)).toEqual([
      { file: 'from-entries.spec.ts', line: 3, rule: 'trace-option' },
    ]);
  });

  it('rejects a shorthand trace option', () => {
    const source = "const trace = 'on'; test.use({ trace });";

    expect(findPlaywrightTraceSourceViolations('shorthand.spec.ts', source)).toEqual([
      { file: 'shorthand.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a statically concatenated trace option key', () => {
    const source = "test.use({ ['tr' + 'ace']: 'on' });";

    expect(findPlaywrightTraceSourceViolations('concat.spec.ts', source)).toEqual([
      { file: 'concat.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a statically substituted template trace option key', () => {
    const source = "test.use({ [`tr${'ace'}`]: 'on' });";

    expect(findPlaywrightTraceSourceViolations('substitution.spec.ts', source)).toEqual([
      { file: 'substitution.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a nested static template trace option key', () => {
    const source = "test.use({ [`t${`r${'ace'}`}`]: 'on' });";

    expect(findPlaywrightTraceSourceViolations('nested-template.spec.ts', source)).toEqual([
      { file: 'nested-template.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a conditional computed trace option key', () => {
    const source = "test.use({ [credentialRun ? 'trace' : 'diagnostic']: 'on' });";

    expect(findPlaywrightTraceSourceViolations('conditional-key.spec.ts', source)).toEqual([
      { file: 'conditional-key.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a statically concatenated method-call trace option key', () => {
    const source = "test.use({ ['tr'.concat('ace')]: 'on' });";

    expect(findPlaywrightTraceSourceViolations('concat-call.spec.ts', source)).toEqual([
      { file: 'concat-call.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects an escaped static trace option key', () => {
    const source = String.raw`test.use({ ['\x74race']: 'on' });`;

    expect(findPlaywrightTraceSourceViolations('escaped-key.spec.ts', source)).toEqual([
      { file: 'escaped-key.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects a const-aliased static trace option key', () => {
    const source = "const key = 'tr' + 'ace'; test.use({ [key]: 'on' });";

    expect(findPlaywrightTraceSourceViolations('const-key.spec.ts', source)).toEqual([
      { file: 'const-key.spec.ts', line: 1, rule: 'trace-option' },
    ]);
  });

  it('rejects statically concatenated manual tracing access', () => {
    const source = "await browserContext['trac' + 'ing'].start();";

    expect(findPlaywrightTraceSourceViolations('manual-concat.spec.ts', source)).toEqual([
      { file: 'manual-concat.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects escaped identifier manual tracing access', () => {
    const source = String.raw`await browserContext.trac\u0069ng.start();`;

    expect(findPlaywrightTraceSourceViolations('manual-escaped.spec.ts', source)).toEqual([
      { file: 'manual-escaped.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects comment-separated manual tracing access', () => {
    const source = 'await browserContext./* static */tracing.start();';

    expect(findPlaywrightTraceSourceViolations('manual-comment.spec.ts', source)).toEqual([
      { file: 'manual-comment.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects Reflect.get manual tracing access', () => {
    const source = "await Reflect.get(browserContext, 'tracing').start();";

    expect(findPlaywrightTraceSourceViolations('reflect.spec.ts', source)).toEqual([
      { file: 'reflect.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects a const-aliased Reflect.get tracing key', () => {
    const source = "const key = `tr${'acing'}`; await Reflect.get(browserContext, key).start();";

    expect(findPlaywrightTraceSourceViolations('reflect-alias.spec.ts', source)).toEqual([
      { file: 'reflect-alias.spec.ts', line: 1, rule: 'tracing-access' },
    ]);
  });

  it('rejects a bound Reflect.get alias used on a BrowserContext', () => {
    const source = `
      import type { BrowserContext } from '@playwright/test';
      const get = Reflect.get.bind(Reflect);
      export async function capture(context: BrowserContext) {
        await get(context, 'tracing').start();
      }
    `;

    expect(findPlaywrightTraceSourceViolations('capture-helper.ts', source)).toEqual([
      { file: 'capture-helper.ts', line: 5, rule: 'tracing-access' },
    ]);
  });

  it('follows relative imports to a tracing helper outside the E2E directory', () => {
    const sources = {
      'e2e/example.spec.ts': `
        import { test } from '@playwright/test';
        import { capture } from '../test-support/capture';
        test('example', async ({ context }) => capture(context));
      `,
      'test-support/capture.ts': `
        import type { BrowserContext } from '@playwright/test';
        export async function capture(context: BrowserContext) {
          await context.tracing.start();
        }
      `,
    };

    expect(findPlaywrightTraceSourceGraphViolations(
      sources,
      ['e2e/example.spec.ts'],
    )).toEqual([
      { file: 'test-support/capture.ts', line: 4, rule: 'tracing-access' },
    ]);
  });
});

describe('Playwright config trace ownership guard', () => {
  it('accepts the single runtime-policy-owned trace in the production config', () => {
    const config = fs.readFileSync('playwright.config.ts', 'utf8');

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(true);
  });

  it('rejects a direct second project trace override', () => {
    const config = configWithProjectOverride("trace: 'on'");

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a computed string-literal second project trace override', () => {
    const config = configWithProjectOverride("['trace']: 'on'");

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a computed no-substitution template second project trace override', () => {
    const config = configWithProjectOverride("[`trace`]: 'on'");

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a statically concatenated second project trace override', () => {
    const config = configWithProjectOverride("['tr' + /* static */ 'ace']: 'on'");

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a statically substituted template second project trace override', () => {
    const config = configWithProjectOverride("[`tr${'ace'}`]: 'on'");

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a conditional computed second project trace override', () => {
    const config = configWithProjectOverride("[credentialRun ? 'trace' : 'diagnostic']: 'on'");

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a static concat-call second project trace override', () => {
    const config = configWithProjectOverride("['tr'.concat('ace')]: 'on'");

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a const-aliased static second project trace override', () => {
    const config = `const key = 'tr' + 'ace';\n${configWithProjectOverride("[key]: 'on'")}`;

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });

  it('rejects a project trace override constructed with Object.fromEntries', () => {
    const config = configWithProjectOverride(
      "...Object.fromEntries([['trace', 'on']])",
    );

    expect(hasOnlyRuntimePolicyOwnedConfigTrace('playwright.config.ts', config)).toBe(false);
  });
});
