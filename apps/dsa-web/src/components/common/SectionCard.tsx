import type React from 'react';
import { forwardRef } from 'react';
import { Section } from './Section';

interface SectionCardProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export const SectionCard = forwardRef<HTMLElement, SectionCardProps>(({
  title,
  subtitle,
  actions,
  children,
  className = '',
  ...props
}, ref) => {
  return (
    <Section
      {...props}
      ref={ref}
      title={title}
      eyebrow={subtitle}
      actions={actions}
      level="section"
      padding="md"
      className={className}
    >
      {children}
    </Section>
  );
});

SectionCard.displayName = 'SectionCard';
