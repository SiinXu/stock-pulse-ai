/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import { productionDesignGuardFixtures } from './fixtures/productionDesignGuardFixtures';

const productionComponents = import.meta.glob('../../**/*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;
const productionStylePaths = import.meta.glob('../../**/*.css');
const productionStyles: Record<string, string> = {
  '../../App.css': fs.readFileSync('src/App.css', 'utf8'),
  '../../index.css': fs.readFileSync('src/index.css', 'utf8'),
};
const productionSources = { ...productionStyles, ...productionComponents };

type DesignRule =
  | 'button-shape'
  | 'hardcoded-hex'
  | 'hardcoded-color'
  | 'legacy-chromatic-token'
  | 'magic-pixel-size'
  | 'raw-viewport-height'
  | 'glow-effect'
  | 'strong-blur';

type DesignViolation = {
  file: string;
  line: number;
  rule: DesignRule;
  token: string;
};

const BUTTON_OPENING_TAG_PATTERN = /<(?:button|Button)\b(?:=>|[^>])*?>/g;
const NON_PILL_RADIUS_PATTERN = /\brounded-(?!full\b)(?:[trblse]{1,2}-)?(?:none|sm|md|lg|xl|2xl|3xl|\[[^\]]+\])/g;
const HARDCODED_HEX_PATTERN = /#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])/g;
const HARDCODED_COLOR_FUNCTION_PATTERN = /(?<![a-zA-Z0-9])(?:rgb|hsl)a?\(\s*(?!var\(|\$\{)[^)]+\)/gi;
const MAGIC_PIXEL_SIZE_PATTERN = /\b(?:text|size|[wh]|min-[wh]|max-[wh]|basis)-\[[^\]\r\n]*\d(?:\.\d+)?px[^\]\r\n]*\]/g;
const ARBITRARY_RADIUS_PATTERN = /\brounded-\[[^\]\r\n]+\]/g;
const RAW_STATIC_VIEWPORT_HEIGHT = /(^|[^a-zA-Z0-9])100vh([^a-zA-Z0-9]|$)/g;
const LEGACY_CHROMATIC_TOKEN_PATTERN = /\b(?:cyan|purple)(?:-\d+)?(?:\/[\d.]+)?\b/gi;
const RAW_CSS_MAGIC_PIXEL_PATTERN = /(?<![\w-])(?:font-size|width|height|min-width|max-width|min-height|max-height|border-radius|padding(?:-(?:top|right|bottom|left))?|margin(?:-(?:top|right|bottom|left))?|gap|row-gap|column-gap|top|right|bottom|left|inset)\s*:\s*[^;{}\r\n]*?(-?\d+(?:\.\d+)?)px\b/g;
const GLOW_EFFECT_PATTERNS = [
  /\b(?:filter\s*:\s*drop-shadow\(|text-shadow\s*:\s*0\s+0\s+(?!0(?:\D|$))|box-shadow\s*:\s*0\s+0\s+(?!0(?:\D|$)))/g,
  /\b(?:drop-)?shadow-\[(?:inset_)?0_0_(?!0_)[^\]]+\]/g,
  /var\(--[\w-]*glow[\w-]*\)/gi,
  /(?:\.[\w-]*glow[\w-]*|\[data-[^\]]*glow[^\]]*\]|@keyframes\s+[\w-]*glow[\w-]*)/gi,
];
const STRONG_BLUR_CLASS_PATTERN = /\b(?:backdrop-)?blur-(?:md|lg|xl|2xl|3xl)\b/g;
const ARBITRARY_BLUR_CLASS_PATTERN = /\b(?:backdrop-)?blur-\[\s*(\d+(?:\.\d+)?)px\s*\]/g;
const CSS_BLUR_PATTERN = /\b(?:backdrop-filter|filter)\s*:\s*blur\(\s*(\d+(?:\.\d+)?)px\s*\)/g;
const MAX_RESTRAINED_BLUR_PX = 4;
const CSS_RULE_PATTERN = /([^{}]+)\{([^{}]*)\}/g;
const CSS_RADIUS_DECLARATION_PATTERN = /\bborder-radius\s*:\s*([^;{}\r\n]+)/i;
const BUTTON_SELECTOR_PATTERN = /\bbutton\b|\.[\w-]*(?:button|btn)[\w-]*/i;
const PILL_RADIUS_PATTERN = /^(?:9999px|50%|var\(--(?:radius-)?(?:pill|full)\))$/i;
const CLASS_LIKE_TOKEN_PATTERN = /(?<![a-zA-Z0-9_-])([a-zA-Z][a-zA-Z0-9_]*(?:-[a-zA-Z0-9_]+)+)(?![a-zA-Z0-9_-])/g;

function isProductionSource(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !filename.includes('/__fixtures__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/generated/')
    && !filename.includes('/stories/')
    && !/\.(?:test|spec)\.(?:css|tsx)$/.test(filename)
    && !/\.(?:story|stories|generated)\.(?:css|tsx)$/.test(filename);
}

function lineNumberAt(source: string, index: number): number {
  return source.slice(0, index).split('\n').length;
}

function findCssBlockEnd(source: string, openBraceIndex: number): number {
  let depth = 1;
  for (let index = openBraceIndex + 1; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') depth -= 1;
    if (depth === 0) return index;
  }
  return -1;
}

function isInsideThemeTokenBlock(source: string, index: number): boolean {
  for (const selectorMatch of source.matchAll(/(?:^|\n)\s*(?::root|\.dark)\s*\{/g)) {
    const openBraceIndex = (selectorMatch.index ?? 0) + selectorMatch[0].lastIndexOf('{');
    const closeBraceIndex = findCssBlockEnd(source, openBraceIndex);
    if (index > openBraceIndex && index < closeBraceIndex) return true;
  }
  return false;
}

function isAllowedIndexCssToken(filename: string, source: string, index: number): boolean {
  if (!filename.endsWith('/index.css')) {
    return false;
  }

  const declarationStart = Math.max(
    source.lastIndexOf(';', index),
    source.lastIndexOf('{', index),
  ) + 1;
  const nextSemicolon = source.indexOf(';', index);
  const declarationEnd = nextSemicolon === -1 ? source.length : nextSemicolon;
  const declaration = maskComments(source.slice(declarationStart, declarationEnd));
  return /^\s*--[\w-]+\s*:/.test(declaration)
    && isInsideThemeTokenBlock(source, index);
}

function maskComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/gm, (comment) => comment.replace(/[^\n]/g, ' '));
}

function isPillRadius(value: string): boolean {
  return PILL_RADIUS_PATTERN.test(value.trim());
}

function extractButtonClassNames(source: string): Set<string> {
  const classNames = new Set<string>();
  for (const buttonMatch of source.matchAll(BUTTON_OPENING_TAG_PATTERN)) {
    for (const tokenMatch of buttonMatch[0].matchAll(CLASS_LIKE_TOKEN_PATTERN)) {
      classNames.add(tokenMatch[1]);
    }
  }
  return classNames;
}

function escapePattern(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function selectorTargetsButton(selector: string, buttonClassNames: Set<string>): boolean {
  if (BUTTON_SELECTOR_PATTERN.test(selector)) return true;
  return Array.from(buttonClassNames).some((className) => (
    new RegExp(`\\.${escapePattern(className)}(?![a-zA-Z0-9_-])`).test(selector)
  ));
}

function hasGlobalPillButtonRule(source: string): boolean {
  for (const ruleMatch of source.matchAll(CSS_RULE_PATTERN)) {
    const selectors = ruleMatch[1].split(',').map((selector) => selector.trim());
    if (!selectors.includes('button')) continue;
    const radius = ruleMatch[2].match(CSS_RADIUS_DECLARATION_PATTERN)?.[1];
    if (radius && isPillRadius(radius)) return true;
  }
  return false;
}

function findProductionDesignViolations(
  filename: string,
  source: string,
  buttonClassNames: Set<string> = new Set(),
): DesignViolation[] {
  const violations: DesignViolation[] = [];

  for (const buttonMatch of source.matchAll(BUTTON_OPENING_TAG_PATTERN)) {
    const button = buttonMatch[0];
    const buttonIndex = buttonMatch.index ?? 0;
    for (const radiusMatch of button.matchAll(NON_PILL_RADIUS_PATTERN)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, buttonIndex + (radiusMatch.index ?? 0)),
        rule: 'button-shape',
        token: radiusMatch[0],
      });
    }
  }

  const sourceWithoutComments = maskComments(source);
  if (filename.endsWith('.css')) {
    for (const ruleMatch of sourceWithoutComments.matchAll(CSS_RULE_PATTERN)) {
      const selector = ruleMatch[1];
      if (!selectorTargetsButton(selector, buttonClassNames)) continue;
      const radiusMatch = ruleMatch[2].match(CSS_RADIUS_DECLARATION_PATTERN);
      if (!radiusMatch || isPillRadius(radiusMatch[1])) continue;
      const ruleIndex = ruleMatch.index ?? 0;
      const radiusIndex = ruleIndex + ruleMatch[0].indexOf(radiusMatch[0]);
      violations.push({
        file: filename,
        line: lineNumberAt(source, radiusIndex),
        rule: 'button-shape',
        token: radiusMatch[0],
      });
    }
  }

  for (const match of sourceWithoutComments.matchAll(HARDCODED_HEX_PATTERN)) {
    const index = match.index ?? 0;
    if (!isAllowedIndexCssToken(filename, source, index)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, index),
        rule: 'hardcoded-hex',
        token: match[0],
      });
    }
  }

  for (const match of sourceWithoutComments.matchAll(HARDCODED_COLOR_FUNCTION_PATTERN)) {
    const index = match.index ?? 0;
    if (!isAllowedIndexCssToken(filename, source, index)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, index),
        rule: 'hardcoded-color',
        token: match[0],
      });
    }
  }

  for (const match of source.matchAll(MAGIC_PIXEL_SIZE_PATTERN)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'magic-pixel-size',
      token: match[0],
    });
  }

  for (const match of source.matchAll(ARBITRARY_RADIUS_PATTERN)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'magic-pixel-size',
      token: match[0],
    });
  }

  if (filename.endsWith('.css')) {
    for (const match of sourceWithoutComments.matchAll(RAW_CSS_MAGIC_PIXEL_PATTERN)) {
      const index = match.index ?? 0;
      const declaration = match[0];
      const pixelValue = Number(match[1]);
      const isCanonicalPillRadius = declaration.startsWith('border-radius') && pixelValue === 9999;
      if (!isCanonicalPillRadius) {
        violations.push({
          file: filename,
          line: lineNumberAt(source, index),
          rule: 'magic-pixel-size',
          token: declaration,
        });
      }
    }
  }

  for (const match of source.matchAll(RAW_STATIC_VIEWPORT_HEIGHT)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'raw-viewport-height',
      token: '100vh',
    });
  }

  for (const match of sourceWithoutComments.matchAll(LEGACY_CHROMATIC_TOKEN_PATTERN)) {
    const index = match.index ?? 0;
    if (!isAllowedIndexCssToken(filename, source, index)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, index),
        rule: 'legacy-chromatic-token',
        token: match[0],
      });
    }
  }

  for (const pattern of GLOW_EFFECT_PATTERNS) {
    for (const match of sourceWithoutComments.matchAll(pattern)) {
      const index = match.index ?? 0;
      if (!isAllowedIndexCssToken(filename, source, index)) {
        violations.push({
          file: filename,
          line: lineNumberAt(source, index),
          rule: 'glow-effect',
          token: match[0],
        });
      }
    }
  }

  for (const match of sourceWithoutComments.matchAll(STRONG_BLUR_CLASS_PATTERN)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'strong-blur',
      token: match[0],
    });
  }

  for (const pattern of [ARBITRARY_BLUR_CLASS_PATTERN, CSS_BLUR_PATTERN]) {
    for (const match of sourceWithoutComments.matchAll(pattern)) {
      const index = match.index ?? 0;
      if (Number(match[1]) > MAX_RESTRAINED_BLUR_PX) {
        violations.push({
          file: filename,
          line: lineNumberAt(source, index),
          rule: 'strong-blur',
          token: match[0],
        });
      }
    }
  }

  return violations;
}

describe('production design guard', () => {
  it('explicitly excludes tests, stories, generated sources, and fixtures', () => {
    expect(isProductionSource('../../pages/HomePage.tsx')).toBe(true);
    expect(isProductionSource('../../pages/HomePage.test.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.spec.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.stories.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.story.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.generated.tsx')).toBe(false);
    expect(isProductionSource('../../pages/__tests__/HomePage.tsx')).toBe(false);
    expect(isProductionSource('../../pages/fixtures/HomePage.tsx')).toBe(false);
    expect(isProductionSource('../../pages/generated/HomePage.tsx')).toBe(false);
    expect(isProductionSource('../../pages/stories/HomePage.tsx')).toBe(false);
    const indexStyles = Object.entries(productionSources)
      .find(([filename]) => filename.endsWith('/index.css'));
    expect(indexStyles, 'root index.css must remain in the production scan').toBeDefined();
    expect(indexStyles?.[1]).toContain('.badge');
    const productionCssPaths = Object.keys(productionStylePaths).filter(isProductionSource).sort();
    expect(Object.keys(productionStyles).sort()).toEqual(productionCssPaths);
  });

  it('self-test detects a non-pill button shape', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.nonPillButton))
      .toEqual([expect.objectContaining({ rule: 'button-shape', token: 'rounded-lg' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.nonPillCssButton))
      .toEqual([expect.objectContaining({ rule: 'button-shape', token: 'border-radius: 0.9rem' })]);
    expect(findProductionDesignViolations(
      'fixture.css',
      productionDesignGuardFixtures.mappedNonPillCssButton,
      new Set(['session-item']),
    )).toEqual([expect.objectContaining({ rule: 'button-shape', token: 'border-radius: 0.75rem' })]);
  });

  it('self-test detects a hardcoded hex colour', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.hardcodedHex))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-hex', token: '#123456' })]);
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.hardcodedFunctionalColor))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-color', token: 'rgba(0,0,0,0.2)' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.hardcodedCssFunctionalColor))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-color', token: 'hsl(0 0% 0% / 0.2)' })]);
  });

  it('keeps native buttons pill-shaped when they have no local radius class', () => {
    const indexStyles = Object.entries(productionSources)
      .find(([filename]) => filename.endsWith('/index.css'))?.[1] ?? '';
    expect(hasGlobalPillButtonRule(indexStyles)).toBe(true);
  });

  it('allows index.css theme tokens but rejects hex variables outside theme blocks', () => {
    const fixture = ':root {\n  --brand: #123456;\n}\n.card {\n  --leak: #abcdef;\n}';
    expect(findProductionDesignViolations('../../index.css', fixture))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-hex', token: '#abcdef' })]);
  });

  it('self-test detects a magic pixel font size', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.magicPixelFont))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'text-[13px]' })]);
  });

  it('self-test detects a magic pixel component size', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.magicPixelSize))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'h-[37px]' })]);
  });

  it('self-test detects a raw CSS magic pixel size', () => {
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.rawCssMagicPixel))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'border-radius: 6px' })]);
  });

  it('self-test detects raw CSS magic pixel spacing', () => {
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.rawCssMagicSpacing))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'padding: 3px' })]);
  });

  it('self-test detects raw 100vh without rejecting 100dvh', () => {
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.rawViewportHeight))
      .toEqual([expect.objectContaining({ rule: 'raw-viewport-height', token: '100vh' })]);
    expect(findProductionDesignViolations('fixture.css', '.shell { min-height: 100dvh; }'))
      .toEqual([]);
  });

  it('self-test detects legacy cyan and purple styling tokens', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.legacyCyan))
      .toEqual([expect.objectContaining({ rule: 'legacy-chromatic-token', token: 'cyan' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.legacyPurple))
      .toEqual([expect.objectContaining({ rule: 'legacy-chromatic-token', token: 'purple' })]);
  });

  it('allows legacy compatibility tokens only in index.css theme declarations', () => {
    const fixture = ':root {\n  --color-cyan: hsl(var(--primary));\n  --login-accent-glow: hsl(var(--primary) / 0.18);\n}';
    expect(findProductionDesignViolations('../../index.css', fixture)).toEqual([]);
  });

  it('self-test detects decorative glow effects', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.glowEffect))
      .toEqual([expect.objectContaining({ rule: 'glow-effect' })]);
  });

  it('self-test detects strong class and CSS blur without rejecting restrained blur', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.strongBlurClass))
      .toEqual([expect.objectContaining({ rule: 'strong-blur', token: 'backdrop-blur-xl' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.strongCssBlur))
      .toEqual([expect.objectContaining({ rule: 'strong-blur', token: 'backdrop-filter: blur(12px)' })]);
    expect(findProductionDesignViolations('fixture.tsx', '<div className="backdrop-blur-sm" />'))
      .toEqual([]);
    expect(findProductionDesignViolations('fixture.css', '.surface { filter: blur(4px); }'))
      .toEqual([]);
  });

  it('self-test accepts a tokenized pill button', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.compliant))
      .toEqual([]);
  });

  it('keeps every production CSS and TSX source within the enforced rules', () => {
    const scannedSources = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename));
    const productionTsxSources = scannedSources
      .filter(([filename]) => filename.endsWith('.tsx'));
    const totalMatchedButtonTags = productionTsxSources.reduce(
      (total, [, source]) => total + Array.from(source.matchAll(BUTTON_OPENING_TAG_PATTERN)).length,
      0,
    );
    const buttonClassNames = new Set(productionTsxSources
      .flatMap(([, source]) => Array.from(extractButtonClassNames(source))));
    const violations = scannedSources.flatMap(([filename, source]) => (
      findProductionDesignViolations(filename, source, buttonClassNames)
    ));

    expect(scannedSources.length).toBeGreaterThan(0);
    expect(totalMatchedButtonTags).toBeGreaterThan(0);
    expect(buttonClassNames.size).toBeGreaterThan(0);
    expect(violations).toEqual([]);
  });

  it('retains the legacy-visual guard for upstream-adapted surfaces', () => {
    const guardedSuffixes = [
      '/watchlist/HomeStockWorkspace.tsx',
      '/report/MarketStructureCard.tsx',
    ];

    for (const suffix of guardedSuffixes) {
      const entry = Object.entries(productionSources)
        .find(([filename]) => filename.endsWith(suffix));
      expect(entry, `${suffix} must remain in the production scan`).toBeDefined();
      const source = entry?.[1] ?? '';
      expect(source).not.toMatch(/\b(?:text|bg|border|ring)-(?:cyan|purple)\b/);
      expect(source).not.toMatch(/pulse-glow|glow-cyan|glow-purple|shadow-glow/);
    }
  });
});
