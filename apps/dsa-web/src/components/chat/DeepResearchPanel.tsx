import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Search, StopCircle } from 'lucide-react';
import { agentApi } from '../../api/agent';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { ApiErrorAlert, Button, Field, InlineAlert, Input, Textarea } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

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
  return `dsa_research_run:${sessionId}`;
}

function loadRun(sessionId: string): ResearchRun | null {
  if (typeof window === 'undefined' || !sessionId) return null;
  try {
    const raw = window.localStorage.getItem(storageKey(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ResearchRun;
    if (!parsed || typeof parsed.question !== 'string') return null;
    // A run persisted while 'running' cannot be resumed after a refresh (the
    // synchronous request was lost), so restore it as re-runnable idle.
    const status: ResearchStatus = parsed.status === 'running' ? 'idle' : parsed.status;
    return { ...parsed, status };
  } catch {
    return null;
  }
}

function saveRun(sessionId: string, run: ResearchRun | null): void {
  if (typeof window === 'undefined' || !sessionId) return;
  try {
    if (run) window.localStorage.setItem(storageKey(sessionId), JSON.stringify(run));
    else window.localStorage.removeItem(storageKey(sessionId));
  } catch {
    // Ignore storage failures (private mode / quota); persistence is best-effort.
  }
}

interface DeepResearchPanelProps {
  sessionId: string;
}

export const DeepResearchPanel: React.FC<DeepResearchPanelProps> = ({ sessionId }) => {
  const { t } = useUiLanguage();
  const [run, setRun] = useState<ResearchRun | null>(() => loadRun(sessionId));
  const [question, setQuestion] = useState(() => loadRun(sessionId)?.question ?? '');
  const [stockCode, setStockCode] = useState(() => loadRun(sessionId)?.stockCode ?? '');
  const [error, setError] = useState<ParsedApiError | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runSeqRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
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
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    persist({ question: trimmedQuestion, stockCode: trimmedStock, status: 'running' });
    try {
      const response = await agentApi.research(
        { question: trimmedQuestion, stockCode: trimmedStock || undefined },
        { signal: controller.signal },
      );
      if (!mountedRef.current || runSeqRef.current !== seq) return;
      persist(response.success
        ? { question: trimmedQuestion, stockCode: trimmedStock, status: 'done', content: response.content, sources: response.sources }
        : { question: trimmedQuestion, stockCode: trimmedStock, status: 'error', error: response.error || t('research.failed') });
    } catch (err) {
      if (!mountedRef.current || runSeqRef.current !== seq) return;
      if (controller.signal.aborted) {
        persist({ question: trimmedQuestion, stockCode: trimmedStock, status: 'idle' });
        return;
      }
      setError(getParsedApiError(err));
      persist({ question: trimmedQuestion, stockCode: trimmedStock, status: 'error' });
    }
  }, [persist, question, running, stockCode, t]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return (
    <section className="space-y-4" aria-labelledby="deep-research-title">
      <div>
        <h2 id="deep-research-title" className="text-base font-semibold text-foreground">{t('research.title')}</h2>
        <p className="mt-1 text-sm text-secondary-text">{t('research.description')}</p>
      </div>

      <form className="space-y-3" onSubmit={handleRun}>
        <Textarea
          label={t('research.questionLabel')}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={t('research.questionPlaceholder')}
          rows={3}
          disabled={running}
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <Field controlId="deep-research-stock" label={t('research.stockCodeLabel')} hint={t('research.stockCodeHint')} className="sm:w-64">
            <Input
              id="deep-research-stock"
              value={stockCode}
              onChange={(event) => setStockCode(event.target.value)}
              disabled={running}
              autoComplete="off"
            />
          </Field>
          {running ? (
            <Button type="button" variant="secondary" size="comfortable" onClick={handleCancel}>
              <StopCircle className="h-4 w-4" aria-hidden="true" />
              {t('research.cancel')}
            </Button>
          ) : (
            <Button type="submit" variant="primary" size="primary" disabled={!question.trim()}>
              <Search className="h-4 w-4" aria-hidden="true" />
              {t('research.run')}
            </Button>
          )}
        </div>
      </form>

      {running ? (
        <p className="text-sm text-secondary-text" role="status">{t('research.running')}</p>
      ) : null}

      {error ? <ApiErrorAlert error={error} /> : null}

      {run && run.status === 'error' && !error ? (
        <InlineAlert variant="danger" title={t('research.errorTitle')} message={run.error || t('research.failed')} />
      ) : null}

      {run && run.status === 'done' ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-border/60 bg-elevated/20 p-4">
            <h3 className="mb-2 text-sm font-semibold text-foreground">{t('research.resultTitle')}</h3>
            <div className="prose prose-sm max-w-none text-sm text-foreground dark:prose-invert">
              <Markdown remarkPlugins={[remarkGfm]}>{run.content || ''}</Markdown>
            </div>
          </div>
          {run.sources && run.sources.length > 0 ? (
            <div className="rounded-xl border border-border/60 bg-elevated/20 p-4">
              <h3 className="mb-2 text-sm font-semibold text-foreground">{t('research.referencesTitle')}</h3>
              <ol className="list-decimal space-y-1 pl-5 text-sm text-secondary-text">
                {run.sources.map((source, index) => (
                  <li key={`${index}-${source}`}>{source}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      ) : null}

      {!run || run.status === 'idle' ? (
        <p className="text-sm text-secondary-text">{t('research.emptyHint')}</p>
      ) : null}
    </section>
  );
};
