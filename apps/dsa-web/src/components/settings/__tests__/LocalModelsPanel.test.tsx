import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type {
  LocalModelCatalogEntry,
  LocalModelRuntimeState,
} from '../../../types/localModels';
import { LocalModelsPanel } from '../LocalModelsPanel';
import {
  LocalModelTransportError,
  type LocalModelTransport,
} from '../localModelTransport';

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
    manualCommand?: string;

    constructor(code: string, message: string, manualCommand?: string) {
      super(message);
      this.code = code;
      this.manualCommand = manualCommand;
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

const FINANCE_MODEL: LocalModelCatalogEntry = {
  ...GENERAL_MODEL,
  id: 'fin-r1-7b',
  section: 'finance',
  displayName: { en: 'Fin-R1 7B', zh: 'Fin-R1 7B' },
  capabilitySummary: { en: 'Finance reasoning model.', zh: '金融推理模型。' },
  capabilities: ['finance', 'reasoning'],
  recommendedRamGb: 16,
  install: {
    method: 'planned_ollama_package',
    status: 'conversion_required',
    plannedOllamaTag: 'stockpulse/fin-r1-7b:q4_k_m',
    downloadUrl: 'https://example.test/fin-r1',
    hostedByStockpulse: false,
  },
};

const AVAILABLE_RUNTIME: LocalModelRuntimeState = {
  runtime: 'ollama',
  status: 'running',
  installedModels: [],
  manualPullSupported: false,
  totalMemoryGb: 16,
  configuration: {
    configVersion: 'config-1',
    registeredModels: [],
    primaryModel: 'openai/gpt-5',
    agentModel: '',
  },
};

function renderPanel(props: Partial<React.ComponentProps<typeof LocalModelsPanel>> = {}) {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <LocalModelsPanel language="en" {...props} />
    </UiLanguageProvider>,
  );
}

function transport(overrides: Partial<LocalModelTransport> = {}): LocalModelTransport {
  return {
    kind: 'web',
    canControlRuntime: false,
    getRuntime: vi.fn().mockResolvedValue(AVAILABLE_RUNTIME),
    pull: vi.fn(),
    remove: vi.fn(),
    assign: vi.fn(),
    openInstallGuide: vi.fn(),
    ...overrides,
  };
}

describe('LocalModelsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCatalog.mockResolvedValue({
      schemaVersion: 1,
      verifiedAt: '2026-07-23',
      models: [GENERAL_MODEL, FINANCE_MODEL],
    });
  });

  it('renders catalog metadata, memory recommendation, and guided finance status', async () => {
    createTransport.mockReturnValue(transport());

    renderPanel();

    const general = await screen.findByTestId('local-model-qwen3-4b');
    expect(within(general).getByText('Qwen3 4B')).toBeInTheDocument();
    expect(within(general).getByText('Q4 · 2.5 GB')).toBeInTheDocument();
    expect(within(general).getByText('8 GB RAM')).toBeInTheDocument();
    expect(within(general).getByText('Apache-2.0')).toBeInTheDocument();
    expect(within(general).getByText('Recommended tier')).toBeInTheDocument();
    const finance = screen.getByTestId('local-model-fin-r1-7b');
    expect(within(finance).getByText('Conversion pending')).toBeInTheDocument();
    expect(within(finance).getByRole('button', { name: 'Open download guide' })).toBeEnabled();
  });

  it('marks a downloaded model ready without replacing the existing primary', async () => {
    const readyRuntime: LocalModelRuntimeState = {
      ...AVAILABLE_RUNTIME,
      installedModels: ['qwen3:4b'],
      configuration: {
        ...AVAILABLE_RUNTIME.configuration,
        configVersion: 'config-2',
        registeredModels: ['qwen3:4b'],
      },
    };
    const pull = vi.fn().mockImplementation(async (_modelId, onProgress) => {
      onProgress({ modelId: 'qwen3:4b', percent: 100, status: 'completed' });
      return { modelId: 'qwen3:4b', activated: true, selectedPrimary: false };
    });
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(AVAILABLE_RUNTIME)
        .mockResolvedValue(readyRuntime),
      pull,
    }));
    const onConfigurationChanged = vi.fn();
    const onModelReady = vi.fn();

    renderPanel({ onConfigurationChanged, onModelReady });
    fireEvent.click(await screen.findByRole('button', { name: 'Download' }));

    expect(await screen.findByText('qwen3:4b is downloaded and registered.')).toBeInTheDocument();
    expect(screen.getByText(/current primary model was preserved/)).toBeInTheDocument();
    expect(onConfigurationChanged).toHaveBeenCalled();
    expect(onModelReady).toHaveBeenCalledWith('qwen3:4b');
  });

  it('does not prompt to reselect a local model that is already primary', async () => {
    const configuredRuntime: LocalModelRuntimeState = {
      ...AVAILABLE_RUNTIME,
      installedModels: ['qwen3:4b'],
      configuration: {
        ...AVAILABLE_RUNTIME.configuration,
        configVersion: 'config-2',
        registeredModels: ['qwen3:4b'],
        primaryModel: 'ollama/qwen3:4b',
      },
    };
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce({
          ...AVAILABLE_RUNTIME,
          configuration: {
            ...AVAILABLE_RUNTIME.configuration,
            primaryModel: 'ollama/qwen3:4b',
          },
        })
        .mockResolvedValue(configuredRuntime),
      pull: vi.fn().mockResolvedValue({
        modelId: 'qwen3:4b',
        activated: true,
        selectedPrimary: false,
      }),
    }));

    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Download' }));

    expect(await screen.findByText('qwen3:4b is downloaded and registered.')).toBeInTheDocument();
    expect(screen.queryByText(/current primary model was preserved/)).not.toBeInTheDocument();
  });

  it('keeps runtime Stop disabled while a model pull is active', async () => {
    let resolvePull: ((value: {
      modelId: string;
      activated: boolean;
      selectedPrimary: boolean;
    }) => void) | undefined;
    const pull = vi.fn().mockReturnValue(new Promise((resolve) => {
      resolvePull = resolve;
    }));
    createTransport.mockReturnValue(transport({
      canControlRuntime: true,
      getRuntime: vi.fn().mockResolvedValue({
        ...AVAILABLE_RUNTIME,
        managed: true,
      }),
      pull,
    }));

    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Download' }));

    expect(screen.getByRole('button', { name: 'Stop service' })).toBeDisabled();
    resolvePull?.({ modelId: 'qwen3:4b', activated: true, selectedPrimary: false });
  });

  it('reports activation failure without recommending a duplicate pull', async () => {
    createTransport.mockReturnValue(transport({
      pull: vi.fn().mockRejectedValue(new LocalModelTransportError(
        'local_model_activation_failed',
        'Local model configuration failed',
      )),
    }));

    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Download' }));

    expect(await screen.findByText(
      'The operation did not complete. Refresh status and try again.',
    )).toBeInTheDocument();
    expect(screen.queryByText('ollama pull qwen3:4b')).not.toBeInTheDocument();
  });

  it('degrades to a copyable command when Ollama is unavailable', async () => {
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn().mockResolvedValue({
        ...AVAILABLE_RUNTIME,
        status: 'unavailable',
        manualPullSupported: true,
      }),
    }));

    renderPanel();

    expect(await screen.findByText('Ollama is unavailable')).toBeInTheDocument();
    expect(screen.getByText('ollama pull qwen3:4b')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled();
  });
});
