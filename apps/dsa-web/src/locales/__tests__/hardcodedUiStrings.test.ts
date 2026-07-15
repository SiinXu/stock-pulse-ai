// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const nonLocaleScript = /[\p{Script=Han}\p{Script=Hangul}]/u;
const englishUiLiteral = /[A-Za-z]{2,}(?:\s+[A-Za-z][A-Za-z0-9'./:-]*)+|^[A-Za-z]{3,}:?$/;
const excludedDirectories = new Set(['__tests__', 'generated', 'stories']);
const excludedFilePattern = /\.(?:generated|spec|stories|test)\.tsx$/;
const userFacingAttributes = new Set(['alt', 'aria-description', 'aria-label', 'placeholder', 'title']);
const userFeedbackCalls = /(?:^|\.)(?:addToast|setToast|showToast|toast)$/;

type DynamicTextAllowance = {
  file: string;
  value: string;
  purpose: string;
};

const dynamicTextAllowlist: DynamicTextAllowance[] = [
  { file: 'components/history/HistoryListItem.tsx', value: '市场阶段: ', purpose: 'Legacy server-generated market-phase prefix removed from dynamic report data.' },
  { file: 'components/history/HistoryListItem.tsx', value: '市场阶段：', purpose: 'Legacy server-generated market-phase prefix removed from dynamic report data.' },
  { file: 'components/history/StockBarItem.tsx', value: '市场阶段: ', purpose: 'Legacy server-generated market-phase prefix removed from dynamic report data.' },
  { file: 'components/history/StockBarItem.tsx', value: '市场阶段：', purpose: 'Legacy server-generated market-phase prefix removed from dynamic report data.' },
  { file: 'components/report/MarketReviewReportView.tsx', value: '大盘复盘', purpose: 'Known generated report heading used only to de-duplicate dynamic Markdown.' },
  { file: 'components/report/MarketReviewReportView.tsx', value: '大盘复盘详情', purpose: 'Known generated report heading used only to de-duplicate dynamic Markdown.' },
  { file: 'components/report/MarketReviewReportView.tsx', value: 'a股市场复盘', purpose: 'Known generated report heading used only to de-duplicate dynamic Markdown.' },
  { file: 'components/report/MarketReviewReportView.tsx', value: 'a 股市场复盘', purpose: 'Known generated report heading used only to de-duplicate dynamic Markdown.' },
  { file: 'components/report/ReportOverview.tsx', value: '行业', purpose: 'Legacy dynamic board-type value normalized before rendering report data.' },
  { file: 'components/report/ReportOverview.tsx', value: '行业板块', purpose: 'Legacy dynamic board-type value normalized before rendering report data.' },
  { file: 'components/report/ReportOverview.tsx', value: '概念', purpose: 'Legacy dynamic board-type value normalized before rendering report data.' },
  { file: 'components/report/ReportOverview.tsx', value: '概念板块', purpose: 'Legacy dynamic board-type value normalized before rendering report data.' },
  { file: 'components/report/ReportOverview.tsx', value: '题材', purpose: 'Legacy dynamic board-type value normalized before rendering report data.' },
  { file: 'components/run-flow/RunFlowGraph.tsx', value: '调用', purpose: 'Legacy server edge label mapped to a localized stable run-flow label.' },
  { file: 'components/run-flow/RunFlowGraph.tsx', value: '详情', purpose: 'Legacy server edge label mapped to a localized stable run-flow label.' },
  { file: 'pages/BacktestPage.tsx', value: '市场阶段: ', purpose: 'Legacy server-generated market-phase prefix removed from dynamic backtest data.' },
  { file: 'pages/BacktestPage.tsx', value: '市场阶段：', purpose: 'Legacy server-generated market-phase prefix removed from dynamic backtest data.' },
];

const englishUiAllowlist: DynamicTextAllowance[] = [
  { file: 'components/StockAutocomplete/SuggestionsList.tsx', value: 'ETF', purpose: 'Asset type abbreviation.' },
  { file: 'components/layout/SidebarNav.tsx', value: 'DSA', purpose: 'Product abbreviation.' },
  { file: 'components/report/MarketReviewReportView.tsx', value: 'MARKET REVIEW', purpose: 'Fixed report masthead.' },
  { file: 'components/settings/GenerationBackendStatusPanel.tsx', value: 'JSON', purpose: 'Protocol capability name.' },
  { file: 'components/settings/GenerationBackendStatusPanel.tsx', value: 'Stream', purpose: 'Protocol capability name.' },
  { file: 'components/settings/NotificationTestPanel.tsx', value: 'HTTP', purpose: 'Protocol name.' },
  { file: 'pages/LoginPage.tsx', value: 'StockPulse', purpose: 'Product name.' },
  { file: 'pages/LoginPage.tsx', value: 'Market Intelligence', purpose: 'Product tagline.' },
  { file: 'pages/LoginPage.tsx', value: 'V3.X QUANTITATIVE SYSTEM', purpose: 'Product edition mark.' },
  { file: 'pages/LoginPage.tsx', value: 'Secure Connection Established via DSA-V3-TLS', purpose: 'Product security mark.' },
  { file: 'pages/StockScreeningPage.tsx', value: 'LLM', purpose: 'Technical abbreviation.' },
];

const allowanceKey = (file: string, value: string) => `${file}\0${value}`;
const allowedDynamicText = new Map(
  dynamicTextAllowlist.map((entry) => [allowanceKey(entry.file, entry.value), entry]),
);
const allowedEnglishUiText = new Map(
  englishUiAllowlist.map((entry) => [allowanceKey(entry.file, entry.value), entry]),
);

function normalizeCandidateText(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function isTransparentExpression(node: ts.Node): boolean {
  return ts.isAsExpression(node)
    || ts.isConditionalExpression(node)
    || ts.isJsxExpression(node)
    || ts.isNonNullExpression(node)
    || ts.isParenthesizedExpression(node)
    || ts.isTemplateExpression(node);
}

function isUserFacingCandidate(node: ts.Node): boolean {
  if (ts.isJsxText(node)) return true;

  let current = node;
  while (current.parent && isTransparentExpression(current.parent)) {
    current = current.parent;
  }
  const parent = current.parent;
  if (!parent) return false;

  if (ts.isJsxAttribute(parent)) {
    return userFacingAttributes.has(parent.name.getText());
  }
  if (ts.isJsxExpression(current) && (ts.isJsxElement(parent) || ts.isJsxFragment(parent))) {
    return true;
  }
  if (
    ts.isBinaryExpression(parent)
    && parent.operatorToken.kind === ts.SyntaxKind.EqualsToken
    && ts.isPropertyAccessExpression(parent.left)
    && parent.left.expression.getText() === 'document'
    && parent.left.name.text === 'title'
  ) {
    return true;
  }
  return ts.isCallExpression(parent)
    && parent.arguments.includes(current as ts.Expression)
    && userFeedbackCalls.test(parent.expression.getText());
}

function collectProductionTsxFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry: { name: string; isDirectory: () => boolean; isFile: () => boolean }) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      return excludedDirectories.has(entry.name) ? [] : collectProductionTsxFiles(fullPath);
    }
    return entry.isFile() && entry.name.endsWith('.tsx') && !excludedFilePattern.test(entry.name)
      ? [fullPath]
      : [];
  });
}

function collectCandidateText(node: ts.Node): Array<{ node: ts.Node; value: string }> {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node)) {
    return [{ node, value: node.text }];
  }
  if (ts.isTemplateExpression(node)) {
    return [
      { node: node.head, value: node.head.text },
      ...node.templateSpans.map((span) => ({ node: span.literal, value: span.literal.text })),
    ];
  }
  return [];
}

describe('hardcoded UI strings', () => {
  it('includes task and report surfaces that were previously outside the guard', () => {
    const relativeFiles = collectProductionTsxFiles(sourceRoot).map((filename) => path.relative(sourceRoot, filename));
    expect(relativeFiles).toContain('components/tasks/TaskPanel.tsx');
    expect(relativeFiles).toContain('components/report/ReportDiagnostics.tsx');
    expect(relativeFiles).toContain('components/report/MarketReviewReportView.tsx');
  });

  it('detects localized and English copy in user-facing production contexts', () => {
    const source = ts.createSourceFile(
      'guard-fixture.tsx',
      `
        const toast = (value: string) => value;
        const Fixture = ({ id }: { id: string }) => {
          document.title = '页面标题';
          toast(\`操作成功 \${id}\`);
          document.title = 'English page title';
          toast(\`Action completed \${id}\`);
          return (
            <>
              <div aria-label="关闭" title={'查看详情'}>
                <input placeholder="请输入" />
                <span>正文文案</span>
              </div>
              <div aria-label="Close report" title={'View details'}>
                <input placeholder="Enter symbol" />
                <span>Visible English copy</span>
              </div>
            </>
          );
        };
      `,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX,
    );
    const detected: string[] = [];
    const detectedEnglish: string[] = [];
    const visit = (node: ts.Node) => {
      collectCandidateText(node).forEach((candidate) => {
        if (nonLocaleScript.test(candidate.value)) detected.push(candidate.value.trim());
        const normalized = normalizeCandidateText(candidate.value);
        if (
          !nonLocaleScript.test(candidate.value)
          && englishUiLiteral.test(normalized)
          && isUserFacingCandidate(candidate.node)
        ) {
          detectedEnglish.push(normalized);
        }
      });
      ts.forEachChild(node, visit);
    };
    visit(source);

    expect(detected).toEqual(expect.arrayContaining([
      '页面标题',
      '操作成功',
      '关闭',
      '查看详情',
      '请输入',
      '正文文案',
    ]));
    expect(detectedEnglish).toEqual(expect.arrayContaining([
      'English page title',
      'Action completed',
      'Close report',
      'View details',
      'Enter symbol',
      'Visible English copy',
    ]));
  });

  it('scans every production TSX and permits only registered dynamic source text', () => {
    const failures: string[] = [];
    const usedAllowances = new Set<string>();
    const usedEnglishAllowances = new Set<string>();
    for (const filename of collectProductionTsxFiles(sourceRoot)) {
      const relative = path.relative(sourceRoot, filename);
      const sourceText = fs.readFileSync(filename, 'utf8');
      const source = ts.createSourceFile(filename, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      const visit = (node: ts.Node) => {
        for (const candidate of collectCandidateText(node)) {
          if (nonLocaleScript.test(candidate.value)) {
            const key = allowanceKey(relative, candidate.value);
            const allowance = allowedDynamicText.get(key);
            if (allowance) {
              usedAllowances.add(key);
              continue;
            }
            const { line } = source.getLineAndCharacterOfPosition(candidate.node.getStart());
            failures.push(`${relative}:${line + 1} ${JSON.stringify(candidate.value.trim())}`);
          } else {
            const normalized = normalizeCandidateText(candidate.value);
            if (!englishUiLiteral.test(normalized) || !isUserFacingCandidate(candidate.node)) continue;
            const key = allowanceKey(relative, normalized);
            const allowance = allowedEnglishUiText.get(key);
            if (allowance) {
              usedEnglishAllowances.add(key);
              continue;
            }
            const { line } = source.getLineAndCharacterOfPosition(candidate.node.getStart());
            failures.push(`${relative}:${line + 1} ${JSON.stringify(normalized)}`);
          }
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }

    const staleAllowances = dynamicTextAllowlist
      .filter((entry) => !usedAllowances.has(allowanceKey(entry.file, entry.value)))
      .map((entry) => `${entry.file} ${JSON.stringify(entry.value)}: ${entry.purpose}`);
    const staleEnglishAllowances = englishUiAllowlist
      .filter((entry) => !usedEnglishAllowances.has(allowanceKey(entry.file, entry.value)))
      .map((entry) => `${entry.file} ${JSON.stringify(entry.value)}: ${entry.purpose}`);
    expect(failures, 'Move UI copy into a locale registry or register a specific dynamic-content use.').toEqual([]);
    expect(staleAllowances, 'Remove stale dynamic-text allowlist entries.').toEqual([]);
    expect(staleEnglishAllowances, 'Remove stale English UI allowlist entries.').toEqual([]);
  });
});
