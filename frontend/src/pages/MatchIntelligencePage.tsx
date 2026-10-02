import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Layers, ShieldCheck, AlertCircle } from 'lucide-react';
import { useMatchIntelligence, useMatch, usePredictionSnapshots, useMatchEvaluation } from '../api/queries';
import { MatchHeader } from '../components/intelligence/MatchHeader';
import { CorePredictionCard } from '../components/intelligence/CorePredictionCard';
import { ExpectedGoalsCard } from '../components/intelligence/ExpectedGoalsCard';
import { DerivedMarketsCard } from '../components/intelligence/DerivedMarketsCard';
import { CorrectScoreGrid } from '../components/intelligence/CorrectScoreGrid';
import { UncertaintySection } from '../components/intelligence/UncertaintySection';
import { ModelAgreementTable } from '../components/intelligence/ModelAgreementTable';
import { MarketComparisonCard } from '../components/intelligence/MarketComparisonCard';
import { HistoricalAnaloguesCard } from '../components/intelligence/HistoricalAnaloguesCard';
import { ScenarioAnalysisCard } from '../components/intelligence/ScenarioAnalysisCard';
import { MiroFishSection } from '../components/intelligence/MiroFishSection';
import { ExplanationSection } from '../components/intelligence/ExplanationSection';
import { DataQualitySection } from '../components/intelligence/DataQualitySection';
import { EvaluationSection } from '../components/intelligence/EvaluationSection';
import { PredictionExecutionSection } from '../components/intelligence/PredictionExecutionSection';
import { WarningsSection } from '../components/intelligence/WarningsSection';
import { ProvenanceSection } from '../components/intelligence/ProvenanceSection';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorCard } from '../components/common/ErrorCard';

export const MatchIntelligencePage: React.FC = () => {
  const { matchId } = useParams<{ matchId: string }>();
  const idNum = parseInt(matchId || '0', 10);

  const [temporalMode, setTemporalMode] = useState<string>('strict_prematch');
  const [activeTab, setActiveTab] = useState<'markets' | 'analysis' | 'telemetry'>('markets');

  const { data: matchFallback } = useMatch(idNum);
  const { data: execution, isLoading: executionLoading } = usePredictionSnapshots(idNum);
  const { data: matchEvaluation, isLoading: evaluationLoading } = useMatchEvaluation(idNum);
  const {
    data: intel,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useMatchIntelligence(idNum, {
    mode: temporalMode,
    response_mode: 'standard',
  });

  if (isLoading) {
    return <LoadingSpinner label={`Assembling Canonical Intelligence for Match #${idNum}...`} />;
  }

  if (error || !intel) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 space-y-4">
        <Link
          to="/matches"
          className="inline-flex items-center gap-1 text-xs font-mono text-slate-400 hover:text-slate-200"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Match Explorer</span>
        </Link>
        <ErrorCard
          error={error as Error}
          title={`Intelligence Unavailable for Match #${idNum}`}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  const matchSection = intel.match;
  const homeName = matchSection.home_team?.name || matchFallback?.home_team_name || 'Home';
  const awayName = matchSection.away_team?.name || matchFallback?.away_team_name || 'Away';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Breadcrumb & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <Link
          to="/matches"
          className="inline-flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Return to Explorer</span>
        </Link>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs font-mono bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800">
            <span className="text-slate-400">Mode:</span>
            <select
              value={temporalMode}
              onChange={(e) => setTemporalMode(e.target.value)}
              className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="strict_prematch">Strict Prematch</option>
              <option value="historical_estimated">Historical Estimated</option>
            </select>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            title="Refresh Canonical Document"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* 1. Hero Match Header */}
      <MatchHeader match={matchSection} cutoff={intel.cutoff} />

      {/* Warnings (if present) */}
      {intel.warnings?.length > 0 && <WarningsSection warnings={intel.warnings} />}

      {/* Navigation Tabs */}
      <div className="border-b border-surface-border">
        <nav className="flex space-x-6 overflow-x-auto" aria-label="Tabs">
          <button
            onClick={() => setActiveTab('markets')}
            className={`py-3 px-1 border-b-2 font-medium text-xs font-mono flex items-center gap-2 whitespace-nowrap transition-colors ${
              activeTab === 'markets'
                ? 'border-emerald-500 text-emerald-400 font-bold'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <span>Core Predictions & Markets</span>
            <span className="px-1.5 py-0.2 rounded bg-slate-800 text-[10px] text-slate-300 font-mono">1X2 / xG / Scores</span>
          </button>

          <button
            onClick={() => setActiveTab('analysis')}
            className={`py-3 px-1 border-b-2 font-medium text-xs font-mono flex items-center gap-2 whitespace-nowrap transition-colors ${
              activeTab === 'analysis'
                ? 'border-emerald-500 text-emerald-400 font-bold'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <span>MiroFish & Scenarios</span>
            <span className="px-1.5 py-0.2 rounded bg-amber-950 text-amber-400 text-[10px] font-mono border border-amber-900/50">Qualitative AI</span>
          </button>

          <button
            onClick={() => setActiveTab('telemetry')}
            className={`py-3 px-1 border-b-2 font-medium text-xs font-mono flex items-center gap-2 whitespace-nowrap transition-colors ${
              activeTab === 'telemetry'
                ? 'border-emerald-500 text-emerald-400 font-bold'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <span>Audit & Cryptographic Telemetry</span>
            <span className="px-1.5 py-0.2 rounded bg-slate-800 text-[10px] text-slate-300 font-mono">Provenance & Quality</span>
          </button>
        </nav>
      </div>

      {/* TAB 1: Core Predictions & Markets */}
      {activeTab === 'markets' && (
        <div className="space-y-6">
          {/* 2. Core 1X2 Prediction & 3. Expected Goals */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7">
              <CorePredictionCard
                prediction={intel.core_prediction}
                cutoff={intel.cutoff}
                homeTeamName={homeName}
                awayTeamName={awayName}
              />
            </div>
            <div className="lg:col-span-5">
              <ExpectedGoalsCard
                goals={intel.expected_goals}
                homeTeamName={homeName}
                awayTeamName={awayName}
              />
            </div>
          </div>

          {/* 4. Derived Markets */}
          <DerivedMarketsCard
            markets={intel.derived_markets}
            homeTeamName={homeName}
            awayTeamName={awayName}
          />

          {/* 5. Correct Score Heatmap & Rankings */}
          <CorrectScoreGrid
            correctScore={intel.correct_score}
            homeTeamName={homeName}
            awayTeamName={awayName}
          />

          {/* 8. Market Comparison */}
          <MarketComparisonCard
            market={intel.market}
            homeTeamName={homeName}
            awayTeamName={awayName}
          />

          {/* 12. Explanation Breakdown */}
          <ExplanationSection explanation={intel.explanation} />
        </div>
      )}

      {/* TAB 2: Simulations & Scenario Analysis */}
      {activeTab === 'analysis' && (
        <div className="space-y-6">
          {/* 11. MiroFish Qualitative Simulation */}
          <MiroFishSection mirofish={intel.mirofish} />

          {/* 9. Scenario Sensitivity Analysis */}
          {intel.scenarios?.length > 0 && (
            <ScenarioAnalysisCard
              scenarios={intel.scenarios}
              homeTeamName={homeName}
              awayTeamName={awayName}
            />
          )}

          {/* 10. Historical Analogues */}
          <HistoricalAnaloguesCard analogues={intel.analogues} />

          {/* 7. Model Agreement Matrix */}
          <ModelAgreementTable
            disagreement={intel.model_disagreement}
            homeTeamName={homeName}
            awayTeamName={awayName}
          />

          {/* 6. Uncertainty Diagnostics */}
          <UncertaintySection
            uncertainty={intel.uncertainty}
            temporalQuality={intel.temporal_quality}
          />
        </div>
      )}

      {/* TAB 3: Audit, Provenance & Telemetry */}
      {activeTab === 'telemetry' && (
        <div className="space-y-6">
          {/* 14. Pre-Match Prediction Execution (Phase 26) */}
          <PredictionExecutionSection
            execution={execution}
            isLoading={executionLoading}
          />

          {/* 15. Post-Match Evaluation (Phase 27, completed matches only) */}
          <EvaluationSection
            evaluation={matchEvaluation}
            isLoading={evaluationLoading}
            predictedHome={intel.core_prediction?.home}
            predictedDraw={intel.core_prediction?.draw}
            predictedAway={intel.core_prediction?.away}
          />

          {/* 13. Data Quality & Feature Telemetry */}
          <DataQualitySection
            dataQuality={intel.data_quality}
            temporalQuality={intel.temporal_quality}
          />

          {/* 16. Cryptographic Provenance */}
          <ProvenanceSection provenance={intel.provenance} rawJson={intel} />
        </div>
      )}
    </div>
  );
};
