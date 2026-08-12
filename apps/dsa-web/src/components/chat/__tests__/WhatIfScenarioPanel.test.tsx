import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { WhatIfScenarioPanel } from '../WhatIfScenarioPanel';
import { DEFAULT_WHAT_IF_DRAFT } from '../whatIfScenario';
import type { UiTextKey } from '../../../i18n/uiText';

const COPY: Partial<Record<UiTextKey, string>> = {
  'chat.whatIf.title': 'What-if',
  'chat.whatIf.toggle': 'Enable what-if',
  'chat.whatIf.bannerTitle': 'Banner',
  'chat.whatIf.bannerMessage': 'Banner body',
  'chat.whatIf.limitTitle': 'Limit',
  'chat.whatIf.limitMessage': 'Limit body',
  'chat.whatIf.dimensionLabel': 'Dimension',
  'chat.whatIf.dimension.index': 'Index',
  'chat.whatIf.dimension.fx': 'FX',
  'chat.whatIf.dimension.rate': 'Rate',
  'chat.whatIf.dimension.earnings': 'Earnings',
  'chat.whatIf.directionLabel': 'Direction',
  'chat.whatIf.direction.up': 'Up',
  'chat.whatIf.direction.down': 'Down',
  'chat.whatIf.outcomeLabel': 'Outcome',
  'chat.whatIf.earnings.beat': 'Beat',
  'chat.whatIf.earnings.miss': 'Miss',
  'chat.whatIf.earnings.inline': 'Inline',
  'chat.whatIf.magnitudePctLabel': 'Pct',
  'chat.whatIf.magnitudeBpLabel': 'Bp',
  'chat.whatIf.fxPairLabel': 'Pair',
  'chat.whatIf.magnitudeInvalid': 'Invalid magnitude',
  'chat.whatIf.extraTurnHint': 'Extra turn',
  'chat.whatIf.promote': 'Open this stock in the analysis workbench',
  'chat.whatIf.promoteHint': 'Opens the analysis workbench with the stock prefilled.',
  'chat.whatIf.promoteNeedStock': 'Bind a stock context first to open the analysis workbench.',
};

const t = (key: UiTextKey) => COPY[key] ?? key;

const enabledDraft = {
  ...DEFAULT_WHAT_IF_DRAFT,
  enabled: true,
};

function renderPanel(props: {
  promoteHref?: string | null;
  disabled?: boolean;
}) {
  return render(
    <MemoryRouter>
      <WhatIfScenarioPanel
        t={t}
        draft={enabledDraft}
        onChange={vi.fn()}
        promoteHref={props.promoteHref ?? null}
        disabled={props.disabled}
      />
    </MemoryRouter>,
  );
}

describe('WhatIfScenarioPanel promote handoff', () => {
  it('shows need-stock guidance when promote href is missing', () => {
    renderPanel({ promoteHref: null });
    expect(screen.getByTestId('chat-what-if-promote-need-stock')).toHaveTextContent(
      'Bind a stock context first to open the analysis workbench.',
    );
    expect(screen.queryByTestId('chat-what-if-promote-link')).not.toBeInTheDocument();
  });

  it('renders an enabled handoff link for the analysis workbench', () => {
    renderPanel({ promoteHref: '/research/analysis?stock=600519' });
    const link = screen.getByTestId('chat-what-if-promote-link');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/research/analysis?stock=600519');
    expect(link).toHaveTextContent('Open this stock in the analysis workbench');
    expect(link).not.toHaveAttribute('aria-disabled');
  });

  it('disables the handoff control while the panel is disabled', () => {
    renderPanel({ promoteHref: '/research/analysis?stock=600519', disabled: true });
    const control = screen.getByTestId('chat-what-if-promote-link');
    expect(control.tagName).toBe('SPAN');
    expect(control).toHaveAttribute('aria-disabled', 'true');
    expect(control).not.toHaveAttribute('href');
  });
});
