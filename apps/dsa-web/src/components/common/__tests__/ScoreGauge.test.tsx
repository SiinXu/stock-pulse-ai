import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ScoreGauge } from '../ScoreGauge';

const { themeState } = vi.hoisted(() => ({
  themeState: { resolvedTheme: 'light' },
}));

vi.mock('next-themes', () => ({
  useTheme: () => themeState,
}));

describe('ScoreGauge', () => {
  let animationFrames: FrameRequestCallback[];

  beforeEach(() => {
    animationFrames = [];
    themeState.resolvedTheme = 'light';
    vi.spyOn(performance, 'now').mockReturnValue(0);
    vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => {
      animationFrames.push(callback);
      return animationFrames.length;
    }));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each([
    [39, 'fear'],
    [40, 'neutral'],
    [59, 'neutral'],
    [60, 'greed'],
  ])('keeps score %i in the %s sentiment band', (score, sentiment) => {
    const { container } = render(<ScoreGauge score={score} showLabel={false} />);

    act(() => animationFrames.shift()?.(1000));

    expect(container.querySelector(`[id^="gauge-gradient-${sentiment}-"]`)).not.toBeNull();
  });

  it.each(['light', 'dark'])(
    'keeps the score animation and established SVG layers without visible glow in %s mode',
    (theme) => {
      themeState.resolvedTheme = theme;
      const { container, getByText } = render(<ScoreGauge score={80} showLabel={false} />);

      act(() => animationFrames.shift()?.(500));
      expect(getByText('70')).toBeInTheDocument();

      act(() => animationFrames.shift()?.(1000));
      expect(getByText('80')).toBeInTheDocument();
      expect(container.querySelectorAll('svg circle')).toHaveLength(3);
      expect(container.querySelector('svg filter')).not.toBeNull();
      expect(container.querySelector('svg')?.style.filter).toBe('none');
      expect(container.querySelectorAll('svg circle')[1]).toHaveAttribute('opacity', '0');
    },
  );
});
