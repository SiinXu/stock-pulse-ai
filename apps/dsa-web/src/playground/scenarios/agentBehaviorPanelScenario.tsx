import { useState } from 'react';
import { Button } from '../../components/common';
import { SettingsAgentOnboardingHost } from '../../components/onboarding/SettingsAgentOnboardingHost';
import { AiOverviewMatrix } from '../../components/settings/AiOverviewMatrix';
import { AgentBehaviorPanel } from '../../components/settings/AgentBehaviorPanel';
import { SettingsModeToggle, type SettingsDisplayMode } from '../../components/settings/SettingsModeToggle';
import {
  AGENT_PRESET_MANAGED_KEYS,
  AGENT_SETUP_PRESETS,
} from '../../components/settings/agentSetupPresets';
import {
  getCategoryFieldGroupId,
  getCategoryFieldGroupOrder,
  getCategoryFieldOrder,
} from '../../components/settings/categoryFieldGroups';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import type { SetupStatusResponse, SystemConfigItem } from '../../types/systemConfig';
import { usePlaygroundScenario } from '../scenarioContext';

const MODEL_REF = 'modelref:v1:fixture:fixture%2Ffixture-route';
const PERSISTED_VALUES: Record<string, string> = {
  ...AGENT_SETUP_PRESETS.find((preset) => preset.id === 'standard_research')!.values,
  AGENT_LITELLM_MODEL: MODEL_REF,
  AGENT_RISK_OVERRIDE: 'true',
  VALUATION_AGENT_TOOL_ENABLED: 'false',
};

const makeItem = (key: string, value: string, displayOrder: number): SystemConfigItem => ({
  key,
  value,
  rawValueExists: value.length > 0,
  isMasked: false,
  schema: {
    key,
    category: 'agent',
    dataType: key.includes('STEPS') || key.includes('TIMEOUT')
      ? 'integer'
      : key.includes('ENABLED') || key === 'AGENT_MODE' || key === 'AGENT_FEATURES_ACKNOWLEDGED_OFF'
        ? 'boolean'
        : 'string',
    uiControl: key.includes('STEPS') || key.includes('TIMEOUT')
      ? 'number'
      : key.includes('ENABLED') || key === 'AGENT_MODE' || key === 'AGENT_FEATURES_ACKNOWLEDGED_OFF'
        ? 'switch'
        : 'text',
    isSensitive: false,
    isRequired: false,
    isEditable: true,
    options: [],
    validation: {},
    displayOrder,
  },
});

const ITEMS = [
  ...AGENT_PRESET_MANAGED_KEYS,
  'AGENT_SKILLS',
  'AGENT_SKILL_DIR',
  'AGENT_RISK_OVERRIDE',
  'VALUATION_AGENT_TOOL_ENABLED',
].map((key, index) => makeItem(key, PERSISTED_VALUES[key] ?? '', index + 1));

const SETUP_STATUS: SetupStatusResponse = {
  isComplete: false,
  readyForSmoke: false,
  requiredMissingKeys: ['LITELLM_MODEL'],
  nextStepKey: 'llm_primary',
  checks: [
    {
      key: 'llm_primary',
      title: 'Primary model',
      category: 'ai_model',
      required: true,
      status: 'needs_action',
      message: 'Primary model is not configured.',
      nextStep: 'Configure a primary model in Settings.',
    },
    {
      key: 'auth',
      title: 'Authentication',
      category: 'system',
      required: false,
      status: 'optional',
      message: 'Password login is optional for local use.',
    },
  ],
};

export const AiOverviewMatrixStory = () => {
  const { language } = useUiLanguage();
  const { scenario } = usePlaygroundScenario();
  const values: Record<string, string> = scenario === 'states'
    ? { GENERATION_BACKEND: 'litellm', LITELLM_MODEL: 'unavailable/route' }
    : {
        GENERATION_BACKEND: 'litellm',
        LITELLM_MODEL: MODEL_REF,
        AGENT_LITELLM_MODEL: MODEL_REF,
        VISION_MODEL: MODEL_REF,
        LITELLM_FALLBACK_MODELS: 'fixture/fixture-route-fast',
      };
  return (
    <AiOverviewMatrix
      getValue={(key) => values[key] ?? ''}
      language={language}
      availableRoutes={new Set([MODEL_REF])}
      onEditRouting={() => undefined}
    />
  );
};

export const SettingsAgentOnboardingHostStory = () => {
  const { language, t } = useUiLanguage();
  const [open, setOpen] = useState(true);
  return (
    <div className="space-y-3">
      <Button variant="primary" onClick={() => setOpen(true)}>
        {PLAYGROUND_TEXT[language].samples.openAgentOnboarding}
      </Button>
      <SettingsAgentOnboardingHost
        open={open}
        onClose={() => setOpen(false)}
        onApplied={() => setOpen(false)}
        setupStatus={SETUP_STATUS}
        reportLanguage="en"
        t={t}
      />
    </div>
  );
};

export const SettingsModeToggleStory = () => {
  const { language } = useUiLanguage();
  const [mode, setMode] = useState<SettingsDisplayMode>('essentials');
  return <SettingsModeToggle mode={mode} onModeChange={setMode} language={language} />;
};

const AgentBehaviorPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [draftValues, setDraftValues] = useState(PERSISTED_VALUES);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'scheduled'>('idle');
  const items = (scenario === 'empty' ? ITEMS.slice(1) : ITEMS)
    .map((item) => ({ ...item, value: draftValues[item.key] ?? item.value }));

  return (
    <div className="mx-auto max-w-5xl">
      <AgentBehaviorPanel
        items={items}
        disabled={false}
        onChange={(key, value) => {
          setDraftValues((current) => ({ ...current, [key]: value }));
          setSaveStatus('scheduled');
        }}
        onBatchChange={(updates) => {
          setDraftValues((current) => ({
            ...current,
            ...Object.fromEntries(updates.map((item) => [item.key, item.value])),
          }));
          setSaveStatus('scheduled');
        }}
        onResetKeys={(keys) => {
          setDraftValues((current) => ({
            ...current,
            ...Object.fromEntries(keys.map((key) => [key, PERSISTED_VALUES[key] ?? ''])),
          }));
          setSaveStatus('idle');
        }}
        issueByKey={{}}
        draftValuesByKey={draftValues}
        persistedValuesByKey={PERSISTED_VALUES}
        saveStatus={saveStatus}
        modelSummary={{
          value: 'Fixture Route · Fixture Cloud',
          source: 'explicit',
          readiness: scenario === 'error' ? 'unknown' : 'ready',
        }}
        fieldGroups={getCategoryFieldGroupOrder('agent') ?? []}
        fieldGroupIdOf={(key) => getCategoryFieldGroupId('agent', key)}
        fieldGroupOrderOf={(key) => getCategoryFieldOrder('agent', key)}
      />
    </div>
  );
};

const AgentSettingsStory = ({ story }: { story: 'overview' | 'onboarding' | 'mode' | 'presets' }) => {
  if (story === 'overview') return <AiOverviewMatrixStory />;
  if (story === 'onboarding') return <SettingsAgentOnboardingHostStory />;
  if (story === 'mode') return <SettingsModeToggleStory />;
  return <AgentBehaviorPanelStory />;
};

export default AgentSettingsStory;
