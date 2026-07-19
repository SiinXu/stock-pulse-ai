import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export type PressableProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

/**
 * Unstyled shared button primitive for compound controls that own their visual
 * treatment, such as menu rows, tabs, and selectable cards.
 */
export const Pressable = forwardRef<HTMLButtonElement, PressableProps>(({
  type = 'button',
  className,
  ...props
}, ref) => (
  <button
    {...props}
    ref={ref}
    type={type}
    className={cn(
      'ui-touch-target min-h-6 min-w-6 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15',
      'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
  />
));

Pressable.displayName = 'Pressable';
