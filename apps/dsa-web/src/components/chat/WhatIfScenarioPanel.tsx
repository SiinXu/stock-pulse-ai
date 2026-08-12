import React, { useMemo, useState } from 'react';
import { BookmarkPlus, FlaskConical, Library } from 'lucide-react';
import { Button, InlineAlert, Input, Select, Switch } from '../common';
import { cn } from '../../utils/cn';
import type { UiTextKey } from '../../i18n/uiText';
import {
  DEFAULT_WHAT_IF_MAX_TURNS,
  type WhatIfDimension,
  type WhatIfDirection,
  type WhatIfDraftState,
  isWhatIfLimitReached,
  parseMagnitude,
} from './whatIfScenario';
import {
  SCENARIO_LIBRARY_VERSION,
  applyScenarioToDraft,
  deleteCustomScenario,
  draftToCustomScenarioInput,
  emptyCustomScenarioIdFromName,
  listAllScenarios,
  projectClientSensitivity,
  saveCustomScenario,
  type LibraryScenario,
} from './scenarioLibrary';
import { ReportScenarioSensitivityPanel } from './ReportScenarioSensitivityPanel';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export interface WhatIfScenarioPanelProps {
  t: Translate;
  draft: WhatIfDraftState;
  onChange: (next: WhatIfDraftState) => void;
  disabled?: boolean;
}

const DIMENSION_OPTIONS: Array<{ value: WhatIfDimension; labelKey: UiTextKey }> = [
  { value: 'index_move', labelKey: 'chat.whatIf.dimension.index' },
  { value: 'fx_rate', labelKey: 'chat.whatIf.dimension.fx' },
  { value: 'interest_rate', labelKey: 'chat.whatIf.dimension.rate' },
  { value: 'sector_shock', labelKey: 'chat.whatIf.dimension.sector' },
  { value: 'earnings', labelKey: 'chat.whatIf.dimension.earnings' },
];

export function WhatIfScenarioPanel({ t, draft, onChange, disabled = false }: WhatIfScenarioPanelProps): React.ReactElement {
  const limitReached = isWhatIfLimitReached(draft);
  const magnitudeInvalid = draft.enabled && draft.dimension !== 'earnings' && parseMagnitude(draft.magnitude) === null;
  const [libraryTick, setLibraryTick] = useState(0);
  const [saveName, setSaveName] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState(false);

  const scenarios = useMemo(() => {
    void libraryTick;
    return listAllScenarios();
  }, [libraryTick]);

  const selectedScenario: LibraryScenario | null = useMemo(() => {
    if (!draft.scenarioId) return null;
    return scenarios.find((item) => item.id === draft.scenarioId) ?? null;
  }, [draft.scenarioId, scenarios]);

  const sensitivity = useMemo(
    () => (selectedScenario ? projectClientSensitivity(selectedScenario) : null),
    [selectedScenario],
  );

  const setField = <K extends keyof WhatIfDraftState>(key: K, value: WhatIfDraftState[K]) => {
    onChange({ ...draft, [key]: value, scenarioId: key === 'enabled' || key === 'dimension' || key === 'direction' || key === 'magnitude' || key === 'currencyPair' ? null : draft.scenarioId });
  };

  const onDimensionChange = (dimension: WhatIfDimension) => {
    if (dimension === 'earnings') {
      onChange({
        ...draft,
        dimension,
        scenarioId: null,
        direction: draft.direction === 'beat' || draft.direction === 'miss' || draft.direction === 'inline' ? draft.direction : 'miss',
      });
      return;
    }
    onChange({
      ...draft,
      dimension,
      scenarioId: null,
      direction: draft.direction === 'up' || draft.direction === 'down' ? draft.direction : 'down',
    });
  };

  const onLibrarySelect = (scenarioId: string) => {
    if (!scenarioId) {
      onChange({ ...draft, scenarioId: null });
      return;
    }
    const scenario = scenarios.find((item) => item.id === scenarioId);
    if (!scenario) return;
    onChange(applyScenarioToDraft(scenario, draft));
  };

  const onSaveCustom = () => {
    setSaveError(null);
    setSaveOk(false);
    const name = saveName.trim();
    if (!name) {
      setSaveError(t('chat.whatIf.library.saveNameRequired'));
      return;
    }
    const input = draftToCustomScenarioInput(draft, {
      id: emptyCustomScenarioIdFromName(name),
      name,
    });
    if (!input) {
      setSaveError(t('chat.whatIf.magnitudeInvalid'));
      return;
    }
    try {
      const saved = saveCustomScenario(input);
      setLibraryTick((value) => value + 1);
      onChange(applyScenarioToDraft(saved, draft));
      setSaveName('');
      setSaveOk(true);
    } catch {
      setSaveError(t('chat.whatIf.library.saveFailed'));
    }
  };

  const onDeleteCustom = () => {
    if (!selectedScenario || selectedScenario.source !== 'custom') return;
    deleteCustomScenario(selectedScenario.id);
    setLibraryTick((value) => value + 1);
    onChange({ ...draft, scenarioId: null });
  };

  return (
    <div className={cn('space-y-3', draft.enabled && '[&_[data-testid=chat-what-if-trigger]]:text-warning')} data-testid="chat-what-if-panel">
      <div
        className="flex h-9 min-w-0 items-center gap-2 rounded-lg px-2 text-xs text-foreground"
        data-testid="chat-what-if-trigger"
      >
        <div className="flex min-w-0 items-center gap-2">
          <FlaskConical className="h-4 w-4 shrink-0 text-warning" aria-hidden />
          <span className="truncate font-medium">{t('chat.whatIf.title')}</span>
        </div>
        <span className="ml-auto whitespace-nowrap text-muted-text" data-testid="chat-what-if-turn-count">
          {draft.turnCount}/{DEFAULT_WHAT_IF_MAX_TURNS}
        </span>
        <Switch
          checked={draft.enabled}
          onCheckedChange={(enabled) => setField('enabled', enabled)}
          disabled={disabled || limitReached}
          aria-label={t('chat.whatIf.toggle')}
          testId="chat-what-if-toggle"
        />
      </div>
      {draft.enabled ? (
        <div className="space-y-3 border-t border-subtle pt-3" data-testid="chat-what-if-form">
          <InlineAlert variant="warning" size="compact" title={t('chat.whatIf.bannerTitle')} message={t('chat.whatIf.bannerMessage')} />
          <div className="space-y-2" data-testid="chat-scenario-library">
            <div className="flex items-center gap-2 text-xs font-medium text-foreground">
              <Library className="h-3.5 w-3.5 text-warning" aria-hidden />
              <span>{t('chat.whatIf.library.title')}</span>
              <span className="ml-auto text-muted-text" data-testid="chat-scenario-library-version">
                {t('chat.whatIf.library.versionLabel', { version: SCENARIO_LIBRARY_VERSION })}
              </span>
            </div>
            <div data-testid="chat-scenario-library-select">
              <Select
                label={t('chat.whatIf.library.selectLabel')}
                value={draft.scenarioId || ''}
                disabled={disabled || limitReached}
                onChange={onLibrarySelect}
                options={[
                  { value: '', label: t('chat.whatIf.library.manual') },
                  ...scenarios.map((item) => ({
                    value: item.id,
                    label: `${item.source === 'custom' ? '★ ' : ''}${item.name}`,
                  })),
                ]}
                className="w-full"
              />
            </div>
            <p className="text-xs text-secondary-text">{t('chat.whatIf.library.hint')}</p>
          </div>
          {limitReached ? (
            <InlineAlert variant="danger" size="compact" title={t('chat.whatIf.limitTitle')} message={t('chat.whatIf.limitMessage', { max: DEFAULT_WHAT_IF_MAX_TURNS })} />
          ) : (
            <div className="grid grid-cols-2 gap-3" data-testid="chat-what-if-fields">
              <div className="min-w-0" data-testid="chat-what-if-dimension">
                <Select
                  label={t('chat.whatIf.dimensionLabel')}
                  value={draft.dimension}
                  disabled={disabled}
                  onChange={(value) => onDimensionChange(value as WhatIfDimension)}
                  options={DIMENSION_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) }))}
                  className="w-full"
                />
              </div>
              {draft.dimension === 'earnings' ? (
                <div className="min-w-0" data-testid="chat-what-if-earnings">
                  <Select
                    label={t('chat.whatIf.outcomeLabel')}
                    value={draft.direction}
                    disabled={disabled}
                    onChange={(value) => setField('direction', value as WhatIfDirection)}
                    options={[
                      { value: 'beat', label: t('chat.whatIf.earnings.beat') },
                      { value: 'miss', label: t('chat.whatIf.earnings.miss') },
                      { value: 'inline', label: t('chat.whatIf.earnings.inline') },
                    ]}
                    className="w-full"
                  />
                </div>
              ) : (
                <>
                  <div className="min-w-0" data-testid="chat-what-if-direction">
                    <Select
                      label={t('chat.whatIf.directionLabel')}
                      value={draft.direction === 'up' || draft.direction === 'down' ? draft.direction : 'down'}
                      disabled={disabled}
                      onChange={(value) => setField('direction', value as WhatIfDirection)}
                      options={[
                        { value: 'up', label: t('chat.whatIf.direction.up') },
                        { value: 'down', label: t('chat.whatIf.direction.down') },
                      ]}
                      className="w-full"
                    />
                  </div>
                  <Input
                    label={t(draft.dimension === 'interest_rate' ? 'chat.whatIf.magnitudeBpLabel' : 'chat.whatIf.magnitudePctLabel')}
                    type="number"
                    min={0}
                    step="any"
                    value={draft.magnitude}
                    disabled={disabled}
                    onChange={(event) => setField('magnitude', event.target.value)}
                    fieldClassName="min-w-0"
                    data-testid="chat-what-if-magnitude"
                  />
                </>
              )}
              {draft.dimension === 'fx_rate' ? (
                <Input
                  label={t('chat.whatIf.fxPairLabel')}
                  type="text"
                  value={draft.currencyPair}
                  disabled={disabled}
                  onChange={(event) => setField('currencyPair', event.target.value)}
                  fieldClassName="min-w-0"
                  data-testid="chat-what-if-fx-pair"
                />
              ) : null}
            </div>
          )}
          {magnitudeInvalid ? <p className="text-xs text-danger" data-testid="chat-what-if-magnitude-error">{t('chat.whatIf.magnitudeInvalid')}</p> : null}
          <div className="space-y-2 rounded-lg border border-subtle p-2" data-testid="chat-scenario-library-save">
            <div className="flex items-center gap-2 text-xs font-medium">
              <BookmarkPlus className="h-3.5 w-3.5" aria-hidden />
              <span>{t('chat.whatIf.library.saveTitle')}</span>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <Input
                label={t('chat.whatIf.library.saveNameLabel')}
                type="text"
                value={saveName}
                disabled={disabled || limitReached}
                onChange={(event) => setSaveName(event.target.value)}
                fieldClassName="min-w-[10rem] flex-1"
                data-testid="chat-scenario-library-save-name"
              />
              <Button
                type="button"
                size="compact"
                variant="secondary"
                disabled={disabled || limitReached}
                onClick={onSaveCustom}
                data-testid="chat-scenario-library-save-btn"
              >
                {t('chat.whatIf.library.saveAction')}
              </Button>
              {selectedScenario?.source === 'custom' ? (
                <Button
                  type="button"
                  size="compact"
                  variant="ghost"
                  disabled={disabled}
                  onClick={onDeleteCustom}
                  data-testid="chat-scenario-library-delete-btn"
                >
                  {t('chat.whatIf.library.deleteAction')}
                </Button>
              ) : null}
            </div>
            {saveError ? <p className="text-xs text-danger" data-testid="chat-scenario-library-save-error">{saveError}</p> : null}
            {saveOk ? <p className="text-xs text-info" data-testid="chat-scenario-library-save-ok">{t('chat.whatIf.library.saveOk')}</p> : null}
          </div>
          {sensitivity ? (
            <ReportScenarioSensitivityPanel t={t} projection={sensitivity} />
          ) : null}
          <p className="text-xs text-secondary-text">{t('chat.whatIf.extraTurnHint')}</p>
        </div>
      ) : null}
    </div>
  );
}
