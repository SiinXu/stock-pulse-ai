import { describe } from 'vitest';
import { registerSettingsPageAdvancedTests } from './SettingsPage.advancedTests';
import { registerSettingsPageDisclosureTests } from './SettingsPage.disclosureTests';
import { registerSettingsPageIntegrationTests } from './SettingsPage.integrationTests';
import { registerSettingsPageLlmTests } from './SettingsPage.llmTests';
import { registerSettingsPageOverviewTests } from './SettingsPage.overviewTests';
import { registerSettingsPageSchedulerTests } from './SettingsPage.schedulerTests';
import SettingsPageTestHarness from './SettingsPage.testHarness';

const { registerSettingsPageBeforeEach } = SettingsPageTestHarness;

describe('SettingsPage', () => {
  registerSettingsPageBeforeEach();
  registerSettingsPageOverviewTests();
  registerSettingsPageLlmTests();
  registerSettingsPageIntegrationTests();
  registerSettingsPageSchedulerTests();
  registerSettingsPageAdvancedTests();
  registerSettingsPageDisclosureTests();
});
