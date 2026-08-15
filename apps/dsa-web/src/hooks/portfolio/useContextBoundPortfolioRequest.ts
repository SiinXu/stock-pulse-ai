// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { useCallback, useEffect, useRef, useState } from 'react';
import type { PortfolioCostMethod } from '../../types/portfolio';

export class PortfolioResponseContextError extends Error {
  constructor() {
    super('Portfolio response context did not match the initiating request');
    this.name = 'PortfolioResponseContextError';
  }
}

export function assertPortfolioResponseContext(
  response: { accountId?: number | null; costMethod: string },
  expected: { accountId?: number; costMethod: PortfolioCostMethod },
): void {
  const accountMatches = expected.accountId === undefined
    ? response.accountId == null
    : response.accountId === expected.accountId;
  if (!accountMatches || response.costMethod !== expected.costMethod) {
    throw new PortfolioResponseContextError();
  }
}

export function useContextBoundPortfolioRequest<TResult>(contextKey: string) {
  const generationRef = useRef(0);
  const pendingGenerationRef = useRef<number | null>(null);
  const [result, setResult] = useState<TResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [hasCompleted, setHasCompleted] = useState(false);

  useEffect(() => {
    generationRef.current += 1;
    pendingGenerationRef.current = null;
    setResult(null);
    setError(null);
    setIsRunning(false);
    setHasCompleted(false);
  }, [contextKey]);

  const clear = useCallback(() => {
    generationRef.current += 1;
    pendingGenerationRef.current = null;
    setResult(null);
    setError(null);
    setIsRunning(false);
    setHasCompleted(false);
  }, []);

  const execute = useCallback(async (
    request: () => Promise<TResult>,
    validateResponse?: (response: TResult) => void,
  ): Promise<void> => {
    if (pendingGenerationRef.current === generationRef.current) return;
    const requestGeneration = generationRef.current;
    pendingGenerationRef.current = requestGeneration;
    setIsRunning(true);
    setError(null);
    try {
      const response = await request();
      validateResponse?.(response);
      if (generationRef.current !== requestGeneration) return;
      setResult(response);
      setHasCompleted(true);
    } catch (requestError) {
      if (generationRef.current !== requestGeneration) return;
      setResult(null);
      setError(requestError);
    } finally {
      if (generationRef.current === requestGeneration) {
        pendingGenerationRef.current = null;
        setIsRunning(false);
      }
    }
  }, []);

  return { result, error, isRunning, hasCompleted, execute, clear };
}
