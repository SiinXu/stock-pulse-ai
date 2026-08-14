/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState } from 'react';
import { Surface } from '../../components/common';
import { ScoreGauge } from '../../components/report/ScoreGauge';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const ScoreGaugeStory = () => {
  const { language } = useUiLanguage();
  const text = PLAYGROUND_TEXT[language].samples;
  const { scenario } = usePlaygroundScenario();
  const [score, setScore] = useState(68);
  if (scenario === 'interactive') {
    return (
      <Surface className="flex flex-col items-center gap-5">
        <ScoreGauge score={score} />
        <input
          type="range"
          min="0"
          max="100"
          value={score}
          onChange={(event) => setScore(Number(event.target.value))}
          className="w-full max-w-sm accent-primary"
          aria-label={text.score}
        />
      </Surface>
    );
  }
  return (
    <Surface className="flex flex-wrap items-end justify-center gap-8">
      <ScoreGauge score={24} size="sm" />
      <ScoreGauge score={52} size="md" />
      <ScoreGauge score={78} size="lg" />
    </Surface>
  );
};

export const REPORT_COMPONENT_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'score-gauge': ScoreGaugeStory,
};
