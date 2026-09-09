// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { lazy, Suspense } from 'react';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import { Loading } from '../common';
import type { UiLang } from './settingsInformationArchitecture';
import { KronosSettingsFields } from './KronosSettingsFields';
import { KronosStatusPanel } from './KronosStatusPanel';

const LocalModelsPanel = lazy(() => import('./LocalModelsPanel'));

interface LocalModelsWithKronosProps {
  language: UiLang;
  onConfigurationChanged?: () => void | Promise<void>;
  kronosItems: SystemConfigItem[];
  allValuesByKey: Record<string, string>;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  disabled?: boolean;
  onKronosChange: (key: string, value: string) => void;
  readOnlyDiagnostic?: (item: SystemConfigItem) => string | null | undefined;
}

/** Local Models tab: Ollama catalog panel plus Kronos status and settings. */
export const LocalModelsWithKronos: React.FC<LocalModelsWithKronosProps> = ({
  language,
  onConfigurationChanged,
  kronosItems,
  allValuesByKey,
  issueByKey,
  disabled = false,
  onKronosChange,
  readOnlyDiagnostic,
}) => (
  <>
    <Suspense fallback={<Loading />}>
      <LocalModelsPanel language={language} onConfigurationChanged={onConfigurationChanged} />
    </Suspense>
    <KronosStatusPanel disabled={disabled} />
    <KronosSettingsFields
      items={kronosItems}
      allValuesByKey={allValuesByKey}
      issueByKey={issueByKey}
      disabled={disabled}
      onChange={onKronosChange}
      readOnlyDiagnostic={readOnlyDiagnostic}
    />
  </>
);
