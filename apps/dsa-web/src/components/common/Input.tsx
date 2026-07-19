import type React from 'react';
import { forwardRef, useCallback, useId, useRef, useState } from 'react';
import { Lock, Key } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { getUiColon } from '../../utils/uiLocale';
import { EyeToggleIcon } from './EyeToggleIcon';
import { Field } from './Field';
import { getFieldDescriptionIds } from './fieldDescription';
import { IconButton } from './IconButton';

export type InputSize = 'default' | 'comfortable' | 'primary';

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
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
  /** Adds field or row context to the password visibility action. */
  passwordToggleLabel?: string;
  /** Selects a semantic visible control size without leaking the native size attribute. */
  size?: InputSize;
  /** Applies layout sizing to the field wrapper without replacing input geometry. */
  fieldClassName?: string;
}

const INPUT_SIZE_STYLES: Record<InputSize, string> = {
  default: 'h-8',
  comfortable: 'h-9',
  primary: 'h-10',
};

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
  passwordToggleLabel,
  size,
  fieldClassName,
  style,
  type: inputType,
  'aria-describedby': ariaDescribedBy,
  'aria-invalid': ariaInvalidProp,
  ...props
}, ref) => {
  const { language, t } = useUiLanguage();
  const generatedId = useId();
  const inputId = id ?? props.name ?? generatedId;
  const { hintId, errorId, describedBy } = getFieldDescriptionIds(
    inputId,
    hint,
    error,
    ariaDescribedBy,
  );
  const ariaInvalid = ariaInvalidProp ?? (error ? true : undefined);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const setInputRef = useCallback((node: HTMLInputElement | null) => {
    inputRef.current = node;
    if (typeof ref === 'function') {
      ref(node);
    } else if (ref) {
      ref.current = node;
    }
  }, [ref]);

  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const isPasswordInput = inputType === 'password';
  const isVisibilityControlled = typeof passwordVisible === 'boolean';
  const isLoginAppearance = appearance === 'login';
  const resolvedSize = size ?? (isLoginAppearance ? 'primary' : 'comfortable');
  const visible = isVisibilityControlled ? passwordVisible : isPasswordVisible;
  const effectiveType = isPasswordInput && allowTogglePassword && visible ? 'text' : inputType;

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
      ...style,
      ['--input-surface-border-focus' as string]: 'hsla(var(--destructive), 0.4)',
      ['--input-surface-focus-ring' as string]: '0 0 0 4px hsla(var(--destructive), 0.1)',
    }
    : style;
  const passwordToggleAction = visible ? t('common.hideContent') : t('common.showContent');
  const passwordToggleAriaLabel = passwordToggleLabel
    ? `${passwordToggleAction}${getUiColon(language)}${passwordToggleLabel}`
    : passwordToggleAction;

  const defaultTrailingAction = isPasswordInput && allowTogglePassword ? (
    <IconButton
      variant="ghost"
      size="default"
      tooltip={false}
      className={cn(
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
      aria-label={passwordToggleAriaLabel}
    >
      <EyeToggleIcon visible={visible} />
    </IconButton>
  ) : null;

  const finalTrailingAction = trailingAction ?? defaultTrailingAction;

  return (
    <Field
      controlId={inputId}
      label={label}
      hint={hint}
      error={error}
      hintId={hintId}
      errorId={errorId}
      className={fieldClassName}
      labelClassName={isLoginAppearance ? 'text-[var(--login-label-text)]' : undefined}
      hintClassName={isLoginAppearance ? 'text-[var(--login-hint-text)]' : undefined}
      errorClassName={isLoginAppearance ? 'text-[var(--login-error-text)]' : undefined}
    >
      <div
        className="control-input-target relative flex items-center"
        onPointerDown={(event) => {
          if (event.target === event.currentTarget) {
            inputRef.current?.focus();
          }
        }}
      >
        {leadingIcon && (
          <div className="absolute left-3.5 z-10 pointer-events-none">
            {leadingIcon}
          </div>
        )}
        <input
          {...props}
          ref={setInputRef}
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={ariaInvalid}
          style={inputStyle}
          data-control="input"
          data-appearance={appearance}
          data-size={resolvedSize}
          className={cn(
            isLoginAppearance
              ? 'input-surface input-focus-ring input-appearance-login w-full rounded-xl border bg-transparent px-4 text-base transition-[color,background-color,border-color,box-shadow] duration-150 focus:outline-none motion-reduce:transition-none sm:text-sm'
              : 'w-full rounded-lg border border-border bg-transparent px-3 text-base text-foreground placeholder:text-muted-text transition-[color,background-color,border-color,box-shadow] duration-150 focus:outline-none focus:border-muted-text motion-reduce:transition-none sm:text-xs',
            INPUT_SIZE_STYLES[resolvedSize],
            error ? (isLoginAppearance ? 'border-danger/30' : 'border-danger/40 focus:border-danger') : '',
            leadingIcon ? (isLoginAppearance ? 'pl-10' : 'pl-9') : '',
            finalTrailingAction ? (isLoginAppearance ? 'pr-12' : 'pr-9') : '',
            'disabled:cursor-not-allowed disabled:opacity-60',
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
