import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import mockData from './mockMatchIntelligence.json';
import { CorePredictionCard } from '../components/intelligence/CorePredictionCard';
import { ProbabilityBar } from '../components/intelligence/ProbabilityBar';
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
import { WarningsSection } from '../components/intelligence/WarningsSection';
import { ProvenanceSection } from '../components/intelligence/ProvenanceSection';
import { MatchStatComparisonCard } from '../components/intelligence/MatchStatComparisonCard';
import { SharePredictionModal } from '../components/intelligence/SharePredictionModal';
import { MatchIntelligence } from '../api/types';

const intel = mockData as unknown as MatchIntelligence;

describe('Match Intelligence Components — Analytical & Statistical Integrity', () => {
  it('renders core predictions with exact percentages and neutral wording', () => {
    render(
      <CorePredictionCard
        prediction={intel.core_prediction}
        cutoff={intel.cutoff}
        homeTeamName="Union Berlin"
        awayTeamName="Bayer Leverkusen"
      />
    );

    // Verify neutral phrasing exists
    expect(screen.getAllByText(/Model probability/i).length).toBeGreaterThanOrEqual(3);

    // Verify forbidden words do NOT exist
    expect(screen.queryByText(/lock/i)).toBeNull();
    expect(screen.queryByText(/sure bet/i)).toBeNull();
    expect(screen.queryByText(/guaranteed/i)).toBeNull();

    // Verify exact backend percentage: Home is 0.202422 -> 20.2%
    expect(screen.getAllByText('20.2%').length).toBeGreaterThanOrEqual(1);
    // Draw is 0.256126 -> 25.6%
    expect(screen.getAllByText('25.6%').length).toBeGreaterThanOrEqual(1);
    // Away is 0.541450 -> 54.1%
    expect(screen.getAllByText('54.1%').length).toBeGreaterThanOrEqual(1);

    // Model version
    expect(screen.getByText(intel.core_prediction.model_version!)).toBeInTheDocument();
  });

  it('renders expected goals as model estimates without predicting exact final score', () => {
    render(
      <ExpectedGoalsCard
        goals={intel.expected_goals}
        homeTeamName="Union Berlin"
        awayTeamName="Bayer Leverkusen"
      />
    );

    // Verify title and labels
    expect(screen.getByText(/Expected Goals \(λ\) Estimates/i)).toBeInTheDocument();
    expect(screen.queryByText(/Predicted final score/i)).toBeNull();

    // Verify exact lambda values: Home 0.78, Away 1.66, Total 2.44
    expect(screen.getByText('0.78')).toBeInTheDocument();
    expect(screen.getByText('1.66')).toBeInTheDocument();
    expect(screen.getByText('2.44')).toBeInTheDocument();
  });

  it('renders derived markets directly from backend without recalculation', () => {
    render(
      <DerivedMarketsCard
        markets={intel.derived_markets}
        homeTeamName="Union Berlin"
        awayTeamName="Bayer Leverkusen"
      />
    );

    // Double chance: 1x = 0.4585 -> 45.9%, x2 = 0.7975 -> 79.8%, 12 = 0.7438 -> 74.4%
    expect(screen.getByText('45.9%')).toBeInTheDocument();
    expect(screen.getByText('79.8%')).toBeInTheDocument();
    expect(screen.getByText('74.4%')).toBeInTheDocument();

    // Verify absence of betting suggestions
    expect(screen.queryByText(/stake/i)).toBeNull();
    expect(screen.queryByText(/roi/i)).toBeNull();
    expect(screen.queryByText(/bankroll/i)).toBeNull();
  });

  it('renders correct score distribution with Highest-probability scoreline label', () => {
    render(
      <CorrectScoreGrid
        correctScore={intel.correct_score}
        homeTeamName="Union Berlin"
        awayTeamName="Bayer Leverkusen"
      />
    );

    // Check mandatory required label
    expect(screen.getByText(/Highest-probability scoreline:/i)).toBeInTheDocument();
    expect(screen.queryByText(/Predicted score/i)).toBeNull();

    // Top score is 0-1 (14.5%)
    expect(screen.getByText('0-1 (14.5%)')).toBeInTheDocument();
  });

  it('renders uncertainty dimensions separately without synthesizing a single confidence score', () => {
    render(
      <UncertaintySection
        uncertainty={intel.uncertainty}
        temporalQuality={intel.temporal_quality}
      />
    );

    // Predictive entropy: 1.0044
    expect(screen.getByText('1.0044')).toBeInTheDocument();
    // Margin: 0.2853
    expect(screen.getByText('0.2853')).toBeInTheDocument();

    // Ensure NO single "Confidence: XX%" badge exists
    expect(screen.queryByText(/Confidence: 9/i)).toBeNull();
    expect(screen.queryByText(/Confidence: 8/i)).toBeNull();
  });

  it('renders model agreement without model ranking', () => {
    render(
      <ModelAgreementTable
        disagreement={intel.model_disagreement}
        homeTeamName="Union Berlin"
        awayTeamName="Bayer Leverkusen"
      />
    );

    // Shows individual models
    expect(screen.getByText('Elo')).toBeInTheDocument();
    expect(screen.getByText('Poisson')).toBeInTheDocument();
    expect(screen.getByText('Ensemble')).toBeInTheDocument();

    // Verify statistical summary columns
    expect(screen.getByText('Mean')).toBeInTheDocument();
    expect(screen.getByText('Std Dev')).toBeInTheDocument();
    expect(screen.getByText('Range')).toBeInTheDocument();

    // Verify absence of ranking words
    expect(screen.queryByText(/Best model/i)).toBeNull();
    expect(screen.queryByText(/Rank 1/i)).toBeNull();
  });

  it('renders market comparison objectively without wagering advice', () => {
    render(
      <MarketComparisonCard
        market={intel.market}
        homeTeamName="Union Berlin"
        awayTeamName="Bayer Leverkusen"
      />
    );

    expect(screen.getByText(/Market Consensus vs Model Alignment/i)).toBeInTheDocument();
    expect(screen.getByText('4 Bookmakers')).toBeInTheDocument();

    // Verify no betting advice
    expect(screen.queryByText(/Value bet/i)).toBeNull();
    expect(screen.queryByText(/Recommended bet/i)).toBeNull();
  });

  it('renders historical analogues with methodology disclosure', () => {
    render(
      <BrowserRouter>
        <HistoricalAnaloguesCard analogues={intel.analogues} />
      </BrowserRouter>
    );

    expect(screen.getByText(/Historical Analogue Matches/i)).toBeInTheDocument();
    expect(screen.getByText(/Similarity Methodology Disclosure:/i)).toBeInTheDocument();
  });

  it('renders scenario analysis preserving baseline', () => {
    render(
      <ScenarioAnalysisCard
        scenarios={intel.scenarios}
        homeTeamName="Union Berlin"
        awayTeamName="Bayer Leverkusen"
      />
    );

    expect(screen.getByText(/Interactive Scenario Sensitivity Analysis/i)).toBeInTheDocument();
    // Baseline scenario
    expect(screen.getAllByText(/baseline/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders MiroFish with SIMULATED SCENARIO EVIDENCE label and handles unavailable state', () => {
    // When unavailable
    const { rerender } = render(<MiroFishSection mirofish={intel.mirofish} />);
    expect(screen.getByText(/MiroFish provider is not configured/i)).toBeInTheDocument();
    expect(screen.getByText(/SIMULATED SCENARIO EVIDENCE/i)).toBeInTheDocument();

    // When completed
    const completedMirofish = {
      status: 'ok',
      provider: 'mirofish_test',
      contract_version: 'v1',
      scenarios: [
        {
          scenario: 'baseline',
          narrative: 'Tactical simulation suggests conservative midblock formation.',
          structured_observations: { press_resistance: 'high' },
        },
      ],
      provenance: {},
    };

    rerender(<MiroFishSection mirofish={completedMirofish} />);
    expect(screen.getByText(/Tactical simulation suggests conservative midblock formation/i)).toBeInTheDocument();
    expect(screen.getByText('press resistance:')).toBeInTheDocument();
  });

  it('renders backend warnings accurately', () => {
    render(<WarningsSection warnings={intel.warnings} />);

    expect(screen.getByText('XG_UNAVAILABLE')).toBeInTheDocument();
    expect(screen.getByText('CLOSING_ONLY')).toBeInTheDocument();
  });

  it('renders cryptographic provenance and copy action', () => {
    render(<ProvenanceSection provenance={intel.provenance} rawJson={intel} />);

    expect(screen.getByText(/CRYPTOGRAPHIC PROVENANCE/i)).toBeInTheDocument();
    expect(screen.getByText(/Copy JSON/i)).toBeInTheDocument();
  });

  it('renders MatchStatComparisonCard with authentic results vs engine & MiroFish predictions', () => {
    const mockComparison = {
      match_id: 1881,
      is_finished: true,
      has_score: true,
      home_team: { id: 111, name: 'Argentina' },
      away_team: { id: 113, name: 'Bolivia' },
      actual_score: { home: 4, away: 0 },
      actual_possession: { home: '69', away: '31' },
      accuracy_summary: {
        total_evaluated: 4,
        correct_hits: 3,
        accuracy_percentage: 75.0,
        brier_score: 0.234674,
        grade: 'EXCELLENT',
      },
      mirofish_summary: {
        status: 'ok',
        narrative: 'High pressing dominance forecasted from opening whistle.',
        scenarios_count: 1,
      },
      comparisons: [
        {
          category: 'Outcome',
          metric: 'Match Winner (1X2)',
          actual: 'Argentina Win (4-0)',
          engine_predicted: 'Argentina Win (51.6%)',
          mirofish_predicted: 'Simulated Argentina Win',
          status: 'HIT' as const,
          delta: 'Exact hit',
          notes: 'Engine favored correct side',
        },
        {
          category: 'Situational',
          metric: 'Corners (Total & Teams)',
          actual: '13 corners (Argentina: 12, Bolivia: 1)',
          engine_predicted: 'Projected: 11.2 (Argentina: 8.5, Bolivia: 2.7)',
          mirofish_predicted: 'Wing pressure simulation',
          status: 'HIT' as const,
          delta: '+1.8 corners',
          notes: 'Within normal match variance',
        },
      ],
    };

    render(
      <MatchStatComparisonCard
        comparison={mockComparison}
        homeTeamName="Argentina"
        awayTeamName="Bolivia"
      />
    );

    // Verify Title & Hero Score
    expect(screen.getByText(/Match Original Data vs Engine & MiroFish AI Prediction/i)).toBeInTheDocument();
    expect(screen.getByText('4 - 0')).toBeInTheDocument();
    expect(screen.getByText('Argentina Won')).toBeInTheDocument();

    // Verify Possession
    expect(screen.getByText(/Argentina: 69%/i)).toBeInTheDocument();

    // Verify Accuracy & Grade
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('EXCELLENT')).toBeInTheDocument();

    // Verify Comparisons Table
    expect(screen.getByText('Match Winner (1X2)')).toBeInTheDocument();
    expect(screen.getByText('Argentina Win (4-0)')).toBeInTheDocument();
    expect(screen.getByText('Corners (Total & Teams)')).toBeInTheDocument();
    expect(screen.getAllByText('Hit').length).toBeGreaterThanOrEqual(2);
  });

  it('renders share prediction modal with export controls and screenshot preview', () => {
    render(
      <SharePredictionModal
        isOpen={true}
        onClose={() => {}}
        intel={intel}
        homeTeamName="Arsenal"
        awayTeamName="Chelsea"
      />
    );

    // Verify Title & Teams
    expect(screen.getByText(/Share Match Prediction Snapshot/i)).toBeInTheDocument();
    expect(screen.getAllByText('Arsenal').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Chelsea').length).toBeGreaterThanOrEqual(1);

    // Verify Action Buttons
    expect(screen.getByText(/Download PNG/i)).toBeInTheDocument();
    expect(screen.getByText(/Copy Image/i)).toBeInTheDocument();
    expect(screen.getByText(/Copy Match Link/i)).toBeInTheDocument();
  });
});


