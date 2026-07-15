// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const scanRoots = ['pages', 'components/common', 'components/settings', 'components/alerts', 'components/report', 'components/StockAutocomplete'];
const han = /[\p{Script=Han}]/u;

const exactAllowedStrings: Record<string, Set<string>> = {
  'pages/BacktestPage.tsx': new Set(['市场阶段: ', '市场阶段：']),
  'components/settings/LLMChannelEditor.tsx': new Set([
    '连接名称已存在，请更换', '缺少 API 密钥', '缺少服务地址', '至少配置一个模型',
    '连接名称必填', '连接名称仅限小写字母、数字或下划线',
  ]),
};

const reportBodyFiles = new Set([
  'components/report/AnalysisContextSummary.tsx',
  'components/report/MarketReviewReportView.tsx',
  'components/report/MarketStructureCard.tsx',
  'components/report/ReportDetails.tsx',
  'components/report/ReportNews.tsx',
  'components/report/ReportOverview.tsx',
  'components/report/ReportStrategy.tsx',
  'components/report/ReportSummary.tsx',
]);

function collectTsxFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry: { name: string; isDirectory: () => boolean; isFile: () => boolean }) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : collectTsxFiles(fullPath);
    return entry.isFile() && entry.name.endsWith('.tsx') ? [fullPath] : [];
  });
}

describe('hardcoded UI strings', () => {
  it('keeps visible Chinese copy out of production TSX', () => {
    const failures: string[] = [];
    for (const root of scanRoots) {
      for (const filename of collectTsxFiles(path.join(sourceRoot, root))) {
        const relative = path.relative(sourceRoot, filename);
        const sourceText = fs.readFileSync(filename, 'utf8');
        const source = ts.createSourceFile(filename, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
        const visit = (node: ts.Node) => {
          if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node)) && han.test(node.text)) {
            const allowed = reportBodyFiles.has(relative) || exactAllowedStrings[relative]?.has(node.text);
            if (!allowed) {
              const { line } = source.getLineAndCharacterOfPosition(node.getStart());
              failures.push(`${relative}:${line + 1} ${JSON.stringify(node.text.trim())}`);
            }
          }
          ts.forEachChild(node, visit);
        };
        visit(source);
      }
    }
    expect(failures).toEqual([]);
  });
});
