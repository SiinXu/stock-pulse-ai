/**
 * Shared runtime-performance measurement sink.
 *
 * Multiple Vitest files can record into one report. Flush merges by id so a
 * later file cannot drop earlier measurements if workers write the same path.
 */
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';

export type RuntimePerfMeasurement = {
  id: string;
  value: number;
  unit: string;
  samples?: number[];
};

const measurements: RuntimePerfMeasurement[] = [];

export function recordRuntimePerf(id: string, value: number, unit: string, samples?: number[]): void {
  const entry: RuntimePerfMeasurement = {
    id,
    value,
    unit,
    ...(samples && samples.length > 0 ? { samples: [...samples] } : {}),
  };
  const existing = measurements.findIndex((item) => item.id === id);
  if (existing >= 0) measurements[existing] = entry;
  else measurements.push(entry);
}

function readExistingReport(reportPath: string): RuntimePerfMeasurement[] {
  if (!existsSync(reportPath)) return [];
  try {
    const parsed = JSON.parse(readFileSync(reportPath, 'utf8')) as {
      measurements?: RuntimePerfMeasurement[];
    };
    return Array.isArray(parsed.measurements) ? parsed.measurements : [];
  } catch {
    return [];
  }
}

export function flushRuntimePerfReport(): void {
  const reportPath = (globalThis as { process?: { env?: Record<string, string | undefined> } })
    .process
    ?.env
    ?.DSA_RUNTIME_PERF_REPORT;
  if (!reportPath || measurements.length === 0) return;
  mkdirSync(path.dirname(reportPath), { recursive: true });
  const byId = new Map<string, RuntimePerfMeasurement>();
  for (const entry of readExistingReport(reportPath)) {
    if (entry && typeof entry.id === 'string') byId.set(entry.id, entry);
  }
  for (const entry of measurements) {
    byId.set(entry.id, entry);
  }
  writeFileSync(
    reportPath,
    JSON.stringify(
      {
        measuredAt: new Date().toISOString(),
        measurements: [...byId.values()],
      },
      null,
      2,
    ),
  );
}
