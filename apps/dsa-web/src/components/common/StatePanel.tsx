import type React from 'react';
import { forwardRef } from 'react';
import { AlertCircle, CircleCheck, LoaderCircle, ShieldAlert, TriangleAlert } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Surface } from './Surface';

export type StatePanelState = 'loading' | 'blocked' | 'partial' | 'empty' | 'error' | 'retrying' | 'success';
export type StatePanelSize = 'compact' | 'default';

type StatePanelTitleElement = 'p' | 'h2' | 'h3' | 'h4' | 'span';

export interface StatePanelProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title' | 'role' | 'aria-live' | 'aria-busy'> {
  state: StatePanelState;
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  size?: StatePanelSize;
  titleAs?: StatePanelTitleElement;
  surfaceLevel?: 'canvas' | 'section';
}

const STATE_ICON_STYLES: Record<StatePanelState, string> = {
  loading: 'bg-primary/10 text-primary',
  retrying: 'bg-primary/10 text-primary',
  empty: 'bg-subtle text-secondary-text',
  blocked: 'bg-warning/10 text-warning',
  partial: 'bg-warning/10 text-warning',
  error: 'bg-danger/10 text-danger',
  success: 'bg-success/10 text-success',
};

function defaultStateIcon(state: StatePanelState): React.ReactNode {
  if (state === 'loading' || state === 'retrying') {
    return <LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" />;
  }
  if (state === 'error') return <AlertCircle aria-hidden="true" />;
  if (state === 'blocked') return <ShieldAlert aria-hidden="true" />;
  if (state === 'partial') return <TriangleAlert aria-hidden="true" />;
  if (state === 'success') return <CircleCheck aria-hidden="true" />;
  return null;
}

export const StatePanel = forwardRef<HTMLElement, StatePanelProps>(({
  state,
  title,
  description,
  icon,
  action,
  size = 'default',
  titleAs = 'h2',
  surfaceLevel = 'canvas',
  className,
  ...props
}, ref) => {
  const isBusy = state === 'loading' || state === 'retrying';
  const role = state === 'error' ? 'alert' : isBusy || state === 'partial' || state === 'success' ? 'status' : undefined;
  const ariaLive = state === 'error' ? 'assertive' : role === 'status' ? 'polite' : undefined;
  const stateIcon = icon ?? defaultStateIcon(state);
  const Title = titleAs;

  return (
    <Surface
      {...props}
      ref={ref}
      level={surfaceLevel}
      role={role}
      aria-live={ariaLive}
      aria-busy={isBusy || undefined}
      data-state-panel={state}
      className={cn(
        'flex flex-col items-center justify-center px-4 text-center',
        size === 'compact' ? 'gap-2 py-5' : 'gap-3 py-8',
        className,
      )}
    >
      {stateIcon ? (
        <div className={cn('flex h-10 w-10 items-center justify-center rounded-full [&>svg]:h-5 [&>svg]:w-5', STATE_ICON_STYLES[state])}>
          {stateIcon}
        </div>
      ) : null}
      <div className="space-y-1">
        <Title className="text-sm font-semibold text-foreground">{title}</Title>
        {description ? <div className="mx-auto max-w-md text-sm text-secondary-text">{description}</div> : null}
      </div>
      {action ? <div className="flex items-center justify-center">{action}</div> : null}
    </Surface>
  );
});

StatePanel.displayName = 'StatePanel';
