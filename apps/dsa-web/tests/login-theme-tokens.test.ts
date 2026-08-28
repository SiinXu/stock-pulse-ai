// @vitest-environment node

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Phase 2 domain collapse (#1300). The `--login-*` family is deleted; the Login
 * page reads Layer 1 semantics directly so theme packs recolour it. This guard
 * keeps the prefix from coming back and pins the Layer 1 replacements.
 */
const COLLAPSED_LOGIN_TOKENS = [
  '--login-bg-main',
  '--login-bg-card',
  '--login-border-card',
  '--login-text-primary',
  '--login-text-secondary',
  '--login-text-muted',
  '--login-accent-soft',
  '--login-input-icon',
  '--login-input-toggle-ring',
];

const REQUIRED_LAYER1_TOKENS = [
  '--background',
  '--card',
  '--border',
  '--foreground',
  '--secondary-text',
  '--muted-text',
  '--primary',
];

function readIndexCss(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'index.css'), 'utf8');
}

function readLoginPage(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'pages', 'LoginPage.tsx'), 'utf8');
}

describe('login theme tokens', () => {
  it('keeps the light theme root block free of page-scoped login tokens', () => {
    const rootMatch = readIndexCss().match(/:root\s*\{([\s\S]*?)\n\}/);

    expect(rootMatch).not.toBeNull();
    const rootBlock = rootMatch?.[1] ?? '';

    for (const token of COLLAPSED_LOGIN_TOKENS) {
      expect(rootBlock, token).not.toContain(token);
    }
    for (const token of REQUIRED_LAYER1_TOKENS) {
      expect(rootBlock, token).toContain(`${token}:`);
    }
  });

  it('keeps the dark theme block free of page-scoped login tokens', () => {
    const darkMatch = readIndexCss().match(/\.dark\s*\{([\s\S]*?)\n\}/);

    expect(darkMatch).not.toBeNull();
    const darkBlock = darkMatch?.[1] ?? '';

    for (const token of COLLAPSED_LOGIN_TOKENS) {
      expect(darkBlock, token).not.toContain(token);
    }
    for (const token of REQUIRED_LAYER1_TOKENS) {
      expect(darkBlock, token).toContain(`${token}:`);
    }
  });

  it('paints the login page from Layer 1 semantics only', () => {
    const source = readLoginPage();

    expect(source).not.toContain('--login-');
    expect(source).toContain('bg-background');
    expect(source).toContain('border border-border bg-card');
    expect(source).toContain('text-foreground');
    expect(source).toContain('text-secondary-text');
    expect(source).toContain('text-muted-text');
    expect(source).toContain('selection:bg-[hsl(var(--primary)/0.08)]');
  });
});
