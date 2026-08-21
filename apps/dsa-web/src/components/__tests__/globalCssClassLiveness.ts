// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Liveness scanner for global class selectors owned by `src/index.css`.
 *
 * A class is live when production TS/TSX/CSS/HTML contains the ident as a class
 * token (not a `--token` custom property) or constructs it from a className/cn
 * template prefix (`backtest-status-chip-${tone}`). Newly unreferenced classes
 * fail closed unless they are listed in the shrink-only suspected-dead allowlist.
 */

export type GlobalCssClassFinding = {
  className: string;
  reason: string;
};

export type SuspectedDeadClass = {
  className: string;
  reason: string;
};

const CLASS_IN_SELECTOR = /\.(-?[_a-zA-Z]+[_a-zA-Z0-9-]*)/g;
const CLASS_CONSTRUCTION_IN_CLASS_CONTEXT =
  /(?:className|class)\s*=\s*(?:\{`|\{\s*(?:cn|clsx|classNames)\()[\s\S]{0,500}?([A-Za-z][\w-]*)-\$\{/g;
const CLASS_CONSTRUCTION_IN_CN =
  /\b(?:cn|clsx|classNames)\(\s*`[\s\S]{0,400}?([A-Za-z][\w-]*)-\$\{/g;
const CLASS_CONCAT_IN_CLASS_CONTEXT =
  /(?:className|class|cn\(|clsx\(|classNames\()[\s\S]{0,400}?['"`]([A-Za-z][\w-]*)-['"`]\s*\+/g;

/**
 * Descendant / size / theme modifiers whose ident is too generic for a
 * token search to prove liveness. Left in CSS; not fail-closed.
 */
export const GENERIC_UNTRACKED_GLOBAL_CLASSES = [
  'accent',
  'active',
  'content',
  'danger',
  'dark',
  'label',
  'md',
  'message',
  'meta',
  'primary',
  'separator',
  'sm',
  'success',
  'title',
  'value',
  'warning',
] as const;

export const GENERIC_UNTRACKED_GLOBAL_CLASS_SET = new Set<string>(GENERIC_UNTRACKED_GLOBAL_CLASSES);

export function maskCssAndScriptComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/gm, (comment) => comment.replace(/[^\n]/g, ' '));
}

function looksLikeDeclarationStart(source: string, index: number): boolean {
  const rest = source.slice(index).replace(/^\s+/, '');
  if (/^\d+%/.test(rest) || /^(from|to)\b/.test(rest)) {
    return false;
  }
  const match = rest.match(/^(--[\w-]+|[a-zA-Z-]+)\s*:/);
  if (!match) return false;
  const afterColon = rest.slice(match[0].length);
  return !/^(hover|focus|active|visited|focus-visible|is|where|not|has|nth|first|last|only|root|empty|checked|disabled|enabled|link|target|before|after|placeholder|file)\b/
    .test(afterColon);
}

export function collectDefinedGlobalClassNames(indexCss: string): string[] {
  const source = maskCssAndScriptComments(indexCss);
  const names = new Set<string>();
  const modes: Array<'selector' | 'decl'> = ['selector'];
  let selector = '';

  const flushSelector = () => {
    const text = selector;
    selector = '';
    for (const match of text.matchAll(CLASS_IN_SELECTOR)) {
      const name = match[1];
      if (name) names.add(name);
    }
  };

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    const mode = modes[modes.length - 1] ?? 'selector';
    if (character === '{') {
      if (mode === 'selector') flushSelector();
      const nextIsDecl = looksLikeDeclarationStart(source, index + 1);
      modes.push(nextIsDecl ? 'decl' : 'selector');
      continue;
    }
    if (character === '}') {
      if (mode === 'selector') flushSelector();
      if (modes.length > 1) modes.pop();
      continue;
    }
    if (mode === 'selector') selector += character;
  }
  flushSelector();
  return [...names].sort();
}

export function collectClassConstructionPrefixes(source: string): string[] {
  const masked = maskCssAndScriptComments(source);
  const prefixes = new Set<string>();
  for (const pattern of [
    CLASS_CONSTRUCTION_IN_CLASS_CONTEXT,
    CLASS_CONSTRUCTION_IN_CN,
    CLASS_CONCAT_IN_CLASS_CONTEXT,
  ]) {
    pattern.lastIndex = 0;
    for (const match of masked.matchAll(pattern)) {
      const prefix = match[1];
      if (prefix) prefixes.add(prefix);
    }
  }
  return [...prefixes].sort();
}

function isCssVariableReference(source: string, matchIndex: number): boolean {
  return source.slice(Math.max(0, matchIndex - 2), matchIndex) === '--';
}

export function sourceReferencesGlobalClass(
  className: string,
  source: string,
  constructionPrefixes: ReadonlySet<string>,
): boolean {
  const token = new RegExp(
    `(?<![A-Za-z0-9_-])${className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_-])`,
    'g',
  );
  for (const match of source.matchAll(token)) {
    if (!isCssVariableReference(source, match.index ?? 0)) {
      return true;
    }
  }
  const parts = className.split('-');
  for (let index = 1; index < parts.length; index += 1) {
    if (constructionPrefixes.has(parts.slice(0, index).join('-'))) {
      return true;
    }
  }
  return false;
}

export function collectUnreferencedGlobalClasses(args: {
  definedClasses: readonly string[];
  sources: Record<string, string>;
  constructionPrefixes: ReadonlySet<string>;
  untracked: ReadonlySet<string>;
}): string[] {
  const unreferenced: string[] = [];
  for (const className of args.definedClasses) {
    if (args.untracked.has(className)) continue;
    let referenced = false;
    for (const source of Object.values(args.sources)) {
      if (sourceReferencesGlobalClass(className, source, args.constructionPrefixes)) {
        referenced = true;
        break;
      }
    }
    if (!referenced) unreferenced.push(className);
  }
  return unreferenced.sort();
}

export function diffGlobalCssClassLiveness(args: {
  unreferenced: readonly string[];
  allowlist: readonly SuspectedDeadClass[];
}): GlobalCssClassFinding[] {
  const allowlistNames = args.allowlist.map((entry) => entry.className);
  const allowlistSet = new Set(allowlistNames);
  const findings: GlobalCssClassFinding[] = [];

  if (allowlistNames.length !== allowlistSet.size) {
    findings.push({
      className: allowlistNames.join(','),
      reason: 'suspected-dead allowlist contains duplicate class names',
    });
  }

  for (const className of args.unreferenced) {
    if (!allowlistSet.has(className)) {
      findings.push({
        className,
        reason: 'unreferenced global class is not on the suspected-dead allowlist',
      });
    }
  }
  for (const entry of args.allowlist) {
    if (!args.unreferenced.includes(entry.className)) {
      findings.push({
        className: entry.className,
        reason: 'suspected-dead allowlist entry is now referenced; remove it from the allowlist',
      });
    }
  }
  return findings;
}

export function formatLivenessFindings(findings: readonly GlobalCssClassFinding[]): string {
  return findings.map((finding) => `${finding.className}: ${finding.reason}`).join('\n');
}
