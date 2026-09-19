import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { cn } from '../../lib/utils';
import { ApiError } from '../../api/client';

export interface ErrorCardProps {
  title?: string;
  error?: Error | ApiError | null;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

const ERROR_TRANSLATIONS: Record<string, { title: string; description: string }> = {
  match_not_found: {
    title: 'Match Not Found',
    description: 'The requested fixture does not exist in the canonical database registry.',
  },
  prediction_unavailable: {
    title: 'Prediction Unavailable',
    description: 'Statistical models cannot produce predictions for this match due to insufficient pre-cutoff history or unsupported league parameters.',
  },
  intelligence_unavailable: {
    title: 'Match Intelligence Unavailable',
    description: 'The unified match intelligence document could not be assembled. Pre-match historical features or required inputs are incomplete.',
  },
  provider_unavailable: {
    title: 'Data Provider Unavailable',
    description: 'The upstream provider source is currently unreachable or has exhausted quota limits.',
  },
  temporal_data_unavailable: {
    title: 'Temporal Data Unavailable',
    description: 'Kickoff timestamp or pre-cutoff audit point is missing for this fixture.',
  },
  network_error: {
    title: 'Connection Error',
    description: 'Unable to reach the TacticX API backend. Please check network connectivity and backend service status.',
  },
};

export const ErrorCard: React.FC<ErrorCardProps> = ({
  title,
  error,
  message,
  onRetry,
  className,
}) => {
  let displayTitle = title;
  let displayMessage = message;

  if (error instanceof ApiError) {
    const translation = ERROR_TRANSLATIONS[error.code];
    if (translation) {
      displayTitle = displayTitle || translation.title;
      displayMessage = displayMessage || translation.description;
    } else {
      displayTitle = displayTitle || 'Service Notice';
      displayMessage = displayMessage || (error.message.includes('Internal') ? 'An unexpected server state occurred.' : error.message);
    }
  } else if (error) {
    displayTitle = displayTitle || 'Application Error';
    displayMessage = displayMessage || 'An unexpected error occurred while processing data.';
  } else {
    displayTitle = displayTitle || 'Notice';
    displayMessage = displayMessage || 'Information unavailable.';
  }

  return (
    <div
      role="alert"
      className={cn(
        'rounded-lg border border-amber-900/50 bg-amber-950/20 p-5 text-amber-200 backdrop-blur-sm',
        className
      )}
    >
      <div className="flex items-start gap-3.5">
        <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm tracking-tight text-amber-300">{displayTitle}</h3>
          <p className="mt-1 text-xs text-amber-200/80 leading-relaxed font-sans">{displayMessage}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-medium rounded border border-amber-800 bg-amber-900/40 text-amber-300 hover:bg-amber-900/60 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry Operation
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
