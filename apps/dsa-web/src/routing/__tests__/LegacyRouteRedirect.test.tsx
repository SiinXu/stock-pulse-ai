import { fireEvent, render, screen } from '@testing-library/react';
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import {
  SESSION_RESTORE_SUPPRESS_STATE_KEY,
} from '../../utils/sessionContinuity';
import { LegacyRouteRedirect } from '../LegacyRedirectRoute';
import { resolveLegacyRouteRedirect } from '../legacyRouteRedirect';
import {
  APP_ROUTE_PATHS,
  LEGACY_ROUTE_PATHS,
  SETTINGS_ROUTE_QUERY_KEYS,
  SETTINGS_SECTION_IDS,
  buildSettingsHref,
} from '../routes';

function SettingsLocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="settings-location">
        {`${location.pathname}${location.search}${location.hash}`}
      </output>
      <output data-testid="settings-state">{JSON.stringify(location.state)}</output>
      <button type="button" onClick={() => navigate(-1)}>Back</button>
    </>
  );
}

describe('resolveLegacyRouteRedirect', () => {
  it('preserves query and hash while destination parameters win conflicts', () => {
    expect(resolveLegacyRouteRedirect(
      { search: '?period=today&section=legacy', hash: '#breakdown' },
      APP_ROUTE_PATHS.settings,
      {
        overrideSearchParams: {
          [SETTINGS_ROUTE_QUERY_KEYS.section]: SETTINGS_SECTION_IDS.usage,
        },
      },
    )).toEqual({
      pathname: APP_ROUTE_PATHS.settings,
      search: '?period=today&section=usage',
      hash: '#breakdown',
    });
  });

  it('supports reusable legacy parameter mapping before destination overrides', () => {
    expect(resolveLegacyRouteRedirect(
      { search: '?legacyTab=history&page=3', hash: '' },
      APP_ROUTE_PATHS.settings,
      {
        mapSearchParams: (searchParams) => {
          const legacyTab = searchParams.get('legacyTab');
          searchParams.delete('legacyTab');
          if (legacyTab) searchParams.set('tab', legacyTab);
        },
        overrideSearchParams: { tab: 'usage' },
      },
    ).search).toBe('?page=3&tab=usage');
  });
});

describe('buildSettingsHref', () => {
  it('owns the Settings path and known query-key serialization', () => {
    expect(buildSettingsHref()).toBe(APP_ROUTE_PATHS.settings);
    expect(buildSettingsHref({
      section: 'ai_models',
      view: 'connections',
      source: 'task_routing',
    })).toBe(`${APP_ROUTE_PATHS.settings}?section=ai_models&view=connections&from=task_routing`);
  });
});

describe('LegacyRouteRedirect', () => {
  it('replaces history and suppresses destination session restoration', async () => {
    render(
      <MemoryRouter
        initialEntries={[
          '/',
          {
            pathname: LEGACY_ROUTE_PATHS.usage,
            search: '?period=all',
            hash: '#recent',
            state: { source: 'bookmark' },
          },
        ]}
        initialIndex={1}
      >
        <Routes>
          <Route path="/" element={<div>Home route</div>} />
          <Route
            path={LEGACY_ROUTE_PATHS.usage}
            element={(
              <LegacyRouteRedirect
                to={APP_ROUTE_PATHS.settings}
                overrideSearchParams={{
                  [SETTINGS_ROUTE_QUERY_KEYS.section]: SETTINGS_SECTION_IDS.usage,
                }}
              />
            )}
          />
          <Route path={APP_ROUTE_PATHS.settings} element={<SettingsLocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('settings-location'))
      .toHaveTextContent(`${APP_ROUTE_PATHS.settings}?period=all&section=usage#recent`);
    expect(JSON.parse(screen.getByTestId('settings-state').textContent ?? '{}')).toEqual({
      source: 'bookmark',
      [SESSION_RESTORE_SUPPRESS_STATE_KEY]: true,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText('Home route')).toBeInTheDocument();
  });
});
