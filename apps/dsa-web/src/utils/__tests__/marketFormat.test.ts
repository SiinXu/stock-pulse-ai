// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  CHANGE_COLOR_CSS_VAR,
  MARKET_CURRENCY,
  MARKET_DISPLAY_CODE,
  MARKET_IANA_TIMEZONE,
  MARKET_PRICE_FRACTION_DIGITS,
  TRADING_CALENDAR_DEPENDENCY,
  changeColorCssVar,
  changeSemantics,
  defaultChangeColorPreference,
  formatMarketBadge,
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

const MARKETS: MarketId[] = ['cn', 'hk', 'us', 'crypto'];
const EQUITY_MARKETS: MarketId[] = ['cn', 'hk', 'us'];
const PREFS: ChangeColorPreference[] = ['red_up', 'green_up'];
const DIRECTION_CASES: Array<{ value: number; direction: 'up' | 'down' | 'flat' }> = [
  { value: 1.25, direction: 'up' },
  { value: -0.5, direction: 'down' },
  { value: 0, direction: 'flat' },
];

describe('marketFormat contract', () => {
  describe('currency and precision snapshots', () => {
    it('maps each market to the documented currency and fraction digits', () => {
      expect(MARKET_CURRENCY).toEqual({ cn: 'CNY', hk: 'HKD', us: 'USD', crypto: 'USD' });
      expect(MARKET_PRICE_FRACTION_DIGITS).toEqual({ cn: 2, hk: 3, us: 2, crypto: 2 });
      expect(MARKET_IANA_TIMEZONE).toEqual({
        cn: 'Asia/Shanghai',
        hk: 'Asia/Hong_Kong',
        us: 'America/New_York',
        crypto: 'UTC',
      });
      expect(MARKET_DISPLAY_CODE).toEqual({ cn: 'CN', hk: 'HK', us: 'US', crypto: 'CRYPTO' });
    });

    it('formats prices with currency code, fixed precision, and thousands separators', () => {
      // en locale keeps grouping stable across CI hosts.
      expect(formatPrice(1680.5, 'cn', 'en')).toBe('CNY 1,680.50');
      expect(formatPrice(321.12345, 'hk', 'en')).toBe('HKD 321.123');
      expect(formatPrice(189.1, 'us', 'en')).toBe('USD 189.10');
      expect(formatPrice(1_234_567.8, 'us', 'en')).toBe('USD 1,234,567.80');
      expect(formatPrice(67_890.12, 'crypto', 'en')).toBe('USD 67,890.12');
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
      expect(defaultChangeColorPreference('crypto')).toBe('green_up');

      expect(changeSemantics(1, 'cn').colorPreference).toBe('red_up');
      expect(changeSemantics(1, 'us').colorPreference).toBe('green_up');
      expect(changeSemantics(1, 'crypto').colorPreference).toBe('green_up');
      expect(changeSemantics(1, 'cn').color).toBe('red');
      expect(changeSemantics(1, 'us').color).toBe('green');
      expect(changeSemantics(1, 'crypto').color).toBe('green');
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

      const crypto = formatMarketTime(INSTANT, 'crypto', 'en');
      expect(crypto!.timeZone).toBe('UTC');
      expect(crypto!.timeZoneLabel).toMatch(/UTC|GMT/i);
      expect(crypto!.text).toMatch(/13/);
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

  describe('trading calendar contract', () => {
    it('documents equity backend dependency and crypto always-open', () => {
      expect(TRADING_CALENDAR_DEPENDENCY.status).toBe('partial');
      expect(TRADING_CALENDAR_DEPENDENCY.backendModule).toBe('src/core/trading_calendar.py');
      expect(TRADING_CALENDAR_DEPENDENCY.exchangeCalendars).toEqual({
        cn: 'XSHG',
        hk: 'XHKG',
        us: 'XNYS',
      });
      expect(TRADING_CALENDAR_DEPENDENCY.alwaysOpenMarkets).toEqual(['crypto']);
      for (const market of EQUITY_MARKETS) {
        expect(isTradingDay(market, '2026-03-19')).toBeNull();
      }
      expect(isTradingDay('crypto', '2026-03-19')).toBe(true);
      expect(isTradingDay('crypto', '2026-07-04')).toBe(true);
      expect(isTradingDay('crypto', '')).toBeNull();
    });
  });

  describe('resolveMarketIdFromStockCode', () => {
    it('resolves cn / hk / us / crypto codes used by quote surfaces', () => {
      expect(resolveMarketIdFromStockCode('600519')).toBe('cn');
      expect(resolveMarketIdFromStockCode('SH600519')).toBe('cn');
      expect(resolveMarketIdFromStockCode('000001.SZ')).toBe('cn');
      expect(resolveMarketIdFromStockCode('HK00700')).toBe('hk');
      expect(resolveMarketIdFromStockCode('00700.HK')).toBe('hk');
      expect(resolveMarketIdFromStockCode('00700')).toBe('hk');
      expect(resolveMarketIdFromStockCode('AAPL')).toBe('us');
      expect(resolveMarketIdFromStockCode('BRK.B')).toBe('us');
      expect(resolveMarketIdFromStockCode('crypto:BTC')).toBe('crypto');
      expect(resolveMarketIdFromStockCode('CRYPTO:ETH')).toBe('crypto');
    });

    it('returns null when market is outside the contract or unknown', () => {
      expect(resolveMarketIdFromStockCode(null)).toBeNull();
      expect(resolveMarketIdFromStockCode('')).toBeNull();
      expect(resolveMarketIdFromStockCode('7203.T')).toBeNull();
      expect(resolveMarketIdFromStockCode('005930.KS')).toBeNull();
      expect(resolveMarketIdFromStockCode('2330.TW')).toBeNull();
      expect(resolveMarketIdFromStockCode('???')).toBeNull();
      expect(resolveMarketIdFromStockCode('BTC')).toBe('us');
      expect(resolveMarketIdFromStockCode('crypto:')).toBeNull();
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
      expect(CHANGE_COLOR_CSS_VAR.red).toBe('var(--price-red)');
      expect(CHANGE_COLOR_CSS_VAR.green).toBe('var(--price-green)');
      expect(changeColorCssVar('red')).toBe('var(--price-red)');
      expect(changeColorCssVar('green')).toBe('var(--price-green)');
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
          color === 'red' ? 'var(--price-red)' : 'var(--price-green)',
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
      expect(formatSignedChangePercent(Number.POSITIVE_INFINITY)).toBe('—');
      expect(formatSignedChangePercent(Number.NEGATIVE_INFINITY)).toBe('—');
    });

    it('formats signed amount with market precision', () => {
      expect(formatSignedChangeAmount(20, 'cn', 'en')).toBe('+20.00');
      expect(formatSignedChangeAmount(-1.2345, 'hk', 'en')).toBe('-1.235');
      expect(formatSignedChangeAmount(0.1, 'us', 'en')).toBe('+0.10');
      expect(formatSignedChangeAmount(1234.5, 'crypto', 'en')).toBe('+1,234.50');
      expect(formatSignedChangeAmount(undefined, 'cn')).toBe('—');
      for (const market of MARKETS) {
        expect(formatSignedChangeAmount(Number.POSITIVE_INFINITY, market, 'en')).toBe('—');
        expect(formatSignedChangeAmount(Number.NEGATIVE_INFINITY, market, 'en')).toBe('—');
      }
    });
  });

  describe('market badge labels', () => {
    it('maps known markets to stable display codes and never invents one', () => {
      expect(formatMarketBadge('cn')).toBe('CN');
      expect(formatMarketBadge('hk')).toBe('HK');
      expect(formatMarketBadge('us')).toBe('US');
      expect(formatMarketBadge('crypto')).toBe('CRYPTO');
      expect(formatMarketBadge(null)).toBeNull();
      expect(formatMarketBadge(undefined)).toBeNull();
    });
  });

  describe('cross-market boundary suites (#881 / #889)', () => {
    it('identity: CN / US / HK / crypto resolution boundaries', () => {
      expect(resolveMarketIdFromStockCode('600519')).toBe('cn');
      expect(resolveMarketIdFromStockCode('00700')).toBe('hk');
      expect(resolveMarketIdFromStockCode('0001')).toBeNull();
      expect(resolveMarketIdFromStockCode('AAPL')).toBe('us');
      expect(resolveMarketIdFromStockCode('crypto:BTC')).toBe('crypto');
      expect(resolveMarketIdFromStockCode('BTC')).toBe('us');
      expect(formatMarketBadge(resolveMarketIdFromStockCode('crypto:BTC'))).toBe('CRYPTO');
      expect(formatMarketBadge(resolveMarketIdFromStockCode('600519'))).toBe('CN');
    });

    it('currency: each market paints ISO code + grouping, never host-locale symbols', () => {
      expect(formatPrice(1680.5, 'cn', 'en')).toMatch(/^CNY /);
      expect(formatPrice(321.1, 'hk', 'en')).toMatch(/^HKD /);
      expect(formatPrice(189.1, 'us', 'en')).toMatch(/^USD /);
      expect(formatPrice(67_890.1, 'crypto', 'en')).toMatch(/^USD /);
      for (const market of MARKETS) {
        expect(formatPrice(1234.5, market, 'en')).not.toMatch(/[¥$€£]/);
      }
    });

    it('color: CN/HK red-up vs US/crypto green-up for the same positive change', () => {
      expect(changeSemantics(1.25, 'cn').color).toBe('red');
      expect(changeSemantics(1.25, 'hk').color).toBe('red');
      expect(changeSemantics(1.25, 'us').color).toBe('green');
      expect(changeSemantics(1.25, 'crypto').color).toBe('green');
      expect(changeSemantics(-1.25, 'cn').color).toBe('green');
      expect(changeSemantics(-1.25, 'us').color).toBe('red');
      expect(changeSemantics(-1.25, 'crypto').color).toBe('red');
      expect(changeSemantics(Number.POSITIVE_INFINITY, 'crypto').color).toBe('neutral');
    });

    it('time/calendar: market TZ labels and crypto always-open vs equity stub', () => {
      const instant = '2026-03-19T13:30:00.000Z';
      expect(formatMarketTime(instant, 'cn', 'en')!.timeZone).toBe('Asia/Shanghai');
      expect(formatMarketTime(instant, 'hk', 'en')!.timeZone).toBe('Asia/Hong_Kong');
      expect(formatMarketTime(instant, 'us', 'en')!.timeZone).toBe('America/New_York');
      expect(formatMarketTime(instant, 'crypto', 'en')!.timeZone).toBe('UTC');
      for (const market of MARKETS) {
        const parts = formatMarketTime(instant, market, 'en');
        expect(parts!.text).toContain(parts!.timeZoneLabel);
      }
      expect(isTradingDay('crypto', '2026-03-22')).toBe(true);
      expect(isTradingDay('cn', '2026-03-22')).toBeNull();
      expect(isTradingDay('us', '2026-03-22')).toBeNull();
    });
  });

});
