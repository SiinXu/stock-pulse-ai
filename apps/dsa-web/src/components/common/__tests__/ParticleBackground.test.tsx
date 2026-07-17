import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ParticleBackground } from '../ParticleBackground';

type CanvasContextStub = Pick<
  CanvasRenderingContext2D,
  'arc' | 'beginPath' | 'clearRect' | 'fill' | 'lineTo' | 'moveTo' | 'stroke'
> & {
  canvas: HTMLCanvasElement;
  fillStyle: string | CanvasGradient | CanvasPattern;
  lineWidth: number;
  strokeStyle: string | CanvasGradient | CanvasPattern;
};

describe('ParticleBackground', () => {
  let animationFrames: FrameRequestCallback[];
  let fillStyles: Array<string | CanvasGradient | CanvasPattern>;
  let strokeStyles: Array<string | CanvasGradient | CanvasPattern>;
  let getPropertyValue: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    animationFrames = [];
    fillStyles = [];
    strokeStyles = [];
    document.documentElement.className = '';

    let randomCall = 0;
    vi.spyOn(Math, 'random').mockImplementation(() => {
      const slot = randomCall % 7;
      const particleIndex = Math.floor(randomCall / 7);
      randomCall += 1;
      return slot === 5 ? ((particleIndex % 3) + 0.1) / 4 : 0;
    });
    getPropertyValue = vi.fn((name: string) => {
      const dark = document.documentElement.classList.contains('dark');
      const tokens: Record<string, string> = dark
        ? {
            '--muted-text': '210 10% 80%',
            '--primary': '120 50% 72%',
            '--secondary-text': '75 5% 62%',
          }
        : {
            '--muted-text': '210 10% 20%',
            '--primary': '120 50% 42%',
            '--secondary-text': '75 5% 42%',
          };
      return tokens[name] ?? '';
    });
    vi.spyOn(window, 'getComputedStyle').mockImplementation(() => {
      return {
        getPropertyValue,
      } as unknown as CSSStyleDeclaration;
    });

    vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => {
      animationFrames.push(callback);
      return animationFrames.length;
    }));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());

    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function getContext(
      this: HTMLCanvasElement,
    ) {
      const context: CanvasContextStub = {
        canvas: this,
        arc: vi.fn(),
        beginPath: vi.fn(),
        clearRect: vi.fn(),
        fill: vi.fn(),
        lineTo: vi.fn(),
        moveTo: vi.fn(),
        stroke: vi.fn(),
        lineWidth: 0,
        get strokeStyle() {
          return strokeStyles.at(-1) ?? '';
        },
        set strokeStyle(value: string | CanvasGradient | CanvasPattern) {
          strokeStyles.push(value);
        },
        get fillStyle() {
          return fillStyles.at(-1) ?? '';
        },
        set fillStyle(value: string | CanvasGradient | CanvasPattern) {
          fillStyles.push(value);
        },
      };
      return context as CanvasRenderingContext2D;
    });
  });

  afterEach(() => {
    cleanup();
    document.documentElement.className = '';
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('uses current CSS tokens after light to dark to light theme changes', () => {
    render(<ParticleBackground />);

    expect(fillStyles).toContain('hsl(210 10% 20% / 0.2)');
    expect(fillStyles).toContain('hsl(120 50% 42% / 0.2)');
    expect(fillStyles).toContain('hsl(75 5% 42% / 0.2)');
    expect(strokeStyles).toContain('hsl(210 10% 20% / 0.3)');

    fillStyles = [];
    strokeStyles = [];
    document.documentElement.classList.add('dark');
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 10, clientY: 10 }));
    act(() => animationFrames.shift()?.(16));
    expect(fillStyles).toContain('hsl(210 10% 80% / 0.2)');
    expect(fillStyles).toContain('hsl(120 50% 72% / 0.2)');
    expect(fillStyles).toContain('hsl(75 5% 62% / 0.2)');
    expect(strokeStyles.some((value) => String(value).startsWith('hsl(210 10% 80% / '))).toBe(true);
    expect(strokeStyles.some((value) => String(value).startsWith('hsl(120 50% 72% / '))).toBe(true);

    fillStyles = [];
    strokeStyles = [];
    document.documentElement.classList.remove('dark');
    act(() => animationFrames.shift()?.(32));
    expect(fillStyles).toContain('hsl(210 10% 20% / 0.2)');
    expect(fillStyles).toContain('hsl(120 50% 42% / 0.2)');
    expect(fillStyles).toContain('hsl(75 5% 42% / 0.2)');
    expect(strokeStyles.some((value) => String(value).startsWith('hsl(120 50% 42% / '))).toBe(true);
    expect(window.getComputedStyle).toHaveBeenCalledTimes(1);
    expect(getPropertyValue).toHaveBeenCalledTimes(9);
  });
});
