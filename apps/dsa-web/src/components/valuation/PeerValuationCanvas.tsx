// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useId, useMemo, useState } from 'react';
import {
  buildPeerValuationCanvas,
  type PeerValuationCanvas as PeerCanvasPayload,
  type PeerValuationCanvasParams,
} from '../../api/valuation';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { VALUATION_TEXT } from '../../locales/valuation';
import {
  Button,
  Card,
  DataTable,
  type DataTableColumn,
  EmptyState,
  InlineAlert,
  Input,
  Select,
} from '../common';
import { RiskHeatmap, type RiskHeatmapCell } from '../charts';

export type PeerValuationCanvasProps = {
  stockCode?: string;
  canvas?: PeerCanvasPayload | null;
  fetchCanvas?: (params: PeerValuationCanvasParams) => Promise<PeerCanvasPayload>;
  readOnly?: boolean;
  className?: string;
};

type CanvasRow = {
  id: string;
  stockCode: string;
  role: string;
  dataStatus: string;
  pe?: number | null;
  pb?: number | null;
  evEbitda?: number | null;
  marketCap?: number | null;
  price?: number | null;
  missing: string[];
  peStatus?: string;
  pbStatus?: string;
  marketCapStatus?: string;
};

const asNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const formatMoney = (value: number | undefined | null): string => {
  if (value === undefined || value === null || !Number.isFinite(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const formatMultiple = (value: number | undefined | null): string => {
  if (value === undefined || value === null || !Number.isFinite(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const cellValue = (
  metrics: Record<string, { value?: number | null; status?: string }> | undefined,
  key: string,
): { value: number | null | undefined; status?: string } => {
  const cell = metrics?.[key];
  if (!cell) return { value: null, status: 'missing' };
  return { value: cell.value, status: cell.status };
};

const parsePeerCodes = (raw: string): string[] =>
  raw
    .split(/[,;\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);

export const PeerValuationCanvas: React.FC<PeerValuationCanvasProps> = ({
  stockCode: initialStockCode = '',
  canvas: initialCanvas = null,
  fetchCanvas,
  readOnly = false,
  className,
}) => {
  const { language } = useUiLanguage();
  const text = VALUATION_TEXT[language] ?? VALUATION_TEXT.en;
  const formId = useId();
  const [canvas, setCanvas] = useState<PeerCanvasPayload | null>(initialCanvas);
  const [stockCode, setStockCode] = useState(initialStockCode || initialCanvas?.stockCode || '');
  const [peerCodesText, setPeerCodesText] = useState('');
  const [peerSource, setPeerSource] = useState<'custom' | 'industry'>('custom');
  const [industryLabel, setIndustryLabel] = useState('');
  const [baseCurrency, setBaseCurrency] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows: CanvasRow[] = useMemo(() => {
    const payloadRows = canvas?.rows ?? [];
    return payloadRows.map((row) => {
      const metrics = (row.metrics ?? {}) as Record<string, { value?: number | null; status?: string }>;
      const pe = cellValue(metrics, 'peRatio');
      const pb = cellValue(metrics, 'pbRatio');
      const ev = cellValue(metrics, 'evEbitda');
      const mc = cellValue(metrics, 'marketCap');
      const price = cellValue(metrics, 'currentPrice');
      return {
        id: row.stockCode,
        stockCode: row.stockCode,
        role: row.role ?? 'peer',
        dataStatus: row.dataStatus ?? 'missing',
        pe: pe.value,
        pb: pb.value,
        evEbitda: ev.value,
        marketCap: mc.value,
        price: price.value,
        missing: row.missingMetrics ?? [],
        peStatus: pe.status,
        pbStatus: pb.status,
        marketCapStatus: mc.status,
      };
    });
  }, [canvas]);

  const columns = useMemo<DataTableColumn<CanvasRow>[]>(
    () => [
      {
        id: 'code',
        header: text.stockCode,
        rowHeader: true,
        nowrap: true,
        cell: (row) => (
          <span className="font-medium text-content">
            {row.stockCode}
            <span className="ml-2 text-xs text-content-muted">
              {row.role === 'target' ? text.roleTarget : text.rolePeer}
            </span>
          </span>
        ),
      },
      {
        id: 'pe',
        header: text.metricPe,
        align: 'end',
        cell: (row) => (
          <span className={row.peStatus === 'missing' ? 'text-content-muted' : 'tabular-nums'}>
            {row.peStatus === 'missing' ? text.missingData : formatMultiple(row.pe)}
          </span>
        ),
      },
      {
        id: 'pb',
        header: text.metricPb,
        align: 'end',
        cell: (row) => (
          <span className={row.pbStatus === 'missing' ? 'text-content-muted' : 'tabular-nums'}>
            {row.pbStatus === 'missing' ? text.missingData : formatMultiple(row.pb)}
          </span>
        ),
      },
      {
        id: 'ev',
        header: text.metricEvEbitda,
        align: 'end',
        cell: (row) => (
          <span className="tabular-nums">{formatMultiple(row.evEbitda)}</span>
        ),
      },
      {
        id: 'mcap',
        header: text.metricMarketCap,
        align: 'end',
        cell: (row) => (
          <span className={row.marketCapStatus === 'missing' ? 'text-content-muted' : 'tabular-nums'}>
            {row.marketCapStatus === 'missing' ? text.missingData : formatMoney(row.marketCap)}
          </span>
        ),
      },
      {
        id: 'price',
        header: text.metricPrice,
        align: 'end',
        cell: (row) => <span className="tabular-nums">{formatMoney(row.price)}</span>,
      },
      {
        id: 'status',
        header: text.status,
        cell: (row) => (
          <span className="text-xs text-content-muted">
            {row.dataStatus === 'missing' || row.dataStatus === 'partial'
              ? text.missingAnnotated
              : row.dataStatus}
          </span>
        ),
      },
    ],
    [text],
  );

  const heatmapCells: RiskHeatmapCell[] = useMemo(() => {
    const cells = canvas?.heatmapCells ?? [];
    return cells.map((raw) => {
      const cell = raw as Record<string, unknown>;
      return {
        rowId: String(cell.rowId ?? cell.row_id ?? ''),
        rowLabel: String(cell.rowLabel ?? cell.row_label ?? ''),
        columnId: String(cell.columnId ?? cell.column_id ?? ''),
        columnLabel: String(cell.columnLabel ?? cell.column_label ?? ''),
        score: asNumber(cell.score) ?? null,
      };
    }).filter((cell) => cell.rowId && cell.columnId);
  }, [canvas]);

  const peerSet = (canvas?.peerSet ?? {}) as Record<string, unknown>;
  const medians = (canvas?.medians ?? {}) as Record<string, unknown>;

  const handleBuild = useCallback(async () => {
    const code = stockCode.trim();
    if (!code) {
      setError(text.stockCode);
      return;
    }
    const peers = parsePeerCodes(peerCodesText);
    if (!peers.length) {
      setError(text.peersRequired);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const fetcher = fetchCanvas ?? buildPeerValuationCanvas;
      const next = await fetcher({
        stockCode: code,
        peerSource,
        peerCodes: peers,
        industryLabel: industryLabel.trim() || null,
        baseCurrency: baseCurrency.trim() || null,
      });
      setCanvas(next);
    } catch (err) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: string }).message || text.loadFailed)
          : text.loadFailed;
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [
    baseCurrency,
    fetchCanvas,
    industryLabel,
    peerCodesText,
    peerSource,
    stockCode,
    text,
  ]);

  return (
    <div className={className}>
      <Card data-testid="peer-valuation-canvas">
        <div className="flex flex-col gap-4 p-4">
          <header className="space-y-1">
            <h2 className="text-base font-semibold text-content">{text.peerTitle}</h2>
            <p className="text-sm text-content-muted">{text.peerDescription}</p>
          </header>

          {!readOnly && (
            <section
              className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
              data-testid="peer-canvas-form"
              aria-label={text.peerTitle}
            >
              <Input
                id={`${formId}-stock`}
                label={text.stockCode}
                value={stockCode}
                onChange={(event) => setStockCode(event.target.value)}
                placeholder={text.stockCodePlaceholder}
                data-testid="peer-canvas-stock-code"
              />
              <Input
                id={`${formId}-peers`}
                label={text.peerCodes}
                value={peerCodesText}
                onChange={(event) => setPeerCodesText(event.target.value)}
                placeholder={text.peerCodesPlaceholder}
                data-testid="peer-canvas-peer-codes"
              />
              <Select
                id={`${formId}-source`}
                label={text.peerSource}
                value={peerSource}
                onChange={(value) => setPeerSource(value === 'industry' ? 'industry' : 'custom')}
                options={[
                  { value: 'custom', label: text.peerSourceCustom },
                  { value: 'industry', label: text.peerSourceIndustry },
                ]}
              />
              <Input
                id={`${formId}-industry`}
                label={text.industryLabel}
                value={industryLabel}
                onChange={(event) => setIndustryLabel(event.target.value)}
                placeholder={text.industryLabelPlaceholder}
                data-testid="peer-canvas-industry-label"
              />
              <Input
                id={`${formId}-ccy`}
                label={text.baseCurrency}
                value={baseCurrency}
                onChange={(event) => setBaseCurrency(event.target.value)}
                placeholder={text.baseCurrencyPlaceholder}
                data-testid="peer-canvas-base-currency"
              />
              <div className="flex items-end">
                <Button
                  variant="primary"
                  type="button"
                  onClick={() => void handleBuild()}
                  disabled={loading}
                  data-testid="peer-canvas-build"
                >
                  {loading ? text.buildingCanvas : text.buildCanvas}
                </Button>
              </div>
            </section>
          )}

          {error && (
            <InlineAlert variant="danger" title={text.loadFailed} message={error} data-testid="peer-canvas-error" />
          )}

          {!canvas && !loading && (
            <EmptyState
              title={text.emptyPeersTitle}
              description={text.emptyPeersDescription}
              data-testid="peer-canvas-empty"
            />
          )}

          {canvas && (
            <section className="space-y-3" data-testid="peer-canvas-result">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2">
                  <div className="text-xs text-content-muted">{text.status}</div>
                  <div className="text-sm font-medium">{canvas.status}</div>
                </div>
                <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2">
                  <div className="text-xs text-content-muted">{text.peerSetSource}</div>
                  <div className="text-sm font-medium">
                    {String(peerSet.source ?? '—')}
                    {peerSet.sourceLabel ? ` · ${String(peerSet.sourceLabel)}` : ''}
                  </div>
                </div>
                <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2">
                  <div className="text-xs text-content-muted">{text.baseCurrency}</div>
                  <div className="text-sm font-medium">{canvas.baseCurrency ?? '—'}</div>
                </div>
              </div>

              {typeof peerSet.explanation === 'string' && peerSet.explanation && (
                <InlineAlert
                  variant="info"
                  title={text.peerSetExplanation}
                  message={peerSet.explanation}
                  data-testid="peer-canvas-source-explanation"
                />
              )}

              {canvas.fxStale && (
                <InlineAlert variant="warning" message={text.fxStale} data-testid="peer-canvas-fx-stale" />
              )}

              {(medians.peMedian != null || medians.pbMedian != null) && (
                <div className="text-sm text-content-muted" data-testid="peer-canvas-medians">
                  {text.medians}: {text.metricPeShort}{' '}
                  {formatMultiple(asNumber(medians.peMedian) ?? null)} · {text.metricPbShort}{' '}
                  {formatMultiple(asNumber(medians.pbMedian) ?? null)}
                </div>
              )}

              <DataTable<CanvasRow>
                caption={text.peerTitle}
                columns={columns}
                rows={rows}
                getRowKey={(row) => row.id}
                emptyState={{
                  title: text.emptyPeersTitle,
                  description: text.emptyPeersDescription,
                }}
                density="compact"
                minWidth="content"
              />

              {heatmapCells.length > 0 && (
                <div data-testid="peer-canvas-heatmap">
                  <h3 className="mb-2 text-sm font-medium text-content">{text.heatmapTitle}</h3>
                  <p className="mb-2 text-xs text-content-muted">{text.heatmapNote}</p>
                  <RiskHeatmap cells={heatmapCells} />
                </div>
              )}

              {canvas.disclaimer && (
                <p className="text-xs text-content-muted" data-testid="peer-canvas-disclaimer">
                  {canvas.disclaimer}
                </p>
              )}
            </section>
          )}
        </div>
      </Card>
    </div>
  );
};
