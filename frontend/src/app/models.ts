export interface Health {
  status: string;
  database: string;
  season: string;
  latest_update_id: string | null;
  fixtures: number;
  predictions: number;
  completed_matches: number;
  simulations: number;
}

export interface Fixture {
  fixture_id: string;
  season: string;
  matchday: number;
  reference_date: string;
  scheduled_date: string | null;
  kickoff_time: string | null;
  home_team_id: string;
  home_team: string;
  away_team_id: string;
  away_team: string;
  status: string;
}

export interface Prediction {
  fixture_id: string;
  matchday: number;
  home_team: string;
  away_team: string;
  model: string;
  probability_home: number;
  probability_draw: number;
  probability_away: number;
  predicted_ftr: 'H' | 'D' | 'A';
  confidence: string;
  expected_home_goals: number;
  expected_away_goals: number;
  predicted_score: string;
  market_odds_available: boolean;
}

export interface Standing {
  team_id: string;
  team: string;
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  position: number | null;
  ppg: number | null;
}

export interface Simulation {
  team_id: string;
  team: string;
  simulations: number;
  expected_points: number;
  points_p05: number;
  points_p95: number;
  expected_position: number;
  champion_probability: number;
  top4_probability: number;
  europe_top7_probability: number;
  relegation_probability: number;
}
