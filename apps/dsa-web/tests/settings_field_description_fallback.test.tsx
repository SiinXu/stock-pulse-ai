import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SettingsField } from '../src/components/settings/SettingsField';

describe('SettingsField description fallback', () => {
  it('uses schema.description when i18n map has no description for key', () => {
    const { container } = render(
      <SettingsField
        item={{
          key: 'UNMAPPED_FALLBACK_FIELD',
          value: '1',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'UNMAPPED_FALLBACK_FIELD',
            title: 'Unmapped fallback field',
            description: 'schema fallback description',
            category: 'system',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            defaultValue: null,
            options: [],
            validation: {},
            displayOrder: 9999,
          },
        }}
        value="1"
        onChange={() => undefined}
      />
    );

    const tooltipTrigger = container.querySelector('.cursor-help')?.parentElement;
    expect(tooltipTrigger).toBeTruthy();
    fireEvent.mouseEnter(tooltipTrigger as HTMLElement);

    expect(screen.getByText('schema fallback description')).toBeTruthy();
  });
});
