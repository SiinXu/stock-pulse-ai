import type React from 'react';
import { forwardRef, useId, useState } from 'react';
import { Lock, Key } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { EyeToggleIcon } from './EyeToggleIcon';
import { Field } from './Field';
import { getFieldDescriptionIds } from './fieldDescription';
import { InputPrimitive } from './InputPrimitive';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
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

export const Input = forwardRef<HTMLInputElement, InputProps>(({
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
}, ref) => {
  const { t } = useUiLanguage();
  const generatedId = useId();
  const inputId = id ?? props.name ?? generatedId;
  const { hintId, errorId, describedBy } = getFieldDescriptionIds(
    inputId,
    hint,
    error,
    props['aria-describedby'],
  );
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
        'inline-flex h-9 w-9 items-center justify-center rounded-lg border border-transparent bg-transparent transition-all duration-200 focus:outline-none focus-visible:ring-2',
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
    <Field
      controlId={inputId}
      label={label}
      hint={hint}
      error={error}
      hintId={hintId}
      errorId={errorId}
      labelClassName={isLoginAppearance ? 'text-[var(--login-label-text)]' : undefined}
      hintClassName={isLoginAppearance ? 'text-[var(--login-hint-text)]' : undefined}
      errorClassName={isLoginAppearance ? 'text-[var(--login-error-text)]' : undefined}
    >
      <div className="relative flex w-full items-center">
        {leadingIcon && (
          <div className="absolute left-3.5 z-10 pointer-events-none">
            {leadingIcon}
          </div>
        )}
        <InputPrimitive
          {...props}
          ref={ref}
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={ariaInvalid}
          invalid={Boolean(error)}
          style={inputStyle}
          data-appearance={appearance}
          className={cn(
            isLoginAppearance
              ? 'input-surface input-focus-ring input-appearance-login h-11 w-full rounded-xl border bg-transparent px-4 text-base transition-all focus:outline-none sm:text-sm'
              : '',
            error ? (isLoginAppearance ? 'border-danger/30' : 'border-danger/40 focus:border-danger') : '',
            leadingIcon ? (isLoginAppearance ? 'pl-10' : 'pl-9') : '',
            finalTrailingAction ? (isLoginAppearance ? 'pr-12' : 'pr-9') : '',
            className,
          )}
          type={effectiveType}
        />
        {finalTrailingAction ? (
          <div className="absolute inset-y-0 right-0 flex items-center">
            {finalTrailingAction}
          </div>
        ) : null}
      </div>
    </Field>
  );
});

Input.displayName = 'Input';
