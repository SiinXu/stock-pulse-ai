import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export type PressableProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

/**
 * Shared button primitive for compound controls that own their visual treatment,
 * such as selectable rows and cards.
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
    data-control="pressable"
    className={cn(
      'control-hit-target relative cursor-pointer',
      'transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-150 motion-reduce:transition-none',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25',
      'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
  />
));

Pressable.displayName = 'Pressable';
