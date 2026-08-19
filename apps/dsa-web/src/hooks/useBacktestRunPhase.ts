import { useRef, useState } from 'react';
import type { BacktestRunClientPhase } from '../api/backtestRunOutcome';

export function useBacktestRunPhase() {
  const [runPhase, setRunPhase] = useState<BacktestRunClientPhase>('idle');
  const runPhaseRef = useRef<BacktestRunClientPhase>('idle');
  const runAbortRef = useRef<AbortController | null>(null);

  const setTrackedRunPhase = (phase: BacktestRunClientPhase) => {
    runPhaseRef.current = phase;
    setRunPhase(phase);
  };

  return {
    runPhase,
    runPhaseRef,
    runAbortRef,
    isRunning: runPhase === 'submitting',
    runBlocked: runPhase !== 'idle',
    setTrackedRunPhase,
  };
}
