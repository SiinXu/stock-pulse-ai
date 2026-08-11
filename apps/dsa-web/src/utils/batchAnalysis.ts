// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { DuplicateTaskError } from '../api/analysis';
import type { ParsedApiError } from '../api/error';
import type { AnalyzeAsyncResponse } from '../types/analysis';
import { normalizeStockCode } from './stockCode';

const BATCH_ANALYSIS_CHUNK_SIZE = 50;

export type BatchAnalysisSubmissionResult = {
  codes: string[];
  acceptedCodes: string[];
  duplicateCodes: string[];
  unconfirmedCodes: string[];
  accepted: number;
  duplicates: number;
  confirmed: number;
  unconfirmed: number;
  stoppedOnIncompleteResponse: boolean;
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

function confirmedCodes(
  result: AnalyzeAsyncResponse,
  chunk: readonly string[],
): { acceptedCodes: string[]; duplicateCodes: string[] } {
  if ('accepted' in result) {
    return {
      acceptedCodes: result.accepted.map((item) => item.stockCode),
      duplicateCodes: result.duplicates.map((item) => item.stockCode),
    };
  }
  return {
    acceptedCodes: chunk.length === 1 ? [chunk[0]] : [],
    duplicateCodes: [],
  };
}

export async function submitBatchAnalysis({
  codes: sourceCodes,
  submitChunk,
  reconcile,
  parseError,
  incompleteResponseMessage,
}: SubmitBatchAnalysisOptions): Promise<BatchAnalysisSubmissionResult> {
  const codes = normalizeBatchAnalysisCodes(sourceCodes);
  const sourceCodeByKey = new Map(
    codes.map((code) => [normalizeStockCode(code).toUpperCase(), code]),
  );
  const acceptedCodes: string[] = [];
  const duplicateCodes: string[] = [];
  const confirmedKeys = new Set<string>();
  let submissionError: ParsedApiError | null = null;
  let stoppedOnIncompleteResponse = false;

  const retainConfirmed = (target: string[], returnedCodes: readonly string[]) => {
    for (const returnedCode of returnedCodes) {
      const key = normalizeStockCode(returnedCode).toUpperCase();
      const sourceCode = sourceCodeByKey.get(key);
      if (!sourceCode || confirmedKeys.has(key)) continue;
      confirmedKeys.add(key);
      target.push(sourceCode);
    }
  };

  for (const chunk of chunkStockCodes(codes)) {
    try {
      const result = confirmedCodes(await submitChunk(chunk), chunk);
      const beforeConfirmed = confirmedKeys.size;
      retainConfirmed(acceptedCodes, result.acceptedCodes);
      retainConfirmed(duplicateCodes, result.duplicateCodes);
      const confirmedInChunk = confirmedKeys.size - beforeConfirmed;
      if (confirmedInChunk !== chunk.length) {
        stoppedOnIncompleteResponse = true;
        submissionError = parseError(new Error(
          incompleteResponseMessage(confirmedInChunk, chunk.length),
        ));
        break;
      }
    } catch (error) {
      if (error instanceof DuplicateTaskError && chunk.length === 1) {
        retainConfirmed(duplicateCodes, [chunk[0]]);
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

  const unconfirmedCodes = codes.filter(
    (code) => !confirmedKeys.has(normalizeStockCode(code).toUpperCase()),
  );

  return {
    codes,
    acceptedCodes,
    duplicateCodes,
    unconfirmedCodes,
    accepted: acceptedCodes.length,
    duplicates: duplicateCodes.length,
    confirmed: confirmedKeys.size,
    unconfirmed: unconfirmedCodes.length,
    stoppedOnIncompleteResponse,
    submissionError,
    reconciliationError,
  };
}
