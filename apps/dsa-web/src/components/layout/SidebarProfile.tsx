import type React from 'react';
import { ProfileMenu } from './ProfileMenu';

interface SidebarProfileProps {
  collapsed?: boolean;
}

export const SidebarProfile: React.FC<SidebarProfileProps> = ({ collapsed = false }) => {
  return <ProfileMenu variant={collapsed ? 'collapsed' : 'sidebar'} />;
};
