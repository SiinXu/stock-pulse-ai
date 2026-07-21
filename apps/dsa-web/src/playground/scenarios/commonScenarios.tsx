/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState, type ReactNode } from 'react';
import { Bell, Check, Copy, Info, Save, Search, Trash2 } from 'lucide-react';
import { createParsedApiError } from '../../api/error';
import {
  AdvancedFilterSheet,
  Alert,
  ApiErrorAlert,
  AppPage,
  AppliedFilterChips,
  Badge,
  Button,
  Card,
  Checkbox,
  Collapsible,
  ConfirmDialog,
  CredentialInput,
  DataTable,
  DatePicker,
  Drawer,
  EmptyState,
  EyeToggleIcon,
  Field,
  FilterBar,
  FilterChip,
  FilterSheet,
  IconButton,
  InlineAlert,
  Input,
  JsonViewer,
  Loading,
  Modal,
  NotificationPanel,
  PageHeader,
  Pagination,
  Popover,
  ResponsiveFilterPanel,
  ResponsiveRail,
  ScoreGauge,
  ScrollArea,
  SearchableSelect,
  SearchInput,
  Section,
  SectionCard,
  SelectionChip,
  SegmentedControl,
  Select,
  Sheet,
  StatCard,
  StatePanel,
  StatusDot,
  StickyActionBar,
  SummaryStrip,
  Surface as CommonSurface,
  Switch,
  TabPanel,
  Tabs,
  Textarea,
  TimePicker,
  ToastViewport,
  ToastProvider,
  Toolbar,
  Tooltip,
  useToast,
  WorkspaceNavigation,
  WorkspacePage,
  type ButtonVariant,
  type DataTableColumn,
  type IconButtonSize,
  type IconButtonVariant,
} from '../../components/common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const Surface = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <div className={`rounded-xl border border-border bg-card p-4 sm:p-6 ${className}`}>
    {children}
  </div>
);

const useSampleText = () => {
  const { language } = useUiLanguage();
  return PLAYGROUND_TEXT[language].samples;
};

const ButtonStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const variants: Array<{ value: ButtonVariant; label: string }> = [
    { value: 'primary', label: text.primaryAction },
    { value: 'secondary', label: text.secondaryAction },
    { value: 'outline', label: text.outlineAction },
    { value: 'ghost', label: text.quietAction },
    { value: 'danger', label: text.destructiveAction },
    { value: 'danger-subtle', label: text.destructiveAction },
  ];
  if (scenario === 'sizes') {
    return (
      <Surface className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="compact">{text.primaryAction}</Button>
        <Button variant="secondary" size="default">{text.primaryAction}</Button>
        <Button variant="secondary" size="comfortable">{text.primaryAction}</Button>
        <Button variant="secondary" size="primary">{text.primaryAction}</Button>
      </Surface>
    );
  }
  if (scenario === 'states') {
    return (
      <Surface className="flex flex-wrap items-center gap-3">
        <Button variant="primary" disabled>{text.primaryAction}</Button>
        <Button variant="secondary" isLoading loadingText={text.loadingAction}>{text.secondaryAction}</Button>
        <Button variant="outline" glow>{text.outlineAction}</Button>
      </Surface>
    );
  }
  return <Surface className="flex flex-wrap items-center gap-3">{variants.map((item) => <Button key={item.value} variant={item.value}>{item.label}</Button>)}</Surface>;
};

const SelectionChipStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [selected, setSelected] = useState(true);
  return (
    <Surface className="flex flex-wrap gap-3">
      <SelectionChip
        label={text.optionOne}
        description={text.fieldHint}
        metadata="CN"
        selected={selected}
        onClick={() => setSelected((value) => !value)}
      />
      <SelectionChip
        label={text.optionTwo}
        description={text.preview}
        selected={false}
        isLoading={scenario === 'states'}
        disabled={scenario === 'states'}
        onClick={() => undefined}
      />
    </Surface>
  );
};

const IconButtonStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const variants: IconButtonVariant[] = ['ghost', 'outline', 'danger'];
  const sizes: IconButtonSize[] = ['compact', 'default', 'comfortable'];
  if (scenario === 'sizes') {
    return <Surface className="flex items-center gap-3">{sizes.map((size) => <IconButton key={size} size={size} variant="outline" aria-label={`${text.preview} ${size}`}><Search /></IconButton>)}</Surface>;
  }
  if (scenario === 'states') {
    return (
      <Surface className="flex items-center gap-3">
        <IconButton variant="outline" aria-label={text.loadingAction} isLoading><Save /></IconButton>
        <IconButton variant="ghost" aria-label={text.quietAction} disabled><Copy /></IconButton>
      </Surface>
    );
  }
  return <Surface className="flex items-center gap-3">{variants.map((variant) => <IconButton key={variant} variant={variant} aria-label={`${text.preview} ${variant}`}>{variant === 'danger' ? <Trash2 /> : <Save />}</IconButton>)}</Surface>;
};

const FieldStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const hasError = scenario === 'states';
  return (
    <Surface className="max-w-md">
      <Field
        controlId="playground-field"
        label={text.fieldLabel}
        hint={hasError ? undefined : text.fieldHint}
        error={hasError ? text.fieldError : undefined}
        hintId="playground-field-hint"
        errorId="playground-field-error"
      >
        <input id="playground-field" className="h-9 w-full rounded-lg border border-border bg-transparent px-3 text-sm text-foreground" />
      </Field>
    </Surface>
  );
};

const TextareaStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  return (
    <Surface className="max-w-lg">
      <Textarea
        label={text.fieldLabel}
        placeholder={text.inputPlaceholder}
        hint={scenario === 'states' ? undefined : text.fieldHint}
        error={scenario === 'states' ? text.fieldError : undefined}
        disabled={scenario === 'states'}
      />
    </Surface>
  );
};

const SegmentedControlStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('one');
  return (
    <Surface>
      <SegmentedControl
        value={value}
        onChange={setValue}
        ariaLabel={text.preview}
        options={[
          { value: 'one', label: text.optionOne },
          { value: 'two', label: text.optionTwo },
          { value: 'three', label: text.optionThree, disabled: scenario === 'states' },
        ]}
      />
    </Surface>
  );
};

const SearchInputStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('');
  return (
    <Surface className="max-w-md">
      <SearchInput
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={text.searchPlaceholder}
        aria-label={text.searchPlaceholder}
        shortcut={scenario === 'states' ? undefined : '/'}
        disabled={scenario === 'states'}
      />
    </Surface>
  );
};

const NotificationPanelStory = () => {
  const text = useSampleText();
  return <NotificationPanel title={text.notificationTitle} emptyText={text.notificationEmpty} filterLabel={text.filter} />;
};

const CommonSurfaceStory = () => {
  const text = useSampleText();
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {(['canvas', 'section', 'interactive', 'overlay'] as const).map((level) => (
        <CommonSurface key={level} level={level} padding="md" hoverable={level === 'interactive'}>
          <p className="text-sm font-semibold text-foreground">{level}</p>
          <p className="mt-1 text-sm text-secondary-text">{text.preview}</p>
        </CommonSurface>
      ))}
    </div>
  );
};

const SectionStory = () => {
  const text = useSampleText();
  return (
    <Section
      title={text.panelTitle}
      eyebrow={text.panelEyebrow}
      description={text.fieldHint}
      actions={<Button variant="secondary">{text.secondaryAction}</Button>}
      level="section"
      padding="md"
    >
      <p className="text-sm text-secondary-text">{text.preview}</p>
    </Section>
  );
};

const StatePanelStory = () => {
  const text = useSampleText();
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {(['loading', 'blocked', 'partial', 'empty', 'error', 'retrying', 'success'] as const).map((state) => (
        <StatePanel
          key={state}
          state={state}
          title={`${text.preview}: ${state}`}
          description={text.emptyDescription}
          size="compact"
          action={state === 'error' ? <Button variant="secondary">{text.retry}</Button> : undefined}
        />
      ))}
    </div>
  );
};

const AlertStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [visible, setVisible] = useState(true);
  if (scenario === 'interactive') {
    return visible ? (
      <Alert
        tone="warning"
        title={text.warning}
        action={<Button variant="ghost" size="compact">{text.secondaryAction}</Button>}
        dismissLabel={text.close}
        onDismiss={() => setVisible(false)}
      >
        {text.confirmMessage}
      </Alert>
    ) : <Button variant="secondary" onClick={() => setVisible(true)}>{text.primaryAction}</Button>;
  }
  return (
    <div className="space-y-3">
      {(['info', 'success', 'warning', 'danger'] as const).map((tone) => (
        <Alert
          key={tone}
          tone={tone}
          title={tone === 'danger' ? text.error : tone === 'warning' ? text.warning : tone === 'success' ? text.success : text.info}
        >
          {text.preview}
        </Alert>
      ))}
    </div>
  );
};

const CardStory = () => {
  const text = useSampleText();
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {(['default', 'bordered', 'gradient'] as const).map((variant) => (
        <Card key={variant} variant={variant} title={variant} subtitle={text.preview}>
          <p className="text-sm text-secondary-text">{text.preview}</p>
        </Card>
      ))}
    </div>
  );
};

const CheckboxStory = () => {
  const text = useSampleText();
  const [checked, setChecked] = useState(true);
  const { scenario } = usePlaygroundScenario();
  return (
    <Surface className="flex flex-wrap gap-5">
      <Checkbox checked={checked} onChange={(event) => setChecked(event.target.checked)} label={text.optionOne} />
      <Checkbox checked={false} readOnly label={text.optionTwo} />
      <Checkbox checked disabled={scenario === 'states'} readOnly label={text.optionThree} />
    </Surface>
  );
};

const AppPageStory = () => {
  const text = useSampleText();
  return <AppPage className="min-h-0"><PageHeader title={text.appPageLabel} description={text.preview} /><Surface>{text.preview}</Surface></AppPage>;
};

const WorkspacePageStory = () => {
  const text = useSampleText();
  return (
    <WorkspacePage
      className="min-h-0"
      rail={(
        <ResponsiveRail title={text.details} expandLabel={text.primaryAction} collapseLabel={text.close} defaultOpen>
          <p className="text-sm text-secondary-text">{text.fieldHint}</p>
        </ResponsiveRail>
      )}
    >
      <PageHeader title={text.appPageLabel} description={text.preview} />
      <CommonSurface level="interactive" padding="md">
        <p className="text-sm text-secondary-text">{text.preview}</p>
      </CommonSurface>
    </WorkspacePage>
  );
};

const ResponsiveFilterPanelStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  return (
    <ResponsiveFilterPanel
      filterLabel={text.filter}
      drawerTitle={text.details}
      applyLabel={text.primaryAction}
      loadingLabel={text.loadingAction}
      resetLabel={text.quietAction}
      onReset={() => undefined}
      onApply={() => undefined}
      isApplying={scenario === 'states'}
      activeCount={2}
      basic={<Input label={text.optionOne} placeholder={text.searchPlaceholder} />}
      advanced={<Select label={text.optionTwo} value="one" onChange={() => undefined} options={[{ value: 'one', label: text.optionOne }, { value: 'two', label: text.optionTwo }]} />}
    />
  );
};

const ResponsiveRailStory = () => {
  const text = useSampleText();
  return (
    <div className="max-w-sm">
      <ResponsiveRail
        title={text.details}
        expandLabel={text.primaryAction}
        collapseLabel={text.close}
        actions={<IconButton variant="outline" aria-label={text.secondaryAction}><Save /></IconButton>}
      >
        <CommonSurface level="section" padding="sm">
          <p className="text-sm text-secondary-text">{text.preview}</p>
        </CommonSurface>
      </ResponsiveRail>
    </div>
  );
};

const WorkspaceNavigationStory = () => {
  const text = useSampleText();
  const [current, setCurrent] = useState('one');
  const items = [
    { id: 'one', label: text.optionOne, to: '#one' },
    { id: 'two', label: text.optionTwo, to: '#two' },
    { id: 'three', label: text.optionThree, to: '#three' },
  ];
  return (
    <WorkspaceNavigation
      id="playground-workspace-navigation"
      ariaLabel={text.navigation}
      current={current}
      items={items}
      onCompactNavigate={(item) => setCurrent(item.id)}
    />
  );
};

const TabsStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('one');
  const items = [
    { id: 'one', label: text.optionOne },
    { id: 'two', label: text.optionTwo },
    { id: 'three', label: text.optionThree, disabled: scenario === 'states' },
  ];
  return (
    <CommonSurface level="section" padding="md">
      <Tabs id="playground-tabs" aria-label={text.tabs} value={value} items={items} onValueChange={setValue} />
      {items.map((item) => (
        <TabPanel key={item.id} tabsId="playground-tabs" value={item.id} activeValue={value}>
          <p className="text-sm text-secondary-text">{item.label}: {text.preview}</p>
        </TabPanel>
      ))}
    </CommonSurface>
  );
};

const TabPanelStory = () => {
  const text = useSampleText();
  const items = [{ id: 'preview', label: text.preview }];
  return (
    <CommonSurface level="section" padding="md">
      <Tabs id="playground-panel-tabs" aria-label={text.tabs} value="preview" items={items} onValueChange={() => undefined} />
      <TabPanel tabsId="playground-panel-tabs" value="preview" activeValue="preview">
        <p className="text-sm text-secondary-text">{text.preview}</p>
      </TabPanel>
    </CommonSurface>
  );
};

const SummaryStripStory = () => {
  const text = useSampleText();
  return (
    <SummaryStrip
      aria-label={text.preview}
      items={[
        { id: 'value', label: text.optionOne, value: '$24,080' },
        { id: 'risk', label: text.optionTwo, value: text.warning, tone: 'warning', detail: text.fieldHint },
        { id: 'change', label: text.optionThree, value: '+2.4%', tone: 'success' },
      ]}
    />
  );
};

const SectionCardStory = () => {
  const text = useSampleText();
  return <SectionCard title={text.details} subtitle={text.preview} actions={<Button variant="secondary">{text.secondaryAction}</Button>}><p className="text-sm text-secondary-text">{text.preview}</p></SectionCard>;
};

const StatCardStory = () => {
  const text = useSampleText();
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {(['default', 'primary', 'success', 'warning', 'danger'] as const).map((tone, index) => (
        <StatCard key={tone} tone={tone} label={tone} value={68 + index} hint={text.preview} icon={<Info className="h-4 w-4" />} />
      ))}
    </div>
  );
};

const EmptyStateStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  return <EmptyState title={text.emptyTitle} description={text.emptyDescription} icon={<Bell className="h-6 w-6" />} action={scenario === 'states' ? undefined : <Button variant="secondary">{text.secondaryAction}</Button>} />;
};

const InlineAlertStory = () => {
  const text = useSampleText();
  const alerts = [
    { variant: 'info' as const, title: text.info },
    { variant: 'success' as const, title: text.success },
    { variant: 'warning' as const, title: text.warning },
    { variant: 'danger' as const, title: text.error },
  ];
  return <div className="space-y-3">{alerts.map((item) => <InlineAlert key={item.variant} variant={item.variant} title={item.title} message={text.preview} />)}</div>;
};

const StickyActionBarStory = () => {
  const text = useSampleText();
  return (
    <div className="min-h-96 space-y-5">
      <Surface>{text.preview}</Surface>
      <StickyActionBar>
        <Button variant="secondary">{text.secondaryAction}</Button>
        <Button variant="primary">{text.primaryAction}</Button>
      </StickyActionBar>
    </div>
  );
};

const ToolbarStory = () => {
  const text = useSampleText();
  return <Toolbar aria-label={text.filter} left={<SearchInput aria-label={text.searchPlaceholder} placeholder={text.searchPlaceholder} />} right={<><Button variant="secondary">{text.secondaryAction}</Button><IconButton variant="outline" aria-label={text.primaryAction}><Save /></IconButton></>} />;
};

const FilterBarStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [applied, setApplied] = useState(true);
  return (
    <CommonSurface level="section" padding="md">
      <FilterBar
        aria-label={text.filter}
        applyLabel={text.primaryAction}
        loadingLabel={text.loadingAction}
        onApply={() => setApplied(true)}
        isApplying={scenario === 'states'}
        advanced={(
          <AdvancedFilterSheet
            triggerLabel={text.details}
            triggerAriaLabel={text.details}
            activeCount={applied ? 1 : 0}
            title={text.details}
            resetLabel={text.quietAction}
            applyLabel={text.primaryAction}
            onReset={() => setApplied(false)}
            onApply={() => true}
          >
            <Input label={text.fieldLabel} placeholder={text.inputPlaceholder} />
          </AdvancedFilterSheet>
        )}
        applied={applied ? (
          <AppliedFilterChips
            aria-label={text.filter}
            clearAllLabel={text.quietAction}
            onClearAll={() => setApplied(false)}
            filters={[{ id: 'market', label: text.optionOne, value: 'CN', removeLabel: text.close, onRemove: () => setApplied(false) }]}
          />
        ) : undefined}
      >
        <Input label={text.optionOne} placeholder={text.inputPlaceholder} />
        <Select label={text.optionTwo} value="one" onChange={() => undefined} options={[{ value: 'one', label: text.optionOne }]} />
      </FilterBar>
    </CommonSurface>
  );
};

const AppliedFilterChipsStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [filters, setFilters] = useState(scenario === 'empty' ? [] : [
    { id: 'market', label: text.optionOne, value: 'CN' },
    { id: 'status', label: text.optionTwo, value: text.success },
  ]);
  return (
    <CommonSurface level="section" padding="md">
      <AppliedFilterChips
        aria-label={text.filter}
        clearAllLabel={text.quietAction}
        onClearAll={() => setFilters([])}
        filters={filters.map((filter) => ({
          ...filter,
          removeLabel: `${text.close}: ${filter.label}`,
          onRemove: () => setFilters((current) => current.filter((item) => item.id !== filter.id)),
        }))}
      />
      {filters.length === 0 ? <p className="text-sm text-muted-text">{text.emptyTitle}</p> : null}
    </CommonSurface>
  );
};

const FilterChipStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [visible, setVisible] = useState(true);
  return visible ? (
    <FilterChip
      label={text.optionOne}
      value="CN"
      removeLabel={text.close}
      disabled={scenario === 'states'}
      onClick={() => setVisible(false)}
    />
  ) : <Button variant="secondary" onClick={() => setVisible(true)}>{text.primaryAction}</Button>;
};

const AdvancedFilterSheetStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [activeCount, setActiveCount] = useState(2);
  return (
    <AdvancedFilterSheet
      triggerLabel={text.details}
      triggerAriaLabel={text.details}
      activeCount={activeCount}
      title={text.details}
      description={text.fieldHint}
      resetLabel={text.quietAction}
      applyLabel={text.primaryAction}
      loadingLabel={text.loadingAction}
      onReset={() => setActiveCount(0)}
      onApply={() => true}
      triggerDisabled={scenario === 'states'}
    >
      <Input label={text.optionOne} placeholder={text.inputPlaceholder} />
      <Select label={text.optionTwo} value="one" onChange={() => undefined} options={[{ value: 'one', label: text.optionOne }, { value: 'two', label: text.optionTwo }]} />
    </AdvancedFilterSheet>
  );
};

type PreviewTableRow = { id: number; symbol: string; price: number; change: number };

const DataTableStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [sort, setSort] = useState<{ columnId: string; direction: 'ascending' | 'descending' }>({ columnId: 'symbol', direction: 'ascending' });
  const [selected, setSelected] = useState<number | null>(null);
  const rows: PreviewTableRow[] = scenario === 'empty' ? [] : [
    { id: 1, symbol: '600519', price: 1482.5, change: 1.28 },
    { id: 2, symbol: 'AAPL', price: 214.6, change: -0.35 },
  ];
  const columns: DataTableColumn<PreviewTableRow>[] = [
    { id: 'symbol', header: text.optionOne, cell: (row) => <span className="font-mono">{row.symbol}</span>, sortControl: { ariaLabel: text.filter } },
    { id: 'price', header: text.optionTwo, cell: (row) => row.price.toFixed(2), align: 'end' },
    { id: 'change', header: text.optionThree, cell: (row) => `${row.change > 0 ? '+' : ''}${row.change}%`, align: 'end' },
  ];
  const status = scenario === 'loading'
    ? { state: 'loading' as const, title: text.loadingAction, description: text.loadingDescription }
    : scenario === 'error'
      ? { state: 'error' as const, title: text.error, description: text.fieldError, action: <Button variant="secondary">{text.retry}</Button> }
      : undefined;
  return (
    <div className="space-y-3">
      <DataTable
        caption={text.preview}
        scrollAreaLabel={text.preview}
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.id}
        emptyState={{ title: text.emptyTitle, description: text.emptyDescription }}
        status={status}
        sort={sort}
        onSortChange={setSort}
        onRowActivate={(row) => setSelected(row.id)}
        getRowAriaLabel={(row) => `${text.details}: ${row.symbol}`}
      />
      {selected ? <p className="text-sm text-secondary-text">{text.optionOne}: {selected}</p> : null}
    </div>
  );
};

const ToastViewportStory = () => {
  const text = useSampleText();
  return <><Surface>{text.preview}</Surface><ToastViewport><InlineAlert variant="success" title={text.success} message={text.preview} /></ToastViewport></>;
};

const ToastProviderTrigger = () => {
  const text = useSampleText();
  const { showToast, clearToasts } = useToast();
  return (
    <Surface className="flex flex-wrap gap-3">
      <Button variant="primary" onClick={() => showToast({ title: text.success, message: text.confirmMessage, tone: 'success', durationMs: 0 })}>{text.primaryAction}</Button>
      <Button variant="secondary" onClick={clearToasts}>{text.close}</Button>
    </Surface>
  );
};

const ToastProviderStory = () => <ToastProvider maxVisible={3}><ToastProviderTrigger /></ToastProvider>;

const PageHeaderStory = () => {
  const text = useSampleText();
  return <PageHeader eyebrow={text.preview} title={text.pageHeaderLabel} description={text.fieldHint} actions={<Button variant="primary">{text.primaryAction}</Button>} />;
};

const InputStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'sizes') {
    return <Surface className="grid max-w-lg gap-4">{(['default', 'comfortable', 'primary'] as const).map((size) => <Input key={size} size={size} label={size} placeholder={text.inputPlaceholder} />)}</Surface>;
  }
  return (
    <Surface className="grid max-w-lg gap-4">
      <Input label={text.fieldLabel} hint={text.fieldHint} placeholder={text.inputPlaceholder} />
      <Input label={text.fieldLabel} error={scenario === 'states' ? text.fieldError : undefined} placeholder={text.inputPlaceholder} />
      <Input label={text.fieldLabel} disabled value={text.preview} readOnly />
    </Surface>
  );
};

const CredentialInputStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('fixture-secret');
  return (
    <Surface className="max-w-lg">
      <CredentialInput
        purpose="provider-secret"
        label={text.fieldLabel}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        allowTogglePassword
        iconType="key"
        disabled={scenario === 'states'}
      />
    </Surface>
  );
};

const DatePickerStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('2026-07-20');
  return <Surface className="max-w-sm"><DatePicker value={value} onChange={setValue} label={text.fieldLabel} ariaLabel={text.fieldLabel} error={scenario === 'states' ? text.fieldError : undefined} disabled={scenario === 'states'} /></Surface>;
};

const TimePickerStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('18:00');
  return <Surface className="max-w-sm"><TimePicker value={value} onChange={setValue} label={text.fieldLabel} ariaLabel={text.fieldLabel} disabled={scenario === 'states'} /></Surface>;
};

const EyeToggleIconStory = () => (
  <Surface className="flex items-center gap-6">
    <EyeToggleIcon visible={false} />
    <EyeToggleIcon visible />
  </Surface>
);

const LoadingStory = () => {
  const text = useSampleText();
  return <Surface><Loading label={text.loadingAction} /></Surface>;
};

const DrawerStory = () => {
  const text = useSampleText();
  const [open, setOpen] = useState(false);
  return <><Button variant="primary" onClick={() => setOpen(true)}>{text.primaryAction}</Button><Drawer isOpen={open} onClose={() => setOpen(false)} title={text.details} variant="detail"><p className="text-sm text-secondary-text">{text.preview}</p></Drawer></>;
};

const SheetStory = () => {
  const text = useSampleText();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>{text.details}</Button>
      <Sheet
        isOpen={open}
        onClose={() => setOpen(false)}
        title={text.details}
        description={text.fieldHint}
        footer={<Button variant="primary" onClick={() => setOpen(false)}>{text.close}</Button>}
      >
        <p className="text-sm text-secondary-text">{text.preview}</p>
      </Sheet>
    </>
  );
};

const FilterSheetStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [open, setOpen] = useState(scenario === 'states');
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>{text.filter}</Button>
      <FilterSheet
        isOpen={open}
        onClose={() => setOpen(false)}
        title={text.filter}
        description={text.fieldHint}
        resetLabel={text.quietAction}
        applyLabel={text.primaryAction}
        loadingLabel={text.loadingAction}
        onReset={() => undefined}
        onApply={() => setOpen(false)}
        isApplying={scenario === 'states'}
      >
        <Input label={text.fieldLabel} placeholder={text.inputPlaceholder} />
      </FilterSheet>
    </>
  );
};

const ScrollAreaStory = () => {
  const text = useSampleText();
  return (
    <Surface className="flex h-72 flex-col">
      <ScrollArea viewportClassName="space-y-2 pr-2">
        {Array.from({ length: 18 }, (_, index) => <div key={index} className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-secondary-text">{text.preview} {index + 1}</div>)}
      </ScrollArea>
    </Surface>
  );
};

const ApiErrorAlertStory = () => {
  const text = useSampleText();
  const error = createParsedApiError({
    title: text.error,
    message: text.fieldError,
    rawMessage: `${text.fieldError}: fixture diagnostic`,
    status: 503,
    category: 'http_error',
  });
  return <ApiErrorAlert error={error} actionLabel={text.secondaryAction} onAction={() => undefined} dismissLabel={text.quietAction} onDismiss={() => undefined} />;
};

const CollapsibleStory = () => {
  const text = useSampleText();
  return <Collapsible title={text.details} icon={<Info className="h-4 w-4" />} defaultOpen><p className="pt-2 text-sm text-secondary-text">{text.preview}</p></Collapsible>;
};

const ScoreGaugeStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [score, setScore] = useState(68);
  if (scenario === 'interactive') {
    return (
      <Surface className="flex flex-col items-center gap-5">
        <ScoreGauge score={score} />
        <input type="range" min="0" max="100" value={score} onChange={(event) => setScore(Number(event.target.value))} className="w-full max-w-sm accent-primary" aria-label={text.score} />
      </Surface>
    );
  }
  return <Surface className="flex flex-wrap items-end justify-center gap-8"><ScoreGauge score={24} size="sm" /><ScoreGauge score={52} size="md" /><ScoreGauge score={78} size="lg" /></Surface>;
};

const JsonViewerStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <JsonViewer data={scenario === 'empty' ? null : { component: 'JsonViewer', enabled: true, score: 68, values: ['one', 'two'] }} maxHeight="320px" />;
};

const SelectStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('one');
  return <Surface className="max-w-sm"><Select value={value} onChange={setValue} label={text.fieldLabel} options={[{ value: 'one', label: text.optionOne }, { value: 'two', label: text.optionTwo }, { value: 'three', label: text.optionThree }]} disabled={scenario === 'states'} error={scenario === 'states'} className="w-full [&>div]:w-full" /></Surface>;
};

const SearchableSelectStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState(scenario === 'states' ? 'stale-value' : 'one');
  return <Surface className="max-w-lg"><SearchableSelect value={value} onChange={setValue} options={[{ value: 'one', label: text.optionOne, group: text.preview }, { value: 'two', label: text.optionTwo, sublabel: text.fieldHint, group: text.preview }, { value: 'three', label: text.optionThree, disabled: true }]} ariaLabel={text.fieldLabel} clearable staleValueLabel={text.warning} staleValueText={text.warning} /></Surface>;
};

const SwitchStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [checked, setChecked] = useState(true);
  return <Surface className="flex items-center gap-4"><Switch checked={checked} onCheckedChange={setChecked} aria-label={text.optionOne} /><Switch checked={false} onCheckedChange={() => undefined} aria-label={text.optionTwo} disabled={scenario === 'states'} /></Surface>;
};

const BadgeStory = () => {
  const variants = ['default', 'success', 'warning', 'danger', 'info', 'history', 'trend-up', 'trend-down'] as const;
  return <Surface className="flex flex-wrap gap-3">{variants.map((variant) => <Badge key={variant} variant={variant}>{variant === 'success' ? <Check className="h-3 w-3" /> : null}{variant}</Badge>)}</Surface>;
};

const StatusDotStory = () => {
  const variants = ['success', 'warning', 'danger', 'info', 'neutral'] as const;
  return <Surface className="flex flex-wrap items-center gap-6">{variants.map((tone) => <span key={tone} className="inline-flex items-center gap-2 text-sm text-secondary-text"><StatusDot tone={tone} aria-label={tone} />{tone}</span>)}</Surface>;
};

const TooltipStory = () => {
  const text = useSampleText();
  return <Surface className="flex min-h-32 items-center justify-center"><Tooltip content={text.details}><Button variant="secondary">{text.preview}</Button></Tooltip></Surface>;
};

const PopoverStory = () => {
  const text = useSampleText();
  return (
    <Surface className="flex min-h-48 items-start justify-center">
      <Popover
        trigger={({ toggle }) => <Button variant="secondary" onClick={toggle}>{text.details}</Button>}
        contentClassName="left-0 top-full mt-2 w-56 p-3"
      >
        <p className="text-sm text-secondary-text">{text.preview}</p>
      </Popover>
    </Surface>
  );
};

const PaginationStory = () => {
  const [page, setPage] = useState(4);
  return <Surface><Pagination currentPage={page} totalPages={12} onPageChange={setPage} /></Surface>;
};

const ConfirmDialogStory = () => {
  const text = useSampleText();
  const { scenario } = usePlaygroundScenario();
  const [open, setOpen] = useState(false);
  return <><Button variant="danger" onClick={() => setOpen(true)}>{text.destructiveAction}</Button><ConfirmDialog isOpen={open} title={text.confirmTitle} message={text.confirmMessage} confirmText={text.primaryAction} error={scenario === 'error' ? text.fieldError : null} isDanger onConfirm={() => setOpen(false)} onCancel={() => setOpen(false)} /></>;
};

const ModalStory = () => {
  const text = useSampleText();
  const [open, setOpen] = useState(false);
  return <><Button variant="primary" onClick={() => setOpen(true)}>{text.details}</Button><Modal isOpen={open} onClose={() => setOpen(false)} title={text.details} description={text.fieldHint}><p className="text-sm text-secondary-text">{text.preview}</p></Modal></>;
};

export const COMMON_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  button: ButtonStory,
  'selection-chip': SelectionChipStory,
  'icon-button': IconButtonStory,
  field: FieldStory,
  textarea: TextareaStory,
  'segmented-control': SegmentedControlStory,
  'search-input': SearchInputStory,
  'notification-panel': NotificationPanelStory,
  surface: CommonSurfaceStory,
  section: SectionStory,
  'state-panel': StatePanelStory,
  alert: AlertStory,
  card: CardStory,
  checkbox: CheckboxStory,
  'app-page': AppPageStory,
  'workspace-page': WorkspacePageStory,
  'responsive-filter-panel': ResponsiveFilterPanelStory,
  'responsive-rail': ResponsiveRailStory,
  'workspace-navigation': WorkspaceNavigationStory,
  tabs: TabsStory,
  'tab-panel': TabPanelStory,
  'summary-strip': SummaryStripStory,
  'section-card': SectionCardStory,
  'stat-card': StatCardStory,
  'empty-state': EmptyStateStory,
  'inline-alert': InlineAlertStory,
  'sticky-action-bar': StickyActionBarStory,
  toolbar: ToolbarStory,
  'filter-bar': FilterBarStory,
  'applied-filter-chips': AppliedFilterChipsStory,
  'filter-chip': FilterChipStory,
  'advanced-filter-sheet': AdvancedFilterSheetStory,
  'data-table': DataTableStory,
  'toast-viewport': ToastViewportStory,
  'toast-provider': ToastProviderStory,
  'page-header': PageHeaderStory,
  input: InputStory,
  'credential-input': CredentialInputStory,
  'date-picker': DatePickerStory,
  'time-picker': TimePickerStory,
  'eye-toggle-icon': EyeToggleIconStory,
  loading: LoadingStory,
  drawer: DrawerStory,
  sheet: SheetStory,
  'filter-sheet': FilterSheetStory,
  'scroll-area': ScrollAreaStory,
  'api-error-alert': ApiErrorAlertStory,
  collapsible: CollapsibleStory,
  'score-gauge': ScoreGaugeStory,
  'json-viewer': JsonViewerStory,
  select: SelectStory,
  'searchable-select': SearchableSelectStory,
  switch: SwitchStory,
  badge: BadgeStory,
  'status-dot': StatusDotStory,
  tooltip: TooltipStory,
  popover: PopoverStory,
  pagination: PaginationStory,
  'confirm-dialog': ConfirmDialogStory,
  modal: ModalStory,
};
