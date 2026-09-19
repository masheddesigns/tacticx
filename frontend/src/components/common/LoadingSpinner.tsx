import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface LoadingSpinnerProps {
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  label = 'Loading intelligence...',
  size = 'md',
  className,
}) => {
  const iconSizes = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  };

  return (
    <div
      role="status"
      aria-label={label}
      className={cn(
        'flex flex-col items-center justify-center py-12 px-4 gap-3 text-slate-400',
        className
      )}
    >
      <Loader2 className={cn('animate-spin text-emerald-500', iconSizes[size])} />
      {label && <span className="text-xs font-mono uppercase tracking-wider text-slate-500">{label}</span>}
    </div>
  );
};
