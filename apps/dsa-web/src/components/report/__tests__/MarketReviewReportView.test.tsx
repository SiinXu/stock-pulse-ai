import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render as rtlRender, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  AnalysisReport,
  MarketReviewPayload,
  MarketStructureContext,
} from '../../../types/analysis';
import { applyPriceDirection } from '../../theme/themeRuntime';
import { MarketReviewReportView } from '../MarketReviewReportView';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getMarkdown: vi.fn(),
  },
}));

vi.mock('../../../api/agentFeedback', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/agentFeedback')>();
  return {
    ...actual,
    agentFeedbackApi: {
      getRunFeedback: vi.fn().mockResolvedValue({
        runId: 'market-review-q-1',
        feedbackValue: null,
        note: null,
        source: null,
        provenanceSource: null,
        actorId: null,
        createdAt: null,
        updatedAt: null,
      }),
      putRunFeedback: vi.fn(),
    },
  };
});

function render(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return rtlRender(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const englishMarketReviewReport: AnalysisReport = {
  meta: {
    queryId: 'market-review-q-1',
    stockCode: 'MARKET',
    stockName: 'Market Review',
    reportType: 'market_review',
    reportLanguage: 'en',
    createdAt: '2026-03-18T08:00:00Z',
  },
  summary: {
    analysisSummary: '',
    operationAdvice: '',
    trendPrediction: '',
    sentimentScore: undefined as unknown as number,
  },
};

const combinedMarketReviewPayload: MarketReviewPayload = {
  version: 1,
  kind: 'market_review',
  region: 'cn,hk',
  language: 'zh',
  rootTitle: '大盘复盘',
  markets: {
    cn: {
      title: 'A股市场',
      breadth: {
        upCount: 3120,
        downCount: 1420,
        limitUpCount: 72,
        limitDownCount: 4,
        totalAmount: 9600,
        turnoverUnit: '亿元',
      },
      indices: [{
        code: '000300',
        name: '沪深300',
        current: 3920.2,
        changePct: 1.2,
        high: 3940.5,
        low: 3860.1,
      }],
      sectors: {
        top: [{ name: '半导体', changePct: 2.35 }],
        bottom: [{ name: '煤炭', changePct: -1.1 }],
      },
      concepts: {
        top: [{ name: '机器人概念', changePct: 4.2 }],
        bottom: [{ name: '转基因', changePct: -2.05 }],
      },
    },
    hk: {
      title: '港股市场',
      breadth: {
        upCount: 680,
        downCount: 410,
        limitUpCount: 0,
        limitDownCount: 0,
        totalAmount: 1180,
        turnoverUnit: '亿港元',
      },
      indices: [{
        code: 'HSI',
        name: '恒生指数',
        current: 18920.4,
        changePct: -0.5,
        high: 19050.2,
        low: 18780.3,
      }],
    },
  },
};

const noBreadthMarketReviewPayload: MarketReviewPayload = {
  version: 1,
  kind: 'market_review',
  region: 'us',
  language: 'en',
  title: 'Market Review',
  rootTitle: 'Market Review',
  indices: [{
    code: 'SPX',
    name: 'S&P 500',
    current: 5200,
    changePct: 0.68,
    high: 5235.2,
    low: 5170.4,
  }],
  sectors: {
    top: [{ name: 'Technology', changePct: 1.9 }],
    bottom: [{ name: 'Energy', changePct: -0.8 }],
  },
  news: [],
  sections: [],
};

const marketStructureContext: MarketStructureContext = {
  schemaVersion: 'market-structure-v1',
  status: 'partial',
  market: 'cn',
  tradeDate: '2026-07-04',
  marketThemeContext: {
    schemaVersion: 'market-theme-v1',
    status: 'partial',
    market: 'cn',
    activeThemes: [
      { name: '机器人概念', changePct: 4.2, rank: 1, source: 'concept', phase: 'accelerating' },
    ],
    leadingConcepts: [
      { name: '机器人概念', changePct: 4.2, rank: 1, source: 'concept' },
    ],
    leadingIndustries: [
      { name: '通用设备', changePct: 2.1, rank: 2, source: 'industry' },
    ],
  },
  stockMarketPosition: {
    schemaVersion: 'stock-market-position-v1',
    status: 'partial',
    stockCode: '300024',
    stockName: '机器人',
    market: 'cn',
    primaryTheme: {
      name: '机器人概念',
      source: 'concept',
      phase: 'accelerating',
      rank: 1,
      changePct: 4.2,
    },
    stockRole: 'follower',
    themePhase: 'accelerating',
  },
};

const marketReviewReportWithStructure: AnalysisReport = {
  meta: {
    id: 101,
    queryId: 'market-review-q-structure',
    stockCode: 'MARKET_REVIEW',
    stockName: '大盘复盘',
    reportType: 'market_review',
    reportLanguage: 'zh',
    createdAt: '2026-07-04T08:00:00Z',
  },
  summary: {
    analysisSummary: '大盘震荡上行',
    operationAdvice: '关注题材轮动',
    trendPrediction: '短期偏多',
    sentimentScore: 68,
  },
  details: {
    marketStructure: marketStructureContext,
  },
};

describe('MarketReviewReportView', () => {
  afterEach(() => {
    cleanup();
    applyPriceDirection('cn', { persist: false });
    document.documentElement.classList.remove('dark');
  });

  it('uses the report locale for the fallback title', () => {
    render(
      <MarketReviewReportView
        content=""
        reportLanguage="ko"
      />,
    );

    expect(screen.getByRole('heading', { name: '시장 리뷰' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Market Review' })).not.toBeInTheDocument();
  });

  it('uses localized summary card labels and fallbacks for English reports', () => {
    render(
      <MarketReviewReportView
        report={englishMarketReviewReport}
        content="# Market Review"
        reportLanguage="en"
      />,
    );

    expect(screen.getByText('Review Summary')).toBeInTheDocument();
    expect(screen.getByText('No review summary yet')).toBeInTheDocument();
    expect(screen.getByText('Market Sentiment')).toBeInTheDocument();
    expect(screen.getByText('No score yet')).toBeInTheDocument();
    expect(screen.getByText('Rotation & Funds')).toBeInTheDocument();
    expect(screen.getByText('No rotation view yet')).toBeInTheDocument();
    expect(screen.getByText('Risks & Watchlist')).toBeInTheDocument();
    expect(screen.getByText('No key observations yet')).toBeInTheDocument();
    expect(screen.queryByText('复盘摘要')).not.toBeInTheDocument();
    expect(screen.queryByText('暂无摘要')).not.toBeInTheDocument();
  });

  it('renders structured data for every market in a combined market review payload', () => {
    render(
      <MarketReviewReportView
        payload={combinedMarketReviewPayload}
        content="# 大盘复盘"
        reportLanguage="zh"
      />,
    );

    expect(screen.getByText('A股市场')).toBeInTheDocument();
    expect(screen.getByText('港股市场')).toBeInTheDocument();
    expect(screen.getByText('沪深300')).toBeInTheDocument();
    expect(screen.getByText('恒生指数')).toBeInTheDocument();
    expect(screen.getByText('3120')).toBeInTheDocument();
    expect(screen.getByText('680')).toBeInTheDocument();
    const cnTable = screen.getByRole('table', { name: 'A股市场: 指数' });
    const hkTable = screen.getByRole('table', { name: '港股市场: 指数' });
    expect(screen.getAllByRole('table')).toHaveLength(2);
    expect(screen.getByRole('rowheader', { name: '沪深300' })).toBeInTheDocument();
    expect(screen.getByRole('rowheader', { name: '恒生指数' })).toBeInTheDocument();
    expect(cnTable.parentElement).toHaveAttribute('data-data-table', 'ready');
    expect(cnTable.parentElement).not.toHaveAttribute('data-surface-level');
    expect(hkTable.parentElement).not.toHaveAttribute('data-surface-level');
  });

  it('renders industry and concept rankings from structured market review payloads', () => {
    render(
      <MarketReviewReportView
        payload={combinedMarketReviewPayload}
        content="# 大盘复盘"
        reportLanguage="zh"
      />,
    );

    expect(screen.getAllByText('行业板块')).toHaveLength(2);
    expect(screen.getAllByText('概念板块')).toHaveLength(2);
    expect(screen.getByText('半导体')).toBeInTheDocument();
    expect(screen.getByText('机器人概念')).toBeInTheDocument();
    expect(screen.getByText('+4.20%')).toBeInTheDocument();
    expect(screen.getByText('-2.05%')).toBeInTheDocument();
  });

  it('localizes structured market data labels for Chinese reports', () => {
    render(
      <MarketReviewReportView
        payload={combinedMarketReviewPayload}
        content="# 大盘复盘"
        reportLanguage="zh"
      />,
    );

    expect(screen.getByText('结构化大盘数据')).toBeInTheDocument();
    expect(screen.getAllByText('上涨家数')).toHaveLength(2);
    expect(screen.getAllByText('下跌家数')).toHaveLength(2);
    expect(screen.getAllByText('涨停/跌停')).toHaveLength(2);
    expect(screen.getAllByText('成交额')).toHaveLength(2);
    expect(screen.getAllByText('指数')).toHaveLength(2);
    expect(screen.getAllByText('最新')).toHaveLength(2);
    expect(screen.getAllByText('涨跌幅')).toHaveLength(2);
    expect(screen.getAllByText('高/低')).toHaveLength(2);
    expect(screen.queryByText('Structured Market Data')).not.toBeInTheDocument();
    expect(screen.queryByText('Advancers')).not.toBeInTheDocument();
    expect(screen.queryByText('Index')).not.toBeInTheDocument();
  });

  it('shows "No data" when breadth is not available for a market review payload', () => {
    render(
      <MarketReviewReportView
        payload={noBreadthMarketReviewPayload}
        content="# Market Review"
        reportLanguage="en"
      />,
    );

    expect(screen.getByText('Structured Market Data')).toBeInTheDocument();
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.getByText('S&P 500')).toBeInTheDocument();
    expect(screen.getAllByText('Industry Sectors').length).toBeGreaterThan(0);
    expect(screen.getByText('Technology')).toBeInTheDocument();
    expect(screen.getByText('Energy')).toBeInTheDocument();
    expect(screen.queryByText('Advancers')).not.toBeInTheDocument();
    expect(screen.queryByText('Decliners')).not.toBeInTheDocument();
  });

  it('formats structured market numbers to two decimal places', () => {
    const payload: MarketReviewPayload = {
      version: 1,
      kind: 'market_review',
      region: 'cn',
      language: 'en',
      title: 'Market Review',
      rootTitle: 'Market Review',
      breadth: {
        upCount: 4327,
        downCount: 1145,
        limitUpCount: 222,
        limitDownCount: 12,
        totalAmount: 36822.49698199988,
        turnoverUnit: 'bn',
      },
      indices: [{
        code: '000001',
        name: 'Shanghai Composite',
        current: 4112.446,
        changePct: 0.44079750937683315,
        high: 4143.314,
        low: 4087.536,
      }],
    };

    render(
      <MarketReviewReportView
        payload={payload}
        content="# Market Review"
        reportLanguage="en"
      />,
    );

    expect(screen.getByText('36822.50 bn')).toBeInTheDocument();
    expect(screen.getByText('4112.45')).toBeInTheDocument();
    expect(screen.getByText('0.44%')).toBeInTheDocument();
    expect(screen.getByText('4143.31 / 4087.54')).toBeInTheDocument();
    expect(screen.queryByText(/36822\.496/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0\.440797/)).not.toBeInTheDocument();
  });

  it('formats string-backed market numbers and hides missing high/low zeros', () => {
    const payload = {
      version: 1,
      kind: 'market_review',
      region: 'cn',
      language: 'en',
      title: 'Market Review',
      rootTitle: 'Market Review',
      breadth: {
        upCount: '4,327',
        downCount: '1,145',
        limitUpCount: '0',
        limitDownCount: '12',
        totalAmount: '36,822.49698199988',
        turnoverUnit: 'bn',
      },
      indices: [{
        code: '000001',
        name: 'Shanghai Composite',
        current: '4,112.446',
        changePct: '0.44079750937683315%',
        high: 0,
        low: '0',
      }],
    } as unknown as MarketReviewPayload;

    render(
      <MarketReviewReportView
        payload={payload}
        content="# Market Review"
        reportLanguage="en"
      />,
    );

    expect(screen.getByText('4327')).toBeInTheDocument();
    expect(screen.getByText('36822.50 bn')).toBeInTheDocument();
    expect(screen.getByText('4112.45')).toBeInTheDocument();
    expect(screen.getByText('0.44%')).toBeInTheDocument();
    expect(screen.queryByText('0.00 / 0.00')).not.toBeInTheDocument();
    expect(screen.queryByText(/0\.440797/)).not.toBeInTheDocument();
  });

  it('renders the market structure card when report details carry marketStructure', () => {
    render(
      <MarketReviewReportView
        report={marketReviewReportWithStructure}
        content="# 大盘复盘"
        reportLanguage="zh"
      />,
    );

    expect(screen.getByRole('region', { name: '题材主线与个股位置' })).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: '市场情绪' })).toHaveAttribute('aria-valuenow', '68');
    expect(screen.getByRole('meter', { name: '市场情绪' }).querySelector('.gauge-ring')).toBeInTheDocument();
    expect(screen.getByText('大盘题材层')).toBeInTheDocument();
    expect(screen.getByText('个股位置层')).toBeInTheDocument();
    expect(screen.getAllByText(/机器人概念/).length).toBeGreaterThan(0);
  });

  it('does not render the market structure card for legacy reports without the field', () => {
    render(
      <MarketReviewReportView
        report={englishMarketReviewReport}
        content="# Market Review"
        reportLanguage="en"
      />,
    );

    expect(screen.queryByRole('region', { name: 'Themes and Stock Position' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '题材主线与个股位置' })).not.toBeInTheDocument();
  });

  it('opens run flow for historical market review records', () => {
    const onOpenRunFlow = vi.fn();

    render(
      <MarketReviewReportView
        payload={combinedMarketReviewPayload}
        content="# 大盘复盘"
        recordId={7}
        reportLanguage="zh"
        onOpenRunFlow={onOpenRunFlow}
      />,
    );

    const runFlowButton = screen.getByRole('button', { name: '查看历史记录 7 运行流' });
    expect(runFlowButton).toHaveAttribute('data-control', 'icon-button');
    expect(runFlowButton).toHaveClass('control-hit-target');
    const shareButton = document.querySelector<HTMLButtonElement>('button.home-surface-button');
    expect(shareButton?.parentElement?.parentElement?.parentElement).toHaveClass(
      '[&_.home-surface-button]:!shadow-none',
    );
    expect(screen.getByRole('button', { name: '复制 Markdown 源码' })).toHaveAttribute('data-control', 'icon-button');
    expect(screen.getByRole('button', { name: '复制纯文本' })).toHaveAttribute('data-control', 'icon-button');

    fireEvent.click(runFlowButton);

    expect(onOpenRunFlow).toHaveBeenCalledWith(7);
  });

  it('paints index and ranking percents with document price-direction hue tokens', () => {
    applyPriceDirection('cn', { persist: false });
    render(
      <MarketReviewReportView
        payload={combinedMarketReviewPayload}
        content="# 大盘复盘"
        reportLanguage="zh"
      />,
    );

    const cnTable = screen.getByRole('table', { name: 'A股市场: 指数' });
    const indexGain = within(cnTable).getByText('1.20%');
    const rankingGain = screen.getByText('+2.35%');
    const rankingLoss = screen.getByText('-1.10%');
    expect(indexGain).toHaveStyle({ color: 'var(--price-red)' });
    expect(rankingGain).toHaveStyle({ color: 'var(--price-red)' });
    expect(rankingLoss).toHaveStyle({ color: 'var(--price-green)' });
    expect(indexGain).not.toHaveClass('text-success');
    expect(indexGain).not.toHaveClass('text-danger');
    expect(rankingGain).not.toHaveClass('text-success');
    expect(rankingLoss).not.toHaveClass('text-danger');
  });

  it('paints the same Market Review cells from US preference even when the payload region is CN', () => {
    applyPriceDirection('us', { persist: false });
    document.documentElement.classList.add('dark');
    render(
      <MarketReviewReportView
        payload={combinedMarketReviewPayload}
        content="# 大盘复盘"
        reportLanguage="zh"
      />,
    );

    const cnTable = screen.getByRole('table', { name: 'A股市场: 指数' });
    expect(within(cnTable).getByText('1.20%')).toHaveStyle({ color: 'var(--price-green)' });
    expect(screen.getByText('+2.35%')).toHaveStyle({ color: 'var(--price-green)' });
    expect(screen.getByText('-1.10%')).toHaveStyle({ color: 'var(--price-red)' });
  });

  it('paints a US-region payload from document CN preference rather than the US convention', () => {
    applyPriceDirection('cn', { persist: false });
    render(
      <MarketReviewReportView
        payload={noBreadthMarketReviewPayload}
        content="# Market Review"
        reportLanguage="en"
      />,
    );

    expect(screen.getByText('0.68%')).toHaveStyle({ color: 'var(--price-red)' });
    expect(screen.getByText('+1.90%')).toHaveStyle({ color: 'var(--price-red)' });
  });

  it('omits unresolved region ids and still paints from document preference', () => {
    applyPriceDirection('us', { persist: false });
    const jpPayload: MarketReviewPayload = {
      version: 1,
      kind: 'market_review',
      region: 'jp',
      language: 'en',
      title: 'Market Review',
      rootTitle: 'Market Review',
      indices: [{
        code: 'N225',
        name: 'Nikkei',
        current: 38000,
        changePct: 0.68,
        high: 38100,
        low: 37900,
      }],
    };
    render(
      <MarketReviewReportView
        payload={jpPayload}
        content="# Market Review"
        reportLanguage="en"
      />,
    );
    expect(screen.getByText('0.68%')).toHaveStyle({ color: 'var(--price-green)' });

    cleanup();
    applyPriceDirection('cn', { persist: false });
    const combinedRegionPayload: MarketReviewPayload = {
      version: 1,
      kind: 'market_review',
      region: 'cn,hk',
      language: 'en',
      title: 'Market Review',
      rootTitle: 'Market Review',
      indices: [{
        code: '000300',
        name: 'CSI 300',
        current: 3920.2,
        changePct: -1.1,
        high: 3940.5,
        low: 3860.1,
      }],
    };
    render(
      <MarketReviewReportView
        payload={combinedRegionPayload}
        content="# Market Review"
        reportLanguage="en"
      />,
    );
    expect(screen.getByText('-1.10%')).toHaveStyle({ color: 'var(--price-green)' });
  });

  it('leaves zero and non-finite Market Review percents unpainted', () => {
    applyPriceDirection('cn', { persist: false });
    const payload: MarketReviewPayload = {
      version: 1,
      kind: 'market_review',
      region: 'cn',
      language: 'en',
      title: 'Market Review',
      rootTitle: 'Market Review',
      indices: [
        {
          code: 'ZERO',
          name: 'Zero Index',
          current: 100,
          changePct: 0,
          high: 101,
          low: 99,
        },
        {
          code: 'NAN',
          name: 'NaN Index',
          current: 100,
          changePct: Number.NaN,
          high: 101,
          low: 99,
        },
        {
          code: 'INF',
          name: 'Inf Index',
          current: 100,
          changePct: Number.POSITIVE_INFINITY,
          high: 101,
          low: 99,
        },
      ],
      sectors: {
        top: [{ name: 'Zero Rank', changePct: 0 }],
        bottom: [{ name: 'Missing Rank', changePct: Number.NaN }],
      },
    };

    render(
      <MarketReviewReportView
        payload={payload}
        content="# Market Review"
        reportLanguage="en"
      />,
    );

    const indexTable = screen.getByRole('table', { name: 'Market Review: Index' });
    const zeroIndex = within(indexTable).getByText('0.00%');
    expect(zeroIndex).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(zeroIndex).not.toHaveStyle({ color: 'var(--price-green)' });
    expect(zeroIndex).not.toHaveClass('text-success');
    expect(zeroIndex).not.toHaveClass('text-danger');

    const zeroRank = screen.getByText('0.00%', { selector: '.text-secondary-text' });
    expect(zeroRank).toHaveClass('text-secondary-text');
    expect(zeroRank).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(zeroRank).not.toHaveStyle({ color: 'var(--price-green)' });

    const missingCells = screen.getAllByText('-');
    expect(missingCells.length).toBeGreaterThan(0);
    for (const node of missingCells) {
      expect(node).not.toHaveStyle({ color: 'var(--price-red)' });
      expect(node).not.toHaveStyle({ color: 'var(--price-green)' });
      expect(node).not.toHaveClass('text-success');
      expect(node).not.toHaveClass('text-danger');
    }
    expect(screen.queryByText('Infinity%')).not.toBeInTheDocument();
    expect(screen.queryByText('NaN%')).not.toBeInTheDocument();
  });

  it('mounts run feedback after market structure and before the markdown body', async () => {
    render(
      <MarketReviewReportView
        report={marketReviewReportWithStructure}
        content="# Market Review"
        reportLanguage="en"
      />,
    );
    const panel = await screen.findByTestId('report-run-feedback');
    const markdown = screen.getByTestId('market-review-report');
    expect(panel.compareDocumentPosition(markdown) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(panel).getByRole('button', { name: '有用' })).toHaveAttribute(
      'data-control',
      'selection-chip',
    );
  });

  it('hides run feedback when queryId is missing', () => {
    render(
      <MarketReviewReportView
        recordId={12}
        content="# Market Review"
        reportLanguage="en"
      />,
    );
    expect(screen.queryByTestId('report-run-feedback')).not.toBeInTheDocument();
  });
});
