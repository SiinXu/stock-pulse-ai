import type React from 'react';

export type PlaygroundFixtureProfile = 'ready' | 'empty' | 'error' | 'slow';
export type PlaygroundViewport = 'auto' | 'phone' | 'tablet' | 'desktop';

export type PlaygroundCategoryId =
  | 'foundation'
  | 'layout'
  | 'dashboard'
  | 'alerts'
  | 'history'
  | 'signals'
  | 'reports'
  | 'runFlow'
  | 'settings'
  | 'stockSearch'
  | 'tasks'
  | 'watchlist';

export type PlaygroundScenarioId =
  | 'default'
  | 'variants'
  | 'sizes'
  | 'states'
  | 'interactive'
  | 'loading'
  | 'empty'
  | 'error';

export interface PlaygroundScenario {
  id: PlaygroundScenarioId;
}

export interface PlaygroundEntry {
  id: string;
  name: string;
  category: PlaygroundCategoryId;
  sourcePath: string;
  scenarios: readonly PlaygroundScenario[];
  canvas?: 'padded' | 'full';
}

export type PlaygroundScenarioRenderer = React.ComponentType;

export interface PlaygroundRequestLog {
  id: string;
  method: string;
  path: string;
  status: number;
  durationMs: number;
}

export type PlaygroundFrameMessage =
  | {
      channel: 'stockpulse-playground';
      version: 1;
      type: 'ready';
    }
  | {
      channel: 'stockpulse-playground';
      version: 1;
      type: 'api-log';
      event: PlaygroundRequestLog;
    };

const REQUEST_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']);

function hasOnlyKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const allowed = new Set(keys);
  return Object.keys(value).every((key) => allowed.has(key));
}

export function isPlaygroundFrameMessage(value: unknown): value is PlaygroundFrameMessage {
  if (!value || typeof value !== 'object') return false;
  const message = value as Record<string, unknown>;
  if (message.channel !== 'stockpulse-playground' || message.version !== 1) return false;
  if (message.type === 'ready') return hasOnlyKeys(message, ['channel', 'version', 'type']);
  if (message.type !== 'api-log' || !message.event || typeof message.event !== 'object') return false;
  if (!hasOnlyKeys(message, ['channel', 'version', 'type', 'event'])) return false;
  const event = message.event as Record<string, unknown>;
  return typeof event.id === 'string'
    && typeof event.method === 'string'
    && REQUEST_METHODS.has(event.method)
    && typeof event.path === 'string'
    && event.path.startsWith('/')
    && !event.path.includes('?')
    && !event.path.includes('#')
    && typeof event.status === 'number'
    && Number.isInteger(event.status)
    && event.status >= 0
    && event.status <= 599
    && typeof event.durationMs === 'number'
    && Number.isFinite(event.durationMs)
    && event.durationMs >= 0
    && hasOnlyKeys(event, ['id', 'method', 'path', 'status', 'durationMs']);
}
