import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider } from 'next-themes';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { installPlaygroundApiMock } from '../mockApi';
import { PlaygroundScenarioProvider } from '../scenarioContext';
import { COMMON_SCENARIOS } from '../scenarios/commonScenarios';
import { DECISION_REPORT_RUN_FLOW_SCENARIOS } from '../scenarios/decisionReportRunFlowScenarios';
import { SETTINGS_SCENARIOS } from '../scenarios/settingsScenarios';
import { ALERT_HISTORY_SCENARIOS } from '../scenarios/alertHistoryScenarios';

let sandbox: ReturnType<typeof installPlaygroundApiMock> | null = null;

function createPlaygroundQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderStory(Renderer: React.ComponentType, scenario = 'default') {
  const queryClient = createPlaygroundQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="dark">
        <UiLanguageProvider initialLanguage="en">
          <MemoryRouter>
            <PlaygroundScenarioProvider profile="ready" scenario={scenario as 'default'}>
              <Renderer />
            </PlaygroundScenarioProvider>
          </MemoryRouter>
        </UiLanguageProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  sandbox?.restore();
  sandbox = null;
});

describe('representative playground scenarios', () => {
  it('renders shared variants and keeps modal focus/Escape behavior real', async () => {
    renderStory(COMMON_SCENARIOS.modal, 'interactive');

    const trigger = screen.getByRole('button', { name: 'Component details' });
    trigger.focus();
    fireEvent.click(trigger);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it('renders report and run-flow fixtures through the production components', () => {
    const ReportStory = DECISION_REPORT_RUN_FLOW_SCENARIOS['report-overview'];
    const FlowStory = DECISION_REPORT_RUN_FLOW_SCENARIOS['run-flow-summary-bar'];
    const { unmount } = renderStory(ReportStory);
    expect(screen.getByText('Kweichow Moutai')).toBeInTheDocument();
    unmount();

    renderStory(FlowStory);
    expect(screen.getByText(/fixture-task-101/)).toBeInTheDocument();
  });

  it('keeps the settings multi-select interactive', () => {
    const Story = SETTINGS_SCENARIOS['multi-select-dropdown'];
    renderStory(Story, 'interactive');

    fireEvent.click(screen.getByRole('button', { name: 'Component details' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Option two' }));
    expect(screen.getByRole('button', { name: 'Component details' })).toHaveTextContent('2 of 3 selected');
  });

  it('renders the local model center from deterministic catalog and runtime fixtures', async () => {
    sandbox = installPlaygroundApiMock('ready', { delayResponse: 0 });
    const Story = SETTINGS_SCENARIOS['local-models-panel'];
    renderStory(Story);

    expect(await screen.findByRole('heading', { name: 'Local Models' })).toBeInTheDocument();
    expect(screen.getByText('Qwen 2.5 7B Instruct')).toBeInTheDocument();
    expect(screen.getByText('Finance Qwen 7B')).toBeInTheDocument();
    expect(screen.getByText('Offline Finance Q4')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import Model Pack' })).toBeEnabled();
    expect(screen.queryByText('playground_mock_not_registered')).not.toBeInTheDocument();
  });

  it('renders a network-owned report story entirely from the iframe API sandbox', async () => {
    sandbox = installPlaygroundApiMock('ready', { delayResponse: 0 });
    const Story = DECISION_REPORT_RUN_FLOW_SCENARIOS['report-news'];
    renderStory(Story);

    expect(await screen.findByText('Earnings visibility improves')).toBeInTheDocument();
    expect(screen.getByText('Sector breadth expands')).toBeInTheDocument();
  });

  it('renders the complete Alerts workspace from deterministic playground APIs', async () => {
    sandbox = installPlaygroundApiMock('ready', { delayResponse: 0 });
    const Story = ALERT_HISTORY_SCENARIOS['alerts-workspace'];
    renderStory(Story);

    expect(await screen.findByText('Price breakout')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Trigger history' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Notification attempts' }));

    expect(await screen.findByText('fixture-notification-701')).toBeInTheDocument();
    expect(screen.queryByText('playground_mock_not_registered')).not.toBeInTheDocument();
  });
});
