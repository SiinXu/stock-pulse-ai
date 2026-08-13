import React, { useMemo, useState, type ReactNode } from 'react';
import { BookmarkPlus, Library } from 'lucide-react';
import type { UiTextKey } from '../../i18n/uiText';
import { Button, Input, Select } from '../common';
import type { WhatIfDraftState } from './whatIfScenario';
import { ReportScenarioSensitivityPanel } from './ReportScenarioSensitivityPanel';
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

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

interface ScenarioLibraryPanelProps {
  t: Translate;
  draft: WhatIfDraftState;
  onChange: (next: WhatIfDraftState) => void;
  disabled: boolean;
  limitReached: boolean;
  children: ReactNode;
}

/**
 * Scenario-library controls are loaded only after the user opens What-if mode.
 * This keeps the built-in catalog out of the shared chat route chunk.
 */
export default function ScenarioLibraryPanel({
  t,
  draft,
  onChange,
  disabled,
  limitReached,
  children,
}: ScenarioLibraryPanelProps): React.ReactElement {
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

  const onLibrarySelect = (scenarioId: string) => {
    if (!scenarioId) {
      onChange({ ...draft, scenarioId: null });
      return;
    }
    const scenario = scenarios.find((item) => item.id === scenarioId);
    if (scenario) onChange(applyScenarioToDraft(scenario, draft));
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
    <>
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
      {children}
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
      {sensitivity ? <ReportScenarioSensitivityPanel t={t} projection={sensitivity} /> : null}
    </>
  );
}
