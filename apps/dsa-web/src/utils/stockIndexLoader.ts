/**
 * Stock Index Loader
 *
 * Responsible for loading and parsing stock index data
 */

import type { StockIndexData, StockIndexItem, StockIndexTuple } from '../types/stockIndex';
import { INDEX_FIELD } from './stockIndexFields';

export interface IndexLoadResult {
  /** Index data */
  data: StockIndexItem[];
  /** Successfully loaded */
  loaded: boolean;
  /** Error information */
  error?: Error;
  /** Whether fallback mode is used */
  fallback: boolean;
}

let inFlight: Promise<IndexLoadResult> | null = null;

/**
 * Drop the module-level load cache. Tests use this so each case starts cold.
 */
export function resetStockIndexCacheForTests(): void {
  inFlight = null;
}

/**
 * Load stock index
 *
 * Concurrent callers share one in-flight fetch and one JSON parse.
 * A successful result stays cached for the page lifetime. A failed
 * result is not cached so the next caller can retry.
 *
 * Fetch the static URL as-is. Do not append ?_t= (or any other cache-buster):
 * the browser revalidates via ETag / Last-Modified. A query-string bust
 * defeats HTTP caching and forced a full download on every hour bucket.
 *
 * @returns Index load result
 */
export function loadStockIndex(): Promise<IndexLoadResult> {
  return inFlight ??= (async () => {
    try {
      const response = await fetch('/stocks.index.json');

      if (!response.ok) {
        throw new Error(`Failed to load index: ${response.status} ${response.statusText}`);
      }

      const data: StockIndexData = await response.json();

      // Uncompress format (if array format)
      const items = isCompressedFormat(data)
        ? unpackTuples(data as StockIndexTuple[])
        : data as StockIndexItem[];

      return {
        data: items,
        loaded: true,
        fallback: false,
      };
    } catch (error) {
      inFlight = null;
      console.error('[StockIndexLoader] Failed to load stock index:', error);
      return {
        data: [],
        loaded: false,
        error: error as Error,
        fallback: true,  // Load failed, fallback to old mode
      };
    }
  })();
}

/**
 * Check if data is in compressed format
 */
function isCompressedFormat(data: StockIndexData): data is StockIndexTuple[] {
  if (!Array.isArray(data) || data.length === 0) return false;
  const firstItem = data[0];
  return Array.isArray(firstItem) && typeof firstItem[0] === 'string';
}

/**
 * Uncompress tuple format to object format
 */
function unpackTuples(tuples: StockIndexTuple[]): StockIndexItem[] {
  return tuples.map(tuple => ({
    canonicalCode: tuple[INDEX_FIELD.CANONICAL_CODE],
    displayCode: tuple[INDEX_FIELD.DISPLAY_CODE],
    nameZh: tuple[INDEX_FIELD.NAME_ZH],
    pinyinFull: tuple[INDEX_FIELD.PINYIN_FULL],
    pinyinAbbr: tuple[INDEX_FIELD.PINYIN_ABBR],
    aliases: tuple[INDEX_FIELD.ALIASES],
    market: tuple[INDEX_FIELD.MARKET],
    assetType: tuple[INDEX_FIELD.ASSET_TYPE],
    active: tuple[INDEX_FIELD.ACTIVE],
    popularity: tuple[INDEX_FIELD.POPULARITY],
  }));
}

/**
 * Compress object format to tuple format
 *
 * For reducing index file size
 */
export function compressIndex(items: StockIndexItem[]): StockIndexTuple[] {
  return items.map(item => [
    item.canonicalCode,
    item.displayCode,
    item.nameZh,
    item.pinyinFull,
    item.pinyinAbbr,
    item.aliases || [],
    item.market,
    item.assetType,
    item.active,
    item.popularity,
  ]);
}

/**
 * Find stock in index
 *
 * @param canonicalCode - Canonical code
 * @param index - Stock index
 * @returns Stock index item or null
 */
export function findStockInIndex(
  canonicalCode: string,
  index: StockIndexItem[]
): StockIndexItem | null {
  return index.find(item => item.canonicalCode === canonicalCode) || null;
}

/**
 * Get popular stocks list
 *
 * @param index - Stock index
 * @param limit - Number of results to return
 * @returns Popular stocks list
 */
export function getPopularStocks(
  index: StockIndexItem[],
  limit: number = 20
): StockIndexItem[] {
  return [...index]
    .filter(item => item.active)
    .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))
    .slice(0, limit);
}

/**
 * Group stocks by market
 *
 * @param index - Stock index
 * @returns Map of stocks grouped by market
 */
export function groupStocksByMarket(
  index: StockIndexItem[]
): Map<string, StockIndexItem[]> {
  const grouped = new Map<string, StockIndexItem[]>();

  for (const item of index) {
    if (!item.active) continue;

    const market = item.market;
    if (!grouped.has(market)) {
      grouped.set(market, []);
    }
    const group = grouped.get(market);
    if (group) {
      group.push(item);
    }
  }

  return grouped;
}
