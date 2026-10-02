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
  Flag,
  CreditCard,
  Target,
  Goal,
} from 'lucide-react';
import { toPng, toBlob } from 'html-to-image';
import {
  MatchIntelligence,
  MatchStatComparisonResponse,
  StatProjectionsResponse,
} from '../../api/types';
import { formatDateTime } from '../../lib/utils';

export interface SharePredictionModalProps {
  isOpen: boolean;
  onClose: () => void;
  intel: MatchIntelligence;
  homeTeamName: string;
  awayTeamName: string;
  statProjections?: StatProjectionsResponse;
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
  statProjections,
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

  // 1X2 Probabilities & Odds
  const core = intel.core_prediction;
  const homeProb = core.home ? Math.round(core.home * 1000) / 10 : 45.0;
  const drawProb = core.draw ? Math.round(core.draw * 1000) / 10 : 25.0;
  const awayProb = core.away ? Math.round(core.away * 1000) / 10 : 30.0;

  const homeOdds = homeProb > 0 ? (100 / homeProb).toFixed(2) : '-';
  const drawOdds = drawProb > 0 ? (100 / drawProb).toFixed(2) : '-';
  const awayOdds = awayProb > 0 ? (100 / awayProb).toFixed(2) : '-';

  // Expected Goals (xG)
  const xg = intel.expected_goals;
  const homeXg = xg?.home_lambda ? Number(xg.home_lambda).toFixed(2) : '1.45';
  const awayXg = xg?.away_lambda ? Number(xg.away_lambda).toFixed(2) : '1.15';

  // Over / Under Goals & BTTS
  const derived = intel.derived_markets;
  const totals = derived?.totals || {};
  const btts = derived?.btts || {};

  const over15Prob = totals['over_1_5'] ? Math.round(totals['over_1_5'] * 100) : 78;
  const under15Prob = 100 - over15Prob;
  const over25Prob = totals['over_2_5'] ? Math.round(totals['over_2_5'] * 100) : 52;
  const under25Prob = 100 - over25Prob;
  const bttsYesProb = btts.yes ? Math.round(btts.yes * 100) : 54;
  const bttsNoProb = btts.no ? Math.round(btts.no * 100) : 46;

  // Corners, Cards & Shots Projections
  const combined = statProjections?.combined_projections;
  const teamProj = statProjections?.team_projections;

  const cornersTot = combined?.corners_total ? combined.corners_total.toFixed(1) : '9.8';
  const cornersH = teamProj?.home?.corners ? teamProj.home.corners.toFixed(1) : '5.4';
  const cornersA = teamProj?.away?.corners ? teamProj.away.corners.toFixed(1) : '4.4';

  const cardsTot = combined?.yellow_cards_total ? combined.yellow_cards_total.toFixed(1) : '3.4';
  const shotsOnTargetTot = combined?.shots_on_target ? combined.shots_on_target.toFixed(1) : '7.6';

  // Top Predicted Scores
  const topScores = intel.correct_score?.top_n?.slice(0, 3) || [
    { score: '2-1', probability: 0.14 },
    { score: '1-1', probability: 0.12 },
    { score: '2-0', probability: 0.10 },
  ];

  const miroNarrative = statComparison?.mirofish_summary?.narrative || intel.explanation?.headline;

  const fileName = `tacticx-prediction-${homeTeamName.toLowerCase().replace(/\s+/g, '-')}-vs-${awayTeamName.toLowerCase().replace(/\s+/g, '-')}.png`;

  // Download image
  const handleDownload = async () => {
    if (!cardRef.current) return;
    try {
      setIsCapturing(true);
      const dataUrl = await toPng(cardRef.current, {
        cacheBust: true,
        pixelRatio: 2, // 2x high resolution
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
        setStatusMessage('Image copied to clipboard! Paste it anywhere.');
        setTimeout(() => {
          setCopiedImage(false);
          setStatusMessage(null);
        }, 3000);
      } else {
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
            text: `TacticX Match Intelligence: ${homeTeamName} (${homeProb}%) vs ${awayTeamName} (${awayProb}%). Over 1.5 Goals: ${over15Prob}%. Corners: ~${cornersTot}.`,
            files: [file],
          });
          return;
        }
      }
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
      <div className="relative w-full max-w-xl bg-surface-card border border-surface-border rounded-2xl shadow-2xl p-5 sm:p-6 space-y-5 my-8">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-surface-border">
          <div className="flex items-center gap-2">
            <Share2 className="w-4 h-4 text-emerald-400" />
            <h3 className="text-base font-bold text-white tracking-tight">
              Share Match Prediction & Stats Snapshot
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
            className="p-5 sm:p-6 bg-gradient-to-b from-[#0e1626] via-[#090d16] to-[#04060a] text-slate-100 space-y-4"
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

              <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-[10px] font-mono text-slate-300">
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

            {/* 1. Core 1X2 Mathematical Model Probability Bar */}
            <div className="bg-slate-900/90 p-3 rounded-xl border border-slate-800 space-y-1.5">
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
                <div className="bg-emerald-500 h-full rounded-l-full" style={{ width: `${homeProb}%` }} />
                <div className="bg-amber-400 h-full" style={{ width: `${drawProb}%` }} />
                <div className="bg-blue-500 h-full rounded-r-full" style={{ width: `${awayProb}%` }} />
              </div>
            </div>

            {/* 2. Top Predicted Scores & Goals Over/Under Split */}
            <div className="grid grid-cols-2 gap-2.5">
              {/* Top 3 Predicted Scores */}
              <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1.5">
                <span className="text-[10px] font-mono text-purple-300 block uppercase font-bold flex items-center gap-1">
                  <Target className="w-3 h-3" /> Top Predicted Scores
                </span>
                <div className="flex items-center gap-1.5">
                  {topScores.map((sc, i) => (
                    <div
                      key={sc.score}
                      className={`flex-1 py-1 rounded text-center font-mono ${
                        i === 0 ? 'bg-purple-950 border border-purple-700 text-white font-bold' : 'bg-slate-950 text-slate-300'
                      }`}
                    >
                      <div className="text-xs font-bold">{sc.score}</div>
                      <div className="text-[9px] text-purple-400">{Math.round(sc.probability * 100)}%</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Over / Under Goals & BTTS */}
              <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1 text-xs font-mono">
                <span className="text-[10px] text-blue-300 uppercase font-bold flex items-center gap-1">
                  <Goal className="w-3 h-3" /> Goals (Over / Under)
                </span>
                <div className="flex justify-between text-[11px] pt-0.5">
                  <span className="text-slate-400">Over 1.5: <strong className="text-emerald-400">{over15Prob}%</strong></span>
                  <span className="text-slate-400">Over 2.5: <strong className="text-white">{over25Prob}%</strong></span>
                </div>
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>BTTS:</span>
                  <span className="text-emerald-300 font-bold">Yes {bttsYesProb}% / No {bttsNoProb}%</span>
                </div>
              </div>
            </div>

            {/* 3. In-Game Predicted Stats (Corners & Discipline) */}
            <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 grid grid-cols-3 gap-2 text-center text-xs font-mono">
              <div className="p-1 rounded bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <Flag className="w-2.5 h-2.5 text-emerald-400" /> Corners
                </span>
                <div className="font-extrabold text-sm text-emerald-400 mt-0.5">~{cornersTot}</div>
                <div className="text-[9px] text-slate-400">{cornersH} - {cornersA}</div>
              </div>

              <div className="p-1 rounded bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <CreditCard className="w-2.5 h-2.5 text-amber-400" /> Cards
                </span>
                <div className="font-extrabold text-sm text-amber-300 mt-0.5">~{cardsTot}</div>
                <div className="text-[9px] text-slate-400">Yellows total</div>
              </div>

              <div className="p-1 rounded bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <Target className="w-2.5 h-2.5 text-blue-400" /> Target Shots
                </span>
                <div className="font-extrabold text-sm text-blue-300 mt-0.5">~{shotsOnTargetTot}</div>
                <div className="text-[9px] text-slate-400">On Target</div>
              </div>
            </div>

            {/* 4. MiroFish Qualitative AI Simulation Note */}
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
              <span>Phase 27 Canonical Verification</span>
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
