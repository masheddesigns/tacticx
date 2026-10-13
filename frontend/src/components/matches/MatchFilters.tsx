import React from 'react';
import { Search, Filter, RotateCcw, Calendar, Sparkles } from 'lucide-react';
import { getTodayString, getDayOffsetString, formatDayDisplay } from '../../lib/utils';

export interface MatchFiltersState {
  league?: string;
  status?: string;
  date?: string;
  team?: string;
  sort_order?: 'asc' | 'desc';
}

export interface MatchFiltersProps {
  filters: MatchFiltersState;
  onFilterChange: (newFilters: MatchFiltersState) => void;
  availableLeagues?: string[];
  timeZone?: 'IST' | 'UTC' | 'local' | string;
  onTimeZoneChange?: (tz: 'IST' | 'UTC') => void;
}

export const MatchFilters: React.FC<MatchFiltersProps> = ({
  filters,
  onFilterChange,
  availableLeagues = ['EPL', 'LA_LIGA', 'SERIE_A', 'BUNDESLIGA', 'LIGUE_1', 'UCL', 'MLS', 'LIGA_ARG', 'BRA_SERIE_A', 'ISL', 'NATIONS_LEAGUE', 'FRIENDLIES'],
  timeZone = 'IST',
  onTimeZoneChange,
}) => {
  const todayStr = getTodayString(timeZone);
  const yesterdayStr = getDayOffsetString(-1, timeZone);
  const tomorrowStr = getDayOffsetString(1, timeZone);

  const handleChange = (key: keyof MatchFiltersState, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value || undefined,
    });
  };

  const handleReset = () => {
    onFilterChange({});
  };

  const handleQuickDay = (dayStr: string) => {
    onFilterChange({
      ...filters,
      date: dayStr,
      status: undefined,
    });
  };

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-3.5">
      {/* Top Filter Bar with Quick Day Chips and Timezone */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-surface-border/80">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-mono text-slate-400 font-semibold mr-1">Quick:</span>
          <button
            onClick={() => onFilterChange({ ...filters, status: 'LIVE', date: undefined })}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors flex items-center gap-1.5 ${
              filters.status === 'LIVE' && !filters.date
                ? 'bg-rose-600 text-white font-bold animate-pulse'
                : 'bg-rose-950/80 text-rose-300 hover:bg-rose-900 border border-rose-800/60'
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-rose-400 animate-ping inline-block" />
            Live Now
          </button>
          <button
            onClick={() => handleQuickDay(yesterdayStr)}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.date === yesterdayStr
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Yesterday ({formatDayDisplay(yesterdayStr, timeZone)})
          </button>
          <button
            onClick={() => handleQuickDay(todayStr)}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.date === todayStr
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Today ({formatDayDisplay(todayStr, timeZone)})
          </button>
          <button
            onClick={() => handleQuickDay(tomorrowStr)}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.date === tomorrowStr
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Tomorrow ({formatDayDisplay(tomorrowStr, timeZone)})
          </button>
          <button
            onClick={() => onFilterChange({ ...filters, status: 'SCHEDULED', date: undefined })}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
              filters.status === 'SCHEDULED' && !filters.date
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            All Upcoming
          </button>
        </div>


        {/* Timezone & Reset Controls */}
        <div className="flex items-center gap-2">
          {onTimeZoneChange && (
            <div className="flex items-center gap-1 text-xs font-mono bg-slate-900 px-2 py-1 rounded border border-slate-800">
              <span className="text-slate-400">Timezone:</span>
              <button
                onClick={() => onTimeZoneChange('IST')}
                className={`px-1.5 py-0.5 rounded ${timeZone === 'IST' ? 'bg-emerald-950/80 text-emerald-400 font-bold border border-emerald-500/40' : 'text-slate-400 hover:text-slate-300'}`}
              >
                IST (+5:30)
              </button>
              <button
                onClick={() => onTimeZoneChange('UTC')}
                className={`px-1.5 py-0.5 rounded ${timeZone === 'UTC' ? 'bg-slate-800 text-emerald-400 font-bold' : 'text-slate-400 hover:text-slate-300'}`}
              >
                UTC
              </button>
            </div>
          )}

          <button
            onClick={handleReset}
            className="inline-flex items-center gap-1 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors px-2 py-1"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>
      </div>

      {/* Quick October Matchday Shortcuts */}
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-[11px] font-mono text-slate-400 font-semibold flex items-center gap-1 mr-0.5">
          <Sparkles className="w-3 h-3 text-emerald-400" />
          <span>Oct Matchdays:</span>
        </span>
        {[
          { label: 'Oct 17 (Top 5 Slate)', date: '2026-10-17' },
          { label: 'Oct 18 (Liverpool-Chelsea)', date: '2026-10-18' },
          { label: 'Oct 20 (UCL MD3)', date: '2026-10-20' },
          { label: 'Oct 21 (Barca-Bayern UCL)', date: '2026-10-21' },
          { label: 'Oct 24 (El Clasico)', date: '2026-10-24' },
          { label: 'Oct 25 (Arsenal-Liverpool)', date: '2026-10-25' },
          { label: 'Oct 28 (Serie A & Cups)', date: '2026-10-28' },
          { label: 'Oct 31 (Halloween Slate)', date: '2026-10-31' },
        ].map((chip) => (
          <button
            key={chip.date}
            onClick={() => handleQuickDay(chip.date)}
            className={`px-2 py-0.5 rounded-md text-[11px] font-sans font-medium transition-all ${
              filters.date === chip.date
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-900 text-slate-300 hover:text-white hover:bg-slate-800 border border-slate-800'
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Primary Filter Selectors & Sort */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {/* Team Search */}
        <div className="relative">
          <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search team name..."
            value={filters.team || ''}
            onChange={(e) => handleChange('team', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          />
        </div>

        {/* Competition Dropdown */}
        <div>
          <select
            value={filters.league || ''}
            onChange={(e) => handleChange('league', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          >
            <option value="">All Competitions</option>
            {availableLeagues.map((lg) => (
              <option key={lg} value={lg}>
                {lg.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>

        {/* Status Dropdown */}
        <div>
          <select
            value={filters.status || ''}
            onChange={(e) => handleChange('status', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          >
            <option value="">All Statuses</option>
            <option value="FINISHED">Finished</option>
            <option value="SCHEDULED">Scheduled</option>
            <option value="PRE_MATCH">Pre-Match</option>
            <option value="LIVE">Live</option>
            <option value="POSTPONED">Postponed</option>
          </select>
        </div>

        {/* Specific Date input */}
        <div>
          <input
            type="date"
            value={filters.date || ''}
            onChange={(e) => handleChange('date', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans [color-scheme:dark]"
          />
        </div>

        {/* Sort Order Selector */}
        <div>
          <select
            value={filters.sort_order || 'asc'}
            onChange={(e) => handleChange('sort_order', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans"
          >
            <option value="asc">Kickoff: Earliest First</option>
            <option value="desc">Kickoff: Latest First</option>
          </select>
        </div>
      </div>
    </div>
  );
};

