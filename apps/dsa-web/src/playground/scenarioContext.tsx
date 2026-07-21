import { createContext, useContext } from 'react';
import type React from 'react';
import type { PlaygroundFixtureProfile, PlaygroundScenarioId } from './types';

type PlaygroundScenarioContextValue = {
  profile: PlaygroundFixtureProfile;
  scenario: PlaygroundScenarioId;
};

const PlaygroundScenarioContext = createContext<PlaygroundScenarioContextValue>({
  profile: 'ready',
  scenario: 'default',
});

export const PlaygroundScenarioProvider: React.FC<PlaygroundScenarioContextValue & { children: React.ReactNode }> = ({
  profile,
  scenario,
  children,
}) => (
  <PlaygroundScenarioContext.Provider value={{ profile, scenario }}>
    {children}
  </PlaygroundScenarioContext.Provider>
);

// eslint-disable-next-line react-refresh/only-export-components -- The hook is the context's public consumer API.
export function usePlaygroundScenario() {
  return useContext(PlaygroundScenarioContext);
}
