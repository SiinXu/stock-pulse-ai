import { describe, expect, it } from 'vitest';
import { parseModelAccessFieldKey } from '../modelAccessFieldKey';

describe('parseModelAccessFieldKey', () => {
  it('recognizes a connection display-name field under the stable connection id', () => {
    expect(parseModelAccessFieldKey('LLM_OPENAI_WORK_DISPLAY_NAME')).toEqual({
      connectionId: 'openai_work',
      suffix: 'DISPLAY_NAME',
    });
  });
});
