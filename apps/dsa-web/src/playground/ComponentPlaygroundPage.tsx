import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  Braces,
  ListFilter,
  Menu,
  PanelRightOpen,
  RotateCcw,
  Trash2,
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { useSearchParams } from 'react-router-dom';
import {
  Badge,
  Drawer,
  IconButton,
  SearchInput,
  SegmentedControl,
  Select,
  StatusDot,
} from '../components/common';
import { UiLanguageToggle } from '../components/i18n/UiLanguageToggle';
import { ThemeToggle } from '../components/theme/ThemeToggle';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText } from '../i18n/uiText';
import { PLAYGROUND_TEXT } from '../locales/playground';
import { cn } from '../utils/cn';
import {
  PLAYGROUND_CATALOG,
  PLAYGROUND_CATEGORIES,
  getPlaygroundEntry,
  getPlaygroundScenario,
} from './catalog';
import {
  isPlaygroundFrameMessage,
  type PlaygroundCategoryId,
  type PlaygroundFixtureProfile,
  type PlaygroundRequestLog,
  type PlaygroundViewport,
} from './types';

const PROFILE_OPTIONS: PlaygroundFixtureProfile[] = ['ready', 'empty', 'error', 'slow'];
const VIEWPORT_OPTIONS: PlaygroundViewport[] = ['auto', 'phone', 'tablet', 'desktop'];
const VIEWPORT_WIDTH: Record<PlaygroundViewport, number | undefined> = {
  auto: undefined,
  phone: 390,
  tablet: 768,
  desktop: 1280,
};

const readEnum = <T extends string>(value: string | null, values: readonly T[], fallback: T): T => (
  value && values.includes(value as T) ? value as T : fallback
);

const searchableText = (value: string): string => value
  .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
  .replace(/[-_/]+/g, ' ')
  .toLowerCase();

type CatalogNavProps = {
  category: PlaygroundCategoryId | 'all';
  filteredEntries: typeof PLAYGROUND_CATALOG;
  query: string;
  selectedId: string;
  onCategoryChange: (category: PlaygroundCategoryId | 'all') => void;
  onQueryChange: (value: string) => void;
  onSelect: (id: string) => void;
  onClose?: () => void;
};

const CatalogNav = ({
  category,
  filteredEntries,
  query,
  selectedId,
  onCategoryChange,
  onQueryChange,
  onSelect,
  onClose,
}: CatalogNavProps) => {
  const { language } = useUiLanguage();
  const text = PLAYGROUND_TEXT[language];
  const categoryOptions = [
    { value: 'all', label: text.categories.all },
    ...PLAYGROUND_CATEGORIES.map((value) => ({ value, label: text.categories[value] })),
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="space-y-3 border-b border-border p-3">
        <SearchInput
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={text.searchPlaceholder}
          aria-label={text.search}
          wrapperClassName="w-full"
        />
        <Select
          value={category}
          onChange={(value) => onCategoryChange(value as PlaygroundCategoryId | 'all')}
          options={categoryOptions}
          ariaLabel={text.catalog}
          className="w-full [&>div]:w-full"
          triggerClassName="w-full"
        />
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto p-2 custom-scrollbar" aria-label={text.catalog}>
        {filteredEntries.length > 0 ? (
          <ul className="space-y-1">
            {filteredEntries.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  aria-current={entry.id === selectedId ? 'page' : undefined}
                  onClick={() => {
                    onSelect(entry.id);
                    onClose?.();
                  }}
                  className={cn(
                    'flex min-h-11 w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors',
                    entry.id === selectedId
                      ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] text-foreground'
                      : 'border-transparent text-secondary-text hover:border-border hover:bg-hover hover:text-foreground',
                  )}
                >
                  <Braces className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{entry.name}</span>
                    <span className="mt-0.5 block truncate text-xs text-muted-text">
                      {text.categories[entry.category]}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex min-h-40 flex-col items-center justify-center gap-2 px-4 text-center text-sm text-muted-text">
            <ListFilter className="h-5 w-5" aria-hidden="true" />
            <p>{text.noResults}</p>
          </div>
        )}
      </nav>
    </div>
  );
};

const ComponentPlaygroundPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { language } = useUiLanguage();
  const { theme, resolvedTheme } = useTheme();
  const text = PLAYGROUND_TEXT[language];
  const selectedEntry = getPlaygroundEntry(searchParams.get('component') ?? undefined);
  const selectedScenario = getPlaygroundScenario(selectedEntry, searchParams.get('scenario') ?? undefined);
  const profile = readEnum(searchParams.get('profile'), PROFILE_OPTIONS, 'ready');
  const viewport = readEnum(searchParams.get('viewport'), VIEWPORT_OPTIONS, 'auto');
  const [category, setCategory] = useState<PlaygroundCategoryId | 'all'>('all');
  const [query, setQuery] = useState('');
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [requestLogOpen, setRequestLogOpen] = useState(false);
  const [requestLogState, setRequestLogState] = useState<{
    frameSrc: string;
    logs: PlaygroundRequestLog[];
  }>({ frameSrc: '', logs: [] });
  const [frameRevision, setFrameRevision] = useState(0);
  const [readyFrameSrc, setReadyFrameSrc] = useState<string | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const setSelection = (updates: Record<string, string>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => next.set(key, value));
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    const canonical = new URLSearchParams(searchParams);
    let changed = false;
    const desired = {
      component: selectedEntry.id,
      scenario: selectedScenario,
      profile,
      viewport,
    };
    Object.entries(desired).forEach(([key, value]) => {
      if (canonical.get(key) !== value) {
        canonical.set(key, value);
        changed = true;
      }
    });
    if (changed) setSearchParams(canonical, { replace: true });
  }, [profile, searchParams, selectedEntry.id, selectedScenario, setSearchParams, viewport]);

  const filteredEntries = useMemo(() => {
    const normalized = searchableText(query.trim());
    return PLAYGROUND_CATALOG.filter((entry) => {
      if (category !== 'all' && entry.category !== category) return false;
      if (!normalized) return true;
      return searchableText(entry.name).includes(normalized)
        || searchableText(entry.sourcePath).includes(normalized)
        || searchableText(entry.id).includes(normalized);
    });
  }, [category, query]);

  const frameQuery = new URLSearchParams({
    profile,
    theme: theme ?? resolvedTheme ?? 'system',
    language,
    revision: String(frameRevision),
  });
  const frameSrc = `/playground/render/${encodeURIComponent(selectedEntry.id)}/${encodeURIComponent(selectedScenario)}?${frameQuery.toString()}`;
  const frameWidth = VIEWPORT_WIDTH[viewport];
  const frameReady = readyFrameSrc === frameSrc;
  const requestLogs = requestLogState.frameSrc === frameSrc ? requestLogState.logs : [];

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frameRef.current?.contentWindow) return;
      if (!isPlaygroundFrameMessage(event.data)) return;
      if (event.data.type === 'ready') {
        setReadyFrameSrc(frameSrc);
        return;
      }
      setRequestLogState((current) => ({
        frameSrc,
        logs: [
          event.data.event,
          ...(current.frameSrc === frameSrc ? current.logs : []),
        ].slice(0, 100),
      }));
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [frameSrc]);

  const catalogNav = (
    <CatalogNav
      category={category}
      filteredEntries={filteredEntries}
      query={query}
      selectedId={selectedEntry.id}
      onCategoryChange={setCategory}
      onQueryChange={setQuery}
      onSelect={(id) => {
        const nextEntry = getPlaygroundEntry(id);
        setSelection({ component: nextEntry.id, scenario: nextEntry.scenarios[0].id });
      }}
      onClose={() => setCatalogOpen(false)}
    />
  );

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="flex min-h-16 shrink-0 items-center gap-2 border-b border-border bg-card px-3 md:px-4">
        <IconButton
          size="comfortable"
          variant="ghost"
          aria-label={text.openCatalog}
          className="lg:hidden"
          onClick={() => setCatalogOpen(true)}
        >
          <Menu />
        </IconButton>
        <a
          href="/"
          aria-label={text.backToApp}
          className="control-hit-target inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </a>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="truncate text-base font-semibold text-foreground">{text.title}</h1>
            <Badge variant="success" size="sm" className="hidden shrink-0 sm:inline-flex">
              <StatusDot tone="success" className="h-1.5 w-1.5" />
              {text.mockReady}
            </Badge>
          </div>
          <p className="truncate text-xs text-muted-text">{selectedEntry.sourcePath}</p>
        </div>
        <div className="hidden items-center gap-2 md:flex">
          <UiLanguageToggle />
          <ThemeToggle />
        </div>
        <IconButton
          size="comfortable"
          variant="ghost"
          aria-label={text.resetPreview}
          onClick={() => setFrameRevision((value) => value + 1)}
        >
          <RotateCcw />
        </IconButton>
        <IconButton
          size="comfortable"
          variant="outline"
          aria-label={text.openRequestLog}
          onClick={() => setRequestLogOpen(true)}
        >
          <PanelRightOpen />
        </IconButton>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-67 shrink-0 flex-col border-r border-border bg-card lg:flex">
          <div className="flex items-center justify-between border-b border-border px-3 py-3">
            <p className="text-sm font-semibold text-foreground">{text.catalog}</p>
            <span className="text-xs text-muted-text">
              {formatUiText(text.componentCount, { count: PLAYGROUND_CATALOG.length })}
            </span>
          </div>
          {catalogNav}
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
          <div className="grid shrink-0 gap-3 border-b border-border bg-card px-3 py-3 xl:grid-cols-[minmax(0,1fr)_auto_auto] xl:items-center xl:px-4">
            <div className="min-w-0">
              <div className="flex min-w-0 items-baseline gap-2">
                <h2 className="truncate text-lg font-semibold text-foreground">{selectedEntry.name}</h2>
                <span className="shrink-0 text-xs text-muted-text">{text.categories[selectedEntry.category]}</span>
              </div>
            </div>
            <SegmentedControl
              value={selectedScenario}
              options={selectedEntry.scenarios.map((item) => ({
                value: item.id,
                label: text.scenarios[item.id],
              }))}
              onChange={(value) => setSelection({ scenario: value })}
              ariaLabel={text.scenario}
              className="max-w-full justify-self-start xl:justify-self-end"
            />
            <div className="flex min-w-0 flex-wrap items-center gap-2 xl:justify-end">
              <Select
                value={profile}
                onChange={(value) => setSelection({ profile: value })}
                options={PROFILE_OPTIONS.map((value) => ({ value, label: text.profiles[value] }))}
                ariaLabel={text.profile}
                triggerClassName="min-w-32"
              />
              <Select
                value={viewport}
                onChange={(value) => setSelection({ viewport: value })}
                options={VIEWPORT_OPTIONS.map((value) => ({ value, label: text.viewports[value] }))}
                ariaLabel={text.viewport}
                triggerClassName="min-w-32"
              />
              <div className="flex items-center gap-2 md:hidden">
                <UiLanguageToggle />
                <ThemeToggle />
              </div>
            </div>
          </div>

          <div className="relative min-h-0 flex-1 overflow-auto bg-base p-2 sm:p-3">
            {!frameReady ? (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-base/80">
                <div role="status" className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-3 text-sm text-secondary-text shadow-soft-card">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary/20 border-t-primary" aria-hidden="true" />
                  {text.loadingPreview}
                </div>
              </div>
            ) : null}
            <div
              className={cn(
                'mx-auto h-full min-h-140 overflow-hidden border border-border bg-background shadow-soft-card transition-[width] duration-200',
                viewport === 'auto' ? 'w-full' : 'w-max',
              )}
              style={{ width: frameWidth ? Math.min(frameWidth, window.innerWidth - 24) : undefined, maxWidth: '100%' }}
            >
              <iframe
                ref={frameRef}
                key={frameSrc}
                src={frameSrc}
                title={`${selectedEntry.name} - ${text.scenarios[selectedScenario]}`}
                className="h-full min-h-140 w-full border-0 bg-background"
              />
            </div>
          </div>
        </main>
      </div>

      <Drawer
        isOpen={catalogOpen}
        onClose={() => setCatalogOpen(false)}
        title={text.catalog}
        variant="navigation"
      >
        {catalogNav}
      </Drawer>

      <Drawer
        isOpen={requestLogOpen}
        onClose={() => setRequestLogOpen(false)}
        title={text.requestLog}
        variant="detail"
        size="compact"
      >
        <div className="flex min-h-full flex-col gap-3">
          <div className="flex justify-end">
            <IconButton
              size="default"
              variant="danger"
              aria-label={text.clearRequestLog}
              disabled={requestLogs.length === 0}
              onClick={() => setRequestLogState({ frameSrc, logs: [] })}
            >
              <Trash2 />
            </IconButton>
          </div>
          {requestLogs.length === 0 ? (
            <div className="flex flex-1 items-center justify-center text-center text-sm text-muted-text">
              {text.noRequests}
            </div>
          ) : (
            <ol className="space-y-2">
              {requestLogs.map((item) => (
                <li key={item.id} className="rounded-lg border border-border bg-background px-3 py-2">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-xs font-semibold text-foreground">{item.method}</span>
                    <Badge variant={item.status >= 400 ? 'danger' : 'success'} size="sm">
                      {item.status}
                    </Badge>
                  </div>
                  <p className="mt-1 break-all font-mono text-xs text-secondary-text">{item.path}</p>
                  <p className="mt-1 text-right text-xs tabular-nums text-muted-text">
                    {formatUiText(text.requestDuration, { value: item.durationMs })}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </Drawer>
    </div>
  );
};

export default ComponentPlaygroundPage;
