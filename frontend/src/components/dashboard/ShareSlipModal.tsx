import React, { useRef, useState } from 'react';
import {
  X,
  Share2,
  Download,
  Copy,
  Check,
  Sparkles,
  Ticket,
  ShieldCheck,
  Zap,
  TrendingUp,
  Flame,
  CheckCircle2,
  Flag,
  Target,
} from 'lucide-react';
import { toPng, toBlob } from 'html-to-image';
import { DailyPredictionSlip } from '../../api/types';
import { formatDayDisplay } from '../../lib/utils';

export interface ShareSlipModalProps {
  isOpen: boolean;
  onClose: () => void;
  slip: DailyPredictionSlip | null;
  dateStr: string;
  timeZone: 'UTC' | 'local' | string;
}

export const ShareSlipModal: React.FC<ShareSlipModalProps> = ({
  isOpen,
  onClose,
  slip,
  dateStr,
  timeZone,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [copiedImage, setCopiedImage] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  if (!isOpen || !slip) return null;

  const handleDownload = async () => {
    if (!cardRef.current) return;
    try {
      setIsCapturing(true);
      const dataUrl = await toPng(cardRef.current, {
        quality: 0.95,
        pixelRatio: 2,
        backgroundColor: '#0e1015',
      });
      const link = document.createElement('a');
      link.download = `tacticx-slip-${slip.type}-${dateStr}.png`;
      link.href = dataUrl;
      link.click();
      setStatusMessage('Screenshot downloaded successfully!');
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Download failed:', err);
      setStatusMessage('Could not generate image');
    } finally {
      setIsCapturing(false);
    }
  };

  const handleCopyImage = async () => {
    if (!cardRef.current) return;
    try {
      setIsCapturing(true);
      const blob = await toBlob(cardRef.current, {
        pixelRatio: 2,
        backgroundColor: '#0e1015',
      });
      if (blob && navigator.clipboard?.write) {
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob }),
        ]);
        setCopiedImage(true);
        setStatusMessage('Betting slip copied to clipboard!');
        setTimeout(() => {
          setCopiedImage(false);
          setStatusMessage(null);
        }, 3000);
      }
    } catch (err) {
      console.error('Copy failed:', err);
      setStatusMessage('Clipboard copying unavailable');
    } finally {
      setIsCapturing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg bg-[#161922] border border-[#242938] rounded-2xl shadow-2xl overflow-hidden p-6 space-y-6">
        {/* Modal Header */}
        <div className="flex items-center justify-between pb-3 border-b border-[#242938]">
          <div className="flex items-center gap-2">
            <Ticket className="w-5 h-5 text-[#21e786]" />
            <h3 className="font-bold text-base text-white font-sans">
              Share Betting Slip
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-[#1e222e] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* The Graphic Slip Card (Captured via html-to-image) */}
        <div
          ref={cardRef}
          className="rounded-2xl border border-[#242938] bg-[#0e1015] p-5 space-y-4 shadow-xl text-left"
        >
          {/* Card Top Branding */}
          <div className="flex items-center justify-between pb-3 border-b border-[#242938]">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#21e786] shadow-[0_0_8px_#21e786]" />
              <span className="font-black text-sm tracking-wider text-white font-sans">
                TACTIC<span className="text-[#21e786]">X</span>
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#161922] text-[#21e786] border border-[#242938]">
                AI Slip
              </span>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              {formatDayDisplay(dateStr, timeZone)}
            </span>
          </div>

          {/* Slip Title & Combined Odds Banner */}
          <div className="p-3.5 rounded-xl bg-gradient-to-r from-[#161922] via-[#1e222e] to-[#161922] border border-[#242938] flex items-center justify-between">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#21e786] font-bold">
                {slip.badge}
              </span>
              <h4 className="text-base font-extrabold text-white font-sans mt-0.5">
                {slip.title}
              </h4>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-mono text-slate-400 uppercase">Total Odds</div>
              <div className="text-xl font-black font-mono text-[#21e786]">
                {slip.total_odds.toFixed(2)}x
              </div>
            </div>
          </div>

          {/* Picks List */}
          <div className="space-y-2">
            {slip.picks.map((pick, pIdx) => (
              <div
                key={pIdx}
                className="p-3 rounded-xl bg-[#161922] border border-[#242938] flex flex-col gap-2"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
                      <span>{pick.league}</span>
                      <span>•</span>
                      <span className="text-[#21e786] font-bold">
                        {Math.round(pick.probability * 100)}% Win Prob
                      </span>
                    </div>
                    <div className="text-xs font-semibold text-slate-200 mt-0.5 truncate">
                      {pick.fixture}
                    </div>
                    <div className="text-xs font-bold text-white mt-0.5 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#21e786] shrink-0" />
                      <span className="truncate">{pick.pick}</span>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <div className="text-[10px] text-slate-400 font-sans">Odds</div>
                    <div className="text-xs font-mono font-bold text-[#21e786] bg-[#0e1015] px-2 py-1 rounded border border-[#242938] mt-0.5">
                      {pick.odds.toFixed(2)}
                    </div>
                  </div>
                </div>

                {/* Projected Stats Bar (Corners, Cards, Shots on Target) */}
                {pick.projected_stats && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1.5 border-t border-[#242938]/60 text-[10px] font-mono">
                    {pick.projected_stats.corners_total !== undefined && (
                      <div className="flex items-center gap-1 bg-[#0e1015] px-1.5 py-0.5 rounded border border-[#242938] text-purple-300">
                        <Flag className="w-2.5 h-2.5 text-purple-400" />
                        <span>~{pick.projected_stats.corners_total} Corn</span>
                        {pick.projected_stats.corners_home !== undefined && pick.projected_stats.corners_away !== undefined && (
                          <span className="text-slate-500 text-[9px]">({pick.projected_stats.corners_home}-{pick.projected_stats.corners_away})</span>
                        )}
                      </div>
                    )}
                    {pick.projected_stats.cards_total !== undefined && (
                      <div className="flex items-center gap-1 bg-[#0e1015] px-1.5 py-0.5 rounded border border-[#242938] text-amber-300">
                        <span className="w-2 h-2.5 bg-amber-400 rounded-[1px] inline-block shadow-[0_0_4px_rgba(251,191,36,0.5)]" />
                        <span>~{pick.projected_stats.cards_total} Cards</span>
                      </div>
                    )}
                    {pick.projected_stats.shots_on_target !== undefined && (
                      <div className="flex items-center gap-1 bg-[#0e1015] px-1.5 py-0.5 rounded border border-[#242938] text-cyan-300">
                        <Target className="w-2.5 h-2.5 text-cyan-400" />
                        <span>~{pick.projected_stats.shots_on_target} SoT</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Card Footer */}
          <div className="pt-3 border-t border-[#242938] flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Win Probability: <strong className="text-white">{slip.win_probability}%</strong></span>
            <span>Parimatch Slip Odds</span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleCopyImage}
            disabled={isCapturing}
            className="flex-1 py-2.5 px-4 rounded-xl text-xs font-sans font-bold bg-[#1e222e] hover:bg-[#242938] text-white border border-[#242938] transition-colors flex items-center justify-center gap-2"
          >
            {copiedImage ? <Check className="w-4 h-4 text-[#21e786]" /> : <Copy className="w-4 h-4" />}
            <span>{copiedImage ? 'Copied Slip!' : 'Copy Image'}</span>
          </button>

          <button
            onClick={handleDownload}
            disabled={isCapturing}
            className="flex-1 py-2.5 px-4 rounded-xl text-xs font-sans font-bold bg-[#21e786] hover:bg-[#1cd378] text-[#0e1015] transition-colors flex items-center justify-center gap-2 shadow-sm"
          >
            <Download className="w-4 h-4" />
            <span>Download PNG</span>
          </button>
        </div>

        {statusMessage && (
          <div className="text-xs font-mono text-center text-[#21e786] animate-pulse">
            {statusMessage}
          </div>
        )}
      </div>
    </div>
  );
};
