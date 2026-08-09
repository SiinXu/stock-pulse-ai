// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  CHANGE_COLOR_CSS_VAR,
  MARKET_CURRENCY,
  MARKET_IANA_TIMEZONE,
  MARKET_PRICE_FRACTION_DIGITS,
  TRADING_CALENDAR_DEPENDENCY,
  changeColorCssVar,
  changeSemantics,
  defaultChangeColorPreference,
  formatMarketTime,
  formatPrice,
  formatSignedChangeAmount,
  formatSignedChangePercent,
  isTradingDay,
  parseChangeColorPreference,
  resolveChangeColorPreference,
  resolveMarketIdFromStockCode,
  type ChangeColorPreference,
  type MarketId,
} from '../marketFormat';

const MARKETS: MarketId[] = ['cn', 'hk', 'us'];
const PREFS: ChangeColorPreference[] = ['red_up', 'green_up'];
const DIRECTION_CASES: Array<{ value: number; direction: 'up' | 'down' | 'flat' }> = [
  { value: 1.25, direction: 'up' },
  { value: -0.5, direction: 'down' },
  { value: 0, direction: 'flat' },
];

describe('marketFormat contract', () => {
  describe('currency and precision snapshots', () => {
    it('maps each market to the documented currency and fraction digits', () => {
      expect(MARKET_CURRENCY).toEqual({ cn: 'CNY', hk: 'HKD', us: 'USD' });
      expect(MARKET_PRICE_FRACTION_DIGITS).toEqual({ cn: 2, hk: 3, us: 2 });
      expect(MARKET_IANA_TIMEZONE).toEqual({
        cn: 'Asia/Shanghai',
        hk: 'Asia/Hong_Kong',
        us: 'America/New_York',
      });
    });

    it('formats prices with currency code, fixed precision, and thousands separators', () => {
      // en locale keeps grouping stable across CI hosts.
      expect(formatPrice(1680.5, 'cn', 'en')).toBe('CNY 1,680.50');
      expect(formatPrice(321.12345, 'hk', 'en')).toBe('HKD 321.123');
      expect(formatPrice(189.1, 'us', 'en')).toBe('USD 189.10');
      expect(formatPrice(1_234_567.8, 'us', 'en')).toBe('USD 1,234,567.80');
    });

    it('returns an em dash for missing, non-numeric, or non-finite prices', () => {
      expect(formatPrice(null, 'cn')).toBe('—');
      expect(formatPrice(undefined, 'hk')).toBe('—');
      expect(formatPrice(Number.NaN, 'us')).toBe('—');
      for (const market of MARKETS) {
        expect(formatPrice(Number.POSITIVE_INFINITY, market, 'en')).toBe('—');
        expect(formatPrice(Number.NEGATIVE_INFINITY, market, 'en')).toBe('—');
      }
    });
  });

  describe('changeSemantics matrix (market × direction × preference)', () => {
    it('uses market convention when userPref is absent', () => {
      expect(defaultChangeColorPreference('cn')).toBe('red_up');
      expect(defaultChangeColorPreference('hk')).toBe('red_up');
      expect(defaultChangeColorPreference('us')).toBe('green_up');

      expect(changeSemantics(1, 'cn').colorPreference).toBe('red_up');
      expect(changeSemantics(1, 'us').colorPreference).toBe('green_up');
      expect(changeSemantics(1, 'cn').color).toBe('red');
      expect(changeSemantics(1, 'us').color).toBe('green');
    });

    it('lets userPref override market convention', () => {
      expect(resolveChangeColorPreference('us', 'red_up')).toBe('red_up');
      expect(resolveChangeColorPreference('cn', 'green_up')).toBe('green_up');
      expect(changeSemantics(1, 'us', 'red_up')).toEqual({
        direction: 'up',
        colorPreference: 'red_up',
        color: 'red',
      });
      expect(changeSemantics(-1, 'cn', 'green_up')).toEqual({
        direction: 'down',
        colorPreference: 'green_up',
        color: 'red',
      });
    });

    it.each(
      MARKETS.flatMap((market) =>
        PREFS.flatMap((pref) =>
          DIRECTION_CASES.map(({ value, direction }) => ({ market, pref, value, direction })),
        ),
      ),
    )(
      'matrix $market / $direction / $pref',
      ({ market, pref, value, direction }) => {
        const result = changeSemantics(value, market, pref);
        expect(result.direction).toBe(direction);
        expect(result.colorPreference).toBe(pref);

        if (direction === 'flat') {
          expect(result.color).toBe('neutral');
          return;
        }

        const expectedColor =
          (direction === 'up' && pref === 'red_up')
          || (direction === 'down' && pref === 'green_up')
            ? 'red'
            : 'green';
        expect(result.color).toBe(expectedColor);
      },
    );

    it('treats null/undefined/NaN/±Infinity as flat + neutral', () => {
      for (const market of MARKETS) {
        for (const pref of PREFS) {
          for (const value of [
            null,
            undefined,
            Number.NaN,
            Number.POSITIVE_INFINITY,
            Number.NEGATIVE_INFINITY,
          ] as const) {
            expect(changeSemantics(value, market, pref)).toEqual({
              direction: 'flat',
              colorPreference: pref,
              color: 'neutral',
            });
          }
        }
      }
    });
  });

  describe('formatMarketTime', () => {
    // Fixed instant: 2026-03-19 13:30:00 UTC
    // CN/HK local: 2026-03-19 21:30:00 GMT+8
    // US Eastern (EDT in March): 2026-03-19 09:30:00 GMT-4
    const INSTANT = '2026-03-19T13:30:00.000Z';

    it('formats in the market timezone and appends an explicit label', () => {
      const cn = formatMarketTime(INSTANT, 'cn', 'en');
      expect(cn).not.toBeNull();
      expect(cn!.timeZone).toBe('Asia/Shanghai');
      expect(cn!.iso).toBe(INSTANT);
      expect(cn!.text).toContain(cn!.timeZoneLabel);
      expect(cn!.timeZoneLabel).toMatch(/GMT\+8|UTC\+8|CST/i);
      // Hour in Shanghai is 21
      expect(cn!.text).toMatch(/21/);

      const hk = formatMarketTime(INSTANT, 'hk', 'en');
      expect(hk!.timeZone).toBe('Asia/Hong_Kong');
      expect(hk!.timeZoneLabel).toMatch(/GMT\+8|UTC\+8|HKT/i);

      const us = formatMarketTime(INSTANT, 'us', 'en');
      expect(us!.timeZone).toBe('America/New_York');
      // March → EDT (GMT-4) or short name EST/EDT depending on runtime
      expect(us!.timeZoneLabel).toMatch(/GMT-4|UTC-4|EDT|EST/i);
      expect(us!.text).toMatch(/09/);
    });

    it('returns null for missing or invalid timestamps', () => {
      expect(formatMarketTime(null, 'cn')).toBeNull();
      expect(formatMarketTime(undefined, 'us')).toBeNull();
      expect(formatMarketTime('not-a-date', 'hk')).toBeNull();
      expect(formatMarketTime('', 'cn')).toBeNull();
      // Invalid Date.getTime() is always NaN (never ±Infinity); pin parseTimestamp isNaN.
      expect(formatMarketTime(Number.POSITIVE_INFINITY, 'us')).toBeNull();
    });
  });

  describe('trading calendar stub', () => {
    it('documents backend dependency and never invents a trading-day answer', () => {
      expect(TRADING_CALENDAR_DEPENDENCY.status).toBe('stub');
      expect(TRADING_CALENDAR_DEPENDENCY.backendModule).toBe('src/core/trading_calendar.py');
      expect(TRADING_CALENDAR_DEPENDENCY.exchangeCalendars).toEqual({
        cn: 'XSHG',
        hk: 'XHKG',
        us: 'XNYS',
      });
      expect(isTradingDay('cn', '2026-03-19')).toBeNull();
      expect(isTradingDay('us', '2026-07-04')).toBeNull();
    });
  });

  describe('resolveMarketIdFromStockCode', () => {
    it('resolves cn / hk / us codes used by quote surfaces', () => {
      expect(resolveMarketIdFromStockCode('600519')).toBe('cn');
      expect(resolveMarketIdFromStockCode('SH600519')).toBe('cn');
      expect(resolveMarketIdFromStockCode('000001.SZ')).toBe('cn');
      expect(resolveMarketIdFromStockCode('HK00700')).toBe('hk');
      expect(resolveMarketIdFromStockCode('00700.HK')).toBe('hk');
      expect(resolveMarketIdFromStockCode('00700')).toBe('hk');
      expect(resolveMarketIdFromStockCode('AAPL')).toBe('us');
      expect(resolveMarketIdFromStockCode('BRK.B')).toBe('us');
    });

    it('returns null when market is outside the cn/hk/us contract or unknown', () => {
      expect(resolveMarketIdFromStockCode(null)).toBeNull();
      expect(resolveMarketIdFromStockCode('')).toBeNull();
      expect(resolveMarketIdFromStockCode('7203.T')).toBeNull();
      expect(resolveMarketIdFromStockCode('005930.KS')).toBeNull();
      expect(resolveMarketIdFromStockCode('2330.TW')).toBeNull();
      expect(resolveMarketIdFromStockCode('???')).toBeNull();
    });
  });

  describe('parseChangeColorPreference + paint tokens', () => {
    it('parses Settings MARKET_REVIEW_COLOR_SCHEME values only', () => {
      expect(parseChangeColorPreference('red_up')).toBe('red_up');
      expect(parseChangeColorPreference('green_up')).toBe('green_up');
      expect(parseChangeColorPreference('RED-UP')).toBe('red_up');
      expect(parseChangeColorPreference('')).toBeNull();
      expect(parseChangeColorPreference('rainbow')).toBeNull();
    });

    it('maps paint tokens to design-token CSS vars (hue, not direction name)', () => {
      expect(CHANGE_COLOR_CSS_VAR.red).toBe('var(--home-price-up)');
      expect(CHANGE_COLOR_CSS_VAR.green).toBe('var(--home-price-down)');
      expect(changeColorCssVar('red')).toBe('var(--home-price-up)');
      expect(changeColorCssVar('green')).toBe('var(--home-price-down)');
      expect(changeColorCssVar('neutral')).toBeUndefined();
    });

    it.each(
      MARKETS.flatMap((market) =>
        PREFS.flatMap((pref) =>
          DIRECTION_CASES.filter((c) => c.direction !== 'flat').map(({ value, direction }) => ({
            market,
            pref,
            value,
            direction,
          })),
        ),
      ),
    )(
      'adoption matrix $market / $direction / $pref → paint CSS var',
      ({ market, pref, value }) => {
        const { color } = changeSemantics(value, market, pref);
        const css = changeColorCssVar(color);
        expect(css).toBe(
          color === 'red' ? 'var(--home-price-up)' : 'var(--home-price-down)',
        );
      },
    );
  });

  describe('signed change formatters', () => {
    it('formats percent with explicit sign', () => {
      expect(formatSignedChangePercent(1.25)).toBe('+1.25%');
      expect(formatSignedChangePercent(-0.5)).toBe('-0.50%');
      expect(formatSignedChangePercent(0)).toBe('0.00%');
      expect(formatSignedChangePercent(null)).toBe('—');
    });

    it('formats signed amount with market precision', () => {
      expect(formatSignedChangeAmount(20, 'cn', 'en')).toBe('+20.00');
      expect(formatSignedChangeAmount(-1.2345, 'hk', 'en')).toBe('-1.235');
      expect(formatSignedChangeAmount(0.1, 'us', 'en')).toBe('+0.10');
      expect(formatSignedChangeAmount(undefined, 'cn')).toBe('—');
    });
  });
});
