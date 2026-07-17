import type React from 'react';
import { useId, useState } from 'react';
import { Lock, Key } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { EyeToggleIcon } from './EyeToggleIcon';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  trailingAction?: React.ReactNode;
  /** Selects a scoped visual appearance for the input. */
  appearance?: 'default' | 'login';
  /** Enables the built-in password visibility toggle. */
  allowTogglePassword?: boolean;
  /** Controls the leading icon style. */
  iconType?: 'password' | 'key' | 'none';
  /** Allows external visibility state control. */
  passwordVisible?: boolean;
  /** Notifies the parent when visibility changes in controlled mode. */
  onPasswordVisibleChange?: (visible: boolean) => void;
}

export const Input = ({ 
  label, 
  hint, 
  error, 
  className = '', 
  id, 
  trailingAction, 
  appearance = 'default',
  allowTogglePassword,
  iconType = 'none',
  passwordVisible,
  onPasswordVisibleChange,
  ...props 
}: InputProps) => {
  const { t } = useUiLanguage();
  const generatedId = useId();
  const inputId = id ?? props.name ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [props['aria-describedby'], errorId ?? hintId].filter(Boolean).join(' ') || undefined;
  const ariaInvalid = props['aria-invalid'] ?? (error ? true : undefined);

  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const isPasswordInput = props.type === 'password';
  const isVisibilityControlled = typeof passwordVisible === 'boolean';
  const isLoginAppearance = appearance === 'login';
  const visible = isVisibilityControlled ? passwordVisible : isPasswordVisible;
  const effectiveType = isPasswordInput && allowTogglePassword && visible ? 'text' : props.type;

  const renderLeadingIcon = () => {
    if (iconType === 'password') {
      return (
        <Lock
          className={cn(
            'h-4 w-4',
            isLoginAppearance ? 'text-[var(--login-input-icon)]' : 'text-muted-text/55'
          )}
        />
      );
    }
    if (iconType === 'key') {
      return (
        <Key
          className={cn(
            'h-4 w-4',
            isLoginAppearance ? 'text-[var(--login-input-icon)]' : 'text-muted-text/55'
          )}
        />
      );
    }
    return null;
  };

  const leadingIcon = renderLeadingIcon();
  const inputStyle = error
    ? {
      ...props.style,
      ['--input-surface-border-focus' as string]: 'hsla(var(--destructive), 0.4)',
      ['--input-surface-focus-ring' as string]: '0 0 0 4px hsla(var(--destructive), 0.1)',
    }
    : props.style;

  const defaultTrailingAction = isPasswordInput && allowTogglePassword ? (
    <button
      type="button"
      className={cn(
        'inline-flex h-11 w-11 items-center justify-center rounded-lg border border-transparent bg-transparent transition-all duration-200 focus:outline-none focus-visible:ring-2',
        isLoginAppearance
          ? visible
            ? 'text-[var(--login-text-secondary)] focus-visible:ring-[var(--login-input-toggle-ring)]'
            : 'text-[var(--login-input-icon)] hover:text-[var(--login-text-secondary)] focus-visible:ring-[var(--login-input-toggle-ring)]'
          : visible
            ? 'text-warning'
            : 'text-muted-text hover:text-warning focus-visible:ring-primary/30'
      )}
      onClick={() => {
        const nextVisible = !visible;
        if (!isVisibilityControlled) {
          setIsPasswordVisible(nextVisible);
        }
        onPasswordVisibleChange?.(nextVisible);
      }}
      aria-label={visible ? t('common.hideContent') : t('common.showContent')}
    >
      <EyeToggleIcon visible={visible} />
    </button>
  ) : null;

  const finalTrailingAction = trailingAction || defaultTrailingAction;

  return (
    <div className="flex flex-col">
      {label ? (
        <label
          htmlFor={inputId}
          className={cn(
            'mb-1.5 text-xs font-medium',
            isLoginAppearance ? 'text-[var(--login-label-text)]' : 'text-secondary-text'
          )}
        >
          {label}
        </label>
      ) : null}
      <div className="relative flex items-center">
        {leadingIcon && (
          <div className="absolute left-3.5 z-10 pointer-events-none">
            {leadingIcon}
          </div>
        )}
        <input
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={ariaInvalid}
          style={inputStyle}
          data-appearance={appearance}
          className={cn(
            isLoginAppearance
              ? 'input-surface input-focus-ring input-appearance-login h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none'
              : 'h-11 w-full rounded-lg border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text',
            error ? (isLoginAppearance ? 'border-danger/30' : 'border-danger/40 focus:border-danger') : '',
            leadingIcon ? (isLoginAppearance ? 'pl-10' : 'pl-9') : '',
            finalTrailingAction ? (isLoginAppearance ? 'pr-12' : 'pr-9') : '',
            'min-h-11 min-w-11 disabled:cursor-not-allowed disabled:opacity-60',
            className,
          )}
          {...props}
          type={effectiveType}
        />
        {finalTrailingAction ? (
          <div className="absolute inset-y-0 right-0 flex items-center">
            {finalTrailingAction}
          </div>
        ) : null}
      </div>
      {error ? (
        <p
          id={errorId}
          role="alert"
          className={cn(
            'mt-2 text-xs',
            isLoginAppearance ? 'text-[var(--login-error-text)]' : 'text-danger'
          )}
        >
          {error}
        </p>
      ) : hint ? (
        <p
          id={hintId}
          className={cn(
            'mt-2 text-xs',
            isLoginAppearance ? 'text-[var(--login-hint-text)]' : 'text-secondary-text'
          )}
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
};
