import type React from 'react';
import { cn } from '../../utils/cn';
import { getOverlayStyle } from './overlayZ';

interface ToastViewportProps {
  children: React.ReactNode;
  className?: string;
}

export const ToastViewport: React.FC<ToastViewportProps> = ({ children, className = '' }) => {
  return (
    <div
      style={getOverlayStyle('toast')}
      className={cn('pointer-events-none fixed bottom-5 right-5 flex w-90 max-w-[calc(100vw-1.5rem)] flex-col gap-3', className)}
    >
      {children}
    </div>
  );
};
