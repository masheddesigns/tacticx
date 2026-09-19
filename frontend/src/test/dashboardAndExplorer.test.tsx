import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { CurrentSeasonBanner } from '../components/dashboard/CurrentSeasonBanner';
import { ErrorCard } from '../components/common/ErrorCard';
import { ApiError } from '../api/client';
import { MatchRow } from '../components/matches/MatchRow';
import { MatchListItem } from '../api/types';

describe('Dashboard & Explorer Components — Honest State Communication', () => {
  it('renders honest zero-data current season banner without fabricating fixtures', () => {
    render(
      <BrowserRouter>
        <CurrentSeasonBanner
          currentSeason="2026/27"
          leaguesCoverage={{
            EPL: { fixture_count: 0 },
            LA_LIGA: { fixture_count: 0 },
            SERIE_A: { fixture_count: 0 },
            BUNDESLIGA: { fixture_count: 0 },
            LIGUE_1: { fixture_count: 0 },
          }}
        />
      </BrowserRouter>
    );

    // Mandatory notice
    expect(screen.getByText(/Current-Season Fixture Source Unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/No validated Level-A provider currently supplies real-time fixtures for the 2026\/27 campaign/i)).toBeInTheDocument();

    // Verify all 5 leagues show 0 fixtures
    const zeroCounts = screen.getAllByText('0 fixtures');
    expect(zeroCounts.length).toBe(5);

    // Verify 0% coverage badge
    const coverageLabels = screen.getAllByText(/Coverage: 0.0%/i);
    expect(coverageLabels.length).toBe(5);
  });

  it('translates backend error codes into friendly user messages without leaking stack traces', () => {
    const error = new ApiError('Detailed internal trace line 42', 'match_not_found', 404);
    render(<ErrorCard error={error} />);

    expect(screen.getByText('Match Not Found')).toBeInTheDocument();
    expect(screen.getByText(/The requested fixture does not exist in the canonical database registry/i)).toBeInTheDocument();
    expect(screen.queryByText('line 42')).toBeNull();
  });

  it('renders match row with kickoff and status cleanly', () => {
    const sampleMatch: MatchListItem = {
      id: 381,
      home_team_name: 'Arsenal',
      away_team_name: 'Chelsea',
      kickoff_at: '2024-05-12T15:00:00Z',
      status: 'FINISHED',
      home_score: 2,
      away_score: 1,
      prediction_eligible: true,
    };

    render(
      <BrowserRouter>
        <MatchRow match={sampleMatch} />
      </BrowserRouter>
    );

    expect(screen.getByText('Arsenal')).toBeInTheDocument();
    expect(screen.getByText('Chelsea')).toBeInTheDocument();
    expect(screen.getByText('2 - 1')).toBeInTheDocument();
    expect(screen.getByText('FINISHED')).toBeInTheDocument();
    expect(screen.getByText(/Intelligence Ready/i)).toBeInTheDocument();
  });
});
