// 사용자 프로필(로컬 암호화 저장) + 백엔드 응답 타입(렌더에 쓰는 부분만).

export interface SajuLocation {
  name: string;
  region: string;
  lat: number;
  lon: number;
  tz: string;
}

export interface Profile {
  gender: "male" | "female";
  calendarType: "solar" | "lunar";
  isLeapMonth: boolean;
  birthDate: string; // YYYY-MM-DD
  birthTime: string | null; // HH:MM
  timeUnknown: boolean;
  place: SajuLocation;
}

export interface HiddenStem {
  stem: string;
  element: string;
  type: string;
  weight: number;
  ten_god: string;
}

export interface Pillar {
  stem: string;
  branch: string;
  ganji: string;
  stem_element: string;
  branch_element: string;
  stem_yinyang: string;
  branch_yinyang: string;
  stem_ten_god: string;
  branch_main_ten_god: string;
  twelve_unseong: string;
  hidden_stems: HiddenStem[];
  naeum: string | null;
  gongmang_hit: boolean;
  palace: string | null;
}

export interface StrengthResult {
  score: number;
  band: string;
  borderline: boolean;
  confidence: number;
  requires_validation: boolean;
  components: Record<string, number>;
  basis: Record<string, boolean>;
  rootedness: Record<string, unknown>;
  strong_chart_gate: Record<string, boolean>;
  has_all_elements?: boolean;
  element_presence_label?: string;
  imbalance_ratio?: number;
  element_balance_status?: string;
  band_note?: string;
  reason?: string[];
  warnings?: string[];
}

export interface ElementCandidate {
  element: string;
  score: number;
  model: string | null;
  reason: string | null;
}

export interface YongsinModel {
  model_type: string;
  label: string;
  yongsin: string | null;
  heesin: string | null;
  gisin: string | null;
  gusin: string | null;
  hansin: string | null;
  confidence: number;
  reasons: string[];
  is_auxiliary: boolean;
}

export interface YongsinAnalysis {
  status: string;
  candidate_models: YongsinModel[];
  useful_candidates: ElementCandidate[];
  unfavorable_candidates: ElementCandidate[];
  axis_weights: Record<string, number>;
  axes: Array<{ axis: string; weight: number; top_element: string; score: number }>;
  final: Record<string, string | number | null>;
  requires_validation: boolean;
  warnings: string[];
}

export interface LuckPolarity {
  element: string;
  type: string; // 용신 / 기신 / 한신
  score: number;
  detail?: string;
  base_score?: number | null;
  is_void?: boolean;
  has_clash?: boolean;
  branch_label?: string;
  event_trigger?: number;
  volatility?: number;
  reliability?: number;
}

export interface LuckSinsal {
  name: string;
  polarity: string; // positive(길신) / caution(흉성) / neutral(신살)
}

export interface DaewoonItem {
  index: number;
  start_age: number;
  approx_start_date: string;
  approx_end_date: string;
  ganji: string;
  stem: string;
  branch: string;
  stem_ten_god: string;
  branch_ten_god: string;
  twelve_unseong: string;
  yongsin_relation: string;
  stem_effect?: LuckPolarity | null;
  branch_effect?: LuckPolarity | null;
  luck_score?: number;
  luck_label?: string;
  luck_label_code?: string;
  luck_summary?: string;
  volatility_score: number;
  relations_to_chart: string[];
  luck_sinsal?: LuckSinsal[];
  sewoon?: LuckPillar[];
}

export interface LuckPillar {
  label: string;
  ganji: string;
  stem: string;
  branch: string;
  stem_ten_god: string;
  branch_ten_god: string;
  twelve_unseong?: string;
  yongsin_alignment: string;
  stem_effect?: LuckPolarity | null;
  branch_effect?: LuckPolarity | null;
  luck_score?: number;
  luck_label?: string;
  luck_label_code?: string;
  luck_summary?: string;
  solar_term_range?: string | null;
  luck_sinsal?: LuckSinsal[];
}

export interface LuckCycles {
  direction: string;
  start_age: number;
  current_age: number | null;
  current_daewoon_index: number | null;
  current_year?: number | null;
  current_month?: number | null;
  daewoon_table: DaewoonItem[];
  yearly_luck: LuckPillar[];
  monthly_luck: LuckPillar[];
  daily_luck: LuckPillar[];
  trace?: Record<string, unknown>;
}

export interface SinsalItem {
  name: string;
  category: string;
  position: string;
  basis: string;
  palace: string | null;
  ten_god_context: string | null;
  element_context: string | null;
  intensity: string;
  repeated: boolean;
  interpretation_tags: string[];
}

export interface CalibrationQuestion {
  id: string;
  question_type: string;
  year: number;
  period_label: string;
  period_range?: string;
  question_text: string;
  ask_domains: string[];
  options: string[];
}

export interface CalibrationResult {
  status: string;
  final_yongsin: string | null;
  final_heesin: string | null;
  final_gisin: string | null;
  final_gusin: string | null;
  confidence: number;
  evidence_count: number;
  match_rate: number;
  selected_model: string | null;
  explanation: string[];
}

export interface ManseResult {
  chart_id: string;
  input_summary: Record<string, unknown>;
  time_correction: Record<string, unknown> | null;
  solar_term_basis: Record<string, unknown> | null;
  pillars: {
    year: Pillar;
    month: Pillar;
    day: Pillar;
    hour: Pillar | null;
    day_master: string;
    gongmang_branches: string[];
  };
  force_analysis: {
    five_elements: {
      effective_percent: Record<string, number>;
      distribution_total: Record<string, number>;
      distribution_environment: Record<string, number>;
      season_adjusted_element_strength: Record<string, number>;
      visible_percent: Record<string, number>;
      visible_percent_without_day_master: Record<string, number>;
      raw_visible: Record<string, number>;
      strongest_element: string;
      weakest_element: string;
      excessive_elements: string[];
      deficient_elements: string[];
      hidden_only_elements: Array<{
        element: string;
        sources: Array<{
          position: string;
          branch: string;
          stage: string;
          stem: string;
          element: string;
          ten_god: string;
        }>;
        label: string;
        operability: string;
      }>;
      hidden_support: Record<string, string[]>;
      display_summary: {
        deficient_visible_elements?: string[];
        warnings?: string[];
      };
    };
    ten_gods: {
      effective_percent: Record<string, number>;
      distribution: Record<string, number>;
      season_adjusted_ten_god_strength: Record<string, number>;
      visible_percent: Record<string, number>;
      visible_absent: string[];
      groups: Record<string, number>;
    };
    rooting: Record<string, unknown>;
    strength: StrengthResult;
  };
  structure_analysis: {
    interactions: Array<Record<string, unknown>>;
    amplifiers?: Array<Record<string, unknown>>;
    gongmang: Record<string, unknown> | null;
  };
  geokguk: Record<string, unknown>;
  yongsin_analysis: YongsinAnalysis;
  luck_cycles: LuckCycles | null;
  calibration: { status: string; questions: CalibrationQuestion[] } | null;
  traditional_extras: { sinsal: { full_list: SinsalItem[] } | null } | null;
}

// 간지달력
export interface CalendarDay {
  date: string;
  weekday: number;
  day_ganji: string;
  day_ganji_ko: string;
  month_ganji: string;
  month_ganji_ko: string;
  year_ganji: string;
  year_ganji_ko: string;
  solar_term: string | null;
  lunar_date: string;
  is_leap_month: boolean;
  naeum: string | null;
  year_zodiac: string;
}

export interface CalendarMonth {
  year: number;
  month: number;
  days: CalendarDay[];
  solar_terms: Array<{ date: string; name: string }>;
}
