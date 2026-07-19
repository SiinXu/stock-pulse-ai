import type React from 'react';
import { Input } from './Input';

export type CredentialPurpose =
  | 'admin-current-password'
  | 'admin-new-password'
  | 'admin-new-password-confirmation'
  | 'provider-secret'
  | 'configuration-secret';

type BaseCredentialInputProps = Omit<
  React.ComponentProps<typeof Input>,
  'autoCapitalize' | 'autoComplete' | 'autoCorrect' | 'name' | 'spellCheck' | 'type'
>;

type CredentialInputProps = BaseCredentialInputProps & (
  | {
      purpose: Exclude<CredentialPurpose, 'configuration-secret'>;
      credentialId?: never;
    }
  | {
      purpose: 'configuration-secret';
      credentialId: string;
    }
);

const CREDENTIAL_INPUT_CONTRACT = {
  'admin-current-password': {
    name: 'stockpulse-admin-current-password',
    autoComplete: 'current-password',
  },
  'admin-new-password': {
    name: 'stockpulse-admin-new-password',
    autoComplete: 'new-password',
  },
  'admin-new-password-confirmation': {
    name: 'stockpulse-admin-new-password-confirmation',
    autoComplete: 'new-password',
  },
  'provider-secret': {
    name: 'stockpulse-provider-api-key',
    autoComplete: 'off',
  },
} as const satisfies Record<
  Exclude<CredentialPurpose, 'configuration-secret'>,
  { name: string; autoComplete: string }
>;

function normalizeCredentialId(credentialId: string): string {
  return credentialId
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'unknown';
}

export const CredentialInput: React.FC<CredentialInputProps> = ({ purpose, ...credentialProps }) => {
  const { credentialId, ...props } = credentialProps as BaseCredentialInputProps & {
    credentialId?: string;
  };
  const contract = purpose === 'configuration-secret'
    ? {
        name: `stockpulse-config-${normalizeCredentialId(credentialId ?? '')}`,
        autoComplete: 'off',
      }
    : CREDENTIAL_INPUT_CONTRACT[purpose];
  return (
    <Input
      {...props}
      type="password"
      name={contract.name}
      autoComplete={contract.autoComplete}
      autoCapitalize="none"
      autoCorrect="off"
      spellCheck={false}
      data-credential-purpose={purpose}
    />
  );
};
