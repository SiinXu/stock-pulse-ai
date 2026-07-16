import { describe, expect, it } from 'vitest';
import { decodeModelRef, encodeModelRef } from '../modelRef';

describe('ModelRef', () => {
  it('round-trips encoded Connection and runtime-route delimiters', () => {
    const value = encodeModelRef('work:primary', 'openai/gpt-4o:latest');

    expect(decodeModelRef(value)).toEqual({
      connectionId: 'work:primary',
      runtimeRoute: 'openai/gpt-4o:latest',
    });
  });

  it.each([
    'openai/gpt-4o',
    'modelref:v1:missing-route',
    'modelref:v1::openai%2Fgpt-4o',
    'modelref:v1:work:%E0%A4%A',
  ])('fails safely for non-decodable input %s', (value) => {
    expect(decodeModelRef(value)).toBeNull();
  });
});
