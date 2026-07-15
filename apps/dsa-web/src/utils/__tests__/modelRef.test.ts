import { describe, expect, it } from 'vitest';
import { decodeModelRef, encodeModelRef, isVersionedModelRef } from '../modelRef';

describe('ModelRef', () => {
  it('matches the backend versioned encoding for connection and runtime route', () => {
    const value = encodeModelRef('openai_work', 'openai/gpt-4o:latest');

    expect(value).toBe('modelref:v1:openai_work:openai%2Fgpt-4o%3Alatest');
    expect(decodeModelRef(value)).toEqual({
      connectionId: 'openai_work',
      runtimeRoute: 'openai/gpt-4o:latest',
    });
  });

  it('keeps legacy routes distinct from malformed versioned values', () => {
    expect(decodeModelRef('openai/gpt-4o')).toBeNull();
    expect(isVersionedModelRef('openai/gpt-4o')).toBe(false);
    expect(decodeModelRef('modelref:v1:missing-route')).toBeNull();
    expect(isVersionedModelRef('modelref:v1:missing-route')).toBe(true);
  });
});
