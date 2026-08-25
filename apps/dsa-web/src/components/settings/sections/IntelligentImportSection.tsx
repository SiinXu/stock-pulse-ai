// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useState } from 'react';
import { Button, Modal } from '../../common';
import {
  IntelligentImport,
  SettingsSectionCard,
} from '..';
import type { UiTextKey } from '../../../i18n/uiText';
import type { SystemConfigItem } from '../../../types/systemConfig';

type IntelligentImportSectionProps = {
  activeCategory: string;
  activeItems: SystemConfigItem[];
  configVersion: string;
  maskToken: string;
  isSaving: boolean;
  isLoading: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
  applyPostSaveEffects: () => void;
};

const IntelligentImportSection: React.FC<IntelligentImportSectionProps> = (props) => {
  const [isIntelligentImportOpen, setIsIntelligentImportOpen] = useState(false);
  if (props.activeCategory !== 'base') return null;

  return (
    <>
      <SettingsSectionCard
        title={props.t('settings.intelligentImport')}
        description={props.t('settings.intelligentImportDescription')}
        actions={(
          <Button
            type="button"
            variant="secondary"
            size="default"
            aria-haspopup="dialog"
            onClick={() => setIsIntelligentImportOpen(true)}
          >
            {props.t('settings.openConfigItems')}
          </Button>
        )}
      >
        <p className="text-xs leading-6 text-muted-text">
          {props.t('settings.intelligentImportSupportedInputs')}
          {' · '}
          {props.t('settings.intelligentImportHint')}
        </p>
      </SettingsSectionCard>
      <Modal
        isOpen={isIntelligentImportOpen}
        onClose={() => setIsIntelligentImportOpen(false)}
        title={props.t('settings.intelligentImport')}
        description={props.t('settings.intelligentImportDescription')}
        size="wide"
      >
        <IntelligentImport
          stockListValue={
            (props.activeItems.find((i) => i.key === 'STOCK_LIST')?.value as string) ?? ''
          }
          configVersion={props.configVersion}
          maskToken={props.maskToken}
          onMerged={async () => {
            await props.refreshAfterExternalSave(['STOCK_LIST']);
            props.applyPostSaveEffects();
          }}
          disabled={props.isSaving || props.isLoading}
        />
      </Modal>
    </>
  );
};

export default IntelligentImportSection;
