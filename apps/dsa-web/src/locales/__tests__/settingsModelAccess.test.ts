import { describe, expect, it } from 'vitest';
import {
  localizeModelAccessIssue,
  type ModelAccessIssueCode,
} from '../settingsModelAccess';

describe('model access issue codes', () => {
  it.each<[ModelAccessIssueCode, string]>([
    ['missing_api_key', 'API key is required'],
    ['missing_base_url', 'Base URL is required'],
    ['name_duplicate', 'Connection name already exists'],
    ['schema_unavailable', 'Connection Schema is incomplete or unavailable'],
  ])('localizes %s without comparing display text', (code, expected) => {
    expect(localizeModelAccessIssue(code, 'en')).toBe(expected);
  });
});
