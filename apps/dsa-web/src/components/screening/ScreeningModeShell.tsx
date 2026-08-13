import type React from 'react';
import type { Ref } from 'react';
import { lazy, Suspense } from 'react';
import { Button, Surface } from '../common';
import ScreeningPageHeader from './ScreeningPageHeader';
import type { DiscoveryScreeningText } from './screeningText';

const ScreeningDiscoveryPanel = lazy(() => import('./ScreeningDiscoveryPanel'));

export type ScreeningMode = 'strategy' | 'discovery';

export type ScreeningModeShellProps = {
  text: DiscoveryScreeningText;
  mode: ScreeningMode;
  strategyEnabled: boolean;
  strategyStatus: string;
  onModeChange: (mode: ScreeningMode) => void;
  headingRef?: Ref<HTMLHeadingElement>;
};

const ScreeningModeShell: React.FC<ScreeningModeShellProps> = ({
  text,
  mode,
  strategyEnabled,
  strategyStatus,
  onModeChange,
  headingRef,
}) => (
  <>
    <ScreeningPageHeader
      text={text}
      enabled={mode === 'discovery' || strategyEnabled}
      status={mode === 'discovery' ? text.discoveryStatusReady : strategyStatus}
      title={text.pageTitle ?? text.title}
      description={text.pageDescription ?? text.description}
      headingRef={headingRef}
    />

    <Surface
      as="section"
      level="interactive"
      padding="none"
      className="flex flex-wrap gap-2 p-3"
      role="group"
      aria-label={text.pageTitle ?? text.title}
    >
      <Button
        type="button"
        size="compact"
        variant={mode === 'discovery' ? 'primary' : 'secondary'}
        aria-pressed={mode === 'discovery'}
        onClick={() => onModeChange('discovery')}
      >
        {text.modeDiscovery}
      </Button>
      <Button
        type="button"
        size="compact"
        variant={mode === 'strategy' ? 'primary' : 'secondary'}
        aria-pressed={mode === 'strategy'}
        onClick={() => onModeChange('strategy')}
      >
        {text.modeStrategy}
      </Button>
    </Surface>

    {mode === 'discovery' ? (
      <Suspense
        fallback={(
          <Surface as="section" level="interactive" padding="none" className="p-4">
            <p role="status" className="text-sm text-secondary-text">{text.discoveryTitle}</p>
          </Surface>
        )}
      >
        <ScreeningDiscoveryPanel text={text} />
      </Suspense>
    ) : null}
  </>
);

export default ScreeningModeShell;
