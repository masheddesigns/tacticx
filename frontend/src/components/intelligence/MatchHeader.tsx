import React from 'react';
import { Shield, Clock, MapPin, Layers, Share2 } from 'lucide-react';
import { MatchSection, CutoffSection } from '../../api/types';
import { formatDateTime } from '../../lib/utils';
import { Badge } from '../common/Badge';

export interface MatchHeaderProps {
  match: MatchSection;
  cutoff?: CutoffSection;
  onShare?: () => void;
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
  if (!name) return 'bg-slate-800 text-slate-200 border-slate-700';
  const colors = [
    'bg-red-950/90 text-red-300 border-red-700/80',
    'bg-blue-950/90 text-blue-300 border-blue-700/80',
    'bg-emerald-950/90 text-emerald-300 border-emerald-700/80',
    'bg-amber-950/90 text-amber-300 border-amber-700/80',
    'bg-purple-950/90 text-purple-300 border-purple-700/80',
    'bg-cyan-950/90 text-cyan-300 border-cyan-700/80',
    'bg-rose-950/90 text-rose-300 border-rose-700/80',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff;
  return colors[Math.abs(hash) % colors.length];
};

export const MatchHeader: React.FC<MatchHeaderProps> = ({ match, cutoff, onShare }) => {
  const kickoff = formatDateTime(match.kickoff);
  const homeName = match.home_team?.name || 'Home Team';
  const awayName = match.away_team?.name || 'Away Team';
  const compName = match.competition?.name || match.competition?.code || 'Football League';

  const isLive = match.status === 'LIVE' || match.status === 'HALFTIME';
  const isFinished = match.status === 'FINISHED';

  const homeInitials = getTeamInitials(homeName);
  const awayInitials = getTeamInitials(awayName);

  return (
    <div className="rounded-2xl border border-surface-border bg-gradient-to-b from-slate-900 via-surface-card to-slate-950 p-6 shadow-lg space-y-6">
      {/* Top bar: Competition, Season, Status */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-surface-border/80">
        <div className="flex items-center gap-2.5">
          <Badge variant="purple" size="md">
            {compName}
          </Badge>
          {match.season && (
            <span className="text-xs font-mono text-slate-400">
              Season {match.season}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2.5">
          {onShare && (
            <button
              onClick={onShare}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-semibold bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white border border-emerald-500/40 transition-all shadow-sm"
              title="Share Match Prediction Snapshot"
            >
              <Share2 className="w-3.5 h-3.5" />
              <span>Share Snapshot</span>
            </button>
          )}

          {isLive ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold font-mono bg-rose-950/90 text-rose-300 border border-rose-700 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping inline-block" />
              LIVE
            </span>
          ) : (
            <Badge
              variant={
                isFinished ? 'default' : 'info'
              }
              size="md"
            >
              {match.status}
            </Badge>
          )}
          <span className="text-xs font-mono text-slate-400">Match #{match.match_id}</span>
        </div>
      </div>

      {/* FotMob Match Hero Display */}
      <div className="py-2 grid grid-cols-1 md:grid-cols-7 items-center gap-6">
        {/* Home Team (Left 3 cols) */}
        <div className="md:col-span-3 flex items-center md:justify-end gap-4 text-left md:text-right order-1">
          <div className="min-w-0">
            <span className="text-[11px] uppercase tracking-wider font-mono text-slate-400 block mb-0.5">
              Home
            </span>
            <h1 className="text-xl sm:text-2xl lg:text-3xl font-extrabold tracking-tight text-white truncate" title={homeName}>
              {homeName}
            </h1>
          </div>

          <div
            className={`w-14 h-14 sm:w-16 sm:h-16 rounded-2xl flex items-center justify-center text-lg sm:text-xl font-black font-mono border-2 shadow-md shrink-0 ${getTeamColorStyle(
              homeName
            )}`}
          >
            {homeInitials}
          </div>
        </div>

        {/* Center: FotMob Score / Kickoff Pill (1 col) */}
        <div className="md:col-span-1 flex flex-col items-center justify-center shrink-0 order-3 md:order-2">
          {isLive ? (
            <div className="text-center space-y-1">
              <div className="px-3 py-1 rounded-full bg-rose-950/80 border border-rose-800 text-[11px] font-mono font-bold text-rose-400 inline-flex items-center gap-1 animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                Live In-Play
              </div>
              <div className="text-xs font-mono text-slate-400">{kickoff.time}</div>
            </div>
          ) : isFinished ? (
            <div className="text-center space-y-1">
              <span className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider px-2.5 py-0.5 rounded bg-slate-900 border border-slate-800">
                Full Time
              </span>
              <div className="text-[11px] font-mono text-slate-400">{kickoff.date}</div>
            </div>
          ) : (
            <div className="text-center space-y-1">
              <span className="text-xs font-mono font-bold text-emerald-400 uppercase tracking-widest px-3 py-1 rounded bg-slate-900 border border-slate-800">
                VS
              </span>
              <div className="text-xs font-mono text-slate-300 font-semibold">{kickoff.time}</div>
              <div className="text-[10px] font-mono text-slate-400">{kickoff.date}</div>
            </div>
          )}
        </div>

        {/* Away Team (Right 3 cols) */}
        <div className="md:col-span-3 flex items-center md:justify-start gap-4 text-left order-2 md:order-3">
          <div
            className={`w-14 h-14 sm:w-16 sm:h-16 rounded-2xl flex items-center justify-center text-lg sm:text-xl font-black font-mono border-2 shadow-md shrink-0 ${getTeamColorStyle(
              awayName
            )}`}
          >
            {awayInitials}
          </div>

          <div className="min-w-0">
            <span className="text-[11px] uppercase tracking-wider font-mono text-slate-400 block mb-0.5">
              Away
            </span>
            <h1 className="text-xl sm:text-2xl lg:text-3xl font-extrabold tracking-tight text-white truncate" title={awayName}>
              {awayName}
            </h1>
          </div>
        </div>
      </div>

      {/* Metadata Footnote: Sources & Cutoff */}
      <div className="pt-4 border-t border-surface-border/80 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400 font-mono">
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-slate-500" />
          <span>Ingested Sources:</span>
          {match.sources?.length > 0 ? (
            match.sources.map((s, idx) => (
              <span key={idx} className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px] border border-slate-700/60">
                {s.source}
              </span>
            ))
          ) : (
            <span className="text-slate-400">Canonical store</span>
          )}
        </div>

        {match.venue && (
          <div className="flex items-center gap-1.5 text-slate-400">
            <MapPin className="w-3.5 h-3.5 text-slate-500" />
            <span>{match.venue}</span>
          </div>
        )}

        {cutoff?.cutoff && (
          <div className="flex items-center gap-1.5 text-slate-300 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>Snapshot Cutoff: {cutoff.cutoff}</span>
          </div>
        )}
      </div>
    </div>
  );
};
