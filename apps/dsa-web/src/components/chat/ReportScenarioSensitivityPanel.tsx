import React from 'react';
import { AlertTriangle } from 'lucide-react';
import type { UiTextKey } from '../../i18n/uiText';
import { SCENARIO_LIBRARY_VERSION, type LibraryScenario, type ScenarioRiskFraming } from './scenarioLibrary';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export interface ReportSensitivityProjection {
  catalog_version: string;
  scenario: LibraryScenario;
  risk_framing: ScenarioRiskFraming;
  hypothetical: true;
  summary: string;
}

export interface ReportScenarioSensitivityPanelProps {
  t: Translate;
  projection: ReportSensitivityProjection;
}

/**
 * Deterministic report-sensitivity preview for a library scenario.
 * Always labeled hypothetical; never presented as a baseline conclusion.
 */
export function ReportScenarioSensitivityPanel({
  t,
  projection,
}: ReportScenarioSensitivityPanelProps): React.ReactElement {
  const framing = projection.risk_framing;
  return (
    <div
      className="space-y-2 rounded-lg border border-warning/40 bg-warning/5 p-3"
      data-testid="report-scenario-sensitivity-panel"
      data-hypothetical="true"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-semibold text-foreground" data-testid="report-scenario-sensitivity-badge">
            {t('chat.whatIf.library.sensitivityBadge')}
          </p>
          <p className="text-xs text-secondary-text">{t('chat.whatIf.library.sensitivityHint')}</p>
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div>
          <dt className="text-muted-text">{t('chat.whatIf.library.catalogVersion')}</dt>
          <dd className="font-medium" data-testid="report-scenario-catalog-version">
            {projection.catalog_version || SCENARIO_LIBRARY_VERSION}
          </dd>
        </div>
        <div>
          <dt className="text-muted-text">{t('chat.whatIf.library.scenarioName')}</dt>
          <dd className="font-medium truncate" title={projection.scenario.name}>
            {projection.scenario.name}
          </dd>
        </div>
        <div>
          <dt className="text-muted-text">{t('chat.whatIf.library.uncertainty')}</dt>
          <dd className="font-medium" data-testid="report-scenario-uncertainty">
            {framing.uncertainty_level}
          </dd>
        </div>
        <div>
          <dt className="text-muted-text">{t('chat.whatIf.library.positionSizing')}</dt>
          <dd className="font-medium" data-testid="report-scenario-position-sizing">
            {framing.position_sizing}
          </dd>
        </div>
      </dl>
      {framing.section_deltas.length > 0 ? (
        <ul className="space-y-1 text-xs text-secondary-text" data-testid="report-scenario-section-deltas">
          {framing.section_deltas.map((item) => (
            <li key={`${item.section}-${item.direction}`}>
              <span className="font-medium text-foreground">{item.section}</span>
              {' · '}
              {item.direction}
              {item.note ? ` — ${item.note}` : ''}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-xs text-warning" data-testid="report-scenario-summary">
        {projection.summary}
      </p>
    </div>
  );
}
