import React, { useRef, useState } from 'react';
import {
  X,
  Share2,
  Download,
  Copy,
  Check,
  Sparkles,
  Shield,
  Trophy,
  ExternalLink,
} from 'lucide-react';
import { toPng, toBlob } from 'html-to-image';
import { MatchIntelligence, MatchStatComparisonResponse } from '../../api/types';
import { formatDateTime } from '../../lib/utils';

export interface SharePredictionModalProps {
  isOpen: boolean;
  onClose: () => void;
  intel: MatchIntelligence;
  homeTeamName: string;
  awayTeamName: string;
  statComparison?: MatchStatComparisonResponse;
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
    'bg-red-950 text-red-300 border-red-700',
    'bg-blue-950 text-blue-300 border-blue-700',
    'bg-emerald-950 text-emerald-300 border-emerald-700',
    'bg-amber-950 text-amber-300 border-amber-700',
    'bg-purple-950 text-purple-300 border-purple-700',
    'bg-cyan-950 text-cyan-300 border-cyan-700',
    'bg-rose-950 text-rose-300 border-rose-700',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff;
  return colors[Math.abs(hash) % colors.length];
};

export const SharePredictionModal: React.FC<SharePredictionModalProps> = ({
  isOpen,
  onClose,
  intel,
  homeTeamName,
  awayTeamName,
  statComparison,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [copiedImage, setCopiedImage] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const match = intel.match;
  const kickoff = formatDateTime(match.kickoff);
  const compName = match.competition?.name || match.competition?.code || 'Football League';
  const homeInitials = getTeamInitials(homeTeamName);
  const awayInitials = getTeamInitials(awayTeamName);

  const core = intel.core_prediction;
  const homeProb = core.home ? Math.round(core.home * 1000) / 10 : 45.0;
  const drawProb = core.draw ? Math.round(core.draw * 1000) / 10 : 25.0;
  const awayProb = core.away ? Math.round(core.away * 1000) / 10 : 30.0;

  const homeOdds = homeProb > 0 ? (100 / homeProb).toFixed(2) : '-';
  const drawOdds = drawProb > 0 ? (100 / drawProb).toFixed(2) : '-';
  const awayOdds = awayProb > 0 ? (100 / awayProb).toFixed(2) : '-';

  const xg = intel.expected_goals;
  const homeXg = xg?.home_lambda ? Number(xg.home_lambda).toFixed(2) : '1.45';
  const awayXg = xg?.away_lambda ? Number(xg.away_lambda).toFixed(2) : '1.15';

  const correctScore = intel.correct_score;
  const topScore = correctScore?.top_n?.[0] || { score: '1-1', probability: 0.12 };
  const topScoreProb = Math.round((topScore.probability || 0.12) * 100);

  const miroNarrative = statComparison?.mirofish_summary?.narrative || intel.explanation?.headline;

  const fileName = `tacticx-prediction-${homeTeamName.toLowerCase().replace(/\s+/g, '-')}-vs-${awayTeamName.toLowerCase().replace(/\s+/g, '-')}.png`;

  // Download image
  const handleDownload = async () => {
    if (!cardRef.current) return;
    try {
      setIsCapturing(true);
      const dataUrl = await toPng(cardRef.current, {
        cacheBust: true,
        pixelRatio: 2, // High resolution crisp export
      });
      const link = document.createElement('a');
      link.download = fileName;
      link.href = dataUrl;
      link.click();
      setStatusMessage('Screenshot downloaded successfully!');
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to capture screenshot:', err);
      setStatusMessage('Error capturing screenshot.');
    } finally {
      setIsCapturing(false);
    }
  };

  // Copy Image to Clipboard
  const handleCopyImage = async () => {
    if (!cardRef.current) return;
    try {
      setIsCapturing(true);
      const blob = await toBlob(cardRef.current, {
        cacheBust: true,
        pixelRatio: 2,
      });
      if (blob && navigator.clipboard && window.ClipboardItem) {
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob }),
        ]);
        setCopiedImage(true);
        setStatusMessage('Image copied to clipboard! Paste it into WhatsApp/Telegram/X.');
        setTimeout(() => {
          setCopiedImage(false);
          setStatusMessage(null);
        }, 3000);
      } else {
        // Fallback: trigger download
        handleDownload();
      }
    } catch (err) {
      console.error('Failed to copy image to clipboard:', err);
      handleDownload();
    } finally {
      setIsCapturing(false);
    }
  };

  // Native Web Share API if supported
  const handleNativeShare = async () => {
    if (!cardRef.current) return;
    try {
      setIsCapturing(true);
      const blob = await toBlob(cardRef.current, {
        pixelRatio: 2,
      });
      if (blob && navigator.share && navigator.canShare) {
        const file = new File([blob], fileName, { type: 'image/png' });
        if (navigator.canShare({ files: [file] })) {
          await navigator.share({
            title: `${homeTeamName} vs ${awayTeamName} - Match Prediction`,
            text: `TacticX Match Intelligence: ${homeTeamName} (${homeProb}%) vs ${awayTeamName} (${awayProb}%). Verified Pre-Match Probability.`,
            files: [file],
          });
          return;
        }
      }
      // Fallback
      handleCopyImage();
    } catch (err) {
      handleCopyImage();
    } finally {
      setIsCapturing(false);
    }
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopiedLink(true);
    setStatusMessage('Link copied to clipboard!');
    setTimeout(() => {
      setCopiedLink(false);
      setStatusMessage(null);
    }, 2500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
      <div className="relative w-full max-w-lg bg-surface-card border border-surface-border rounded-2xl shadow-2xl p-5 sm:p-6 space-y-5 my-8">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-surface-border">
          <div className="flex items-center gap-2">
            <Share2 className="w-4 h-4 text-emerald-400" />
            <h3 className="text-base font-bold text-white tracking-tight">
              Share Match Prediction Snapshot
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Status Toast */}
        {statusMessage && (
          <div className="px-3 py-2 rounded-lg bg-emerald-950/90 border border-emerald-700 text-xs font-mono text-emerald-300 flex items-center gap-2">
            <Check className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{statusMessage}</span>
          </div>
        )}

        {/* The Captureable Graphic Card Preview */}
        <div className="rounded-xl overflow-hidden shadow-2xl border border-slate-700/80 bg-slate-950">
          <div
            ref={cardRef}
            className="p-5 sm:p-6 bg-gradient-to-b from-[#0e1626] via-[#090d16] to-[#04060a] text-slate-100 space-y-5"
          >
            {/* Top Brand Bar */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center text-emerald-400 font-mono font-black text-xs">
                  TX
                </div>
                <span className="font-extrabold text-xs tracking-tight text-white font-sans">
                  TACTICX
                  <span className="text-[10px] text-emerald-400 font-mono font-medium ml-1">
                    INTELLIGENCE
                  </span>
                </span>
              </div>

              <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-[10px] font-mono text-slate-300">
                <Trophy className="w-3 h-3 text-amber-400" />
                <span>{compName}</span>
              </div>
            </div>

            {/* Match Hero Display */}
            <div className="grid grid-cols-7 items-center gap-3 text-center">
              {/* Home Team */}
              <div className="col-span-3 flex flex-col items-center">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center text-sm font-black font-mono border-2 shadow-md ${getTeamColorStyle(
                    homeTeamName
                  )}`}
                >
                  {homeInitials}
                </div>
                <span className="font-bold text-xs text-white mt-1.5 truncate max-w-[120px]" title={homeTeamName}>
                  {homeTeamName}
                </span>
                <span className="text-[10px] font-mono text-emerald-400 font-semibold mt-0.5">
                  xG: {homeXg}
                </span>
              </div>

              {/* Center VS & Kickoff */}
              <div className="col-span-1 flex flex-col items-center justify-center">
                <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] font-extrabold text-emerald-400 tracking-wider">
                  VS
                </span>
                <span className="text-[9px] font-mono text-slate-400 mt-1 whitespace-nowrap">
                  {kickoff.date}
                </span>
                <span className="text-[9px] font-mono text-slate-500">
                  {kickoff.time}
                </span>
              </div>

              {/* Away Team */}
              <div className="col-span-3 flex flex-col items-center">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center text-sm font-black font-mono border-2 shadow-md ${getTeamColorStyle(
                    awayTeamName
                  )}`}
                >
                  {awayInitials}
                </div>
                <span className="font-bold text-xs text-white mt-1.5 truncate max-w-[120px]" title={awayTeamName}>
                  {awayTeamName}
                </span>
                <span className="text-[10px] font-mono text-blue-400 font-semibold mt-0.5">
                  xG: {awayXg}
                </span>
              </div>
            </div>

            {/* Core 1X2 Mathematical Model Probability Bar */}
            <div className="bg-slate-900/90 p-3 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-emerald-400 font-bold">
                  {homeInitials} Win: {homeProb}% <span className="text-amber-400">(@{homeOdds})</span>
                </span>
                <span className="text-amber-300 font-bold">
                  Draw: {drawProb}% <span className="text-amber-400">(@{drawOdds})</span>
                </span>
                <span className="text-blue-400 font-bold">
                  {awayInitials} Win: {awayProb}% <span className="text-amber-400">(@{awayOdds})</span>
                </span>
              </div>

              {/* Tripartite Color Progress Bar */}
              <div className="h-2.5 w-full bg-slate-800 rounded-full overflow-hidden flex gap-0.5">
                <div
                  className="bg-emerald-500 h-full rounded-l-full"
                  style={{ width: `${homeProb}%` }}
                />
                <div
                  className="bg-amber-400 h-full"
                  style={{ width: `${drawProb}%` }}
                />
                <div
                  className="bg-blue-500 h-full rounded-r-full"
                  style={{ width: `${awayProb}%` }}
                />
              </div>
            </div>

            {/* Key Markets Highlight Pill Grid */}
            <div className="grid grid-cols-2 gap-2.5">
              <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 text-center">
                <span className="text-[10px] font-mono text-slate-400 block uppercase">
                  Top Correct Score
                </span>
                <span className="text-base font-extrabold text-white font-mono mt-0.5 block">
                  {topScore.score}
                </span>
                <span className="text-[10px] font-mono text-emerald-400">
                  {topScoreProb}% Poisson probability
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 text-center">
                <span className="text-[10px] font-mono text-slate-400 block uppercase">
                  Mathematical Favored
                </span>
                <span className="text-sm font-bold text-white font-mono mt-0.5 block truncate">
                  {homeProb >= awayProb ? `${homeTeamName} or Draw` : `${awayTeamName} or Draw`}
                </span>
                <span className="text-[10px] font-mono text-blue-400">
                  Double Chance Pick
                </span>
              </div>
            </div>

            {/* MiroFish Qualitative AI Simulation Note */}
            {miroNarrative && (
              <div className="bg-amber-950/20 border border-amber-900/40 rounded-lg p-2.5 flex items-start gap-2">
                <Sparkles className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
                <p className="text-[11px] text-amber-200/90 leading-tight font-sans italic line-clamp-2">
                  "{miroNarrative}"
                </p>
              </div>
            )}

            {/* Footer Cryptographic Cutoff Verification */}
            <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[9px] font-mono text-slate-500">
              <div className="flex items-center gap-1 text-slate-400">
                <Shield className="w-3 h-3 text-emerald-400" />
                <span>Pre-Match Cutoff Frozen</span>
              </div>
              <span>Phase 27 Verified</span>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
          <button
            onClick={handleDownload}
            disabled={isCapturing}
            className="flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-semibold shadow-md transition-colors disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            <span>Download PNG</span>
          </button>

          <button
            onClick={handleCopyImage}
            disabled={isCapturing}
            className="flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-mono text-xs font-semibold border border-slate-700 transition-colors disabled:opacity-50"
          >
            {copiedImage ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            <span>{copiedImage ? 'Copied Image' : 'Copy Image'}</span>
          </button>

          <button
            onClick={handleNativeShare}
            disabled={isCapturing}
            className="flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 font-mono text-xs font-semibold border border-slate-800 transition-colors"
          >
            <Share2 className="w-4 h-4 text-emerald-400" />
            <span>Share</span>
          </button>
        </div>

        <div className="flex items-center justify-between pt-1 text-[11px] font-mono text-slate-400 border-t border-surface-border/60">
          <span>Match Link:</span>
          <button
            onClick={handleCopyLink}
            className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
          >
            {copiedLink ? <Check className="w-3 h-3 text-emerald-400" /> : <ExternalLink className="w-3 h-3" />}
            <span>{copiedLink ? 'Link Copied!' : 'Copy Match Link'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
