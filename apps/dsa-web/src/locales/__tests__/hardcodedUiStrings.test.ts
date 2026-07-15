// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const han = /[\p{Script=Han}]/u;

const exactAllowedStrings: Record<string, Record<string, string>> = {
  'components/settings/LLMChannelEditor.tsx': {
    '连接名称已存在，请更换': 'backend-compatible structural issue token mapped to localized UI copy',
    '缺少 API 密钥': 'backend-compatible structural issue token mapped to localized UI copy',
    '缺少服务地址': 'backend-compatible structural issue token mapped to localized UI copy',
    '至少配置一个模型': 'backend-compatible structural issue token mapped to localized UI copy',
    '连接名称必填': 'backend-compatible structural issue token mapped to localized UI copy',
    '连接名称仅限小写字母、数字或下划线': 'backend-compatible structural issue token mapped to localized UI copy',
  },
};

function collectTsxFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry: { name: string; isDirectory: () => boolean; isFile: () => boolean }) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      return ['__tests__', '__stories__', 'generated'].includes(entry.name) ? [] : collectTsxFiles(fullPath);
    }
    if (!entry.isFile() || !entry.name.endsWith('.tsx')) return [];
    if (/\.(?:test|spec|stories|generated)\.tsx$/.test(entry.name)) return [];
    return [fullPath];
  });
}

function collectText(node: ts.Node): string[] {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node)) {
    return [node.text];
  }
  if (ts.isTemplateExpression(node)) {
    return [node.head.text, ...node.templateSpans.map((span) => span.literal.text)];
  }
  return [];
}

describe('hardcoded UI strings', () => {
  it('keeps visible Chinese copy out of production TSX', () => {
    const failures: string[] = [];
    for (const filename of collectTsxFiles(sourceRoot)) {
        const relative = path.relative(sourceRoot, filename);
        const sourceText = fs.readFileSync(filename, 'utf8');
        const source = ts.createSourceFile(filename, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
        const visit = (node: ts.Node) => {
          for (const text of collectText(node)) {
            if (han.test(text) && !exactAllowedStrings[relative]?.[text]) {
              const { line } = source.getLineAndCharacterOfPosition(node.getStart());
              failures.push(`${relative}:${line + 1} ${JSON.stringify(text.trim())}`);
            }
          }
          ts.forEachChild(node, visit);
        };
        visit(source);
    }
    expect(failures).toEqual([]);
  });
});
