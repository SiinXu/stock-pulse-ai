// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { SETTINGS_INTELLIGENCE_TEXT } from '../../locales/settingsIntelligence';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../../api/error';
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
import { Modal } from '../common/Modal';
import { Select } from '../common/Select';

type LoadPhase = 'loading' | 'error' | 'ready';

const SOURCE_TYPE_OPTIONS = ['rss', 'atom', 'json'];
const SCOPE_TYPE_OPTIONS = ['market', 'stock'];
const MARKET_OPTIONS = ['cn', 'hk', 'us'];
const toSelectOptions = (options: string[]) => options.map((value) => ({ value, label: value }));

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

export function IntelligenceSourcesPanel() {
  const { language, t } = useUiLanguage();
  const text = SETTINGS_INTELLIGENCE_TEXT[language];

  const [phase, setPhase] = useState<LoadPhase>('loading');
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [sources, setSources] = useState<IntelligenceSource[]>([]);
  const [templates, setTemplates] = useState<IntelligenceSourceTemplate[]>([]);
  const [items, setItems] = useState<IntelligenceItem[] | null>(null);

  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
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
        try {
          const sourceList = await intelligenceApi.listSources({ pageSize: 100 });
          setSources(sourceList.items);
        } catch (error: unknown) {
          setLoadError(getParsedApiError(error, language));
          setPhase('error');
        }
      }
      return true;
    } catch (error: unknown) {
      setActionError(getParsedApiError(error, language));
      return false;
    } finally {
      setBusy(null);
    }
  }, [language]);

  const handleCreate = useCallback(() => {
    if (!draft.name.trim() || !draft.url.trim()) {
      setActionError(null);
      setNotice(null);
      setActionError(createParsedApiError({ title: text.actionFailed, message: text.requiredFields }));
      return;
    }
    void (async () => {
      const succeeded = await runAction('create', async () => {
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
      if (succeeded) {
        setIsCreateOpen(false);
      }
    })();
  }, [draft, runAction, text]);

  const handleTest = useCallback(() => {
    if (!draft.name.trim() || !draft.url.trim()) {
      setActionError(createParsedApiError({ title: text.actionFailed, message: text.requiredFields }));
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
  const feedback = notice ? (
    <div role="status" aria-live="polite">
      <InlineAlert variant="success" message={notice} />
    </div>
  ) : actionError ? (
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
  ) : null;

  const openCreateDialog = () => {
    setNotice(null);
    setActionError(null);
    setIsCreateOpen(true);
  };

  const closeCreateDialog = () => {
    setNotice(null);
    setActionError(null);
    setIsCreateOpen(false);
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 className="text-base font-semibold text-foreground">{text.title}</h2>
          <p className="max-w-2xl text-xs leading-6 text-secondary-text sm:text-sm">{text.description}</p>
        </div>
        <Button type="button" variant="primary" size="default" className="shrink-0" onClick={openCreateDialog}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {text.addSourceTitle}
        </Button>
      </header>

      {!isCreateOpen ? feedback : null}

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
            <Button variant="secondary" size="compact" onClick={handleFetchAll} isLoading={busy === 'fetch-all'} loadingText={text.fetchingAll}>
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
                    <Button variant="outline" size="compact" onClick={() => handleFetch(source.id, true)} isLoading={busy === `fetch:${source.id}:dry`}>
                      {text.dryRun}
                    </Button>
                    <Button variant="secondary" size="compact" onClick={() => handleFetch(source.id, false)} isLoading={busy === `fetch:${source.id}:live`} loadingText={text.fetching}>
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
                <Button variant="ghost" size="compact" onClick={() => handleAddTemplate(template.templateId)} isLoading={busy === `template:${template.templateId}`}>
                  {text.addFromTemplate}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-label={text.itemsTitle} className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-foreground">{text.itemsTitle}</h3>
          <Button variant="secondary" size="compact" onClick={() => void handleLoadItems()} isLoading={busy === 'items'} loadingText={text.loadingItems}>
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

      <Modal
        isOpen={isCreateOpen}
        onClose={closeCreateDialog}
        title={text.addSourceTitle}
        description={text.unsupportedNote}
        size="wide"
        footer={(
          <div className="flex w-full flex-wrap justify-end gap-2">
            <Button type="button" variant="secondary" onClick={closeCreateDialog}>
              {t('common.cancel')}
            </Button>
            <Button type="button" variant="outline" onClick={handleTest} isLoading={busy === 'test'} loadingText={text.testing}>
              {text.test}
            </Button>
            <Button type="submit" form="intelligence-source-create-form" variant="primary" isLoading={busy === 'create'} loadingText={text.creating}>
              {text.create}
            </Button>
          </div>
        )}
      >
        <form
          id="intelligence-source-create-form"
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            handleCreate();
          }}
        >
          {isCreateOpen ? feedback : null}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input label={text.name} value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} fieldClassName={inputClass} />
            <Input label={text.url} value={draft.url} onChange={(event) => setDraft((current) => ({ ...current, url: event.target.value }))} fieldClassName={inputClass} inputMode="url" />
            <Select label={text.sourceType} value={draft.sourceType} onChange={(value) => setDraft((current) => ({ ...current, sourceType: value }))} options={toSelectOptions(SOURCE_TYPE_OPTIONS)} className="w-full" />
            <Select label={text.scopeType} value={draft.scopeType} onChange={(value) => setDraft((current) => ({ ...current, scopeType: value }))} options={toSelectOptions(SCOPE_TYPE_OPTIONS)} className="w-full" />
            <Select label={text.market} value={draft.market} onChange={(value) => setDraft((current) => ({ ...current, market: value }))} options={toSelectOptions(MARKET_OPTIONS)} className="w-full" />
          </div>
          <Textarea label={text.sourceDescription} value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} rows={2} />
        </form>
      </Modal>
    </div>
  );
}
