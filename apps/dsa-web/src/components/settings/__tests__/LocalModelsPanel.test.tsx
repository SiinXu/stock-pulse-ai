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
  memoryTier: 'standard',
  recommendedRamGb: 16,
  install: {
    method: 'planned_ollama_package',
    status: 'conversion_required',
    plannedOllamaTag: 'stockpulse/fin-r1-7b:q4_k_m',
    downloadUrl: 'https://example.test/fin-r1',
    hostedByStockpulse: false,
  },
};

const GENERAL_MODEL_8B: LocalModelCatalogEntry = {
  ...GENERAL_MODEL,
  id: 'qwen3-8b',
  displayName: { en: 'Qwen3 8B', zh: 'Qwen3 8B' },
  q4: {
    ...GENERAL_MODEL.q4,
    sizeBytes: 4_930_000_000,
    sourceUrl: 'https://ollama.com/library/qwen3:8b',
  },
  recommendedRamGb: 16,
  install: {
    ...GENERAL_MODEL.install,
    ollamaTag: 'qwen3:8b',
    downloadUrl: 'https://ollama.com/library/qwen3:8b',
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
    importPack: vi.fn(),
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
    expect(within(general).getByText('Light tier')).toBeInTheDocument();
    expect(within(general).getByText('Apache-2.0')).toBeInTheDocument();
    expect(within(general).getByText('Recommended tier')).toBeInTheDocument();
    const finance = screen.getByTestId('local-model-fin-r1-7b');
    expect(within(finance).getByText('Standard tier')).toBeInTheDocument();
    expect(within(finance).getByText('Conversion pending')).toBeInTheDocument();
    expect(within(finance).getByRole('button', { name: 'Open download guide' })).toBeEnabled();
  });

  it('does not auto-select an existing ready model in wizard mode', async () => {
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn().mockResolvedValue({
        ...AVAILABLE_RUNTIME,
        installedModels: ['qwen3:4b'],
        configuration: {
          ...AVAILABLE_RUNTIME.configuration,
          registeredModels: ['qwen3:4b'],
        },
      }),
    }));
    const onModelReady = vi.fn();

    renderPanel({
      onModelReady,
      selectModelLabel: 'Select model',
      selectedModelLabel: 'Selected model',
    });

    expect(await screen.findByRole('button', { name: 'Select model' })).toBeEnabled();
    expect(onModelReady).not.toHaveBeenCalled();
  });

  it('registers and selects an installed model only after an explicit action', async () => {
    const assign = vi.fn().mockResolvedValue({
      ...AVAILABLE_RUNTIME.configuration,
      configVersion: 'config-2',
      registeredModels: ['qwen3:4b'],
    });
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn().mockResolvedValue({
        ...AVAILABLE_RUNTIME,
        installedModels: ['qwen3:4b'],
      }),
      assign,
    }));
    const onModelReady = vi.fn();

    renderPanel({
      onModelReady,
      selectModelLabel: 'Select model',
      selectedModelLabel: 'Selected model',
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Select model' }));

    await vi.waitFor(() => {
      expect(assign).toHaveBeenCalledWith('qwen3:4b', 'auto');
      expect(onModelReady).toHaveBeenCalledWith('qwen3:4b');
    });
  });

  it('keeps a newly downloaded model selected when another model is already ready', async () => {
    getCatalog.mockResolvedValue({
      schemaVersion: 1,
      verifiedAt: '2026-07-23',
      models: [GENERAL_MODEL, GENERAL_MODEL_8B, FINANCE_MODEL],
    });
    const initialRuntime: LocalModelRuntimeState = {
      ...AVAILABLE_RUNTIME,
      installedModels: ['qwen3:4b'],
      configuration: {
        ...AVAILABLE_RUNTIME.configuration,
        registeredModels: ['qwen3:4b'],
      },
    };
    const completedRuntime: LocalModelRuntimeState = {
      ...initialRuntime,
      installedModels: ['qwen3:4b', 'qwen3:8b'],
      configuration: {
        ...initialRuntime.configuration,
        configVersion: 'config-2',
        registeredModels: ['qwen3:4b', 'qwen3:8b'],
      },
    };
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(initialRuntime)
        .mockResolvedValue(completedRuntime),
      pull: vi.fn().mockResolvedValue({
        modelId: 'qwen3:8b',
        activated: true,
        selectedPrimary: false,
      }),
    }));
    const onModelReady = vi.fn();

    renderPanel({
      onModelReady,
      selectModelLabel: 'Select model',
      selectedModelLabel: 'Selected model',
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Download' }));

    expect(await screen.findByText('qwen3:8b is downloaded and registered.')).toBeInTheDocument();
    expect(onModelReady).toHaveBeenCalledTimes(1);
    expect(onModelReady).toHaveBeenCalledWith('qwen3:8b');
  });

  it('shows a non-destructive warning when deletion finalization is unconfirmed', async () => {
    const installedRuntime: LocalModelRuntimeState = {
      ...AVAILABLE_RUNTIME,
      installedModels: ['qwen3:4b'],
      configuration: {
        ...AVAILABLE_RUNTIME.configuration,
        registeredModels: ['qwen3:4b'],
      },
    };
    const removedRuntime: LocalModelRuntimeState = {
      ...installedRuntime,
      installedModels: [],
      configuration: {
        ...installedRuntime.configuration,
        configVersion: 'config-2',
        registeredModels: [],
      },
    };
    const remove = vi.fn().mockResolvedValue({
      ...removedRuntime.configuration,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: true,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: ['local_model_delete_finalize_unconfirmed'],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
    });
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(installedRuntime)
        .mockResolvedValue(removedRuntime),
      remove,
    }));

    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Delete model' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText(
      'The model was deleted, but final cleanup was not confirmed. Configuration changes may be briefly blocked; refresh and try again shortly.',
    )).toBeInTheDocument();
    expect(remove).toHaveBeenCalledWith('qwen3:4b');
  });

  it('keeps the explicit first-run selection when a different model is deleted', async () => {
    getCatalog.mockResolvedValue({
      schemaVersion: 1,
      verifiedAt: '2026-07-23',
      models: [GENERAL_MODEL, GENERAL_MODEL_8B, FINANCE_MODEL],
    });
    const installedRuntime: LocalModelRuntimeState = {
      ...AVAILABLE_RUNTIME,
      installedModels: ['qwen3:4b', 'qwen3:8b'],
      configuration: {
        ...AVAILABLE_RUNTIME.configuration,
        registeredModels: ['qwen3:4b', 'qwen3:8b'],
      },
    };
    const removedRuntime: LocalModelRuntimeState = {
      ...installedRuntime,
      installedModels: ['qwen3:8b'],
      configuration: {
        ...installedRuntime.configuration,
        configVersion: 'config-2',
        registeredModels: ['qwen3:8b'],
      },
    };
    const remove = vi.fn().mockResolvedValue({
      ...removedRuntime.configuration,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: true,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
    });
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(installedRuntime)
        .mockResolvedValue(removedRuntime),
      remove,
    }));
    const onModelReady = vi.fn();

    renderPanel({
      selectedModelId: 'qwen3:8b',
      selectModelLabel: 'Select model',
      selectedModelLabel: 'Selected model',
      onModelReady,
    });
    const firstModel = await screen.findByTestId('local-model-qwen3-4b');
    fireEvent.click(within(firstModel).getByRole('button', { name: 'Delete model' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await vi.waitFor(() => {
      expect(remove).toHaveBeenCalledWith('qwen3:4b');
      expect(within(firstModel).queryByRole('button', { name: 'Delete model' })).not.toBeInTheDocument();
    });
    const selectedModel = screen.getByTestId('local-model-qwen3-8b');
    expect(within(selectedModel).getByRole('button', { name: 'Selected model' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(onModelReady).not.toHaveBeenCalled();
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

  it('uploads a Model Pack from Web and renders unknown manifest metadata', async () => {
    const importedRuntime: LocalModelRuntimeState = {
      ...AVAILABLE_RUNTIME,
      installedModels: ['licensed/finance:q4'],
      configuration: {
        ...AVAILABLE_RUNTIME.configuration,
        configVersion: 'config-2',
        registeredModels: ['licensed/finance:q4'],
        importedModels: [{
          modelId: 'licensed/finance:q4',
          displayName: 'Licensed Finance Q4',
          minimumMemoryGb: 16,
          licenseId: 'LicenseRef-Finance',
        }],
      },
    };
    const importPack = vi.fn().mockImplementation(async (_file, onProgress) => {
      onProgress({ modelId: '', percent: 80, status: 'creating' });
      return {
        modelId: 'licensed/finance:q4',
        displayName: 'Licensed Finance Q4',
        minimumMemoryGb: 16,
        licenseId: 'LicenseRef-Finance',
        warnings: ['extra'],
        activated: true,
        selectedPrimary: false,
      };
    });
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn()
        .mockResolvedValueOnce(AVAILABLE_RUNTIME)
        .mockResolvedValue(importedRuntime),
      importPack,
    }));

    const view = renderPanel();
    await screen.findByRole('button', { name: 'Import Model Pack' });
    const input = view.container.querySelector('input[type="file"]');
    const file = new File(['pack'], 'finance.modelpack', { type: 'application/zip' });
    fireEvent.change(input as HTMLInputElement, { target: { files: [file] } });

    expect(await screen.findByText(
      'licensed/finance:q4 was verified, created, and registered.',
    )).toBeInTheDocument();
    expect(screen.getByText('Import completed, but 1 undeclared files were ignored.')).toBeInTheDocument();
    const imported = screen.getByTestId('local-model-imported-licensed/finance:q4');
    expect(within(imported).getByText('Licensed Finance Q4')).toBeInTheDocument();
    expect(within(imported).getByText('LicenseRef-Finance')).toBeInTheDocument();
    expect(importPack).toHaveBeenCalledWith(file, expect.any(Function), expect.any(AbortSignal));
  });

  it('keeps catalog presentation authoritative for an imported matching model', async () => {
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn().mockResolvedValue({
        ...AVAILABLE_RUNTIME,
        installedModels: ['qwen3:4b'],
        configuration: {
          ...AVAILABLE_RUNTIME.configuration,
          registeredModels: ['qwen3:4b'],
          importedModels: [{
            modelId: 'qwen3:4b',
            displayName: 'Untrusted replacement name',
            minimumMemoryGb: 99,
            licenseId: 'LicenseRef-Other',
          }],
        },
      }),
    }));

    renderPanel();

    expect(await screen.findByText('Qwen3 4B')).toBeInTheDocument();
    expect(screen.queryByText('Untrusted replacement name')).not.toBeInTheDocument();
    expect(screen.queryByText('Imported models')).not.toBeInTheDocument();
  });

  it('does not offer pullable-only deletion for a planned catalog import', async () => {
    const plannedModelId = FINANCE_MODEL.install.plannedOllamaTag as string;
    const remove = vi.fn();
    createTransport.mockReturnValue(transport({
      getRuntime: vi.fn().mockResolvedValue({
        ...AVAILABLE_RUNTIME,
        installedModels: [plannedModelId],
        configuration: {
          ...AVAILABLE_RUNTIME.configuration,
          registeredModels: [plannedModelId],
          importedModels: [{
            modelId: plannedModelId,
            displayName: 'Untrusted replacement name',
            minimumMemoryGb: 99,
            licenseId: 'LicenseRef-Other',
          }],
        },
      }),
      remove,
    }));

    renderPanel();

    const finance = await screen.findByTestId('local-model-fin-r1-7b');
    expect(within(finance).getByText('Fin-R1 7B')).toBeInTheDocument();
    expect(within(finance).getByText('Installed')).toBeInTheDocument();
    expect(within(finance).queryByRole('button', { name: 'Delete model' })).not.toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
  });

  it('maps Model Pack integrity failures to localized actionable copy', async () => {
    createTransport.mockReturnValue(transport({
      importPack: vi.fn().mockRejectedValue(new LocalModelTransportError(
        'hash_mismatch',
        'private path details',
      )),
    }));

    const view = renderPanel();
    await screen.findByRole('button', { name: 'Import Model Pack' });
    const input = view.container.querySelector('input[type="file"]');
    fireEvent.change(input as HTMLInputElement, {
      target: { files: [new File(['pack'], 'bad.modelpack')] },
    });

    expect(await screen.findByText(
      'Model Pack integrity verification failed. Do not use it; download it again from a trusted source.',
    )).toBeInTheDocument();
    expect(screen.queryByText('private path details')).not.toBeInTheDocument();
  });
});
