#!/usr/bin/env node

import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');
const SOURCE_ROOT = path.join(WEB_ROOT, 'src');
const TRANSLATIONS_DIRECTORY = path.join(SOURCE_ROOT, 'i18n', 'translations');
const ENGLISH_INVENTORY_PATH = path.join(TRANSLATIONS_DIRECTORY, 'en.ts');
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

const argumentsSet = new Set(process.argv.slice(2));
const supportedArguments = new Set(['--write']);
const unknownArguments = [...argumentsSet].filter((argument) => !supportedArguments.has(argument));

if (unknownArguments.length > 0) {
  throw new Error(`Unknown argument${unknownArguments.length === 1 ? '' : 's'}: ${unknownArguments.join(', ')}`);
}

const shouldWrite = argumentsSet.has('--write');
const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), 'stockpulse-i18n-'));
let bundleSequence = 0;

async function importBundle(source, plugins = []) {
  const outputPath = path.join(temporaryDirectory, `bundle-${bundleSequence}.mjs`);
  bundleSequence += 1;
  await build({
    stdin: {
      contents: source,
      loader: 'ts',
      resolveDir: SOURCE_ROOT,
      sourcefile: 'check-ui-i18n-resources.ts',
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

function valueAtPath(value, parts) {
  let current = value;
  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    current = current[part];
  }
  return current;
}

function flattenSourceRecords(records) {
  const entries = [];
  const namespaces = new Set();
  const keys = new Set();

  for (const record of records) {
    if (namespaces.has(record.namespace)) {
      throw new Error(`Duplicate UI translation namespace: ${record.namespace}`);
    }
    namespaces.add(record.namespace);

    function visit(value, parts = [], propertyName) {
      if (typeof value === 'string') {
        if (propertyName && NON_TRANSLATABLE_PROPERTIES.has(propertyName)) return;
        const key = [record.namespace, ...parts].join('.');
        if (keys.has(key)) throw new Error(`Duplicate UI translation key: ${key}`);
        keys.add(key);
        if (typeof valueAtPath(record.zh, parts) !== 'string') {
          throw new Error(`Missing Simplified Chinese source text: ${key}`);
        }
        entries.push([key, value]);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach((item, index) => visit(item, [...parts, String(index)]));
        return;
      }
      if (value && typeof value === 'object') {
        for (const [key, child] of Object.entries(value)) {
          visit(child, [...parts, key], key);
        }
      }
    }

    visit(record.en);
  }

  return entries.sort(([left], [right]) => left.localeCompare(right, 'en'));
}

function renderRecord(entries) {
  return entries
    .map(([key, value]) => `  ${JSON.stringify(key)}: ${JSON.stringify(value)},`)
    .join('\n');
}

function renderEnglishInventory(entries) {
  const keys = entries.map(([key]) => key);
  return `// Generated stable-key inventory for complete UI locale bundles.\nexport const UI_TRANSLATION_KEYS = ${JSON.stringify(keys, null, 2)} as const;\n\nexport type UiTranslationKey = (typeof UI_TRANSLATION_KEYS)[number];\n\nexport const SOURCE_UI_TRANSLATIONS: Record<UiTranslationKey, string> = {\n${renderRecord(entries)}\n};\n`;
}

function placeholders(value) {
  return Array.from(value.matchAll(/\{([A-Za-z0-9_]+)\}/g), (match) => match[1]).sort();
}

function formatDifferences(expected, actual) {
  const expectedSet = new Set(expected);
  const actualSet = new Set(actual);
  const missing = expected.filter((key) => !actualSet.has(key));
  const stale = actual.filter((key) => !expectedSet.has(key));
  const details = [];
  if (missing.length > 0) details.push(`missing: ${missing.slice(0, 10).join(', ')}${missing.length > 10 ? ', ...' : ''}`);
  if (stale.length > 0) details.push(`stale: ${stale.slice(0, 10).join(', ')}${stale.length > 10 ? ', ...' : ''}`);
  return details.join('; ');
}

function assertSameKeys(label, expected, actual) {
  const sortedExpected = [...expected].sort((left, right) => left.localeCompare(right, 'en'));
  const sortedActual = [...actual].sort((left, right) => left.localeCompare(right, 'en'));
  if (new Set(actual).size !== actual.length) {
    throw new Error(`${label} contains duplicate keys`);
  }
  if (JSON.stringify(sortedExpected) !== JSON.stringify(sortedActual)) {
    throw new Error(`${label} key mismatch (${formatDifferences(sortedExpected, sortedActual)})`);
  }
}

async function extractLanguageMetadata() {
  return importBundle("export { UI_LANGUAGES, ADDITIONAL_UI_LANGUAGES } from './i18n/uiLanguages';");
}

async function extractSourceEntries(uiLanguages) {
  const sourceFiles = await listSourceFiles(SOURCE_ROOT);
  const imports = sourceFiles
    .map((filename, index) => `import * as sourceModule${index} from ${JSON.stringify(filename)};`)
    .join('\n');
  const moduleReferences = sourceFiles.map((_, index) => `sourceModule${index}`).join(', ');
  const entry = `${imports}\nvoid [${moduleReferences}];\nexport const records = globalThis.__stockPulseUiLanguageRecords ?? [];\n`;
  const stub = `
const UI_LANGUAGES = ${JSON.stringify(uiLanguages)};
export function createUiLanguageRecord(namespace, base, overrides = {}) {
  const record = { ...base };
  for (const language of UI_LANGUAGES) {
    if (language !== 'zh' && language !== 'en') record[language] = overrides[language] ?? base.en;
  }
  globalThis.__stockPulseUiLanguageRecords ??= [];
  globalThis.__stockPulseUiLanguageRecords.push({ namespace, zh: base.zh, en: base.en });
  return record;
}
`;
  const module = await importBundle(entry, [{
    name: 'capture-ui-language-records',
    setup(esbuild) {
      esbuild.onResolve({ filter: /\/createUiLanguageRecord(?:\.ts)?$/ }, () => ({
        namespace: 'ui-language-record-stub',
        path: 'createUiLanguageRecord',
      }));
      esbuild.onLoad({ filter: /.*/, namespace: 'ui-language-record-stub' }, () => ({
        contents: stub,
        loader: 'js',
      }));
    },
  }]);
  return {
    entries: flattenSourceRecords(module.records),
    recordCount: module.records.length,
    sourceFileCount: sourceFiles.length,
  };
}

async function loadTranslationResources(additionalLanguages) {
  const imports = [
    `import { UI_TRANSLATION_KEYS, SOURCE_UI_TRANSLATIONS } from ${JSON.stringify(ENGLISH_INVENTORY_PATH)};`,
    ...additionalLanguages.map((language, index) => (
      `import { translations as locale${index} } from ${JSON.stringify(path.join(TRANSLATIONS_DIRECTORY, `${language}.ts`))};`
    )),
  ].join('\n');
  const translations = additionalLanguages
    .map((language, index) => `${JSON.stringify(language)}: locale${index}`)
    .join(', ');
  return importBundle(`${imports}\nexport { UI_TRANSLATION_KEYS, SOURCE_UI_TRANSLATIONS };\nexport const translations = { ${translations} };\n`);
}

async function validateLocaleFilenames(additionalLanguages) {
  const actual = (await readdir(TRANSLATIONS_DIRECTORY))
    .filter((filename) => filename.endsWith('.ts') && filename !== 'en.ts' && filename !== 'index.ts')
    .map((filename) => filename.slice(0, -3));
  assertSameKeys('Locale resource files', additionalLanguages, actual);
}

async function run() {
  const { UI_LANGUAGES: uiLanguages, ADDITIONAL_UI_LANGUAGES: additionalLanguages } = await extractLanguageMetadata();
  const { entries, recordCount, sourceFileCount } = await extractSourceEntries(uiLanguages);

  if (shouldWrite) {
    const nextInventory = renderEnglishInventory(entries);
    const currentInventory = await readFile(ENGLISH_INVENTORY_PATH, 'utf8');
    if (currentInventory !== nextInventory) {
      await writeFile(ENGLISH_INVENTORY_PATH, nextInventory);
      process.stdout.write('Updated src/i18n/translations/en.ts.\n');
    } else {
      process.stdout.write('src/i18n/translations/en.ts is already current.\n');
    }
  }

  await validateLocaleFilenames(additionalLanguages);
  const resources = await loadTranslationResources(additionalLanguages);
  const expectedKeys = entries.map(([key]) => key);
  assertSameKeys('English inventory', expectedKeys, resources.UI_TRANSLATION_KEYS);
  assertSameKeys('English source map', expectedKeys, Object.keys(resources.SOURCE_UI_TRANSLATIONS));

  for (const [key, source] of entries) {
    if (resources.SOURCE_UI_TRANSLATIONS[key] !== source) {
      throw new Error(`Stale English source text: ${key}`);
    }
  }

  for (const language of additionalLanguages) {
    const translations = resources.translations[language];
    assertSameKeys(`${language} resource`, expectedKeys, Object.keys(translations));
    for (const [key, source] of entries) {
      const translated = translations[key];
      if (typeof translated !== 'string' || translated.trim() === '') {
        throw new Error(`Empty ${language} translation: ${key}`);
      }
      if (JSON.stringify(placeholders(translated)) !== JSON.stringify(placeholders(source))) {
        throw new Error(`${language} placeholder mismatch: ${key}`);
      }
    }
  }

  process.stdout.write(
    `UI i18n resources are current: ${recordCount} records from ${sourceFileCount} source files, `
      + `${expectedKeys.length} stable keys, ${additionalLanguages.length} locale bundles.\n`,
  );
}

try {
  await run();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`UI i18n resource check failed: ${message}\n`);
  process.stderr.write('Run `npm run i18n:resources -- --write` after changing source copy, then update every affected locale.\n');
  process.exitCode = 1;
} finally {
  await rm(temporaryDirectory, { force: true, recursive: true });
}
