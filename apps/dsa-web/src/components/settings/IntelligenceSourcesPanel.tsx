// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useState } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { SETTINGS_INTELLIGENCE_TEXT } from '../../locales/settingsIntelligence';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import {
  intelligenceApi,
  type IntelligenceItem,
  type IntelligenceSource,
  type IntelligenceSourceTemplate,
} from '../../api/intelligence';
import { Button } from '../common/Button';
import { Input } from '../common/Input';
import { Textarea } from '../common/Textarea';
import { StatePanel } from '../common/StatePanel';
import { InlineAlert } from '../common/InlineAlert';

type LoadPhase = 'loading' | 'error' | 'ready';

const SOURCE_TYPE_OPTIONS = ['rss', 'atom', 'json'];
const SCOPE_TYPE_OPTIONS = ['market', 'stock'];
const MARKET_OPTIONS = ['cn', 'hk', 'us'];

function format(template: string, params: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(params[key] ?? ''));
}

interface DraftState {
  name: string;
  url: string;
  sourceType: string;
  scopeType: string;
  market: string;
  description: string;
}

const EMPTY_DRAFT: DraftState = {
  name: '',
  url: '',
  sourceType: 'rss',
  scopeType: 'market',
  market: 'cn',
  description: '',
};

export function IntelligenceSourcesPanel(): JSX.Element {
  const { language } = useUiLanguage();
  const text = SETTINGS_INTELLIGENCE_TEXT[language];

  const [phase, setPhase] = useState<LoadPhase>('loading');
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [sources, setSources] = useState<IntelligenceSource[]>([]);
  const [templates, setTemplates] = useState<IntelligenceSourceTemplate[]>([]);
  const [items, setItems] = useState<IntelligenceItem[] | null>(null);

  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);

  const load = useCallback(async () => {
    setPhase('loading');
    setLoadError(null);
    try {
      const [sourceList, templateList] = await Promise.all([
        intelligenceApi.listSources({ pageSize: 100 }),
        intelligenceApi.listTemplates(),
      ]);
      setSources(sourceList.items);
      setTemplates(templateList.items);
      setPhase('ready');
    } catch (error: unknown) {
      setLoadError(getParsedApiError(error, language));
      setPhase('error');
    }
  }, [language]);

  useEffect(() => {
    void load();
  }, [load]);

  const runAction = useCallback(async (
    key: string,
    action: () => Promise<string>,
    reload = true,
  ) => {
    setBusy(key);
    setActionError(null);
    setNotice(null);
    try {
      const message = await action();
      setNotice(message);
      if (reload) {
        const sourceList = await intelligenceApi.listSources({ pageSize: 100 });
        setSources(sourceList.items);
      }
    } catch (error: unknown) {
      setActionError(getParsedApiError(error, language));
    } finally {
      setBusy(null);
    }
  }, [language]);

  const handleCreate = useCallback(() => {
    if (!draft.name.trim() || !draft.url.trim()) {
      setActionError(null);
      setNotice(null);
      setActionError({ title: text.actionFailed, message: text.requiredFields, rawMessage: text.requiredFields, category: 'validation' });
      return;
    }
    void runAction('create', async () => {
      await intelligenceApi.createSource({
        name: draft.name.trim(),
        url: draft.url.trim(),
        sourceType: draft.sourceType,
        scopeType: draft.scopeType,
        market: draft.market,
        description: draft.description.trim() || undefined,
        enabled: true,
      });
      setDraft(EMPTY_DRAFT);
      return text.create;
    });
  }, [draft, runAction, text]);

  const handleTest = useCallback(() => {
    if (!draft.name.trim() || !draft.url.trim()) {
      setActionError({ title: text.actionFailed, message: text.requiredFields, rawMessage: text.requiredFields, category: 'validation' });
      return;
    }
    void runAction('test', async () => {
      const result = await intelligenceApi.testSource({
        name: draft.name.trim(),
        url: draft.url.trim(),
        sourceType: draft.sourceType,
        scopeType: draft.scopeType,
        market: draft.market,
        description: draft.description.trim() || undefined,
      });
      return format(text.testSucceeded, { count: result.fetchedCount });
    }, false);
  }, [draft, runAction, text]);

  const handleCreateDefaults = useCallback(() => {
    void runAction('defaults', async () => {
      const result = await intelligenceApi.createDefaultSources(true);
      return format(text.fetchEnabledSucceeded, { sources: result.createdCount, saved: result.total });
    });
  }, [runAction, text]);

  const handleAddTemplate = useCallback((templateId: string) => {
    void runAction(`template:${templateId}`, async () => {
      await intelligenceApi.createSourceFromTemplate(templateId);
      return text.create;
    });
  }, [runAction, text]);

  const handleFetch = useCallback((sourceId: number, dryRun: boolean) => {
    void runAction(`fetch:${sourceId}:${dryRun ? 'dry' : 'live'}`, async () => {
      const result = await intelligenceApi.fetchSource(sourceId, dryRun);
      return format(text.fetchSucceeded, { saved: result.savedCount ?? 0, fetched: result.fetchedCount ?? 0 });
    }, !dryRun);
  }, [runAction, text]);

  const handleFetchAll = useCallback(() => {
    void runAction('fetch-all', async () => {
      const result = await intelligenceApi.fetchEnabledSources();
      return format(text.fetchEnabledSucceeded, { sources: result.sourceCount ?? 0, saved: result.savedCount ?? 0 });
    });
  }, [runAction, text]);

  const handleLoadItems = useCallback(async () => {
    setBusy('items');
    setActionError(null);
    try {
      const result = await intelligenceApi.listItems({ pageSize: 20 });
      setItems(result.items);
    } catch (error: unknown) {
      setActionError(getParsedApiError(error, language));
    } finally {
      setBusy(null);
    }
  }, [language]);

  if (phase === 'loading') {
    return <StatePanel state="loading" title={text.loading} />;
  }
  if (phase === 'error') {
    return (
      <StatePanel
        state="error"
        title={text.loadFailed}
        description={loadError?.message}
        action={<Button variant="secondary" onClick={() => void load()}>{text.retry}</Button>}
      />
    );
  }

  const inputClass = 'w-full';

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h2 className="text-base font-semibold text-foreground">{text.title}</h2>
        <p className="max-w-2xl text-xs leading-6 text-secondary-text sm:text-sm">{text.description}</p>
      </header>

      {notice ? (
        <div role="status" aria-live="polite">
          <InlineAlert variant="success" message={notice} />
        </div>
      ) : null}
      {actionError ? (
        <div role="alert">
          <InlineAlert
            variant="danger"
            message={(
              <>
                {actionError.message}
                {actionError.traceId ? <span className="ml-1 opacity-70">{format(text.traceId, { id: actionError.traceId })}</span> : null}
              </>
            )}
          />
        </div>
      ) : null}

      {sources.length === 0 ? (
        <StatePanel
          state="empty"
          title={text.emptyTitle}
          description={text.emptyDescription}
          action={(
            <Button variant="primary" onClick={handleCreateDefaults} isLoading={busy === 'defaults'} loadingText={text.creatingDefaults}>
              {text.createDefaults}
            </Button>
          )}
        />
      ) : (
        <section aria-label={text.sourcesTitle} className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">{text.sourcesTitle}</h3>
            <Button variant="secondary" size="compact" className="min-h-11" onClick={handleFetchAll} isLoading={busy === 'fetch-all'} loadingText={text.fetchingAll}>
              {text.fetchAll}
            </Button>
          </div>
          <ul className="space-y-2">
            {sources.map((source) => (
              <li key={source.id} className="rounded-md border border-[var(--settings-border)] p-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium text-foreground">{source.name}</span>
                      <span className={`rounded px-1.5 text-xs ${source.enabled ? 'bg-success/10 text-success' : 'bg-subtle text-secondary-text'}`}>
                        {source.enabled ? text.enabledBadge : text.disabledBadge}
                      </span>
                      <span className="text-xs text-secondary-text">{source.sourceType} · {source.market}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-secondary-text">{source.url}</p>
                    <p className="mt-1 text-xs text-secondary-text">
                      {source.lastFetchedAt ? format(text.lastFetched, { time: source.lastFetchedAt }) : text.neverFetched}
                    </p>
                    {source.lastError ? (
                      <p className="mt-1 text-xs text-danger">{format(text.lastErrorLabel, { error: source.lastError })}</p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button variant="outline" size="compact" className="min-h-11" onClick={() => handleFetch(source.id, true)} isLoading={busy === `fetch:${source.id}:dry`}>
                      {text.dryRun}
                    </Button>
                    <Button variant="secondary" size="compact" className="min-h-11" onClick={() => handleFetch(source.id, false)} isLoading={busy === `fetch:${source.id}:live`} loadingText={text.fetching}>
                      {text.fetch}
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {templates.length > 0 ? (
        <section aria-label={text.templatesTitle} className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground">{text.templatesTitle}</h3>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {templates.map((template) => (
              <li key={template.templateId} className="flex items-center justify-between gap-2 rounded-md border border-[var(--settings-border)] p-2">
                <span className="min-w-0 truncate text-xs text-foreground">{template.name}</span>
                <Button variant="ghost" size="compact" className="min-h-11 shrink-0" onClick={() => handleAddTemplate(template.templateId)} isLoading={busy === `template:${template.templateId}`}>
                  {text.addFromTemplate}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-label={text.addSourceTitle} className="space-y-3 rounded-md border border-[var(--settings-border)] p-3">
        <h3 className="text-sm font-semibold text-foreground">{text.addSourceTitle}</h3>
        <p className="text-xs text-secondary-text">{text.unsupportedNote}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Input label={text.name} value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} fieldClassName={inputClass} />
          <Input label={text.url} value={draft.url} onChange={(e) => setDraft((d) => ({ ...d, url: e.target.value }))} fieldClassName={inputClass} inputMode="url" />
          <label className="flex flex-col gap-1 text-xs text-secondary-text">
            {text.sourceType}
            <select className="min-h-11 rounded-md border border-[var(--settings-border)] bg-transparent px-2 text-sm text-foreground" value={draft.sourceType} onChange={(e) => setDraft((d) => ({ ...d, sourceType: e.target.value }))}>
              {SOURCE_TYPE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-secondary-text">
            {text.scopeType}
            <select className="min-h-11 rounded-md border border-[var(--settings-border)] bg-transparent px-2 text-sm text-foreground" value={draft.scopeType} onChange={(e) => setDraft((d) => ({ ...d, scopeType: e.target.value }))}>
              {SCOPE_TYPE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-secondary-text">
            {text.market}
            <select className="min-h-11 rounded-md border border-[var(--settings-border)] bg-transparent px-2 text-sm text-foreground" value={draft.market} onChange={(e) => setDraft((d) => ({ ...d, market: e.target.value }))}>
              {MARKET_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
            </select>
          </label>
        </div>
        <Textarea label={text.sourceDescription} value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} rows={2} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="min-h-11" onClick={handleTest} isLoading={busy === 'test'} loadingText={text.testing}>
            {text.test}
          </Button>
          <Button variant="primary" className="min-h-11" onClick={handleCreate} isLoading={busy === 'create'} loadingText={text.creating}>
            {text.create}
          </Button>
        </div>
      </section>

      <section aria-label={text.itemsTitle} className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-foreground">{text.itemsTitle}</h3>
          <Button variant="secondary" size="compact" className="min-h-11" onClick={() => void handleLoadItems()} isLoading={busy === 'items'} loadingText={text.loadingItems}>
            {text.loadItems}
          </Button>
        </div>
        {items === null ? null : items.length === 0 ? (
          <p className="text-xs text-secondary-text">{text.noItems}</p>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li key={item.id} className="rounded-md border border-[var(--settings-border)] p-2">
                <a href={item.url} target="_blank" rel="noreferrer" className="settings-accent-text block truncate text-xs">
                  {item.title}
                </a>
                <span className="text-xs text-secondary-text">{item.sourceName ?? item.source ?? item.sourceType}{item.publishedAt ? ` · ${item.publishedAt}` : ''}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
