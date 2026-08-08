import { describe, expect, test } from 'vitest';
import {
  isObviouslyInvalidStockQuery,
  looksLikeStockCode,
  validateStockCode,
} from '../validation';

describe('stock code validation', () => {
  test.each([
    ['7203.T', '7203.T'],
    ['6758.t', '6758.T'],
    ['005930.KS', '005930.KS'],
    ['035900.kq', '035900.KQ'],
  ])('accepts JP/KR Yahoo suffix code %s', (input, normalized) => {
    expect(looksLikeStockCode(input)).toBe(true);
    expect(validateStockCode(input)).toEqual({
      valid: true,
      normalized,
    });
    expect(isObviouslyInvalidStockQuery(input)).toBe(false);
  });

  test.each(['005930.K', '035900.KRX'])(
    'does not treat ambiguous JP/KR-like query %s as a valid suffix code',
    (input) => {
      const result = validateStockCode(input);
      expect(result.valid).toBe(false);
    }
  );

  test('bare 4-digit 7203 is a valid HK code, not a JP suffix code', () => {
    expect(looksLikeStockCode('7203')).toBe(true);
    expect(validateStockCode('7203')).toEqual({
      valid: true,
      normalized: 'HK07203',
    });
  });

  test.each([
    ['0001', 'HK00001'],
    ['0941', 'HK00941'],
    ['1810', 'HK01810'],
  ])('accepts bare 4-digit HK code %s and rewrites to %s', (input, canonical) => {
    expect(looksLikeStockCode(input)).toBe(true);
    expect(validateStockCode(input)).toEqual({
      valid: true,
      normalized: canonical,
    });
    expect(isObviouslyInvalidStockQuery(input)).toBe(false);
  });
});
