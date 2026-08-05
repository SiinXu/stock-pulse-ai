/**
 * Shared helpers for Vitest unit tests in apps/dsa-web.
 * Import from here instead of redefining createDeferred / chooseOption per file.
 */
import { fireEvent, within } from '@testing-library/react';

/**
 * Create a manually controlled Promise for async test sequencing.
 * Returns resolve and reject so callers can settle the promise on demand.
 */
export function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

/** Open a Radix/custom Select listbox by clicking its trigger. */
export function openListbox(trigger: HTMLElement): HTMLElement {
  fireEvent.click(trigger);
  return document.getElementById(trigger.getAttribute('aria-controls')!)!;
}

/**
 * Select an option in a listbox by data-value.
 * trigger must be the Select trigger element (role=combobox).
 */
export function chooseOption(trigger: HTMLElement, value: string): void {
  const listbox = openListbox(trigger);
  const option = within(listbox)
    .getAllByRole('option')
    .find((item) => item.getAttribute('data-value') === value)!;
  fireEvent.click(option);
}
