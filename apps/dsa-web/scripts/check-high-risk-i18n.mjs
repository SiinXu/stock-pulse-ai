#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import ts from 'typescript';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');
const REPOSITORY_ROOT = path.resolve(WEB_ROOT, '..', '..');
const SOURCE_ROOT = path.join(WEB_ROOT, 'src');
const TRANSLATIONS_DIRECTORY = path.join(SOURCE_ROOT, 'i18n', 'translations');
const AUDIT_PATH = path.join(SCRIPT_DIRECTORY, 'high-risk-i18n-audit.json');
const execFileAsync = promisify(execFile);
const NON_TRANSLATABLE_PROPERTIES = new Set([
  'value',
  'filename',
  'id',
  'key',
  'href',
  'url',
  'route',
  'path',
]);
const REQUIRED_CATEGORIES = new Set([
  'trading_action',
  'risk',
  'authentication',
  'credential',
  'error',
  'disclaimer',
]);
const SOURCE_STATUS = 'PRODUCT_SOURCE';
const PENDING_STATUS = 'PENDING_NATIVE_REVIEW';
const REVIEWED_STATUS = 'NATIVE_REVIEWED';

const argumentsSet = new Set(process.argv.slice(2));
const supportedArguments = new Set(['--print-snapshot', '--verify-baseline']);
const unknownArguments = [...argumentsSet].filter((argument) => !supportedArguments.has(argument));

if (unknownArguments.length > 0) {
  throw new Error(`Unknown argument${unknownArguments.length === 1 ? '' : 's'}: ${unknownArguments.join(', ')}`);
}

const shouldPrintSnapshot = argumentsSet.has('--print-snapshot');
const shouldVerifyBaseline = argumentsSet.has('--verify-baseline');
const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), 'stockpulse-high-risk-i18n-'));
let bundleSequence = 0;

function fail(message) {
  throw new Error(message);
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function canonicalDigest(value) {
  return sha256(JSON.stringify(value));
}

async function runGit(argumentsList) {
  const { stdout } = await execFileAsync('git', ['-C', REPOSITORY_ROOT, ...argumentsList], {
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
  });
  return stdout.trimEnd();
}

function assertNonEmptyString(value, label) {
  if (typeof value !== 'string' || !value.trim()) {
    fail(`${label} must be a non-empty string`);
  }
}

function assertStringArray(value, label) {
  if (!Array.isArray(value) || value.length === 0 || value.some((entry) => typeof entry !== 'string' || !entry)) {
    fail(`${label} must be a non-empty string array`);
  }
  if (new Set(value).size !== value.length) {
    fail(`${label} contains duplicates`);
  }
}

function assertPositiveIntegerArray(value, label) {
  if (!Array.isArray(value) || value.some((entry) => !Number.isSafeInteger(entry) || entry <= 0)) {
    fail(`${label} must be an array of positive integers`);
  }
  if (new Set(value).size !== value.length) {
    fail(`${label} contains duplicates`);
  }
}

async function importBundle(source, plugins = []) {
  const outputPath = path.join(temporaryDirectory, `bundle-${bundleSequence}.mjs`);
  bundleSequence += 1;
  await build({
    stdin: {
      contents: source,
      loader: 'ts',
      resolveDir: SOURCE_ROOT,
      sourcefile: 'check-high-risk-i18n.ts',
    },
    bundle: true,
    format: 'esm',
    logLevel: 'silent',
    outfile: outputPath,
    platform: 'node',
    plugins,
    target: 'node20',
  });
  return import(`${pathToFileURL(outputPath).href}?sequence=${bundleSequence}`);
}

async function listSourceFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === '__tests__' || entry.name === 'translations') continue;
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listSourceFiles(fullPath));
      continue;
    }
    if (!entry.name.endsWith('.ts') && !entry.name.endsWith('.tsx')) continue;
    const source = await readFile(fullPath, 'utf8');
    if (source.includes('createUiLanguageRecord(') && !fullPath.endsWith('createUiLanguageRecord.ts')) {
      files.push(fullPath);
    }
  }
  return files.sort((left, right) => left.localeCompare(right, 'en'));
}

function flattenValue(target, namespace, value, parts = [], propertyName) {
  if (typeof value === 'string') {
    if (propertyName && NON_TRANSLATABLE_PROPERTIES.has(propertyName)) return;
    const key = [namespace, ...parts].join('.');
    if (target.has(key)) fail(`Duplicate source translation key: ${key}`);
    target.set(key, value);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => flattenValue(target, namespace, item, [...parts, String(index)]));
    return;
  }
  if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      flattenValue(target, namespace, child, [...parts, key], key);
    }
  }
}

async function extractSourceBundles(uiLanguages) {
  const sourceFiles = await listSourceFiles(SOURCE_ROOT);
  const imports = sourceFiles
    .map((filename, index) => `import * as sourceModule${index} from ${JSON.stringify(filename)};`)
    .join('\n');
  const references = sourceFiles.map((_, index) => `sourceModule${index}`).join(', ');
  const entry = `${imports}\nvoid [${references}];\nexport const records = globalThis.__stockPulseHighRiskRecords ?? [];\n`;
  const stub = `
const UI_LANGUAGES = ${JSON.stringify(uiLanguages)};
export function createUiLanguageRecord(namespace, base, overrides = {}) {
  const record = { ...base };
  for (const language of UI_LANGUAGES) {
    if (language !== 'zh' && language !== 'en') record[language] = overrides[language] ?? base.en;
  }
  globalThis.__stockPulseHighRiskRecords ??= [];
  globalThis.__stockPulseHighRiskRecords.push({ namespace, zh: base.zh, en: base.en });
  return record;
}
`;
  const module = await importBundle(entry, [{
    name: 'capture-high-risk-ui-records',
    setup(esbuild) {
      esbuild.onResolve({ filter: /\/createUiLanguageRecord(?:\.ts)?$/ }, () => ({
        namespace: 'high-risk-ui-language-record-stub',
        path: 'createUiLanguageRecord',
      }));
      esbuild.onLoad({ filter: /.*/, namespace: 'high-risk-ui-language-record-stub' }, () => ({
        contents: stub,
        loader: 'js',
      }));
    },
  }]);
  const bundles = { zh: new Map(), en: new Map() };
  for (const record of module.records) {
    flattenValue(bundles.zh, record.namespace, record.zh);
    flattenValue(bundles.en, record.namespace, record.en);
  }
  return bundles;
}

async function loadGeneratedBundles(additionalLanguages) {
  const englishPath = path.join(TRANSLATIONS_DIRECTORY, 'en.ts');
  const imports = [
    `import { UI_TRANSLATION_KEYS, SOURCE_UI_TRANSLATIONS } from ${JSON.stringify(englishPath)};`,
    ...additionalLanguages.map((language, index) => (
      `import { translations as locale${index} } from ${JSON.stringify(path.join(TRANSLATIONS_DIRECTORY, `${language}.ts`))};`
    )),
  ].join('\n');
  const translations = additionalLanguages
    .map((language, index) => `${JSON.stringify(language)}: locale${index}`)
    .join(', ');
  return importBundle(`${imports}\nexport { UI_TRANSLATION_KEYS, SOURCE_UI_TRANSLATIONS };\nexport const translations = { ${translations} };\n`);
}

function validateAuditMetadata(audit, uiLanguages, additionalLanguages) {
  if (audit.schemaVersion !== 1) fail('Audit schemaVersion must be 1');
  assertNonEmptyString(audit.auditBaseline?.repository, 'auditBaseline.repository');
  if (audit.auditBaseline.repository !== 'SiinXu/stock-pulse-ai') {
    fail('auditBaseline.repository must be SiinXu/stock-pulse-ai');
  }
  assertNonEmptyString(audit.auditBaseline?.ref, 'auditBaseline.ref');
  if (audit.auditBaseline.ref !== 'origin/main') {
    fail('auditBaseline.ref must be origin/main');
  }
  if (!/^[0-9a-f]{40}$/.test(audit.auditBaseline?.commit ?? '')) {
    fail('auditBaseline.commit must be a full Git commit SHA');
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(audit.auditBaseline?.auditedAt ?? '')) {
    fail('auditBaseline.auditedAt must use YYYY-MM-DD');
  }
  assertNonEmptyString(audit.auditBaseline?.scope, 'auditBaseline.scope');
  assertPositiveIntegerArray(
    audit.auditBaseline?.openPullRequestsExcluded,
    'auditBaseline.openPullRequestsExcluded',
  );
  if (JSON.stringify(audit).match(/\bAPPROVED\b/i)) {
    fail('Audit evidence must not use APPROVED without a real native-review contract');
  }

  const reviewLanguages = Object.keys(audit.languageReview ?? {}).sort();
  if (JSON.stringify(reviewLanguages) !== JSON.stringify([...uiLanguages].sort())) {
    fail('languageReview must cover every and only supported UI language');
  }
  for (const language of uiLanguages) {
    const review = audit.languageReview[language];
    if (!review || ![SOURCE_STATUS, PENDING_STATUS, REVIEWED_STATUS].includes(review.status)) {
      fail(`Invalid review status for ${language}`);
    }
    if ((language === 'zh' || language === 'en') && review.status !== SOURCE_STATUS) {
      fail(`${language} must be labeled PRODUCT_SOURCE, not translation approval`);
    }
    if (review.status === SOURCE_STATUS && (review.reviewer !== null || review.reviewedAt !== null)) {
      fail(`${language} is product-source provenance and cannot name a native reviewer or review date`);
    }
    if (additionalLanguages.includes(language) && review.status === SOURCE_STATUS) {
      fail(`${language} is a translated bundle and cannot be labeled PRODUCT_SOURCE`);
    }
    if (review.status === PENDING_STATUS && (review.reviewer !== null || review.reviewedAt !== null)) {
      fail(`${language} is pending native review and cannot name a reviewer or review date`);
    }
    if (review.status === REVIEWED_STATUS) {
      assertNonEmptyString(review.reviewer, `${language}.reviewer`);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(review.reviewedAt ?? '')) {
        fail(`${language}.reviewedAt must use YYYY-MM-DD`);
      }
    }
  }

  if (!Array.isArray(audit.sources) || audit.sources.length === 0) fail('sources must not be empty');
  const sourceIds = new Set();
  for (const source of audit.sources) {
    assertNonEmptyString(source.id, 'source.id');
    if (sourceIds.has(source.id)) fail(`Duplicate source id: ${source.id}`);
    sourceIds.add(source.id);
    assertNonEmptyString(source.authority, `${source.id}.authority`);
    assertNonEmptyString(source.scope, `${source.id}.scope`);
    if (source.url !== null) {
      assertNonEmptyString(source.url, `${source.id}.url`);
      if (!source.url.startsWith('https://')) fail(`${source.id}.url must use HTTPS`);
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(source.accessedAt ?? '')) {
      fail(`${source.id}.accessedAt must use YYYY-MM-DD`);
    }
  }
  return sourceIds;
}

function validateDecisionEvidence(audit) {
  if (!Number.isSafeInteger(audit.decisionEvidence?.count) || audit.decisionEvidence.count <= 0) {
    fail('decisionEvidence.count must be a positive integer');
  }
  if (!/^[0-9a-f]{64}$/.test(audit.decisionEvidence?.sha256 ?? '')) {
    fail('decisionEvidence.sha256 must be a SHA-256 digest');
  }
  if (audit.decisionEvidence.count !== audit.decisions?.length) {
    fail('decision evidence count differs from the recorded decisions');
  }
  if (audit.decisionEvidence.sha256 !== canonicalDigest(audit.decisions)) {
    fail('decision evidence changed; review the rationale and refresh its count/hash together');
  }
}

function selectorMatches(key, selector, label) {
  const selectorKinds = ['exact', 'prefix', 'pattern'].filter((kind) => selector[kind] !== undefined);
  if (selectorKinds.length !== 1) fail(`${label} must contain exactly one selector kind`);
  if (selector.exact !== undefined) {
    assertStringArray(selector.exact, `${label}.exact`);
    return selector.exact.includes(key);
  }
  if (selector.prefix !== undefined) {
    assertNonEmptyString(selector.prefix, `${label}.prefix`);
    return key.startsWith(selector.prefix);
  }
  assertNonEmptyString(selector.pattern, `${label}.pattern`);
  return new RegExp(selector.pattern, 'u').test(key);
}

function validateDecisions(audit, bundles, uiLanguages, sourceIds) {
  if (!Array.isArray(audit.decisions) || audit.decisions.length === 0) {
    fail('decisions must document the revised high-risk strings');
  }
  const decisionIds = new Set();
  const categoriesById = new Map(audit.categories.map((category) => [category.id, category]));
  for (const decision of audit.decisions) {
    assertNonEmptyString(decision.id, 'decision.id');
    if (decisionIds.has(decision.id)) fail(`Duplicate decision id: ${decision.id}`);
    decisionIds.add(decision.id);
    assertNonEmptyString(decision.key, `${decision.id}.key`);
    const category = categoriesById.get(decision.category);
    if (!category) fail(`${decision.id} has an unknown category`);
    if (!category.selectors.some((selector, index) => (
      selectorMatches(decision.key, selector, `${decision.category}.selectors[${index}]`)
    ))) {
      fail(`${decision.id} is not covered by its declared ${decision.category} category`);
    }
    assertNonEmptyString(decision.rationale, `${decision.id}.rationale`);
    assertStringArray(decision.sourceIds, `${decision.id}.sourceIds`);
    decision.sourceIds.forEach((sourceId) => {
      if (!sourceIds.has(sourceId)) fail(`${decision.id} references unknown source ${sourceId}`);
    });
    const recommendedLanguages = Object.keys(decision.recommended ?? {});
    if (recommendedLanguages.length === 0) fail(`${decision.id}.recommended must not be empty`);
    if (JSON.stringify(recommendedLanguages.sort()) !== JSON.stringify(Object.keys(decision.before ?? {}).sort())) {
      fail(`${decision.id}.before and recommended must cover the same languages`);
    }
    for (const language of recommendedLanguages) {
      if (!uiLanguages.includes(language)) fail(`${decision.id} uses unsupported language ${language}`);
      assertNonEmptyString(decision.before[language], `${decision.id}.before.${language}`);
      assertNonEmptyString(decision.recommended[language], `${decision.id}.recommended.${language}`);
      if (decision.before[language] === decision.recommended[language]) {
        fail(`${decision.id} records an unchanged value for ${language}`);
      }
      if (bundles[language][decision.key] !== decision.recommended[language]) {
        fail(`${decision.id} does not match the ${language} bundle at ${decision.key}`);
      }
    }
  }
}

function unwrapExpression(expression) {
  let current = expression;
  while (
    ts.isParenthesizedExpression(current)
    || ts.isAsExpression(current)
    || ts.isSatisfiesExpression(current)
  ) {
    current = current.expression;
  }
  return current;
}

function extractExportedStringRecord(source, sourcePath, exportName) {
  const sourceFile = ts.createSourceFile(
    sourcePath,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  let declaration;
  for (const statement of sourceFile.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    const isExported = ts.getModifiers(statement)?.some(
      (modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword,
    );
    if (!isExported) continue;
    declaration = statement.declarationList.declarations.find(
      (candidate) => ts.isIdentifier(candidate.name) && candidate.name.text === exportName,
    );
    if (declaration) break;
  }
  const initializer = declaration?.initializer ? unwrapExpression(declaration.initializer) : undefined;
  if (!initializer || !ts.isObjectLiteralExpression(initializer)) {
    fail(`${sourcePath} must export ${exportName} as an object literal`);
  }

  const record = {};
  for (const property of initializer.properties) {
    if (!ts.isPropertyAssignment(property)) {
      fail(`${sourcePath} ${exportName} must contain only property assignments`);
    }
    const propertyName = property.name;
    if (!ts.isStringLiteral(propertyName) && !ts.isIdentifier(propertyName)) {
      fail(`${sourcePath} ${exportName} contains an unsupported property name`);
    }
    const value = unwrapExpression(property.initializer);
    if (!ts.isStringLiteral(value) && !ts.isNoSubstitutionTemplateLiteral(value)) {
      fail(`${sourcePath} ${exportName}.${propertyName.text} must be a string literal`);
    }
    if (Object.hasOwn(record, propertyName.text)) {
      fail(`${sourcePath} ${exportName} contains duplicate key ${propertyName.text}`);
    }
    record[propertyName.text] = value.text;
  }
  return record;
}

async function loadBaselineRecord(commit, language) {
  const relativePath = `apps/dsa-web/src/i18n/translations/${language}.ts`;
  const source = await runGit(['show', `${commit}:${relativePath}`]);
  return extractExportedStringRecord(
    source,
    relativePath,
    language === 'en' ? 'SOURCE_UI_TRANSLATIONS' : 'translations',
  );
}

async function verifyDecisionBaseline(audit) {
  const mergeBase = await runGit(['merge-base', 'HEAD', audit.auditBaseline.ref]);
  if (mergeBase !== audit.auditBaseline.commit) {
    fail(
      `HEAD/${audit.auditBaseline.ref} merge-base ${mergeBase} differs from audit baseline ${audit.auditBaseline.commit}`,
    );
  }

  const decisionLanguages = [...new Set(audit.decisions.flatMap(
    (decision) => Object.keys(decision.before ?? {}),
  ))].sort();
  if (decisionLanguages.includes('zh')) {
    fail('Baseline verification cannot use generated bundles for zh product-source decisions');
  }
  const baselineRecords = Object.fromEntries(await Promise.all(decisionLanguages.map(async (language) => [
    language,
    await loadBaselineRecord(audit.auditBaseline.commit, language),
  ])));
  for (const decision of audit.decisions) {
    for (const [language, before] of Object.entries(decision.before)) {
      const baselineValue = baselineRecords[language]?.[decision.key];
      if (baselineValue !== before) {
        fail(
          `${decision.id}.before.${language} does not match ${audit.auditBaseline.commit}:${decision.key}; `
            + `expected ${JSON.stringify(baselineValue)}, recorded ${JSON.stringify(before)}`,
        );
      }
    }
  }
}

async function extractStringUnion(contract, label) {
  const contractPath = path.resolve(WEB_ROOT, contract.path);
  if (!contractPath.startsWith(`${WEB_ROOT}${path.sep}`)) fail(`${label}.path must stay within the Web workspace`);
  const source = await readFile(contractPath, 'utf8');
  const sourceFile = ts.createSourceFile(contractPath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  let declaration;
  sourceFile.forEachChild((node) => {
    if (ts.isTypeAliasDeclaration(node) && node.name.text === contract.alias) declaration = node;
  });
  if (!declaration || !ts.isUnionTypeNode(declaration.type)) {
    fail(`${label} must point to a string-union type alias`);
  }
  const values = declaration.type.types.map((node) => {
    if (!ts.isLiteralTypeNode(node) || !ts.isStringLiteral(node.literal)) {
      fail(`${label} must contain only string literals`);
    }
    return node.literal.text;
  });
  return values.sort();
}

async function validateContractBoundaries(audit, allKeys, bundles, uiLanguages) {
  if (!Array.isArray(audit.contractBoundaries) || audit.contractBoundaries.length === 0) {
    fail('contractBoundaries must not be empty');
  }
  const boundaryIds = new Set();
  for (const boundary of audit.contractBoundaries) {
    assertNonEmptyString(boundary.id, 'contractBoundary.id');
    if (boundaryIds.has(boundary.id)) fail(`Duplicate contract boundary: ${boundary.id}`);
    boundaryIds.add(boundary.id);
    assertNonEmptyString(boundary.contractSource, `${boundary.id}.contractSource`);
    assertStringArray(boundary.internalCodes, `${boundary.id}.internalCodes`);
    if (!boundary.codeToDisplayKeys || typeof boundary.codeToDisplayKeys !== 'object') {
      fail(`${boundary.id}.codeToDisplayKeys must be an object`);
    }
    const mappedCodes = Object.keys(boundary.codeToDisplayKeys).sort();
    if (JSON.stringify(mappedCodes) !== JSON.stringify([...boundary.internalCodes].sort())) {
      fail(`${boundary.id} must map every and only declared internal code`);
    }
    if (boundary.typeContract) {
      assertNonEmptyString(boundary.typeContract.path, `${boundary.id}.typeContract.path`);
      assertNonEmptyString(boundary.typeContract.alias, `${boundary.id}.typeContract.alias`);
      const sourceCodes = await extractStringUnion(boundary.typeContract, `${boundary.id}.typeContract`);
      if (JSON.stringify(sourceCodes) !== JSON.stringify([...boundary.internalCodes].sort())) {
        fail(`${boundary.id} internal codes differ from ${boundary.typeContract.alias}`);
      }
    }
    if (boundary.translationCodePattern) {
      assertNonEmptyString(boundary.translationCodePattern, `${boundary.id}.translationCodePattern`);
      const pattern = new RegExp(boundary.translationCodePattern, 'u');
      const sourceCodes = [...new Set(allKeys.flatMap((key) => {
        const match = key.match(pattern);
        return match?.[1] ? [match[1]] : [];
      }))].sort();
      if (JSON.stringify(sourceCodes) !== JSON.stringify([...boundary.internalCodes].sort())) {
        fail(`${boundary.id} internal codes differ from the localized display-key inventory`);
      }
    }
    for (const code of boundary.internalCodes) {
      const displayKeys = boundary.codeToDisplayKeys[code];
      assertStringArray(displayKeys, `${boundary.id}.${code}`);
      displayKeys.forEach((key) => {
        if (!allKeys.includes(key)) fail(`${boundary.id} display key is missing: ${key}`);
        if (key === code) fail(`${boundary.id} exposes internal code ${code} as its display key`);
        for (const language of uiLanguages) {
          if (bundles[language][key] === code) {
            fail(`${boundary.id} exposes internal code ${code} as ${language} display copy at ${key}`);
          }
        }
      });
    }
  }
}

function buildSnapshot(audit, bundles, uiLanguages, allKeys, sourceIds) {
  if (!Array.isArray(audit.categories) || audit.categories.length === 0) fail('categories must not be empty');
  const categoryIds = new Set();
  const snapshot = {};
  for (const category of audit.categories) {
    assertNonEmptyString(category.id, 'category.id');
    if (!REQUIRED_CATEGORIES.has(category.id)) fail(`Unknown high-risk category: ${category.id}`);
    if (categoryIds.has(category.id)) fail(`Duplicate high-risk category: ${category.id}`);
    categoryIds.add(category.id);
    assertNonEmptyString(category.semanticBoundary, `${category.id}.semanticBoundary`);
    assertStringArray(category.sourceIds, `${category.id}.sourceIds`);
    category.sourceIds.forEach((sourceId) => {
      if (!sourceIds.has(sourceId)) fail(`${category.id} references unknown source ${sourceId}`);
    });
    if (!Array.isArray(category.selectors) || category.selectors.length === 0) {
      fail(`${category.id}.selectors must not be empty`);
    }
    const keys = allKeys.filter((key) => category.selectors.some((selector, index) => (
      selectorMatches(key, selector, `${category.id}.selectors[${index}]`)
    ))).sort((left, right) => left.localeCompare(right, 'en'));
    if (keys.length === 0) fail(`${category.id} matched no translation keys`);
    const bundleSha256 = Object.fromEntries(uiLanguages.map((language) => [
      language,
      canonicalDigest(keys.map((key) => [key, bundles[language][key]])),
    ]));
    snapshot[category.id] = {
      keyCount: keys.length,
      keySetSha256: canonicalDigest(keys),
      bundleSha256,
    };
  }
  const missingCategories = [...REQUIRED_CATEGORIES].filter((category) => !categoryIds.has(category));
  if (missingCategories.length > 0) fail(`Missing high-risk categories: ${missingCategories.join(', ')}`);
  return snapshot;
}

function compareSnapshot(audit, actualSnapshot, uiLanguages) {
  for (const category of audit.categories) {
    const expected = category.snapshot;
    const actual = actualSnapshot[category.id];
    if (!expected || expected.keyCount !== actual.keyCount || expected.keySetSha256 !== actual.keySetSha256) {
      fail(`${category.id} audited key set changed; run with --print-snapshot and review the semantic scope`);
    }
    for (const language of uiLanguages) {
      if (expected.bundleSha256?.[language] !== actual.bundleSha256[language]) {
        fail(`${category.id} ${language} copy changed without a matching semantic audit update`);
      }
    }
  }
}

async function run() {
  const audit = JSON.parse(await readFile(AUDIT_PATH, 'utf8'));
  const languageModule = await importBundle("export { UI_LANGUAGES, ADDITIONAL_UI_LANGUAGES } from './i18n/uiLanguages';");
  const uiLanguages = [...languageModule.UI_LANGUAGES];
  const additionalLanguages = [...languageModule.ADDITIONAL_UI_LANGUAGES];
  const sourceIds = validateAuditMetadata(audit, uiLanguages, additionalLanguages);
  validateDecisionEvidence(audit);
  const sourceBundles = await extractSourceBundles(uiLanguages);
  const generated = await loadGeneratedBundles(additionalLanguages);
  const allKeys = [...generated.UI_TRANSLATION_KEYS];
  const bundles = {
    zh: Object.fromEntries(sourceBundles.zh),
    en: { ...generated.SOURCE_UI_TRANSLATIONS },
    ...generated.translations,
  };

  if (canonicalDigest([...sourceBundles.en].sort()) !== canonicalDigest(Object.entries(generated.SOURCE_UI_TRANSLATIONS).sort())) {
    fail('Captured English source copy differs from the generated English inventory');
  }
  for (const language of uiLanguages) {
    if (!bundles[language]) fail(`Missing loaded translation bundle: ${language}`);
    for (const key of allKeys) {
      if (typeof bundles[language][key] !== 'string') fail(`Missing ${language} translation: ${key}`);
    }
  }

  await validateContractBoundaries(audit, allKeys, bundles, uiLanguages);
  validateDecisions(audit, bundles, uiLanguages, sourceIds);
  if (shouldVerifyBaseline) {
    await verifyDecisionBaseline(audit);
    process.stdout.write(
      `High-risk i18n baseline verified: ${audit.decisions.length} decisions against ${audit.auditBaseline.commit}.\n`,
    );
  }
  const snapshot = buildSnapshot(audit, bundles, uiLanguages, allKeys, sourceIds);
  if (shouldPrintSnapshot) {
    process.stdout.write(`${JSON.stringify(snapshot, null, 2)}\n`);
    return;
  }
  compareSnapshot(audit, snapshot, uiLanguages);
  const distinctKeys = new Set();
  for (const category of audit.categories) {
    allKeys.filter((key) => category.selectors.some((selector, index) => (
      selectorMatches(key, selector, `${category.id}.selectors[${index}]`)
    ))).forEach((key) => distinctKeys.add(key));
  }
  const pendingCount = Object.values(audit.languageReview).filter((review) => review.status === PENDING_STATUS).length;
  process.stdout.write(
    `High-risk i18n audit passed: ${audit.categories.length} categories, ${distinctKeys.size} stable keys, `
      + `${uiLanguages.length} locales; ${pendingCount} locales remain ${PENDING_STATUS}.\n`,
  );
}

try {
  await run();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`High-risk i18n audit failed: ${message}\n`);
  process.exitCode = 1;
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}
