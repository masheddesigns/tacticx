import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Clock, Shield, CheckCircle2 } from 'lucide-react';
import { MatchListItem } from '../../api/types';
import { formatDateTime } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface MatchRowProps {
  match: MatchListItem;
  timeZone?: 'UTC' | 'local' | string;
}

const getTeamInitials = (name?: string | null): string => {
  if (!name) return '??';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 3).toUpperCase();
};

const getTeamColorStyle = (name?: string | null): string => {
  if (!name) return 'bg-slate-800 text-slate-300 border-slate-700';
  const colors = [
    'bg-red-950/80 text-red-300 border-red-800/60',
    'bg-blue-950/80 text-blue-300 border-blue-800/60',
    'bg-emerald-950/80 text-emerald-300 border-emerald-800/60',
    'bg-amber-950/80 text-amber-300 border-amber-800/60',
    'bg-purple-950/80 text-purple-300 border-purple-800/60',
    'bg-cyan-950/80 text-cyan-300 border-cyan-800/60',
    'bg-indigo-950/80 text-indigo-300 border-indigo-800/60',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff;
  return colors[Math.abs(hash) % colors.length];
};

export const MatchRow: React.FC<MatchRowProps> = ({ match, timeZone = 'UTC' }) => {
  const kickoff = formatDateTime(match.kickoff_at, timeZone);

  const getStatusBadgeVariant = (status: string) => {
    switch (status.toUpperCase()) {
      case 'LIVE':
      case 'HALFTIME':
        return 'error';
      case 'FINISHED':
        return 'default';
      case 'SCHEDULED':
      case 'PRE_MATCH':
        return 'info';
      default:
        return 'outline';
    }
  };

  const isLive = match.status.toUpperCase() === 'LIVE' || match.status.toUpperCase() === 'HALFTIME';
  const isFinished = match.status.toUpperCase() === 'FINISHED';
  const hasScore = match.home_score !== null && match.away_score !== null && match.home_score !== undefined;

  const homeScore = match.home_score ?? 0;
  const awayScore = match.away_score ?? 0;
  const isHomeWinner = hasScore && homeScore > awayScore;
  const isAwayWinner = hasScore && awayScore > homeScore;

  const homeInitials = getTeamInitials(match.home_team_name);
  const awayInitials = getTeamInitials(match.away_team_name);

  return (
    <div className="group flex flex-col sm:flex-row items-stretch sm:items-center justify-between p-3.5 sm:px-4 sm:py-3 bg-surface-card hover:bg-slate-800/70 border-b border-surface-border transition-colors gap-3">
      {/* Left: FotMob Status & Kickoff Time Column */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="flex flex-col items-center justify-center w-16 text-center">
          {isLive ? (
            <div className="flex flex-col items-center">
              <span className="inline-flex items-center gap-1 text-[11px] font-bold font-mono text-rose-400 bg-rose-950/80 border border-rose-800/70 px-2 py-0.5 rounded-full animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping inline-block" />
                {match.minute ? `${match.minute}'` : 'LIVE'}
              </span>
              <span className="sr-only">LIVE</span>
            </div>
          ) : (
            <Badge variant={getStatusBadgeVariant(match.status)} size="sm">
              {match.status}
            </Badge>
          )}

          <div className="text-[10px] font-mono text-slate-400 mt-1 flex items-center gap-0.5">
            <Clock className="w-2.5 h-2.5 text-slate-500" />
            <span>{kickoff.time}</span>
          </div>
        </div>

        <div className="h-8 w-px bg-slate-800 hidden sm:block" />
      </div>

      {/* Center: FotMob Teams and Score */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between sm:justify-start gap-4">
          {/* Teams Stack / Side-by-side Layout */}
          <div className="flex-1 min-w-0 space-y-1.5">
            {/* Home Team */}
            <div className="flex items-center gap-2.5">
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold font-mono border shrink-0 ${getTeamColorStyle(
                  match.home_team_name
                )}`}
              >
                {homeInitials}
              </span>
              <span
                className={`truncate text-xs sm:text-sm ${
                  isHomeWinner ? 'font-bold text-white' : isFinished ? 'text-slate-300 font-medium' : 'text-slate-100 font-medium'
                }`}
                title={match.home_team_name || 'Home'}
              >
                {match.home_team_name || 'Home Team'}
              </span>
            </div>

            {/* Away Team */}
            <div className="flex items-center gap-2.5">
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold font-mono border shrink-0 ${getTeamColorStyle(
                  match.away_team_name
                )}`}
              >
                {awayInitials}
              </span>
              <span
                className={`truncate text-xs sm:text-sm ${
                  isAwayWinner ? 'font-bold text-white' : isFinished ? 'text-slate-300 font-medium' : 'text-slate-100 font-medium'
                }`}
                title={match.away_team_name || 'Away'}
              >
                {match.away_team_name || 'Away Team'}
              </span>
            </div>
          </div>

          {/* FotMob Score Box */}
          <div className="shrink-0 flex flex-col items-center justify-center px-3">
            {hasScore ? (
              <span className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700/80 font-mono text-sm sm:text-base font-bold text-emerald-400 tracking-wider shadow-inner">
                {match.home_score} - {match.away_score}
              </span>
            ) : (
              <span className="text-xs text-slate-500 font-mono font-medium px-2 py-1 rounded bg-slate-900/50">
                vs
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Right: Intel Pill & Analyze Link */}
      <div className="flex items-center gap-3 justify-between sm:justify-end shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-800/80">
        <div className="flex items-center gap-2">
          {match.prediction_eligible !== false ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 px-2 py-0.5 rounded">
              <CheckCircle2 className="w-3 h-3" />
              Intelligence Ready
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded">
              <Shield className="w-3 h-3" />
              Audit Complete
            </span>
          )}
        </div>

        <Link
          to={`/matches/${match.id}`}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-mono font-medium text-slate-200 bg-slate-800/90 hover:bg-emerald-600 hover:text-white border border-slate-700 hover:border-emerald-500 transition-all shadow-sm"
        >
          <span>Analyze</span>
          <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      </div>
    </div>
  );
};
