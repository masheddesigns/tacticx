import React, { useState } from 'react';
import { getTeamMeta } from '../../lib/teamLogos';

export interface TeamLogoProps {
  teamName?: string | null;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  className?: string;
  imgClassName?: string;
  showFallbackText?: boolean;
}

const SIZE_MAP = {
  xs: { box: 'w-4 h-4', text: 'text-[9px]' },
  sm: { box: 'w-5 h-5', text: 'text-[10px]' },
  md: { box: 'w-6 h-6', text: 'text-[11px]' },
  lg: { box: 'w-8 h-8', text: 'text-xs' },
  xl: { box: 'w-10 h-10', text: 'text-sm' },
  '2xl': { box: 'w-14 h-14 sm:w-16 sm:h-16', text: 'text-base sm:text-lg' },
};

/**
 * FotMob-style Team Logo Component
 * - Renders official club crest from FotMob / API-Sports CDN.
 * - Gracefully falls back to a sleek, circular team monogram avatar with official club colors on network error or missing crest.
 */
export const TeamLogo: React.FC<TeamLogoProps> = ({
  teamName,
  size = 'md',
  className = '',
  imgClassName = '',
}) => {
  const [hasError, setHasError] = useState(false);
  const meta = getTeamMeta(teamName);
  const sizeConfig = SIZE_MAP[size] || SIZE_MAP.md;

  if (meta.logoUrl && !hasError) {
    return (
      <div
        className={`relative inline-flex items-center justify-center shrink-0 rounded-full bg-[#181d28]/80 border border-[#242c3c] overflow-hidden ${sizeConfig.box} ${className}`}
        title={teamName || 'Team'}
      >
        <img
          src={meta.logoUrl}
          alt={teamName || 'Team Crest'}
          className={`w-full h-full object-contain p-0.5 transition-transform duration-200 group-hover:scale-105 ${imgClassName}`}
          loading="lazy"
          onError={() => setHasError(true)}
        />
      </div>
    );
  }

  // FotMob fallback badge with team brand color
  return (
    <div
      className={`inline-flex items-center justify-center shrink-0 rounded-full font-mono font-bold border border-white/10 shadow-sm ${sizeConfig.box} ${sizeConfig.text} ${className}`}
      style={{
        backgroundColor: `${meta.primaryColor}25`,
        borderColor: `${meta.primaryColor}50`,
        color: meta.primaryColor,
      }}
      title={teamName || 'Team'}
    >
      <span>{meta.initials}</span>
    </div>
  );
};
