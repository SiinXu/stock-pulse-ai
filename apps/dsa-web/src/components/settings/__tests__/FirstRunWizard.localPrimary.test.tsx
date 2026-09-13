// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../../../api/analysis';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { createAppQueryClient } from '../../../query/createAppQueryClient';
import type {
  LocalModelCatalogEntry,
  LocalModelRuntimeState,
} from '../../../types/localModels';
import { FirstRunWizard } from '../FirstRunWizard';
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

vi.mock('../../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../../api/analysis')>('../../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      analyzeAsync: vi.fn(),
    },
  };
});

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

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

const CLOUD_PRIMARY_RUNTIME: LocalModelRuntimeState = {
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

const PROVIDERS = [
  {
    id: 'openai',
    label: 'OpenAI 官方',
    labelEn: 'OpenAI Official',
    protocol: 'openai',
    defaultBaseUrl: 'https://api.openai.com/v1',
    capabilities: ['official-api'],
    requiresApiKey: true,
    requiresBaseUrl: false,
    supportsDiscovery: true,
    isLocal: false,
    isCustom: false,
  },
  {
    id: 'ollama',
    label: 'Ollama（本地）',
    labelEn: 'Ollama (Local)',
    protocol: 'ollama',
    defaultBaseUrl: 'http://127.0.0.1:11434',
    capabilities: ['local-runtime'],
    requiresApiKey: false,
    requiresBaseUrl: false,
    supportsDiscovery: true,
    isLocal: true,
    isCustom: false,
  },
];

function transport(overrides: Partial<LocalModelTransport> = {}): LocalModelTransport {
  return {
    kind: 'web',
    installAction: 'download',
    installPlatform: 'macos',
    canControlRuntime: false,
    getRuntime: vi.fn().mockResolvedValue(CLOUD_PRIMARY_RUNTIME),
    pull: vi.fn(),
    importPack: vi.fn(),
    remove: vi.fn(),
    assign: vi.fn(),
    openInstallTarget: vi.fn(),
    ...overrides,
  };
}

function renderWizard() {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <UiLanguageProvider initialLanguage="en">
        <FirstRunWizard
          onComplete={vi.fn().mockResolvedValue({ success: true })}
          onClose={() => {}}
          isSaving={false}
          language="en"
          providers={PROVIDERS}
          firstAnalysisStockCode="600519"
        />
      </UiLanguageProvider>
    </QueryClientProvider>,
  );
}

async function openLocalModelStep() {
  fireEvent.click(screen.getByRole('button', { name: /Local model/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByTestId('local-model-qwen3-4b')).toBeInTheDocument();
}

describe('FirstRunWizard local primary contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCatalog.mockResolvedValue({
      schemaVersion: 1,
      verifiedAt: '2026-07-23',
      models: [GENERAL_MODEL],
    });
    vi.mocked(analysisApi.analyzeAsync).mockResolvedValue({
      taskId: 'wizard-smoke-task',
      status: 'accepted',
    } as never);
  });

  it('does not start first-run smoke while a cloud primary is preserved after download', async () => {
    const readyRuntime: LocalModelRuntimeState = {
      ...CLOUD_PRIMARY_RUNTIME,
      installedModels: ['qwen3:4b'],
      configuration: {
        ...CLOUD_PRIMARY_RUNTIME.configuration,
        configVersion: 'config-2',
        registeredModels: ['qwen3:4b'],
      },
    };
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(CLOUD_PRIMARY_RUNTIME)
        .mockResolvedValue(readyRuntime),
      pull: vi.fn().mockResolvedValue({
        modelId: 'qwen3:4b',
        activated: true,
        selectedPrimary: false,
      }),
    }));

    renderWizard();
    await openLocalModelStep();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Download' }));

    expect(await screen.findByText(/current primary model was preserved/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Set as primary' }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(analysisApi.analyzeAsync).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Complete setup' })).not.toBeInTheDocument();
  });

  it('starts first-run smoke only after Set as primary binds the local route', async () => {
    const registeredRuntime: LocalModelRuntimeState = {
      ...CLOUD_PRIMARY_RUNTIME,
      installedModels: ['qwen3:4b'],
      configuration: {
        ...CLOUD_PRIMARY_RUNTIME.configuration,
        configVersion: 'config-2',
        registeredModels: ['qwen3:4b'],
      },
    };
    const assign = vi.fn().mockResolvedValue({
      ...registeredRuntime.configuration,
      configVersion: 'config-3',
      primaryModel: 'ollama/qwen3:4b',
    });
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(CLOUD_PRIMARY_RUNTIME)
        .mockResolvedValue(registeredRuntime),
      pull: vi.fn().mockResolvedValue({
        modelId: 'qwen3:4b',
        activated: true,
        selectedPrimary: false,
      }),
      assign,
    }));

    renderWizard();
    await openLocalModelStep();
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    expect(await screen.findByText(/current primary model was preserved/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();

    fireEvent.click(screen.getAllByRole('button', { name: 'Set as primary' })[0]);
    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('qwen3:4b', 'primary');
      expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Complete setup' }));
    await waitFor(() => {
      expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(expect.objectContaining({
        stockCode: '600519',
        reportType: 'brief',
        notify: false,
      }));
    });
  });

  it('keeps the fresh-install auto-primary path able to start smoke', async () => {
    const emptyPrimaryRuntime: LocalModelRuntimeState = {
      ...CLOUD_PRIMARY_RUNTIME,
      configuration: {
        ...CLOUD_PRIMARY_RUNTIME.configuration,
        primaryModel: '',
      },
    };
    const readyRuntime: LocalModelRuntimeState = {
      ...emptyPrimaryRuntime,
      installedModels: ['qwen3:4b'],
      configuration: {
        ...emptyPrimaryRuntime.configuration,
        configVersion: 'config-2',
        registeredModels: ['qwen3:4b'],
        primaryModel: 'ollama/qwen3:4b',
      },
    };
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(emptyPrimaryRuntime)
        .mockResolvedValue(readyRuntime),
      pull: vi.fn().mockResolvedValue({
        modelId: 'qwen3:4b',
        activated: true,
        selectedPrimary: true,
      }),
    }));

    renderWizard();
    await openLocalModelStep();
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
    });
    expect(screen.queryByText(/current primary model was preserved/)).not.toBeInTheDocument();
  });
});
