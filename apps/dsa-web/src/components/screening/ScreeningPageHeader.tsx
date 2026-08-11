import type React from 'react';
import { PlusCircle } from 'lucide-react';
import { Surface } from '../common';
import type { ScreeningText } from './screeningText';

export type ScreeningPageHeaderProps = {
  text: ScreeningText;
  enabled: boolean;
  status: string;
};

const ScreeningPageHeader: React.FC<ScreeningPageHeaderProps> = ({
  text,
  enabled,
  status,
}) => (
  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
    <div className="flex items-center gap-3">
      <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-primary text-primary shadow-soft-card">
        <PlusCircle className="h-4 w-4" />
      </span>
      <div>
        <h1 className="text-2xl font-bold tracking-normal text-foreground">{text.title}</h1>
        <p className="mt-1 text-sm text-secondary-text">{text.description}</p>
      </div>
    </div>

    <Surface level="interactive" className="inline-flex w-fit items-center gap-2 px-3 py-2 text-sm">
      <span className={`h-2.5 w-2.5 rounded-full ${enabled ? 'bg-success' : 'bg-warning'}`} />
      <span className="font-medium text-secondary-text">{status}</span>
    </Surface>
  </div>
);

export default ScreeningPageHeader;
