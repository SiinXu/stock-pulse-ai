import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CircleHelp, Minimize2, Search } from 'lucide-react';
import { agentApi } from '../../api/agent';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { ApiErrorAlert, Button, StatePanel, Surface, Textarea, Tooltip } from '../common';
import { StockAutocomplete } from '../StockAutocomplete';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { STOCK_SEARCH_TEXT } from '../../locales/stockSearch';
import {
  DEEP_RESEARCH_SESSION_STORAGE_PREFIX,
  readSessionItemWithLegacyLocal,
  removeSessionItem,
  writeSessionItem,
} from '../../utils/sessionPersistence';
import { generateUUID } from '../../utils/uuid';

type ResearchStatus = 'idle' | 'running' | 'done' | 'error';

interface ResearchRun {
  question: string;
  stockCode: string;
  status: ResearchStatus;
  content?: string;
  sources?: string[];
  error?: string;
}

function storageKey(sessionId: string): string {
  return `${DEEP_RESEARCH_SESSION_STORAGE_PREFIX}${sessionId}`;
}

function loadRun(sessionId: string): ResearchRun | null {
  if (typeof window === 'undefined' || !sessionId) return null;
  try {
    const raw = readSessionItemWithLegacyLocal(storageKey(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ResearchRun>;
    if (!parsed || typeof parsed.question !== 'string') return null;
    // Whitelist the persisted status: a 'running' run cannot resume after a
    // refresh (the synchronous request was lost) and any unknown value is
    // treated as re-runnable idle rather than silently dropping content.
    const content = typeof parsed.content === 'string' ? parsed.content : undefined;
    let status: ResearchStatus = parsed.status === 'done' || parsed.status === 'error' ? parsed.status : 'idle';
    let storedError = typeof parsed.error === 'string' ? parsed.error : undefined;
    if (status === 'done' && !content?.trim()) {
      status = 'error';
      storedError = 'agent_research_failed';
    }
    return {
      question: parsed.question,
      stockCode: typeof parsed.stockCode === 'string' ? parsed.stockCode : '',
      status,
      content,
      sources: Array.isArray(parsed.sources) ? parsed.sources.filter((item): item is string => typeof item === 'string') : undefined,
      error: storedError,
    };
  } catch {
    return null;
  }
}

function saveRun(sessionId: string, run: ResearchRun | null): void {
  if (typeof window === 'undefined' || !sessionId) return;
  try {
    if (run) writeSessionItem(storageKey(sessionId), JSON.stringify(run));
    else removeSessionItem(storageKey(sessionId));
  } catch {
    // Ignore storage failures (private mode / quota); persistence is best-effort.
  }
}

interface DeepResearchPanelProps {
  sessionId: string;
  onHistoryChanged?: () => void;
  onRunInBackground?: () => void;
}

export const DeepResearchPanel: React.FC<DeepResearchPanelProps> = ({
  sessionId,
  onHistoryChanged,
  onRunInBackground,
}) => {
  const { language, t } = useUiLanguage();
  // The panel is remounted per session (keyed by sessionId in the parent), so
  // this reads the persisted run once on mount.
  const initialRun = useMemo(() => loadRun(sessionId), [sessionId]);
  const [run, setRun] = useState<ResearchRun | null>(initialRun);
  const [question, setQuestion] = useState(initialRun?.question ?? '');
  const [stockCode, setStockCode] = useState(initialRun?.stockCode ?? '');
  const [error, setError] = useState<ParsedApiError | null>(() => (
    initialRun?.status === 'error' && initialRun.error
      ? getParsedApiError({ error: initialRun.error }, language)
      : null
  ));
  const formRef = useRef<HTMLFormElement>(null);
  const runSeqRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Session changes remount this panel (via a key on the parent), so the
  // useState initializers above restore the persisted run per session.
  const persist = useCallback((next: ResearchRun | null) => {
    setRun(next);
    saveRun(sessionId, next);
  }, [sessionId]);

  const running = run?.status === 'running';

  const handleRun = useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || running) return;
    const trimmedStock = stockCode.trim();
    const seq = runSeqRef.current + 1;
    runSeqRef.current = seq;
    setError(null);
    persist({ question: trimmedQuestion, stockCode: trimmedStock, status: 'running' });
    try {
      const response = await agentApi.research({
        question: trimmedQuestion,
        stockCode: trimmedStock || undefined,
        sessionId,
        turnId: generateUUID(),
      });
      onHistoryChanged?.();
      if (!mountedRef.current || runSeqRef.current !== seq) return;
      if (response.success && response.content.trim()) {
        persist({
          question: trimmedQuestion,
          stockCode: trimmedStock,
          status: 'done',
          content: response.content,
          sources: response.sources,
        });
      } else {
        const errorCode = response.error || 'agent_research_failed';
        setError(getParsedApiError({ error: errorCode }, language));
        persist({
          question: trimmedQuestion,
          stockCode: trimmedStock,
          status: 'error',
          error: errorCode,
        });
      }
    } catch (err) {
      onHistoryChanged?.();
      if (!mountedRef.current || runSeqRef.current !== seq) return;
      const parsed = getParsedApiError(err);
      setError(parsed);
      persist({ question: trimmedQuestion, stockCode: trimmedStock, status: 'error', error: parsed.message });
    }
  }, [language, onHistoryChanged, persist, question, running, sessionId, stockCode]);

  const handleRunInBackground = useCallback(() => {
    onRunInBackground?.();
  }, [onRunInBackground]);

  return (
    <section className="flex min-h-full flex-col gap-4" aria-labelledby="deep-research-title">
      <div>
        <h2 id="deep-research-title" className="text-base font-semibold text-foreground">{t('research.title')}</h2>
        <p className="mt-1 text-sm text-secondary-text">{t('research.description')}</p>
      </div>

      {running ? (
        <StatePanel state="loading" title={t('research.running')} titleAs="p" size="compact" />
      ) : null}

      {error ? <ApiErrorAlert error={error} /> : null}

      {run && run.status === 'done' ? (
        <div className="space-y-4">
          <Surface level="interactive" className="p-4">
            <h3 className="mb-2 text-sm font-semibold text-foreground">{t('research.resultTitle')}</h3>
            <div className="prose prose-sm max-w-none text-sm text-foreground dark:prose-invert">
              <Markdown remarkPlugins={[remarkGfm]}>{run.content || ''}</Markdown>
            </div>
          </Surface>
          {run.sources && run.sources.length > 0 ? (
            <Surface level="interactive" className="p-4">
              <h3 className="mb-2 text-sm font-semibold text-foreground">{t('research.referencesTitle')}</h3>
              <ol className="list-decimal space-y-1 pl-5 text-sm text-secondary-text">
                {run.sources.map((source, index) => (
                  <li key={`${index}-${source}`}>{source}</li>
                ))}
              </ol>
            </Surface>
          ) : null}
        </div>
      ) : null}

      {!run || run.status === 'idle' ? (
        <p className="text-sm text-muted-text">{t('research.emptyHint')}</p>
      ) : null}

      <form ref={formRef} className="mt-auto space-y-3" onSubmit={handleRun}>
        <Textarea
          label={t('research.questionLabel')}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={t('research.questionPlaceholder')}
          rows={3}
          disabled={running}
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div data-testid="deep-research-stock-field" className="w-full sm:min-w-0 sm:flex-1">
            <div className="mb-1.5 flex items-center gap-1">
              <label htmlFor="deep-research-stock" className="text-xs font-medium text-secondary-text">
                {t('research.stockCodeLabel')}
              </label>
              <Tooltip
                content={(
                  <span className="space-y-1">
                    <span className="block">{STOCK_SEARCH_TEXT[language].suffixExamples}</span>
                    <span className="block">{STOCK_SEARCH_TEXT[language].manualEntryHint}</span>
                  </span>
                )}
              >
                <button
                  type="button"
                  data-testid="deep-research-stock-help"
                  aria-label={`${t('research.stockCodeLabel')} · ${t('common.details')}`}
                  className="inline-flex h-5 w-5 items-center justify-center rounded-sm text-muted-text hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
                >
                  <CircleHelp className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </Tooltip>
            </div>
            <div className="[&>div>p]:sr-only">
              <StockAutocomplete
                id="deep-research-stock"
                value={stockCode}
                onChange={setStockCode}
                onSubmit={(code, _name, source, metadata) => {
                  setStockCode(metadata?.displayCode ?? code);
                  if (source !== 'autocomplete') {
                    formRef.current?.requestSubmit();
                  }
                }}
                disabled={running}
                placeholder={t('research.stockCodeHint')}
                ariaLabel={t('research.stockCodeLabel')}
              />
            </div>
          </div>
          {running ? (
            <Button type="button" variant="secondary" size="comfortable" onClick={handleRunInBackground}>
              <Minimize2 className="h-4 w-4" aria-hidden="true" />
              {t('research.runInBackground')}
            </Button>
          ) : (
            <Button type="submit" variant="primary" size="primary" disabled={!question.trim()}>
              <Search className="h-4 w-4" aria-hidden="true" />
              {t('research.run')}
            </Button>
          )}
        </div>
      </form>
    </section>
  );
};
