import type { SystemConfigItem } from '../../types/systemConfig';

export function getConfigItem(items: SystemConfigItem[], key: string) {
  return items.find((item) => item.key === key);
}
