import type React from 'react';
import { Eye, EyeOff } from 'lucide-react';

interface EyeToggleIconProps {
  /** true = password visible, show eye-slash (hide). false = password hidden, show eye (show) */
  visible: boolean;
  className?: string;
}

export const EyeToggleIcon: React.FC<EyeToggleIconProps> = ({ visible, className = 'w-4 h-4' }) => {
  if (visible) {
    return <EyeOff className={className} aria-hidden="true" />;
  }
  return <Eye className={className} aria-hidden="true" />;
};
