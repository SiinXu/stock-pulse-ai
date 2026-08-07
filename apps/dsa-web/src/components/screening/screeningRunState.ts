import { formatParsedApiError, type ParsedApiError } from '../../api/error';
import {
  RESEARCH_DISCOVER_LIMITS,
} from '../../routing/routes';
import {
  DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE,
  resolveResearchDiscoverRouteState,
  setResearchDiscoverRouteState,
  type ResearchDiscoverRouteState,
} from '../../routing/researchRouteState';
import { SCREEN_TASK_SESSION_STORAGE_KEY } from '../../utils/sessionPersistence';
import type { ScreeningText } from './screeningText';

export type PersistedScreenTask = {
  taskId: string;
  market: string;
  strategy: string;
  maxResults: number;
};

export type ScreeningRunParameters = ResearchDiscoverRouteState;

export const SCREEN_TASK_POLL_INTERVAL_MS = 2000;

export const readScreeningRunParameters = (
  restoredTask: PersistedScreenTask | null,
  search = typeof window === 'undefined' ? '' : window.location.search,
): ScreeningRunParameters => {
  return resolveResearchDiscoverRouteState(search, restoredTask).state;
};

export const getScreeningRunParametersLocation = ({ market, strategy, maxResults }: ScreeningRunParameters) => {
  if (typeof window === 'undefined') return null;
  const url = new URL(window.location.href);
  url.search = setResearchDiscoverRouteState(url.searchParams, { market, strategy, maxResults }).toString();
  return `${url.pathname}${url.search}${url.hash}`;
};

export const readPersistedScreenTask = (): PersistedScreenTask | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(SCREEN_TASK_SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<PersistedScreenTask>;
    if (typeof parsed.taskId !== 'string' || !parsed.taskId.trim()) {
      return null;
    }
    const restoredMaxResults = Number(parsed.maxResults);
    return {
      taskId: parsed.taskId,
      market: typeof parsed.market === 'string' && parsed.market.trim()
        ? parsed.market
        : DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.market,
      strategy: typeof parsed.strategy === 'string' && parsed.strategy.trim()
        ? parsed.strategy
        : DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.strategy,
      maxResults: Number.isFinite(restoredMaxResults)
        ? Math.min(RESEARCH_DISCOVER_LIMITS.maxCount, Math.max(1, restoredMaxResults))
        : DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.maxResults,
    };
  } catch {
    return null;
  }
};

export const persistScreenTask = (task: PersistedScreenTask) => {
  try {
    window.sessionStorage.setItem(SCREEN_TASK_SESSION_STORAGE_KEY, JSON.stringify(task));
  } catch {
    // Session storage is best-effort; polling still works while the page stays mounted.
  }
};

export const clearPersistedScreenTask = () => {
  try {
    window.sessionStorage.removeItem(SCREEN_TASK_SESSION_STORAGE_KEY);
  } catch {
    // Ignore storage cleanup failures.
  }
};

export const isUnrecoverableScreenTaskError = (error: ParsedApiError) =>
  error.code === 'alphasift_screen_task_not_found';

export const formatRecoverableScreenTaskPollingError = (error: ParsedApiError, text: ScreeningText) => {
  if (error.category === 'upstream_timeout') {
    return text.pollingTimeout;
  }
  if (error.category === 'upstream_network' || error.category === 'local_connection_failed') {
    return text.pollingNetwork;
  }
  return formatParsedApiError(error) || text.pollingFallback;
};

export const isRunningScreenTask = (status: string | undefined | null) =>
  status === 'pending' || status === 'processing';
