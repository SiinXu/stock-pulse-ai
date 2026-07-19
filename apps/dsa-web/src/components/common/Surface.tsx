import type React from 'react';
import { createElement, forwardRef } from 'react';
import { cn } from '../../utils/cn';

export type SurfaceLevel = 'canvas' | 'section' | 'interactive' | 'overlay';
export type SurfacePadding = 'none' | 'sm' | 'md' | 'lg';
export type SurfaceElement = 'div' | 'section' | 'article' | 'aside';

export interface SurfaceProps extends React.HTMLAttributes<HTMLElement> {
  as?: SurfaceElement;
  level?: SurfaceLevel;
  padding?: SurfacePadding;
  hoverable?: boolean;
}

const SURFACE_LEVEL_STYLES: Record<SurfaceLevel, string> = {
  canvas: 'bg-transparent',
  section: 'rounded-xl bg-card',
  interactive: 'rounded-xl border border-border bg-card',
  overlay: 'rounded-xl border border-border bg-elevated shadow-soft-card-strong',
};

const SURFACE_PADDING_STYLES: Record<SurfacePadding, string> = {
  none: '',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
};

export const Surface = forwardRef<HTMLElement, SurfaceProps>(({
  as = 'div',
  level = 'canvas',
  padding = 'none',
  hoverable = false,
  className,
  children,
  ...props
}, ref) => createElement(
  as,
  {
    ...props,
    ref,
    'data-surface-level': level,
    'data-surface-hoverable': hoverable || undefined,
    className: cn(
      'relative',
      SURFACE_LEVEL_STYLES[level],
      SURFACE_PADDING_STYLES[padding],
      hoverable && 'transition-[background-color,border-color] duration-150 hover:border-primary/25 hover:bg-hover/60 motion-reduce:transition-none',
      className,
    ),
  },
  children,
));

Surface.displayName = 'Surface';
