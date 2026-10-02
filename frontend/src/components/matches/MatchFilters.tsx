import React from 'react';
import { Search, Filter, RotateCcw } from 'lucide-react';

export interface MatchFiltersState {
  league?: string;
  status?: string;
  date?: string;
  team?: string;
}

export interface MatchFiltersProps {
  filters: MatchFiltersState;
  onFilterChange: (newFilters: MatchFiltersState) => void;
  availableLeagues?: string[];
}

export const MatchFilters: React.FC<MatchFiltersProps> = ({
  filters,
  onFilterChange,
  availableLeagues = ['EPL', 'LA_LIGA', 'SERIE_A', 'BUNDESLIGA', 'LIGUE_1', 'UCL', 'NATIONS_LEAGUE', 'FRIENDLIES'],
}) => {
  const handleChange = (key: keyof MatchFiltersState, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value || undefined,
    });
  };

  const handleReset = () => {
    onFilterChange({});
  };

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-mono font-semibold text-slate-300">
          <Filter className="w-3.5 h-3.5 text-emerald-400" />
          <span>MATCH REGISTRY FILTERS</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onFilterChange({ status: 'SCHEDULED' })}
            className={`px-2 py-1 rounded text-[11px] font-mono transition-colors ${
              filters.status === 'SCHEDULED' && !filters.league
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            All Upcoming
          </button>
          <button
            onClick={() => onFilterChange({ league: 'NATIONS_LEAGUE', status: 'SCHEDULED' })}
            className={`px-2 py-1 rounded text-[11px] font-mono transition-colors ${
              filters.league === 'NATIONS_LEAGUE'
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Nations League
          </button>
          <button
            onClick={() => onFilterChange({ league: 'FRIENDLIES', status: 'SCHEDULED' })}
            className={`px-2 py-1 rounded text-[11px] font-mono transition-colors ${
              filters.league === 'FRIENDLIES'
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Friendlies
          </button>
          <button
            onClick={handleReset}
            className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-400 hover:text-slate-200 transition-colors ml-1"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
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

        {/* Date input */}
        <div>
          <input
            type="date"
            value={filters.date || ''}
            onChange={(e) => handleChange('date', e.target.value)}
            className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/60 font-sans [color-scheme:dark]"
          />
        </div>
      </div>
    </div>
  );
};
