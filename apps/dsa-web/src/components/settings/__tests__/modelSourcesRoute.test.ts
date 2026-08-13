// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  MODEL_SOURCE_SETUP_QUERY_KEYS,
  MODEL_SOURCE_SETUP_VALUES,
  MODEL_SOURCE_STEPS,
  MODEL_SOURCE_TYPES,
  resolveModelSourceSetupRestore,
} from '../modelSourcesRoute';

function params(entries: Record<string, string>) {
  return new URLSearchParams(entries);
}

describe('resolveModelSourceSetupRestore', () => {
  it('returns none when setup is inactive', () => {
    expect(resolveModelSourceSetupRestore(params({}))).toEqual({ kind: 'none' });
  });

  it('restores the type picker for setup without a source type', () => {
    expect(resolveModelSourceSetupRestore(params({
      [MODEL_SOURCE_SETUP_QUERY_KEYS.setup]: MODEL_SOURCE_SETUP_VALUES.active,
      [MODEL_SOURCE_SETUP_QUERY_KEYS.step]: MODEL_SOURCE_STEPS.type,
    }))).toEqual({ kind: 'type_picker' });
  });

  it('restores cloud add for cloud source without a connection', () => {
    expect(resolveModelSourceSetupRestore(params({
      [MODEL_SOURCE_SETUP_QUERY_KEYS.setup]: MODEL_SOURCE_SETUP_VALUES.active,
      [MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType]: MODEL_SOURCE_TYPES.cloud,
      [MODEL_SOURCE_SETUP_QUERY_KEYS.step]: MODEL_SOURCE_STEPS.provider,
    }))).toEqual({ kind: 'cloud_add' });
  });

  it('restores cloud edit when the connection is known', () => {
    expect(resolveModelSourceSetupRestore(params({
      [MODEL_SOURCE_SETUP_QUERY_KEYS.setup]: MODEL_SOURCE_SETUP_VALUES.active,
      [MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType]: MODEL_SOURCE_TYPES.cloud,
      [MODEL_SOURCE_SETUP_QUERY_KEYS.connection]: 'openai',
      [MODEL_SOURCE_SETUP_QUERY_KEYS.step]: MODEL_SOURCE_STEPS.models,
    }), ['openai'])).toEqual({
      kind: 'cloud_edit',
      connection: 'openai',
      focusModels: true,
    });
  });

  it('routes local server and CLI types to their management surfaces', () => {
    expect(resolveModelSourceSetupRestore(params({
      [MODEL_SOURCE_SETUP_QUERY_KEYS.setup]: MODEL_SOURCE_SETUP_VALUES.active,
      [MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType]: MODEL_SOURCE_TYPES.localServer,
    }))).toEqual({ kind: 'navigate_local_server' });
    expect(resolveModelSourceSetupRestore(params({
      [MODEL_SOURCE_SETUP_QUERY_KEYS.setup]: MODEL_SOURCE_SETUP_VALUES.active,
      [MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType]: MODEL_SOURCE_TYPES.localCli,
    }))).toEqual({ kind: 'navigate_local_cli' });
  });
});
