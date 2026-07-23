import { describe, expect, it } from 'vitest';
import * as settingsPageModule from '../../../pages/SettingsPage';
import * as llmChannelEditorModule from '../LLMChannelEditor';
import * as settingsHelpModule from '../../../locales/settingsHelp';

function runtimeExportNames(module: Record<string, unknown>): string[] {
  return Object.keys(module).sort();
}

describe('Settings module surfaces', () => {
  it('keeps the established runtime exports stable across structural splits', () => {
    expect(runtimeExportNames(settingsPageModule)).toEqual(['default']);
    expect(runtimeExportNames(llmChannelEditorModule)).toEqual(['LLMChannelEditor']);
    expect(runtimeExportNames(settingsHelpModule)).toEqual(['getSettingsHelpContent']);
  });
});
