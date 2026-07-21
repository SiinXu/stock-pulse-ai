import { create } from 'zustand';
import type { ParsedApiError } from '../api/error';
import type { AnalysisResult, AnalysisReport } from '../types/analysis';

interface AnalysisState {
  // Analysis status.
  isLoading: boolean;
  result: AnalysisResult | null;
  error: ParsedApiError | null;

  // Historical report view
  isHistoryView: boolean;
  historyReport: AnalysisReport | null;

  // Actions
  setLoading: (loading: boolean) => void;
  setResult: (result: AnalysisResult | null) => void;
  setError: (error: ParsedApiError | null) => void;
  setHistoryReport: (report: AnalysisReport | null) => void;
  reset: () => void;
  resetToAnalysis: () => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  // Initial state
  isLoading: false,
  result: null,
  error: null,
  isHistoryView: false,
  historyReport: null,

  // Actions
  setLoading: (loading) => set({ isLoading: loading }),

  setResult: (result) =>
    set({
      result,
      error: null,
      isHistoryView: false,
      historyReport: null,
    }),

  setError: (error) => set({ error, isLoading: false }),

  setHistoryReport: (report) =>
    set({
      historyReport: report,
      isHistoryView: true,
      result: null,
      error: null,
      isLoading: false,
    }),

  reset: () =>
    set({
      isLoading: false,
      result: null,
      error: null,
      isHistoryView: false,
      historyReport: null,
    }),

  resetToAnalysis: () =>
    set({
      isHistoryView: false,
      historyReport: null,
    }),
}));
