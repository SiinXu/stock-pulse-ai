import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { createAppQueryClient } from '../../../query/createAppQueryClient';
import { createDeferred } from '../../../test-utils';
import type {
  LocalModelCatalogEntry,
  LocalModelCatalogResponse,
  LocalModelRuntimeState,
} from '../../../types/localModels';
import { LocalModelsPanel } from '../LocalModelsPanel';
import type { LocalModelTransport } from '../localModelTransport';

const { getCatalog, createTransport } = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  createTransport: vi.fn(),
}));

vi.mock('../../../api/localModels', () => ({
  localModelsApi: { getCatalog },
}));

vi.mock('../localModelTransport', () => ({
  createLocalModelTransport: () => createTransport(),
  LocalModelTransportError: class LocalModelTransportError extends Error {
    code: string;

    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
}));

const GENERAL_MODEL: LocalModelCatalogEntry = {
  id: 'qwen3-4b',
  section: 'general',
  displayName: { en: 'Qwen3 4B', zh: 'Qwen3 4B' },
  capabilitySummary: { en: 'Compact local reasoning model.', zh: '轻量本地推理模型。' },
  capabilities: ['general', 'reasoning'],
  q4: {
    quantization: 'Q4_K_M',
    sizeBytes: 2_497_280_480,
    sourceKind: 'official_ollama',
    sourceUrl: 'https://ollama.com/library/qwen3:4b',
    sourceRevision: 'sha256:test',
  },
  memoryTier: 'light',
  recommendedRamGb: 8,
  license: {
    identifier: 'Apache-2.0',
    name: 'Apache License 2.0',
    evidenceUrl: 'https://example.test/license',
    redistribution: 'allowed_with_notice',
    standaloneLicenseFile: true,
  },
  upstream: { primaryUrl: 'https://ollama.com/library/qwen3:4b', revision: 'test' },
  install: {
    method: 'ollama_pull',
    status: 'available',
    ollamaTag: 'qwen3:4b',
    downloadUrl: 'https://ollama.com/library/qwen3:4b',
    hostedByStockpulse: false,
  },
  desktop: { recommended: true, role: 'lightweight', guidanceEn: '8 GB RAM' },
};

const CATALOG: LocalModelCatalogResponse = {
  schemaVersion: 1,
  verifiedAt: '2026-07-23',
  models: [GENERAL_MODEL],
};

const RUNTIME: LocalModelRuntimeState = {
  runtime: 'ollama',
  status: 'running',
  installedModels: [],
  manualPullSupported: false,
  localInstallPlatform: 'macos',
  totalMemoryGb: 16,
  configuration: {
    configVersion: 'config-1',
    registeredModels: [],
    primaryModel: 'openai/gpt-5',
    agentModel: '',
  },
};

function classifyHost(host: HTMLElement) {
  const failed = Boolean(within(host).queryByText('The model catalog is temporarily unavailable.'));
  const hasPanel = Boolean(within(host).queryByTestId('local-models-panel'));
  const hasModel = Boolean(within(host).queryByTestId('local-model-qwen3-4b'));
  let state: 'loading' | 'catalogFailed' | 'ready' | 'emptyStale' | 'unknown';
  if (failed) state = 'catalogFailed';
  else if (hasModel) state = 'ready';
  else if (hasPanel) state = 'emptyStale';
  else if (within(host).queryByText('Detecting')) state = 'loading';
  else state = 'unknown';
  return { state, failed, hasPanel, hasModel };
}

function transport(overrides: Partial<LocalModelTransport> = {}): LocalModelTransport {
  return {
    kind: 'web',
    installAction: 'download',
    installPlatform: 'macos',
    canControlRuntime: false,
    getRuntime: vi.fn().mockResolvedValue(RUNTIME),
    pull: vi.fn(),
    importPack: vi.fn(),
    remove: vi.fn(),
    assign: vi.fn(),
    openInstallTarget: vi.fn(),
    ...overrides,
  };
}

function DualPanels({
  client,
  showSettings,
  showWizard,
}: {
  client: QueryClient;
  showSettings: boolean;
  showWizard: boolean;
}) {
  return (
    <QueryClientProvider client={client}>
      <UiLanguageProvider initialLanguage="en">
        {showSettings ? (
          <div data-testid="host-settings">
            <LocalModelsPanel language="en" />
          </div>
        ) : null}
        {showWizard ? (
          <div data-testid="host-wizard">
            <LocalModelsPanel language="en" headingAs="h3" />
          </div>
        ) : null}
      </UiLanguageProvider>
    </QueryClientProvider>
  );
}

function hostFrom(container: HTMLElement, testId: string): HTMLElement {
  return within(container).getByTestId(testId);
}

describe('LocalModelsPanel dual-mount catalog ownership', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    getCatalog.mockReset();
    createTransport.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('settings then wizard while catalog is in flight both reach ready, never stale-empty', async () => {
    const catalogPending = createDeferred<LocalModelCatalogResponse>();
    const runtimePending = createDeferred<LocalModelRuntimeState>();
    getCatalog.mockReturnValue(catalogPending.promise);
    createTransport.mockImplementation(() => transport({
      getRuntime: vi.fn().mockReturnValue(runtimePending.promise),
    }));
    const client = createAppQueryClient();
    const view = render(<DualPanels client={client} showSettings showWizard={false} />);
    await waitFor(() => expect(getCatalog).toHaveBeenCalledTimes(1));
    expect(classifyHost(hostFrom(view.container, 'host-settings')).state).toBe('loading');

    view.rerender(<DualPanels client={client} showSettings showWizard />);
    await waitFor(() => expect(within(view.container).getByTestId('host-wizard')).toBeInTheDocument());
    expect(getCatalog).toHaveBeenCalledTimes(1);
    expect(classifyHost(hostFrom(view.container, 'host-settings')).state).toBe('loading');
    expect(classifyHost(hostFrom(view.container, 'host-wizard')).state).toBe('loading');

    await act(async () => {
      runtimePending.resolve(RUNTIME);
      catalogPending.resolve(CATALOG);
      await Promise.all([runtimePending.promise, catalogPending.promise]);
    });

    await waitFor(() => {
      expect(classifyHost(hostFrom(view.container, 'host-settings')).state).toBe('ready');
      expect(classifyHost(hostFrom(view.container, 'host-wizard')).state).toBe('ready');
    });
  });

  it('unmounting the wizard while settings is loading leaves settings ready, never stale-empty', async () => {
    const catalogPending = createDeferred<LocalModelCatalogResponse>();
    const runtimePending = createDeferred<LocalModelRuntimeState>();
    getCatalog.mockReturnValue(catalogPending.promise);
    createTransport.mockImplementation(() => transport({
      getRuntime: vi.fn().mockReturnValue(runtimePending.promise),
    }));
    const client = createAppQueryClient();
    const view = render(<DualPanels client={client} showSettings showWizard={false} />);
    await waitFor(() => expect(getCatalog).toHaveBeenCalledTimes(1));

    view.rerender(<DualPanels client={client} showSettings showWizard />);
    await waitFor(() => expect(within(view.container).getByTestId('host-wizard')).toBeInTheDocument());
    expect(getCatalog).toHaveBeenCalledTimes(1);

    view.rerender(<DualPanels client={client} showSettings showWizard={false} />);
    expect(within(view.container).queryByTestId('host-wizard')).toBeNull();
    expect(classifyHost(hostFrom(view.container, 'host-settings')).state).not.toBe('emptyStale');

    await act(async () => {
      runtimePending.resolve(RUNTIME);
      catalogPending.resolve(CATALOG);
      await Promise.all([runtimePending.promise, catalogPending.promise]);
    });

    await waitFor(() => {
      expect(classifyHost(hostFrom(view.container, 'host-settings')).state).toBe('ready');
    });
    expect(classifyHost(hostFrom(view.container, 'host-settings')).state).not.toBe('emptyStale');
    expect(classifyHost(hostFrom(view.container, 'host-settings')).state).not.toBe('catalogFailed');
  });

  it('unmounting settings while wizard is loading leaves wizard ready, never stale-empty', async () => {
    const catalogPending = createDeferred<LocalModelCatalogResponse>();
    const runtimePending = createDeferred<LocalModelRuntimeState>();
    getCatalog.mockReturnValue(catalogPending.promise);
    createTransport.mockImplementation(() => transport({
      getRuntime: vi.fn().mockReturnValue(runtimePending.promise),
    }));
    const client = createAppQueryClient();
    const view = render(<DualPanels client={client} showSettings showWizard={false} />);
    await waitFor(() => expect(getCatalog).toHaveBeenCalledTimes(1));

    view.rerender(<DualPanels client={client} showSettings showWizard />);
    await waitFor(() => expect(within(view.container).getByTestId('host-wizard')).toBeInTheDocument());

    view.rerender(<DualPanels client={client} showSettings={false} showWizard />);
    expect(within(view.container).queryByTestId('host-settings')).toBeNull();

    await act(async () => {
      runtimePending.resolve(RUNTIME);
      catalogPending.resolve(CATALOG);
      await Promise.all([runtimePending.promise, catalogPending.promise]);
    });

    await waitFor(() => {
      expect(classifyHost(hostFrom(view.container, 'host-wizard')).state).toBe('ready');
    });
    expect(classifyHost(hostFrom(view.container, 'host-wizard')).state).not.toBe('emptyStale');
    expect(classifyHost(hostFrom(view.container, 'host-wizard')).state).not.toBe('catalogFailed');
  });
});
