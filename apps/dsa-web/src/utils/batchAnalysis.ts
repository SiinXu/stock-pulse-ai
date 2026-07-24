// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { DuplicateTaskError } from '../api/analysis';
import type { ParsedApiError } from '../api/error';
import type { AnalyzeAsyncResponse } from '../types/analysis';
import { normalizeStockCode } from './stockCode';

const BATCH_ANALYSIS_CHUNK_SIZE = 50;

export type BatchAnalysisSubmissionResult = {
  codes: string[];
  accepted: number;
  duplicates: number;
  confirmed: number;
  unconfirmed: number;
  submissionError: ParsedApiError | null;
  reconciliationError: ParsedApiError | null;
};

type SubmitBatchAnalysisOptions = {
  codes: readonly string[];
  submitChunk: (codes: string[]) => Promise<AnalyzeAsyncResponse>;
  reconcile: () => Promise<unknown>;
  parseError: (error: unknown) => ParsedApiError;
  incompleteResponseMessage: (confirmed: number, requested: number) => string;
};

export function normalizeBatchAnalysisCodes(codes: readonly string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const code of codes) {
    const normalized = code.trim().toUpperCase();
    const key = normalizeStockCode(normalized).toUpperCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    unique.push(normalized);
  }
  return unique;
}

function chunkStockCodes(codes: readonly string[]): string[][] {
  const chunks: string[][] = [];
  for (let index = 0; index < codes.length; index += BATCH_ANALYSIS_CHUNK_SIZE) {
    chunks.push(codes.slice(index, index + BATCH_ANALYSIS_CHUNK_SIZE));
  }
  return chunks;
}

function countConfirmed(result: AnalyzeAsyncResponse): { accepted: number; duplicates: number } {
  if ('accepted' in result) {
    return {
      accepted: result.accepted.length,
      duplicates: result.duplicates.length,
    };
  }
  return { accepted: 1, duplicates: 0 };
}

export async function submitBatchAnalysis({
  codes: sourceCodes,
  submitChunk,
  reconcile,
  parseError,
  incompleteResponseMessage,
}: SubmitBatchAnalysisOptions): Promise<BatchAnalysisSubmissionResult> {
  const codes = normalizeBatchAnalysisCodes(sourceCodes);
  let accepted = 0;
  let duplicates = 0;
  let confirmed = 0;
  let submissionError: ParsedApiError | null = null;

  for (const chunk of chunkStockCodes(codes)) {
    try {
      const counts = countConfirmed(await submitChunk(chunk));
      accepted += counts.accepted;
      duplicates += counts.duplicates;
      const confirmedInChunk = counts.accepted + counts.duplicates;
      confirmed += Math.min(confirmedInChunk, chunk.length);
      if (confirmedInChunk !== chunk.length) {
        submissionError = parseError(new Error(
          incompleteResponseMessage(confirmedInChunk, chunk.length),
        ));
        break;
      }
    } catch (error) {
      if (error instanceof DuplicateTaskError && chunk.length === 1) {
        duplicates += 1;
        confirmed += 1;
        continue;
      }
      submissionError = parseError(error);
      break;
    }
  }

  let reconciliationError: ParsedApiError | null = null;
  try {
    await reconcile();
  } catch (error) {
    reconciliationError = parseError(error);
  }

  return {
    codes,
    accepted,
    duplicates,
    confirmed,
    unconfirmed: Math.max(0, codes.length - confirmed),
    submissionError,
    reconciliationError,
  };
}
