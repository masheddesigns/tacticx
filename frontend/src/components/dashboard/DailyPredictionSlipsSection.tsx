import React, { useState } from 'react';
import {
  Ticket,
  ShieldCheck,
  Zap,
  TrendingUp,
  Flame,
  CheckCircle2,
  ChevronRight,
  Sparkles,
  Share2,
} from 'lucide-react';
import { DailyPredictionSlip } from '../../api/types';
import { formatDayDisplay } from '../../lib/utils';
import { ShareSlipModal } from './ShareSlipModal';

export interface DailyPredictionSlipsSectionProps {
  slips: DailyPredictionSlip[];
  dateStr: string;
  timeZone: 'UTC' | 'local' | string;
  isLoading?: boolean;
}

export const DailyPredictionSlipsSection: React.FC<DailyPredictionSlipsSectionProps> = ({
  slips,
  dateStr,
  timeZone,
  isLoading,
}) => {
  const [selectedSlipForShare, setSelectedSlipForShare] = useState<DailyPredictionSlip | null>(null);

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-[#242938] bg-[#161922] p-6 animate-pulse space-y-4">
        <div className="h-5 w-48 bg-slate-800 rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="h-52 bg-slate-800/50 rounded-xl" />
          <div className="h-52 bg-slate-800/50 rounded-xl" />
          <div className="h-52 bg-slate-800/50 rounded-xl" />
        </div>
      </div>
    );
  }

  if (!slips || slips.length === 0) {
    return null;
  }

  const getSlipIcon = (type: string) => {
    switch (type) {
      case 'banker':
        return <ShieldCheck className="w-4 h-4 text-[#21e786]" />;
      case 'accumulator':
        return <Zap className="w-4 h-4 text-amber-400" />;
      case 'goals':
        return <Flame className="w-4 h-4 text-rose-400" />;
      case 'value':
        return <TrendingUp className="w-4 h-4 text-purple-400" />;
      case 'mega':
        return <Sparkles className="w-4 h-4 text-cyan-400" />;
      default:
        return <Ticket className="w-4 h-4 text-blue-400" />;
    }
  };

  const getSlipBorder = (type: string) => {
    switch (type) {
      case 'banker':
        return 'border-[#21e786]/30 hover:border-[#21e786]/60 shadow-[0_0_15px_rgba(33,231,134,0.06)]';
      case 'accumulator':
        return 'border-amber-400/30 hover:border-amber-400/60 shadow-[0_0_15px_rgba(251,191,36,0.06)]';
      case 'goals':
        return 'border-rose-400/30 hover:border-rose-400/60 shadow-[0_0_15px_rgba(244,63,94,0.06)]';
      case 'value':
        return 'border-purple-400/30 hover:border-purple-400/60 shadow-[0_0_15px_rgba(192,132,252,0.06)]';
      case 'mega':
        return 'border-cyan-400/30 hover:border-cyan-400/60 shadow-[0_0_15px_rgba(34,211,238,0.06)]';
      default:
        return 'border-[#242938] hover:border-slate-700';
    }
  };

  return (
    <div className="rounded-2xl border border-[#242938] bg-[#161922] p-5 sm:p-6 space-y-5 shadow-sm">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#242938]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#21e786]/10 border border-[#21e786]/20 flex items-center justify-center text-[#21e786]">
            <Ticket className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-white font-sans flex items-center gap-2">
                <span>Daily AI Prediction Slips</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[#21e786]/20 text-[#21e786] border border-[#21e786]/30">
                  Parimatch Aligned
                </span>
              </h2>
            </div>
            <p className="text-xs text-slate-400 font-sans mt-0.5">
              Mathematically curated slips with highest predictive accuracy & multi-league cross combos for {formatDayDisplay(dateStr, timeZone)}.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-slate-400 bg-[#1e222e] px-2.5 py-1 rounded-md border border-[#242938]">
            {slips.length} Slips Generated
          </span>
        </div>
      </div>

      {/* Slips Grid (3 Cards: Banker, Acca, Value) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {slips.map((slip, idx) => (
          <div
            key={idx}
            className={`rounded-xl bg-[#0e1015] border p-4 flex flex-col justify-between transition-all space-y-4 ${getSlipBorder(
              slip.type
            )}`}
          >
            {/* Slip Header */}
            <div>
              <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-[#242938]">
                <div className="flex items-center gap-1.5">
                  {getSlipIcon(slip.type)}
                  <h3 className="font-bold text-sm text-white font-sans">{slip.title}</h3>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#1e222e] border border-[#242938] text-slate-300">
                  {slip.selections_count} Picks
                </span>
              </div>

              <p className="text-[11px] text-slate-400 font-sans mt-2">
                {slip.description}
              </p>

              {/* Picks List */}
              <div className="space-y-2 mt-3.5">
                {slip.picks.map((pick, pIdx) => (
                  <div
                    key={pIdx}
                    className="p-2.5 rounded-lg bg-[#161922] border border-[#242938] hover:border-slate-700 transition-colors flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-mono text-slate-400 truncate">
                          {pick.league}
                        </span>
                        <span className="text-[10px] text-slate-600">•</span>
                        <span className="text-[10px] font-mono font-semibold text-[#21e786]">
                          {Math.round(pick.probability * 100)}% Win
                        </span>
                      </div>
                      <div className="text-xs font-semibold text-slate-200 truncate mt-0.5">
                        {pick.fixture}
                      </div>
                      <div className="text-[11px] font-sans font-bold text-white mt-0.5 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3 text-[#21e786]" />
                        <span>{pick.pick}</span>
                      </div>
                    </div>

                    <div className="text-right shrink-0">
                      <div className="text-[10px] text-slate-400 font-sans">Odds</div>
                      <div className="text-xs font-mono font-bold text-[#21e786] bg-[#0e1015] px-2 py-1 rounded border border-[#242938] mt-0.5">
                        {pick.odds.toFixed(2)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Slip Summary / Total Odds Footer & Share Button */}
            <div className="pt-3 border-t border-[#242938] space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-[10px] text-slate-400 font-sans uppercase tracking-wider">
                    Combined Odds
                  </div>
                  <div className="text-lg font-black font-mono text-[#21e786]">
                    {slip.total_odds.toFixed(2)}x
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-[10px] text-slate-400 font-sans uppercase tracking-wider">
                    Win Probability
                  </div>
                  <div className="text-xs font-bold font-mono text-slate-200">
                    {slip.win_probability}%
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedSlipForShare(slip)}
                className="w-full py-1.5 px-3 rounded-lg text-xs font-sans font-semibold bg-[#1e222e] hover:bg-[#242938] text-slate-200 hover:text-white border border-[#242938] transition-colors flex items-center justify-center gap-1.5 shadow-sm"
              >
                <Share2 className="w-3.5 h-3.5 text-[#21e786]" />
                <span>Share Slip Screenshot</span>
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Share Slip Modal */}
      <ShareSlipModal
        isOpen={Boolean(selectedSlipForShare)}
        onClose={() => setSelectedSlipForShare(null)}
        slip={selectedSlipForShare}
        dateStr={dateStr}
        timeZone={timeZone}
      />
    </div>
  );
};
