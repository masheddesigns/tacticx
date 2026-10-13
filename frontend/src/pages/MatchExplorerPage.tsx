import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Database, ChevronLeft, ChevronRight, AlertCircle, RefreshCw, Search, RotateCcw, Filter } from 'lucide-react';
import { useMatches, useLeagues } from '../api/queries';
import { MatchRow } from '../components/matches/MatchRow';
import { DateSliderTabs } from '../components/matches/DateSliderTabs';
import { getRelativeDateLabel, getTodayString, getDayOffsetString, formatDayDisplay } from '../lib/utils';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';
import { LeagueLogo } from '../components/common/LeagueLogo';

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
  if (upper.includes('MLS') || upper.includes('MAJOR_LEAGUE_SOCCER')) {
    return { name: 'Major League Soccer', country: 'USA', flag: '🇺🇸' };
  }
  if (upper.includes('LIGA_ARG') || upper.includes('ARGENTINA') || upper.includes('PROFESIONAL')) {
    return { name: 'Liga Profesional', country: 'Argentina', flag: '🇦🇷' };
  }
  if (upper.includes('BRA_SERIE_A') || upper.includes('BRASIL') || upper.includes('SERIE_A_BRAZIL') || upper.includes('BRASILEIRÃO') || upper.includes('BRASILEIRAO')) {
    return { name: 'Brasileirão Série A', country: 'Brazil', flag: '🇧🇷' };
  }
  if (upper.includes('ISL') || upper.includes('INDIAN_SUPER_LEAGUE') || upper.includes('INDIA')) {
    return { name: 'Indian Super League', country: 'India', flag: '🇮🇳' };
  }
  if (upper.includes('FRIENDLIES') || upper.includes('FRIENDLY')) {
    return { name: 'Club Friendlies', country: 'International', flag: '🌍' };
  }
  return { name: leagueKey.replace(/_/g, ' '), country: 'Football', flag: '⚽' };
}

const LEAGUE_PRIORITY: Record<string, number> = {
  'Premier League': 1,
  'EPL': 1,
  'La Liga': 2,
  'LA_LIGA': 2,
  'Serie A': 3,
  'SERIE_A': 3,
  'Bundesliga': 4,
  'BUNDESLIGA': 4,
  'Ligue 1': 5,
  'LIGUE_1': 5,
  'UEFA Champions League': 6,
  'UCL': 6,
  'Indian Super League': 7,
  'ISL': 7,
  'Major League Soccer': 8,
  'MLS': 8,
  'Brasileirão Série A': 9,
  'BRA_SERIE_A': 9,
  'Liga Profesional': 10,
  'LIGA_ARG': 10,
  'UEFA Nations League': 11,
  'NATIONS_LEAGUE': 11,
  'International Friendlies': 12,
  'FRIENDLIES': 12,
};

export interface MatchFiltersState {
  league?: string;
  status?: string;
  date?: string;
  team?: string;
  sort_order?: 'asc' | 'desc';
}

export const MatchExplorerPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState<number>(1);
  const pageSize = 50;

  const [timeZone, setTimeZone] = useState<'IST' | 'UTC'>('IST');
  const todayStr = useMemo(() => getTodayString(timeZone), [timeZone]);

  // Initialize filters from URL query parameters, defaulting to Today in IST if no date/status is specified
  const [filters, setFilters] = useState<MatchFiltersState>(() => {
    const urlStatus = searchParams.get('status') || undefined;
    const urlLeague = searchParams.get('league') || undefined;
    const urlDate = searchParams.get('date');
    const urlTeam = searchParams.get('team') || undefined;
    const urlSort = (searchParams.get('sort_order') as 'asc' | 'desc') || undefined;

    // Default to today in IST if user visits /matches without specific date or status query
    const initialDate = urlDate !== null ? (urlDate || undefined) : (!urlStatus && !urlLeague && !urlTeam ? todayStr : undefined);

    return {
      status: urlStatus,
      league: urlLeague,
      date: initialDate,
      team: urlTeam,
      sort_order: urlSort || (initialDate ? 'asc' : 'desc'),
    };
  });

  // Sync state if URL search parameters change externally
  useEffect(() => {
    const urlStatus = searchParams.get('status') || undefined;
    const urlLeague = searchParams.get('league') || undefined;
    const urlDate = searchParams.get('date');
    const urlTeam = searchParams.get('team') || undefined;
    const urlSort = (searchParams.get('sort_order') as 'asc' | 'desc') || undefined;

    setFilters((prev) => ({
      ...prev,
      status: urlStatus,
      league: urlLeague,
      date: urlDate !== null ? (urlDate || undefined) : prev.date,
      team: urlTeam,
      sort_order: urlSort || prev.sort_order,
    }));
  }, [searchParams]);

  const { data: leaguesData } = useLeagues();
  const availableLeagueCodes = leaguesData?.data?.map((l: { code: string }) => l.code) || [
    'EPL',
    'LA_LIGA',
    'SERIE_A',
    'BUNDESLIGA',
    'LIGUE_1',
    'UCL',
    // MLS / LIGA_ARG / BRA_SERIE_A / ISL hidden until real provider coverage lands.
    'NATIONS_LEAGUE',
    'FRIENDLIES',
  ];

  // Query in-play live matches for badge count
  const { data: liveData } = useMatches({
    status: 'LIVE',
    page_size: 20,
  });
  const liveCount = liveData?.data?.length || 0;

  // Query matches matching active filters and timezone
  const { data, isLoading, error, refetch, isFetching } = useMatches({
    page,
    page_size: pageSize,
    league: filters.league,
    status: filters.status,
    date: filters.date,
    team: filters.team,
    tz: timeZone,
    sort_order: filters.sort_order || (filters.date ? 'asc' : 'desc'),
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
    if (newFilters.sort_order) params.sort_order = newFilters.sort_order;
    setSearchParams(params, { replace: true });
  };

  const handleSelectDate = (date?: string) => {
    handleFilterChange({
      ...filters,
      date: date || undefined,
      status: undefined,
    });
  };

  const handleSelectStatus = (status?: string) => {
    handleFilterChange({
      ...filters,
      status: status || undefined,
      date: undefined,
    });
  };

  const handleResetFilters = () => {
    handleFilterChange({
      date: todayStr,
      status: undefined,
      league: undefined,
      team: undefined,
      sort_order: 'asc',
    });
  };

  // Group matches by relative date in target timezone
  const groupedMatches = useMemo(() => {
    return matches.reduce<Record<string, typeof matches>>((acc, m) => {
      const label = getRelativeDateLabel(m.kickoff_at, timeZone);
      if (!acc[label]) acc[label] = [];
      acc[label].push(m);
      return acc;
    }, {});
  }, [matches, timeZone]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2 font-sans">
            <Database className="w-6 h-6 text-[#21e786]" />
            <span>Match Explorer</span>
            <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-[#21e786]/10 text-[#21e786] border border-[#21e786]/30">
              IST Default
            </span>
          </h1>
          <p className="text-xs text-slate-400 font-sans mt-0.5">
            Browse, search and filter canonical fixtures across all 10 leagues with pre-match intelligence and decimal odds.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-400">
            {meta.total} matches recorded
          </span>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 rounded-lg border border-[#242938] bg-[#161922] text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            title="Refresh Fixture List"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin text-[#21e786]' : ''}`} />
          </button>
        </div>
      </div>

      {/* 1. Modern FotMob Date Slider Tabs */}
      <DateSliderTabs
        selectedDate={filters.date}
        onSelectDate={handleSelectDate}
        selectedStatus={filters.status}
        onSelectStatus={handleSelectStatus}
        timeZone={timeZone}
        onTimeZoneChange={(tz) => setTimeZone(tz)}
        liveCount={liveCount}
        minDate="2026-10-01"
        maxDate="2026-11-30"
      />

      {/* 2. Search & Filter Toolbar */}
      <div className="rounded-2xl border border-[#242938] bg-[#141822] p-3 sm:p-4 space-y-3 shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {/* Team Search */}
          <div className="relative">
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search team name..."
              value={filters.team || ''}
              onChange={(e) => handleFilterChange({ ...filters, team: e.target.value || undefined })}
              className="w-full bg-[#0d1017] border border-[#242938] rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-[#21e786]/60 transition-colors font-sans"
            />
          </div>

          {/* Competition Dropdown */}
          <div>
            <select
              value={filters.league || ''}
              onChange={(e) => handleFilterChange({ ...filters, league: e.target.value || undefined })}
              className="w-full bg-[#0d1017] border border-[#242938] rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-[#21e786]/60 transition-colors font-sans"
            >
              <option value="">All Competitions</option>
              {availableLeagueCodes.map((code) => {
                const meta = getLeagueMeta(code);
                return (
                  <option key={code} value={code}>
                    {meta.flag} {meta.name}
                  </option>
                );
              })}
            </select>
          </div>

          {/* Status Dropdown */}
          <div>
            <select
              value={filters.status || ''}
              onChange={(e) => handleFilterChange({ ...filters, status: e.target.value || undefined })}
              className="w-full bg-[#0d1017] border border-[#242938] rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-[#21e786]/60 transition-colors font-sans"
            >
              <option value="">All Statuses</option>
              <option value="LIVE">Live In-Play</option>
              <option value="SCHEDULED">Scheduled</option>
              <option value="FINISHED">Finished</option>
              <option value="POSTPONED">Postponed</option>
            </select>
          </div>

          {/* Sort Order Selector */}
          <div>
            <select
              value={filters.sort_order || (filters.date ? 'asc' : 'desc')}
              onChange={(e) => handleFilterChange({ ...filters, sort_order: e.target.value as 'asc' | 'desc' })}
              className="w-full bg-[#0d1017] border border-[#242938] rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-[#21e786]/60 transition-colors font-sans"
            >
              <option value="asc">Kickoff: Earliest First</option>
              <option value="desc">Kickoff: Latest First</option>
            </select>
          </div>

          {/* Reset Filters Button */}
          <div className="flex items-center">
            <button
              onClick={handleResetFilters}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-mono bg-[#1a202c] hover:bg-[#222a3a] text-slate-300 hover:text-white border border-[#2b354a] transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset to Today</span>
            </button>
          </div>
        </div>
      </div>

      {/* 3. Fixtures List with FotMob Date & League Groupings */}
      <div className="rounded-2xl border border-[#242938] bg-[#161922] overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-12 text-center">
            <LoadingSpinner label="Fetching fixtures from canonical store..." />
          </div>
        ) : error ? (
          <div className="p-6">
            <ErrorCard error={error as Error} title="Unable to Load Matches" onRetry={() => refetch()} />
          </div>
        ) : matches.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <AlertCircle className="w-8 h-8 text-slate-500 mx-auto" />
            <h3 className="font-semibold text-sm text-slate-200 font-sans">No Matching Fixtures Found</h3>
            <p className="text-xs text-slate-400 font-sans max-w-sm mx-auto">
              No matches matched the current filter criteria for{' '}
              {filters.date ? formatDayDisplay(filters.date, timeZone) : 'this selection'}.
            </p>
            <button
              onClick={handleResetFilters}
              className="px-3.5 py-1.5 rounded-xl text-xs font-sans font-semibold bg-[#21e786] text-[#0a0d14] hover:bg-[#1cd378] transition-colors"
            >
              View Today's Matches ({formatDayDisplay(todayStr, timeZone)})
            </button>
          </div>
        ) : (
          <div className="divide-y divide-[#242938]">
            {Object.entries(groupedMatches).map(([dateLabel, dayMatches]) => {
              // Sub-group dayMatches by league
              const leagueGroups = dayMatches.reduce<Record<string, typeof dayMatches>>((acc, m) => {
                const lKey = m.league_name || m.league_code || 'Other Competitions';
                if (!acc[lKey]) acc[lKey] = [];
                acc[lKey].push(m);
                return acc;
              }, {});

              const sortedLeagues = Object.entries(leagueGroups).sort(([a], [b]) => {
                const rankA = LEAGUE_PRIORITY[a] ?? 99;
                const rankB = LEAGUE_PRIORITY[b] ?? 99;
                if (rankA !== rankB) return rankA - rankB;
                return a.localeCompare(b);
              });

              return (
                <div key={dateLabel} className="border-b border-[#242938] last:border-b-0">
                  {/* FotMob Date Ribbon */}
                  <div className="bg-[#0e1015] px-4 py-2.5 border-b border-[#242938] flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-xs font-mono font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-lg ${
                          dateLabel === 'Today'
                            ? 'bg-[#21e786]/15 text-[#21e786] border border-[#21e786]/35 font-bold'
                            : dateLabel === 'Tomorrow'
                            ? 'bg-blue-500/15 text-blue-400 border border-blue-500/35'
                            : dateLabel === 'Yesterday'
                            ? 'bg-amber-500/15 text-amber-400 border border-amber-500/35'
                            : 'bg-[#1e222e] text-slate-300 border border-[#242938]'
                        }`}
                      >
                        {dateLabel}
                      </span>
                      <span className="text-[11px] font-mono text-slate-400">
                        ({dayMatches.length} {dayMatches.length === 1 ? 'match' : 'matches'})
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">
                      Showing in {timeZone === 'IST' ? 'IST (UTC+5:30)' : 'UTC'}
                    </span>
                  </div>

                  {/* FotMob League Sections */}
                  <div className="divide-y divide-[#242938]">
                    {sortedLeagues.map(([leagueKey, leagueMatches]) => {
                      const lMeta = getLeagueMeta(leagueKey);
                      return (
                        <div key={leagueKey} className="bg-[#161922]">
                          {/* FotMob League Banner Header */}
                          <div className="px-4 py-2 bg-[#12151d] border-b border-[#242938] flex items-center justify-between">
                            <div className="flex items-center gap-2.5">
                              <LeagueLogo league={leagueKey} size="sm" />
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-white tracking-wide font-sans">
                                  {lMeta.name}
                                </span>
                                <span className="text-[10px] text-slate-400 font-sans">
                                  • {lMeta.country}
                                </span>
                              </div>
                            </div>
                            <span className="text-[10px] font-mono text-slate-400 bg-[#0e1015] px-2 py-0.5 rounded-md border border-[#242938]">
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
          <div className="p-4 border-t border-[#242938] bg-[#0f121a] flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-mono">
            <span className="text-slate-400">
              Showing {(page - 1) * pageSize + 1} – {Math.min(page * pageSize, meta.total)} of{' '}
              {meta.total} fixtures
            </span>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || isLoading}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[#161a24] border border-[#242c3d] text-slate-300 hover:bg-[#202738] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Prev</span>
              </button>

              <span className="px-3 py-1.5 rounded-lg bg-[#1f2636] text-slate-200 font-bold border border-[#2b354a]">
                {page} / {totalPages}
              </span>

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || isLoading}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[#161a24] border border-[#242c3d] text-slate-300 hover:bg-[#202738] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
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
