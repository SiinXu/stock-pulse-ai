import React, { useState } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

interface JsonViewerProps {
  data: Record<string, unknown> | unknown[] | null | undefined;
  maxHeight?: string;
  className?: string;
}

const JSON_TOKEN_PATTERN = /"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|true|false|null/g;

function getTokenClassName(token: string, remainingLine: string): string {
  if (token.startsWith('"')) {
    return /^\s*:/.test(remainingLine) ? 'text-cyan-400' : 'text-emerald-400';
  }
  if (token === 'true' || token === 'false' || token === 'null') {
    return 'text-purple-400';
  }
  return 'text-amber-400';
}

function renderHighlightedLine(line: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const matcher = new RegExp(JSON_TOKEN_PATTERN);
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = matcher.exec(line)) !== null) {
    if (match.index > lastIndex) {
      parts.push(line.slice(lastIndex, match.index));
    }

    const token = match[0];
    const nextIndex = match.index + token.length;
    parts.push(
      <span key={`${match.index}-${token}`} className={getTokenClassName(token, line.slice(nextIndex))}>
        {token}
      </span>,
    );
    lastIndex = nextIndex;
  }

  if (lastIndex < line.length) {
    parts.push(line.slice(lastIndex));
  }

  return parts;
}

/**
 * Structured JSON viewer with syntax highlighting and copy support.
 */
export const JsonViewer: React.FC<JsonViewerProps> = ({
  data,
  maxHeight = '400px',
  className = '',
}) => {
  const [copied, setCopied] = useState(false);
  const { t } = useUiLanguage();

  if (!data) {
    return (
      <div className="text-muted-text italic py-4 text-center">{t('common.noData')}</div>
    );
  }

  const jsonString = JSON.stringify(data, null, 2);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const highlightJson = (json: string): React.ReactNode => {
    return json.split('\n').map((line, index) => {
      return (
        <div key={index} className="leading-relaxed">
          {renderHighlightedLine(line)}
        </div>
      );
    });
  };

  return (
    <div className={`relative ${className}`}>
      {/* Copy action */}
      <button
        type="button"
        onClick={handleCopy}
        className="absolute top-2 right-2 min-h-11 min-w-11 px-2 py-1 text-xs rounded-full
          border border-border bg-elevated hover:bg-hover text-secondary-text
          transition-colors z-10"
      >
        {copied ? t('common.copied') : t('common.copy')}
      </button>

      {/* JSON content */}
      <div
        className="bg-elevated/80 rounded-lg p-4 overflow-auto custom-scrollbar
          border border-border/60 font-mono text-sm text-secondary-text"
        style={{ maxHeight }}
      >
        <pre className="whitespace-pre-wrap break-words">
          {highlightJson(jsonString)}
        </pre>
      </div>
    </div>
  );
};
