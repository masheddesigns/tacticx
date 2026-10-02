import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Database, ChevronLeft, ChevronRight, AlertCircle, RefreshCw } from 'lucide-react';
import { useMatches, useLeagues } from '../api/queries';
import { MatchRow } from '../components/matches/MatchRow';
import { MatchFilters, MatchFiltersState } from '../components/matches/MatchFilters';
import { getRelativeDateLabel } from '../lib/utils';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

export interface LeagueInfo {
  name: string;
  country: string;
  flag: string;
}

export function getLeagueMeta(leagueKey?: string | null): LeagueInfo {
  if (!leagueKey) return { name: 'Other Competitions', country: 'Global', flag: '⚽' };
  const upper = leagueKey.toUpperCase().replace(/\s+/g, '_');
  if (upper.includes('EPL') || upper.includes('PREMIER_LEAGUE')) {
    return { name: 'Premier League', country: 'England', flag: '🏴󠁧󠁢󠁥󠁮󠁧󠁿' };
  }
  if (upper.includes('LA_LIGA') || upper.includes('LALIGA') || upper.includes('PRIMERA')) {
    return { name: 'La Liga', country: 'Spain', flag: '🇪🇸' };
  }
  if (upper.includes('SERIE_A')) {
    return { name: 'Serie A', country: 'Italy', flag: '🇮🇹' };
  }
  if (upper.includes('BUNDESLIGA')) {
    return { name: 'Bundesliga', country: 'Germany', flag: '🇩🇪' };
  }
  if (upper.includes('LIGUE_1') || upper.includes('LIGUE1')) {
    return { name: 'Ligue 1', country: 'France', flag: '🇫🇷' };
  }
  if (upper.includes('UCL') || upper.includes('CHAMPIONS_LEAGUE')) {
    return { name: 'UEFA Champions League', country: 'Europe', flag: '🏆' };
  }
  if (upper.includes('NATIONS_LEAGUE')) {
    return { name: 'UEFA Nations League', country: 'Europe', flag: '🇪🇺' };
  }
  if (upper.includes('FRIENDLIES') || upper.includes('FRIENDLY')) {
    return { name: 'Club Friendlies', country: 'International', flag: '🌍' };
  }
  return { name: leagueKey.replace(/_/g, ' '), country: 'Football', flag: '⚽' };
}

export const MatchExplorerPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  // Initialize filters from URL query parameters if present
  const [filters, setFilters] = useState<MatchFiltersState>(() => {
    const urlStatus = searchParams.get('status') || undefined;
    const urlLeague = searchParams.get('league') || undefined;
    const urlDate = searchParams.get('date') || undefined;
    const urlTeam = searchParams.get('team') || undefined;
    return {
      status: urlStatus,
      league: urlLeague,
      date: urlDate,
      team: urlTeam,
    };
  });

  // Sync state if URL search parameters change externally
  useEffect(() => {
    const urlStatus = searchParams.get('status') || undefined;
    const urlLeague = searchParams.get('league') || undefined;
    const urlDate = searchParams.get('date') || undefined;
    const urlTeam = searchParams.get('team') || undefined;
    setFilters((prev) => ({
      ...prev,
      status: urlStatus,
      league: urlLeague,
      date: urlDate,
      team: urlTeam,
    }));
  }, [searchParams]);

  const { data: leaguesData } = useLeagues();
  const availableLeagueCodes = leaguesData?.data?.map((l) => l.code) || [
    'EPL',
    'LA_LIGA',
    'SERIE_A',
    'BUNDESLIGA',
    'LIGUE_1',
    'UCL',
    'NATIONS_LEAGUE',
    'FRIENDLIES',
  ];

  const [timeZone, setTimeZone] = useState<'UTC' | 'local'>('UTC');

  const { data, isLoading, error, refetch, isFetching } = useMatches({
    page,
    page_size: pageSize,
    league: filters.league,
    status: filters.status,
    date: filters.date,
    team: filters.team,
    sort_order: filters.sort_order || 'asc',
  });

  const matches = data?.data || [];
  const meta = data?.meta || { page: 1, page_size: pageSize, total: 0 };
  const totalPages = Math.max(1, Math.ceil(meta.total / pageSize));

  const handleFilterChange = (newFilters: MatchFiltersState) => {
    setFilters(newFilters);
    setPage(1); // Reset to page 1 on filter change

    // Keep URL in sync
    const params: Record<string, string> = {};
    if (newFilters.status) params.status = newFilters.status;
    if (newFilters.league) params.league = newFilters.league;
    if (newFilters.date) params.date = newFilters.date;
    if (newFilters.team) params.team = newFilters.team;
    setSearchParams(params, { replace: true });
  };


  // Group matches by relative date (Today, Tomorrow, Yesterday, etc.) FotMob-style
  const groupedMatches = matches.reduce<Record<string, typeof matches>>((acc, m) => {
    const label = getRelativeDateLabel(m.kickoff_at, timeZone);
    if (!acc[label]) acc[label] = [];
    acc[label].push(m);
    return acc;
  }, {});

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Database className="w-6 h-6 text-emerald-400" />
            <span>Match Explorer</span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-1">
            Browse and search canonical fixtures grouped by date with pre-match intelligence and decimal odds.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-400">
            {meta.total} matches recorded
          </span>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            title="Refresh Fixture List"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filter Component with Days & Timezone */}
      <MatchFilters
        filters={filters}
        onFilterChange={handleFilterChange}
        availableLeagues={availableLeagueCodes}
        timeZone={timeZone}
        onTimeZoneChange={(tz) => setTimeZone(tz)}
      />

      {/* Fixtures List with FotMob-style Date Sections */}
      <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden shadow-sm">
        {isLoading ? (
          <LoadingSpinner label="Fetching fixtures from canonical store..." />
        ) : error ? (
          <div className="p-6">
            <ErrorCard error={error as Error} title="Unable to Load Matches" onRetry={() => refetch()} />
          </div>
        ) : matches.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <AlertCircle className="w-8 h-8 text-slate-500 mx-auto" />
            <h3 className="font-semibold text-sm text-slate-200">No Matching Fixtures Found</h3>
            <p className="text-xs text-slate-400 font-sans max-w-sm mx-auto">
              No matches matched the current filter criteria. Try clicking "Today", "Tomorrow", or resetting filters.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {Object.entries(groupedMatches).map(([dateLabel, dayMatches]) => {
              // Sub-group dayMatches by league
              const leagueGroups = dayMatches.reduce<Record<string, typeof dayMatches>>((acc, m) => {
                const lKey = m.league_name || m.league_code || 'Other Competitions';
                if (!acc[lKey]) acc[lKey] = [];
                acc[lKey].push(m);
                return acc;
              }, {});

              return (
                <div key={dateLabel} className="border-b border-surface-border last:border-b-0">
                  {/* FotMob-style Date Group Header Ribbon */}
                  <div className="bg-slate-900/90 px-4 py-2.5 border-b border-surface-border flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-xs font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                          dateLabel === 'Today'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : dateLabel === 'Tomorrow'
                            ? 'bg-blue-950 text-blue-400 border border-blue-800'
                            : dateLabel === 'Yesterday'
                            ? 'bg-amber-950 text-amber-400 border border-amber-800'
                            : 'bg-slate-950 text-slate-300 border border-slate-800'
                        }`}
                      >
                        {dateLabel}
                      </span>
                      <span className="text-[11px] font-mono text-slate-400">
                        ({dayMatches.length} {dayMatches.length === 1 ? 'match' : 'matches'})
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">
                      Showing in {timeZone === 'local' ? 'Local Browser Time' : 'UTC'}
                    </span>
                  </div>

                  {/* FotMob League Sections */}
                  <div className="divide-y divide-surface-border/70">
                    {Object.entries(leagueGroups).map(([leagueKey, leagueMatches]) => {
                      const lMeta = getLeagueMeta(leagueKey);
                      return (
                        <div key={leagueKey} className="bg-surface-card">
                          {/* FotMob League Banner Header */}
                          <div className="px-4 py-2 bg-slate-950/70 border-b border-surface-border/50 flex items-center justify-between">
                            <div className="flex items-center gap-2.5">
                              <span className="text-base select-none">{lMeta.flag}</span>
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-slate-200 tracking-wide font-sans">
                                  {lMeta.name}
                                </span>
                                <span className="text-[10px] text-slate-400 font-mono">
                                  • {lMeta.country}
                                </span>
                              </div>
                            </div>
                            <span className="text-[10px] font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                              {leagueMatches.length} {leagueMatches.length === 1 ? 'fixture' : 'fixtures'}
                            </span>
                          </div>

                          {/* Match Rows for this League */}
                          <div className="divide-y divide-surface-border/60">
                            {leagueMatches.map((m) => (
                              <MatchRow key={m.id} match={m} timeZone={timeZone} />
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination Bar */}
        {meta.total > 0 && (
          <div className="p-4 border-t border-surface-border bg-slate-950/60 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-mono">
            <span className="text-slate-400">
              Showing {(page - 1) * pageSize + 1} – {Math.min(page * pageSize, meta.total)} of{' '}
              {meta.total} fixtures
            </span>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || isLoading}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Prev</span>
              </button>

              <span className="px-3 py-1.5 rounded bg-slate-800 text-slate-200 font-bold">
                {page} / {totalPages}
              </span>

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || isLoading}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <span>Next</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
