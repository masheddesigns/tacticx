import React, { useState } from 'react';
import { getLeagueMeta, getLeagueLogoUrl } from '../../lib/leagueLogos';

export interface LeagueLogoProps {
  league?: string | null;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  className?: string;
  showFallbackFlag?: boolean;
  alt?: string;
  darkVariant?: boolean;
}

const SIZE_MAP = {
  xs: 'w-3.5 h-3.5 min-w-[14px]',
  sm: 'w-5 h-5 min-w-[20px]',
  md: 'w-7 h-7 min-w-[28px]',
  lg: 'w-9 h-9 min-w-[36px]',
  xl: 'w-12 h-12 min-w-[48px]',
  '2xl': 'w-16 h-16 min-w-[64px]',
};

const TEXT_SIZE_MAP = {
  xs: 'text-[10px]',
  sm: 'text-xs',
  md: 'text-sm',
  lg: 'text-base',
  xl: 'text-xl',
  '2xl': 'text-2xl',
};

export const LeagueLogo: React.FC<LeagueLogoProps> = ({
  league,
  size = 'md',
  className = '',
  showFallbackFlag = true,
  alt,
  darkVariant = false,
}) => {
  const [hasError, setHasError] = useState(false);
  const meta = getLeagueMeta(league);
  const logoUrl = getLeagueLogoUrl(league, darkVariant);

  const sizeClass = SIZE_MAP[size] || SIZE_MAP.md;
  const textSizeClass = TEXT_SIZE_MAP[size] || TEXT_SIZE_MAP.md;
  const displayName = meta?.shortName || meta?.name || league || 'League';

  if (!logoUrl || hasError) {
    if (showFallbackFlag) {
      const emoji = meta?.flagEmoji || '⚽';
      return (
        <span
          className={`inline-flex items-center justify-center select-none ${sizeClass} ${textSizeClass} ${className}`}
          title={displayName}
          role="img"
          aria-label={displayName}
        >
          {emoji}
        </span>
      );
    }

    // Default monogram badge if no emoji
    const initials = displayName
      .split(' ')
      .map((w) => w[0])
      .slice(0, 2)
      .join('')
      .toUpperCase();

    return (
      <span
        className={`inline-flex items-center justify-center rounded-md bg-[#161a24] border border-[#242c3c] text-slate-300 font-mono font-bold select-none ${sizeClass} ${textSizeClass} ${className}`}
        title={displayName}
        role="img"
        aria-label={displayName}
      >
        {initials}
      </span>
    );
  }

  return (
    <div
      className={`inline-flex items-center justify-center rounded-lg bg-[#0e1118]/80 p-0.5 border border-[#1f2638] shrink-0 shadow-xs overflow-hidden ${sizeClass} ${className}`}
      title={displayName}
    >
      <img
        src={logoUrl}
        alt={alt || `${displayName} logo`}
        className="w-full h-full object-contain filter drop-shadow-xs"
        loading="lazy"
        crossOrigin="anonymous"
        referrerPolicy="no-referrer"
        onError={() => setHasError(true)}
      />
    </div>
  );
};
