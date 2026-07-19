import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Button } from './Button';
import { IconButton } from './IconButton';
import { InlineAlert } from './InlineAlert';
import { useClipboard } from './useClipboard';

interface JsonViewerProps {
  data: Record<string, unknown> | unknown[] | null | undefined;
  maxHeight?: string;
  className?: string;
  copyIconOnly?: boolean;
}

const JSON_TOKEN_PATTERN = /"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|true|false|null/g;

function getTokenClassName(token: string, remainingLine: string): string {
  if (token.startsWith('"')) {
    return /^\s*:/.test(remainingLine) ? 'text-primary' : 'text-success';
  }
  if (token === 'true' || token === 'false' || token === 'null') {
    return 'text-secondary-text';
  }
  return 'text-warning';
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
  copyIconOnly = false,
}) => {
  const [copied, setCopied] = useState(false);
  const { t } = useUiLanguage();
  const { copyText, copyError } = useClipboard();

  if (!data) {
    return (
      <div className="text-muted-text italic py-4 text-center">{t('common.noData')}</div>
    );
  }

  const jsonString = JSON.stringify(data, null, 2);

  const handleCopy = async () => {
    if (!await copyText(jsonString)) return;
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
    <div className={className}>
      {copyError ? <InlineAlert variant="danger" message={copyError} className="mb-2" /> : null}
      <div className="relative">
        {/* Copy action */}
        {copyIconOnly ? (
          <IconButton
            onClick={handleCopy}
            aria-label={copied ? t('common.copied') : t('common.copy')}
            tooltip={false}
            className="absolute right-2 top-2 z-10"
          >
            {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
          </IconButton>
        ) : (
          <Button
            type="button"
            variant="secondary"
            size="xl"
            onClick={handleCopy}
            aria-label={copied ? t('common.copied') : t('common.copy')}
            className="absolute right-2 top-2 z-10 min-h-11 min-w-11 px-3 text-xs"
          >
            {copied ? t('common.copied') : t('common.copy')}
          </Button>
        )}

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
    </div>
  );
};
