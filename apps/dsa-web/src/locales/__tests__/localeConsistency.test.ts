// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import { UI_TEXT } from '../../i18n/uiText';
import { ALERT_FORM_TEXT, ALERT_LIST_TEXT, ALERT_PAGE_TEXT, ALERT_TRIGGER_TEXT } from '../alerts';
import { BACKTEST_TEXT } from '../backtest';
import { PORTFOLIO_TEXT } from '../portfolio';
import {
  ANALYSIS_CONTEXT_CONTENT_TEXT,
  MARKET_REVIEW_CONTENT_TEXT,
  MARKET_STRUCTURE_CONTENT_TEXT,
  REPORT_NEWS_CONTENT_TEXT,
} from '../reportContent';
import { REPORT_CHROME_TEXT } from '../reportChrome';
import { SCREENING_TEXT } from '../screening';
import { SETTINGS_CONTROLS_TEXT } from '../settingsControls';
import { SETTINGS_MISC_TEXT } from '../settingsMisc';
import {
  MODEL_ACCESS_EDITOR_TEXT,
  MODEL_ACCESS_ERROR_LABELS,
  MODEL_ACCESS_ISSUES,
  MODEL_ACCESS_REASON_HINTS,
  MODEL_ACCESS_STAGE_LABELS,
  MODEL_ACCESS_TEXT,
  MODEL_ACCESS_TROUBLESHOOTING,
} from '../settingsModelAccess';
import { SETTINGS_NOTIFICATION_TEXT } from '../settingsNotifications';
import { SETTINGS_PAGE_TEXT } from '../settingsPage';
import { SETTINGS_WIZARD_TEXT } from '../settingsWizard';
import { STOCK_SEARCH_TEXT } from '../stockSearch';

type LocaleMap = { zh: unknown; en: unknown };

const registries: Record<string, LocaleMap> = {
  ui: UI_TEXT,
  alertsForm: ALERT_FORM_TEXT,
  alertsList: ALERT_LIST_TEXT,
  alertsPage: ALERT_PAGE_TEXT,
  alertsTrigger: ALERT_TRIGGER_TEXT,
  backtest: BACKTEST_TEXT,
  portfolio: PORTFOLIO_TEXT,
  reportAnalysisContext: ANALYSIS_CONTEXT_CONTENT_TEXT,
  reportMarketReview: MARKET_REVIEW_CONTENT_TEXT,
  reportMarketStructure: MARKET_STRUCTURE_CONTENT_TEXT,
  reportNewsContent: REPORT_NEWS_CONTENT_TEXT,
  reportChrome: REPORT_CHROME_TEXT,
  screening: SCREENING_TEXT,
  settingsControls: SETTINGS_CONTROLS_TEXT,
  settingsMisc: SETTINGS_MISC_TEXT,
  settingsModelAccess: MODEL_ACCESS_TEXT,
  settingsModelEditor: MODEL_ACCESS_EDITOR_TEXT,
  settingsModelErrors: MODEL_ACCESS_ERROR_LABELS,
  settingsModelIssues: MODEL_ACCESS_ISSUES,
  settingsModelReasons: MODEL_ACCESS_REASON_HINTS,
  settingsModelStages: MODEL_ACCESS_STAGE_LABELS,
  settingsModelTroubleshooting: MODEL_ACCESS_TROUBLESHOOTING,
  settingsNotifications: SETTINGS_NOTIFICATION_TEXT,
  settingsPage: SETTINGS_PAGE_TEXT,
  settingsWizard: SETTINGS_WIZARD_TEXT,
  stockSearch: STOCK_SEARCH_TEXT,
};

function flatten(value: unknown, prefix = ''): Map<string, string> {
  const result = new Map<string, string>();
  if (typeof value === 'string') {
    result.set(prefix, value);
    return result;
  }
  if (!value || typeof value !== 'object') {
    return result;
  }
  for (const [key, child] of Object.entries(value)) {
    const childPrefix = prefix ? `${prefix}.${key}` : key;
    for (const [childKey, text] of flatten(child, childPrefix)) {
      result.set(childKey, text);
    }
  }
  return result;
}

function placeholders(value: string): string[] {
  return Array.from(value.matchAll(/\{([A-Za-z0-9_]+)\}/g), (match) => match[1]).sort();
}

describe('locale registries', () => {
  it.each(Object.entries(registries))('%s keeps zh/en keys, values, and interpolation aligned', (_, registry) => {
    const zh = flatten(registry.zh);
    const en = flatten(registry.en);
    expect([...en.keys()].sort()).toEqual([...zh.keys()].sort());
    for (const key of zh.keys()) {
      expect(zh.get(key)?.trim(), `empty zh translation: ${key}`).not.toBe('');
      expect(en.get(key)?.trim(), `empty en translation: ${key}`).not.toBe('');
      expect(placeholders(en.get(key) ?? ''), `placeholder mismatch: ${key}`).toEqual(placeholders(zh.get(key) ?? ''));
    }
  });

  it('contains no duplicate object keys in locale source files', () => {
    const localesDir = path.dirname(fileURLToPath(import.meta.url)).replace(`${path.sep}__tests__`, '');
    const failures: string[] = [];
    for (const filename of fs.readdirSync(localesDir).filter((name: string) => name.endsWith('.ts'))) {
      const sourceText = fs.readFileSync(path.join(localesDir, filename), 'utf8');
      const source = ts.createSourceFile(filename, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
      const visit = (node: ts.Node) => {
        if (ts.isObjectLiteralExpression(node)) {
          const seen = new Set<string>();
          for (const property of node.properties) {
            if (!('name' in property) || !property.name) continue;
            const name = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) || ts.isNumericLiteral(property.name)
              ? property.name.text
              : undefined;
            if (!name) continue;
            if (seen.has(name)) failures.push(`${filename}:${source.getLineAndCharacterOfPosition(property.getStart()).line + 1} duplicate ${name}`);
            seen.add(name);
          }
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(failures).toEqual([]);
  });
});
