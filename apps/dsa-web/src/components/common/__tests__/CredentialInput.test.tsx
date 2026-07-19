import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CredentialInput } from '../CredentialInput';

describe('CredentialInput', () => {
  it.each([
    ['admin-current-password', 'stockpulse-admin-current-password', 'current-password'],
    ['admin-new-password', 'stockpulse-admin-new-password', 'new-password'],
    ['admin-new-password-confirmation', 'stockpulse-admin-new-password-confirmation', 'new-password'],
    ['provider-secret', 'stockpulse-provider-api-key', 'off'],
  ] as const)('enforces the %s browser identity', (purpose, name, autoComplete) => {
    render(<CredentialInput purpose={purpose} label={purpose} />);

    const input = screen.getByLabelText(purpose);
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('name', name);
    expect(input).toHaveAttribute('autocomplete', autoComplete);
    expect(input).toHaveAttribute('autocapitalize', 'none');
    expect(input).toHaveAttribute('autocorrect', 'off');
    expect(input).toHaveAttribute('spellcheck', 'false');
    expect(input).toHaveAttribute('data-credential-purpose', purpose);
  });

  it('retains the shared password visibility control', () => {
    render(<CredentialInput purpose="provider-secret" label="Provider API key" allowTogglePassword />);

    const input = screen.getByLabelText('Provider API key');
    fireEvent.click(screen.getByRole('button', { name: '显示内容' }));
    expect(input).toHaveAttribute('type', 'text');
    expect(input).toHaveAttribute('name', 'stockpulse-provider-api-key');
    expect(input).toHaveAttribute('autocomplete', 'off');
  });

  it('gives configuration secrets stable field-specific browser identities', () => {
    render(
      <CredentialInput
        purpose="configuration-secret"
        credentialId="OPENAI_API_KEYS.2"
        label="Configuration secret"
      />,
    );

    const input = screen.getByLabelText('Configuration secret');
    expect(input).toHaveAttribute('name', 'stockpulse-config-openai-api-keys-2');
    expect(input).toHaveAttribute('autocomplete', 'off');
    expect(input).toHaveAttribute('data-credential-purpose', 'configuration-secret');
  });
});
