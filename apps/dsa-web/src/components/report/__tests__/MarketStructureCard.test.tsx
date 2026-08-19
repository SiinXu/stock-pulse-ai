import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { MarketStructureContext } from '../../../types/analysis';
import { applyPriceDirection } from '../../theme/themeRuntime';
import { MarketStructureCard } from '../MarketStructureCard';

const context: MarketStructureContext = {
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
    laggingThemes: [],
    themeBreadth: {
      activeCount: 1,
      leadingConceptCount: 1,
      leadingIndustryCount: 1,
      laggingCount: 0,
    },
    dataQuality: {
      status: 'partial',
      missingFields: ['industry_rankings'],
      sources: [],
      errors: [],
    },
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
    relatedBoards: [
      { name: '机器人概念', type: '概念', source: 'concept', rank: 1, changePct: 4.2 },
    ],
    stockRole: 'follower',
    themePhase: 'accelerating',
    riskTags: [
      { code: 'theme_data_partial', message: '题材主线数据不完整' },
      { code: 'stock_theme_evidence_partial', message: '个股板块未匹配到市场题材榜单，个股位置按降级证据处理' },
    ],
    missingFields: ['hotspot_constituents', 'leader_stocks'],
  },
};

describe('MarketStructureCard', () => {
  afterEach(() => {
    applyPriceDirection('cn', { persist: false });
  });

  it('renders market layer and stock layer in Chinese', () => {
    render(<MarketStructureCard context={context} language="zh" />);

    expect(screen.getByRole('region', { name: '题材主线与个股位置' })).toBeInTheDocument();
    expect(screen.getByText('大盘题材层')).toBeVisible();
    expect(screen.getByText('个股位置层')).toBeVisible();
    expect(screen.getAllByText('部分可用')).toHaveLength(3);
    expect(screen.getAllByText(/机器人概念/)).toHaveLength(3);
    expect(screen.getByText('加速')).toBeVisible();
    expect(screen.getByText('跟随')).toBeVisible();
    expect(screen.getByText('题材主线数据不完整')).toBeVisible();
    expect(screen.getByText('leader_stocks')).toBeVisible();
  });

  it('renders English labels', () => {
    render(<MarketStructureCard context={context} language="en" />);

    expect(screen.getByRole('region', { name: 'Themes and Stock Position' })).toBeInTheDocument();
    expect(screen.getByText('Market Theme Layer')).toBeVisible();
    expect(screen.getByText('Stock Position Layer')).toBeVisible();
    expect(screen.getByText('Accelerating')).toBeVisible();
    expect(screen.getByText('Follower')).toBeVisible();
    expect(screen.getByText('Missing Evidence')).toBeVisible();
    expect(screen.getByText('Market theme data is incomplete')).toBeVisible();
    expect(screen.getByText('Stock board did not match theme rankings')).toBeVisible();
    expect(screen.queryByText('题材主线数据不完整')).not.toBeInTheDocument();
  });

  it('renders Korean labels', () => {
    render(<MarketStructureCard context={context} language="ko" />);

    expect(screen.getByRole('region', { name: '테마 라인 및 종목 포지션' })).toBeInTheDocument();
    expect(screen.getByText('시장 테마 레이어')).toBeVisible();
    expect(screen.getByText('종목 포지션 레이어')).toBeVisible();
    expect(screen.getByText('가속')).toBeVisible();
    expect(screen.getByText('추종')).toBeVisible();
    expect(screen.getByText('테마 데이터가 불완전합니다')).toBeVisible();
    expect(screen.getByText('종목 보드가 테마 랭킹과 일치하지 않았습니다')).toBeVisible();
  });

  it('does not render unsupported or invalid context', () => {
    const unsupported = {
      ...context,
      status: 'not_supported',
    } satisfies MarketStructureContext;

    const { container, rerender } = render(<MarketStructureCard context={unsupported} />);
    expect(container).toBeEmptyDOMElement();

    rerender(<MarketStructureCard context={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('paints ranked theme change percents with price tokens for both preferences', () => {
    applyPriceDirection('cn', { persist: false });
    const first = render(<MarketStructureCard context={context} language="en" />);
    const up = screen.getAllByText('+4.20%')[0];
    expect(up).toHaveStyle({ color: 'var(--price-red)' });
    expect(up).not.toHaveClass('text-success');
    first.unmount();

    applyPriceDirection('us', { persist: false });
    render(<MarketStructureCard context={context} language="en" />);
    expect(screen.getAllByText('+4.20%')[0]).toHaveStyle({ color: 'var(--price-green)' });
  });

  it('leaves a flat 0% theme change unpainted', () => {
    const flat = {
      ...context,
      marketThemeContext: {
        ...context.marketThemeContext,
        activeThemes: [{ name: 'Flat theme', changePct: 0, rank: 1, source: 'concept' }],
        leadingConcepts: [],
        leadingIndustries: [],
      },
    } satisfies MarketStructureContext;
    render(<MarketStructureCard context={flat} language="en" />);
    const node = screen.getByText('0.00%');
    expect(node).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(node).not.toHaveStyle({ color: 'var(--price-green)' });
    expect(node).not.toHaveClass('text-success');
  });

  it('leaves unknown theme change percents unpainted', () => {
    const unknownChange = {
      ...context,
      marketThemeContext: {
        ...context.marketThemeContext,
        activeThemes: [{ name: 'Unknown theme', changePct: Number.NaN, rank: 1, source: 'concept' }],
        leadingConcepts: [],
        leadingIndustries: [],
      },
    } satisfies MarketStructureContext;
    render(<MarketStructureCard context={unknownChange} language="en" />);
    expect(screen.getByText('Unknown theme')).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(screen.getByText('Unknown theme')).not.toHaveStyle({ color: 'var(--price-green)' });
  });
});
