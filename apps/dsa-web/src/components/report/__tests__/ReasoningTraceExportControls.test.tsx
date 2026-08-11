// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import { reasoningTraceExportApi } from '../../../api/reasoningTraceExport';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ReasoningTraceExportControls } from '../ReasoningTraceExportControls';

vi.mock('../../../api/reasoningTraceExport', () => ({
  reasoningTraceExportApi: {
    download: vi.fn(),
  },
}));

function renderControls() {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <ReasoningTraceExportControls recordId={99} variant="section" />
    </UiLanguageProvider>,
  );
}

describe('ReasoningTraceExportControls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps export actions visible and downloads on success', async () => {
    vi.mocked(reasoningTraceExportApi.download).mockResolvedValue({
      filename: 'reasoning-trace-99.json',
      truncated: false,
      contentType: 'application/json',
      byteLength: 12,
    });

    renderControls();

    expect(screen.getByTestId('reasoning-trace-export-json')).toBeInTheDocument();
    expect(screen.getByTestId('reasoning-trace-export-markdown')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('reasoning-trace-export-json'));
    await waitFor(() => {
      expect(reasoningTraceExportApi.download).toHaveBeenCalledWith(99, 'json');
    });
    expect(screen.queryByTestId('reasoning-trace-export-error')).not.toBeInTheDocument();
    expect(screen.queryByTestId('reasoning-trace-export-disabled')).not.toBeInTheDocument();
  });

  it('shows settings guidance when export is disabled', async () => {
    const parsed = createParsedApiError({
      title: 'Reasoning trace export is disabled',
      message: 'Enable REASONING_TRACE_EXPORT_ENABLED under Settings.',
      rawMessage: 'disabled',
      status: 404,
      category: 'http_error',
      code: 'reasoning_trace_export_disabled',
    });
    vi.mocked(reasoningTraceExportApi.download).mockRejectedValue(createApiError(parsed));

    renderControls();
    fireEvent.click(screen.getByTestId('reasoning-trace-export-json'));

    expect(await screen.findByTestId('reasoning-trace-export-disabled')).toBeInTheDocument();
    const link = screen.getByTestId('reasoning-trace-export-settings-link');
    expect(link).toHaveAttribute('href', expect.stringContaining('/settings'));
    expect(link.getAttribute('href')).toMatch(/agent_behavior|section=/);
    expect(screen.getByTestId('reasoning-trace-export-json')).toBeInTheDocument();
  });

  it('shows truncation notice after a truncated download', async () => {
    vi.mocked(reasoningTraceExportApi.download).mockResolvedValue({
      filename: 'reasoning-trace-99.json',
      truncated: true,
      contentType: 'application/json',
      byteLength: 5000,
    });

    renderControls();
    fireEvent.click(screen.getByTestId('reasoning-trace-export-json'));

    expect(await screen.findByTestId('reasoning-trace-export-truncated')).toBeInTheDocument();
  });

  it('shows a readable error for non-disabled failures', async () => {
    const parsed = createParsedApiError({
      title: 'Export failed',
      message: 'Security audit storage is unavailable',
      rawMessage: 'unavailable',
      status: 503,
      category: 'http_error',
      code: 'security_audit_unavailable',
    });
    vi.mocked(reasoningTraceExportApi.download).mockRejectedValue(createApiError(parsed));

    renderControls();
    fireEvent.click(screen.getByTestId('reasoning-trace-export-markdown'));

    expect(await screen.findByTestId('reasoning-trace-export-error')).toBeInTheDocument();
    expect(screen.getByTestId('reasoning-trace-export-error')).toHaveTextContent(
      /unavailable|failed|audit/i,
    );
  });
});
