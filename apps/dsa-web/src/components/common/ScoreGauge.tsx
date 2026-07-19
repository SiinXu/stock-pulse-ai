import type React from 'react';
import { useState, useEffect, useRef } from 'react';
import { useTheme } from 'next-themes';
import { getSentimentLabel, type ReportLanguage } from '../../types/analysis';
import { cn } from '../../utils/cn';
import { normalizeReportLanguage, getReportText } from '../../utils/reportLanguage';

interface ScoreGaugeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
  language?: ReportLanguage;
}

type SentimentKey = 'greed' | 'neutral' | 'fear';

type GaugeVisualStyle = {
  svgFilter?: string;
  glowBlur: number;
  glowOpacity: number;
  glowStrokeExtra: number;
  valueTextShadow?: string;
};

/**
 * Sentiment score gauge with an animated progress ring.
 * Dynamically calculates colors based on sentiment score.
 */
export const ScoreGauge: React.FC<ScoreGaugeProps> = ({
  score,
  size = 'md',
  showLabel = true,
  className = '',
  language = 'zh',
}) => {
  // Animated score state.
  const [animatedScore, setAnimatedScore] = useState(0);
  const [displayScore, setDisplayScore] = useState(0);
  const animationRef = useRef<number | null>(null);
  const prevScoreRef = useRef(0);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  // Animate transitions between score updates.
  useEffect(() => {
    const startScore = prevScoreRef.current;
    const endScore = score;
    const duration = 1000; // Animation duration in ms.
    const startTime = performance.now();

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Use an ease-out cubic curve for a smoother finish.
      const easeOut = 1 - Math.pow(1 - progress, 3);

      const currentScore = startScore + (endScore - startScore) * easeOut;
      setAnimatedScore(currentScore);
      setDisplayScore(Math.round(currentScore));

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      } else {
        prevScoreRef.current = endScore;
      }
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [score]);

  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const label = getSentimentLabel(score, reportLanguage);

  // Size configuration for each gauge variant.
  const sizeConfig = {
    sm: { width: 100, stroke: 8, fontSize: 'text-2xl', labelSize: 'text-xs', gap: 6 },
    md: { width: 140, stroke: 10, fontSize: 'text-4xl', labelSize: 'text-sm', gap: 8 },
    lg: { width: 180, stroke: 12, fontSize: 'text-5xl', labelSize: 'text-base', gap: 10 },
  };

  const { width, stroke, fontSize, labelSize, gap } = sizeConfig[size];
  const radius = (width - stroke) / 2;
  const circumference = 2 * Math.PI * radius;

  // Start from the top and render a 270-degree arc.
  const arcLength = circumference * 0.75;
  const progress = (animatedScore / 100) * arcLength;

  // Sentiment colors are dynamically computed based on score thresholds.
  const sentimentConfig = {
    greed: {
      color: 'hsl(var(--primary))',
      glowFilter: 'transparent',
      lightColor: 'hsl(var(--primary))',
      lightEndColor: 'hsl(var(--primary))',
    },
    neutral: {
      color: 'hsl(var(--secondary-text))',
      glowFilter: 'transparent',
      lightColor: 'hsl(var(--secondary-text))',
      lightEndColor: 'hsl(var(--secondary-text))',
    },
    fear: {
      color: 'hsl(var(--destructive))',
      glowFilter: 'transparent',
      lightColor: 'hsl(var(--destructive))',
      lightEndColor: 'hsl(var(--destructive))',
    },
  };

  // Map score to sentiment key
  const getSentimentKey = (s: number): SentimentKey => {
    if (s >= 60) return 'greed';
    if (s >= 40) return 'neutral';
    return 'fear';
  };

  const sentimentKey = getSentimentKey(animatedScore);
  const colors = sentimentConfig[sentimentKey];
  const uniqueId = `${sentimentKey}-${score}-${animatedScore.toFixed(0)}`;
  // Preserve the established SVG layers while disabling decorative glow.
  const gaugeTheme: GaugeVisualStyle = isDark
    ? {
        svgFilter: 'none',
        glowBlur: 0,
        glowOpacity: 0,
        glowStrokeExtra: gap,
        valueTextShadow: 'none',
      }
    : {
        svgFilter: 'none',
        glowBlur: 0,
        glowOpacity: 0,
        glowStrokeExtra: Math.max(3, gap * 0.55),
        valueTextShadow: 'none',
      };
  const {
    svgFilter,
    glowBlur: overlayBlur,
    glowOpacity: overlayOpacity,
    glowStrokeExtra: overlayStrokeExtra,
    valueTextShadow,
  } = gaugeTheme;

  return (
    <div className={cn('flex flex-col items-center', className)}>
      {showLabel && (
        <span className="label-uppercase mb-3 text-secondary-text">
          {text.fearGreedIndex}
        </span>
      )}

      <div className="relative" style={{ width, height: width }}>
        <svg
          className="gauge-ring overflow-visible"
          width={width}
          height={width}
          style={svgFilter ? { filter: svgFilter } : {}}
        >
          <defs>
            {/* Keep the progress gradient theme-aware without decorative effects. */}
            <linearGradient id={`gauge-gradient-${uniqueId}`} x1="0%" y1="0%" x2="100%" y2="100%">
              {isDark ? (
                <>
                  <stop offset="0%" stopColor={colors.color} stopOpacity="0.6" />
                  <stop offset="100%" stopColor={colors.color} stopOpacity="1" />
                </>
              ) : (
                <>
                  <stop offset="0%" stopColor={colors.lightColor} stopOpacity="0.9" />
                  <stop offset="100%" stopColor={colors.lightEndColor} stopOpacity="1" />
                </>
              )}
            </linearGradient>

            <filter id={`gauge-glow-${uniqueId}`}>
              <feGaussianBlur stdDeviation={overlayBlur} result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Background track */}
          <circle
            cx={width / 2}
            cy={width / 2}
            r={radius}
            fill="none"
            stroke="hsl(var(--foreground) / 0.08)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${arcLength} ${circumference}`}
            transform={`rotate(135 ${width / 2} ${width / 2})`}
          />

          <circle
            cx={width / 2}
            cy={width / 2}
            r={radius}
            fill="none"
            stroke={isDark ? colors.color : colors.lightColor}
            strokeWidth={stroke + overlayStrokeExtra}
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference}`}
            transform={`rotate(135 ${width / 2} ${width / 2})`}
            opacity={overlayOpacity}
            filter={`url(#gauge-glow-${uniqueId})`}
          />

          {/* Progress arc */}
          <circle
            cx={width / 2}
            cy={width / 2}
            r={radius}
            fill="none"
            stroke={`url(#gauge-gradient-${uniqueId})`}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference}`}
            transform={`rotate(135 ${width / 2} ${width / 2})`}
          />
        </svg>

        {/* Center value */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className={cn('font-bold text-foreground', fontSize)}
            style={valueTextShadow ? { textShadow: valueTextShadow } : {}}
          >
            {displayScore}
          </span>
          {showLabel && (
            <span
              className={`${labelSize} font-semibold mt-1`}
              style={{ color: isDark ? colors.color : colors.lightEndColor }}
            >
              {label.toUpperCase()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
