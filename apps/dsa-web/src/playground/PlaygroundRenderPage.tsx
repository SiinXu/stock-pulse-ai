import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import { useParams, useSearchParams } from 'react-router-dom';
import { InlineAlert, Loading } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { UI_LANGUAGES, type UiLanguage } from '../i18n/uiLanguages';
import { PLAYGROUND_TEXT } from '../locales/playground';
import { getPlaygroundEntry, getPlaygroundScenario } from './catalog';
import { PlaygroundScenarioProvider } from './scenarioContext';
import { hasPlaygroundRenderer, renderPlaygroundScenario } from './scenarios';
import type { PlaygroundFixtureProfile } from './types';

const FIXTURE_PROFILES: PlaygroundFixtureProfile[] = ['ready', 'empty', 'error', 'slow'];

const PlaygroundRenderPage = () => {
  const { componentId, scenarioId } = useParams();
  const [searchParams] = useSearchParams();
  const { language, setLanguage } = useUiLanguage();
  const { setTheme } = useTheme();
  const [mockReadyProfile, setMockReadyProfile] = useState<PlaygroundFixtureProfile | null>(null);
  const entry = getPlaygroundEntry(componentId);
  const scenario = getPlaygroundScenario(entry, scenarioId);
  const rawProfile = searchParams.get('profile');
  const profile = FIXTURE_PROFILES.includes(rawProfile as PlaygroundFixtureProfile)
    ? rawProfile as PlaygroundFixtureProfile
    : 'ready';
  const requestedLanguage = searchParams.get('language');
  const text = PLAYGROUND_TEXT[language];
  const mockReady = mockReadyProfile === profile;

  useEffect(() => {
    const nextLanguage = UI_LANGUAGES.includes(requestedLanguage as UiLanguage)
      ? requestedLanguage as UiLanguage
      : language;
    if (nextLanguage !== language) setLanguage(nextLanguage);
  }, [language, requestedLanguage, setLanguage]);

  useEffect(() => {
    const requestedTheme = searchParams.get('theme');
    if (requestedTheme === 'light' || requestedTheme === 'dark' || requestedTheme === 'system') {
      setTheme(requestedTheme);
    }
  }, [searchParams, setTheme]);

  useEffect(() => {
    let active = true;
    let restore = () => {};

    const markReady = () => {
      if (active) setMockReadyProfile(profile);
    };

    // The mock adapter is a development dependency. Playground routes are
    // omitted from production composition, and this dynamic import must stay
    // behind the compile-time DEV flag so the adapter cannot enter the graph.
    if (import.meta.env.DEV) {
      void import('./mockApi').then(({ installPlaygroundApiMock }) => {
        if (!active) return;
        const sandbox = installPlaygroundApiMock(profile);
        restore = () => sandbox.restore();
        markReady();
      });
    } else {
      queueMicrotask(markReady);
    }

    return () => {
      active = false;
      restore();
    };
  }, [profile]);

  useEffect(() => {
    if (!mockReady) return;
    window.parent.postMessage({
      channel: 'stockpulse-playground',
      version: 1,
      type: 'ready',
    }, window.location.origin);
  }, [mockReady]);

  useEffect(() => {
    document.title = `${entry.name} - ${text.title}`;
  }, [entry.name, text.title]);

  if (!mockReady) {
    return (
      <div className="min-h-dvh bg-background">
        <Loading label={text.loadingPreview} className="min-h-dvh" />
      </div>
    );
  }

  if (!hasPlaygroundRenderer(entry.id)) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background p-4">
        <InlineAlert variant="danger" title={text.previewUnavailable} message={text.invalidScenario} />
      </div>
    );
  }

  return (
    <PlaygroundScenarioProvider profile={profile} scenario={scenario}>
      <div
        className={`min-h-dvh bg-background text-foreground ${entry.canvas === 'full' ? 'overflow-hidden' : 'p-4 sm:p-6'}`}
      >
        {renderPlaygroundScenario(entry.id)}
      </div>
    </PlaygroundScenarioProvider>
  );
};

export default PlaygroundRenderPage;
