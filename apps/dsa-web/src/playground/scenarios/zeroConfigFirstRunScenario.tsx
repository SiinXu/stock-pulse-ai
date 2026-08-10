import { ZeroConfigFirstRunPanel } from '../../components/onboarding/ZeroConfigFirstRunPanel';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { FirstRunReadiness } from '../../types/onboarding';
import { usePlaygroundScenario } from '../scenarioContext';

const FIXTURE_FIRST_RUN_DEMO: FirstRunReadiness = {
  schemaVersion: 1,
  isFreshEnvironment: true,
  hasPrimaryModel: false,
  beginnerModeRecommended: true,
  primaryPath: 'demo',
  primaryCta: 'view_demo',
  reasonCode: 'local_runtime_unavailable',
  reasonParams: {},
  localRuntime: {
    reachable: false,
    modelsAvailable: false,
    runnable: false,
    models: [],
    suggestedProfile: {},
    reasonCode: 'ollama_unreachable',
    detectEnabled: true,
  },
  suggestedProfile: {},
  demoAvailable: true,
  configMutated: false,
  existingConfigUntouched: true,
  snapshotId: '0123456789abcdef01234567',
  generatedAt: '2026-08-09T00:00:00Z',
};

const FIXTURE_FIRST_RUN_CONFIGURED: FirstRunReadiness = {
  ...FIXTURE_FIRST_RUN_DEMO,
  isFreshEnvironment: false,
  hasPrimaryModel: true,
  beginnerModeRecommended: false,
  primaryPath: 'configured',
  primaryCta: 'continue',
  reasonCode: 'primary_model_configured',
};

export const ZeroConfigFirstRunPanelStory = () => {
  const { t } = useUiLanguage();
  const { scenario } = usePlaygroundScenario();
  const readiness = scenario === 'empty' ? FIXTURE_FIRST_RUN_CONFIGURED : FIXTURE_FIRST_RUN_DEMO;

  return (
    <div className="max-w-2xl">
      <ZeroConfigFirstRunPanel
        readiness={readiness}
        autoLoad={false}
        reportLanguage="en"
        t={t}
      />
    </div>
  );
};
