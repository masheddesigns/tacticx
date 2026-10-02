import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Clock, Shield, CheckCircle2 } from 'lucide-react';
import { MatchListItem } from '../../api/types';
import { formatDateTime } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface MatchRowProps {
  match: MatchListItem;
}

export const MatchRow: React.FC<MatchRowProps> = ({ match }) => {
  const kickoff = formatDateTime(match.kickoff_at);

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

  const isFinished = match.status.toUpperCase() === 'FINISHED';
  const hasScore = match.home_score !== null && match.away_score !== null && match.home_score !== undefined;

  return (
    <div className="group flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 bg-surface-card hover:bg-slate-800/60 border-b border-surface-border transition-colors gap-3">
      <div className="flex items-center gap-3.5 flex-1 min-w-0">
        <div className="flex flex-col items-center justify-center w-14 shrink-0 text-center">
          <Badge variant={getStatusBadgeVariant(match.status)} size="sm">
            {match.status}
          </Badge>
          {match.minute !== null && match.minute !== undefined && (
            <span className="text-[10px] font-mono text-emerald-400 mt-1">{match.minute}'</span>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            {match.league_name && (
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                {match.league_name}
              </span>
            )}
            <span className="text-[11px] font-mono text-slate-400">Match #{match.id}</span>
            <span className="text-slate-600">•</span>
            <span className="text-[11px] font-mono text-emerald-400/90 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {kickoff.date} {kickoff.time}
            </span>
          </div>

          <div className="flex items-center gap-3 font-semibold text-sm text-slate-100">
            <span className="truncate max-w-[140px] sm:max-w-[200px]" title={match.home_team_name || 'Home'}>
              {match.home_team_name || 'Home Team'}
            </span>
            {hasScore ? (
              <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 font-mono text-xs text-emerald-400 font-bold">
                {match.home_score} - {match.away_score}
              </span>
            ) : (
              <span className="text-xs text-slate-500 font-mono">vs</span>
            )}
            <span className="truncate max-w-[140px] sm:max-w-[200px]" title={match.away_team_name || 'Away'}>
              {match.away_team_name || 'Away Team'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4 w-full sm:w-auto justify-between sm:justify-end shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-800">
        <div className="flex items-center gap-2 text-xs">
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
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded text-xs font-mono font-medium text-slate-300 bg-slate-800/80 group-hover:bg-emerald-600 group-hover:text-white border border-slate-700 group-hover:border-emerald-500 transition-all shadow-sm"
        >
          <span>Analyze</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
};
