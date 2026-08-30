import type React from 'react';
import { Surface } from '../common';

export const SettingsLoading: React.FC = () => {
  return (
    <div className="flex flex-col animate-fade-in density-gap-stack">
      {Array.from({ length: 6 }).map((_, index) => (
        <Surface key={index} level="section" padding="sm">
          <div className="bg-muted h-3 w-32 rounded" />
          <div className="bg-muted/50 mt-3 h-10 rounded-lg" />
        </Surface>
      ))}
    </div>
  );
};
