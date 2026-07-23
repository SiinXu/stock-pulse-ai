// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import * as settingsPageModule from '../../../pages/SettingsPage';
import * as llmChannelEditorModule from '../LLMChannelEditor';
import * as settingsHelpModule from '../../../locales/settingsHelp';
import * as firstRunSetupCardModule from '../FirstRunSetupCard';
import * as schedulerSettingsCardModule from '../SchedulerSettingsCard';
import * as settingsConfigItemsModule from '../settingsConfigItems';
import * as connectionUpdateContractModule from '../settingsConnectionUpdateContract';
import * as llmChannelEditorModelModule from '../llmChannelEditorModel';

const SOURCE_EXPORT_SURFACES = {
  'src/pages/SettingsPage.tsx': ['default'],
  'src/components/settings/LLMChannelEditor.tsx': [
    'type:ModelReferenceReplacement',
    'type:TaskModelReference',
    'value:LLMChannelEditor',
  ],
  'src/components/settings/llmChannelEditorModel.ts': [
    'type:ChannelConfig',
    'type:ChannelDiscoveryState',
    'type:ChannelTestState',
    'type:LLMChannelEditorProps',
    'type:ModelReferenceReplacement',
    'type:TaskModelReference',
    'value:CONNECTION_FIELD_BY_DRAFT_KEY',
    'value:CONNECTION_SCHEMA_UNAVAILABLE_ISSUE',
    'value:CONNECTION_SCHEMA_UNKNOWN_CONDITION_ISSUE',
    'value:applyChannelDraftItems',
    'value:areModelsEquivalent',
    'value:buildChannelContractValues',
    'value:buildChannelDraftItems',
    'value:buildItemSourceByKey',
    'value:buildProtocolOptions',
    'value:canonicalizeHermesRouteModel',
    'value:channelAllowsEmptyApiKey',
    'value:channelConnectionNameCanWrite',
    'value:channelFieldCanWrite',
    'value:channelIdentityCanWrite',
    'value:channelSchemaAllowsKnownOperations',
    'value:channelsAreEqual',
    'value:collectChannelRouteSet',
    'value:countChannelsForProvider',
    'value:describeProviderOption',
    'value:evaluateChannelSchemaAuthority',
    'value:findCatalogProvider',
    'value:formatProtocolLabel',
    'value:getChannelCompletenessIssues',
    'value:getChannelDisplayNameIssues',
    'value:getChannelNameIssues',
    'value:getChannelSaveIssues',
    'value:hasRuntimeOnlyMaskedHermesSecret',
    'value:isHermesChannel',
    'value:modelIdentityForConnection',
    'value:normalizeModelForRuntime',
    'value:normalizeProtocol',
    'value:normalizeTaskReferenceRoute',
    'value:parseChannelsFromItems',
    'value:parseRuntimeConfigFromItems',
    'value:preservesUnavailableProviderSnapshot',
    'value:resolveChannelRouteModels',
    'value:runChannelConnectionTest',
    'value:runChannelModelDiscovery',
    'value:shouldUseSavedHermesSecret',
    'value:splitModels',
    'value:toggleModelSelection',
  ],
  'src/locales/settingsHelp.ts': [
    'type:SettingsHelpContent',
    'value:getSettingsHelpContent',
  ],
  'src/components/settings/FirstRunSetupCard.tsx': ['default'],
  'src/components/settings/SchedulerSettingsCard.tsx': ['default'],
  'src/components/settings/settingsConfigItems.ts': ['value:getConfigItem'],
  'src/components/settings/settingsConnectionUpdateContract.ts': [
    'value:connectionItemsRespectSchema',
  ],
} as const;

function runtimeExportNames(module: Record<string, unknown>): string[] {
  return Object.keys(module).sort();
}

function sourceExportSurface(filename: string): string[] {
  const source = fs.readFileSync(filename, 'utf8');
  const sourceFile = ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    true,
    filename.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const exports: string[] = [];

  for (const statement of sourceFile.statements) {
    if (ts.isExportAssignment(statement)) {
      exports.push(statement.isExportEquals ? 'value:export=' : 'default');
      continue;
    }

    if (ts.isExportDeclaration(statement)) {
      const moduleSpecifier = statement.moduleSpecifier?.getText(sourceFile) ?? '';
      if (!statement.exportClause) {
        exports.push(`${statement.isTypeOnly ? 'type' : 'value'}:*:${moduleSpecifier}`);
        continue;
      }
      if (ts.isNamedExports(statement.exportClause)) {
        for (const element of statement.exportClause.elements) {
          const kind = statement.isTypeOnly || element.isTypeOnly ? 'type' : 'value';
          exports.push(`${kind}:${element.name.text}`);
        }
      }
      continue;
    }

    const modifiers = ts.canHaveModifiers(statement)
      ? ts.getModifiers(statement)
      : undefined;
    if (!modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword)) {
      continue;
    }
    if (modifiers.some((modifier) => modifier.kind === ts.SyntaxKind.DefaultKeyword)) {
      exports.push('default');
      continue;
    }

    const kind = ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement)
      ? 'type'
      : 'value';
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        if (ts.isIdentifier(declaration.name)) {
          exports.push(`${kind}:${declaration.name.text}`);
        }
      }
    } else if (
      (ts.isFunctionDeclaration(statement)
        || ts.isClassDeclaration(statement)
        || ts.isInterfaceDeclaration(statement)
        || ts.isTypeAliasDeclaration(statement)
        || ts.isEnumDeclaration(statement))
      && statement.name
    ) {
      exports.push(`${kind}:${statement.name.text}`);
    }
  }

  return exports.sort();
}

describe('Settings module surfaces', () => {
  it('keeps the established runtime exports stable across structural splits', () => {
    expect(runtimeExportNames(settingsPageModule)).toEqual(['default']);
    expect(runtimeExportNames(llmChannelEditorModule)).toEqual(['LLMChannelEditor']);
    expect(runtimeExportNames(settingsHelpModule)).toEqual(['getSettingsHelpContent']);
    expect(runtimeExportNames(firstRunSetupCardModule)).toEqual(['default']);
    expect(runtimeExportNames(schedulerSettingsCardModule)).toEqual(['default']);
    expect(runtimeExportNames(settingsConfigItemsModule)).toEqual(['getConfigItem']);
    expect(runtimeExportNames(connectionUpdateContractModule)).toEqual(['connectionItemsRespectSchema']);
    expect(runtimeExportNames(llmChannelEditorModelModule)).toEqual(
      SOURCE_EXPORT_SURFACES['src/components/settings/llmChannelEditorModel.ts']
        .filter((entry) => entry.startsWith('value:'))
        .map((entry) => entry.slice('value:'.length)),
    );
  });

  it('freezes default, type, and value exports for every split Settings module', () => {
    for (const [filename, expected] of Object.entries(SOURCE_EXPORT_SURFACES)) {
      expect(sourceExportSurface(filename), filename).toEqual(expected);
    }
  });
});
