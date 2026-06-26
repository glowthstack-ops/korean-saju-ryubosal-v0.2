CREATE TABLE IF NOT EXISTS external_geo_feature (
  feature_id TEXT PRIMARY KEY,
  feature_type TEXT NOT NULL,
  feature_subtype TEXT,
  feature_name TEXT,
  source_name TEXT NOT NULL,
  source_feature_id TEXT,
  x_5179 REAL NOT NULL,
  y_5179 REAL NOT NULL,
  lon REAL,
  lat REAL,
  elevation_m REAL,
  area_m2 REAL,
  length_m REAL,
  element_wood REAL DEFAULT 0,
  element_fire REAL DEFAULT 0,
  element_earth REAL DEFAULT 0,
  element_metal REAL DEFAULT 0,
  element_water REAL DEFAULT 0,
  importance REAL DEFAULT 1.0,
  confidence REAL DEFAULT 0.5,
  anchor_role TEXT,
  anchor_index INTEGER,
  parent_feature_id TEXT,
  raw_props_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_external_geo_feature_type ON external_geo_feature(feature_type);
CREATE INDEX IF NOT EXISTS idx_external_geo_feature_xy ON external_geo_feature(x_5179, y_5179);

CREATE TABLE IF NOT EXISTS region_feature_direction (
  region_code TEXT NOT NULL,
  feature_id TEXT NOT NULL,
  feature_type TEXT NOT NULL,
  feature_name TEXT,
  distance_m REAL NOT NULL,
  bearing_deg REAL NOT NULL,
  direction_code TEXT NOT NULL,
  radius_bucket TEXT NOT NULL,
  signal_wood REAL DEFAULT 0,
  signal_fire REAL DEFAULT 0,
  signal_earth REAL DEFAULT 0,
  signal_metal REAL DEFAULT 0,
  signal_water REAL DEFAULT 0,
  influence_score REAL DEFAULT 0,
  confidence REAL DEFAULT 0.5,
  PRIMARY KEY (region_code, feature_id)
);

CREATE INDEX IF NOT EXISTS idx_region_feature_direction_region ON region_feature_direction(region_code);
CREATE INDEX IF NOT EXISTS idx_region_feature_direction_direction ON region_feature_direction(region_code, direction_code);
CREATE INDEX IF NOT EXISTS idx_region_feature_direction_distance ON region_feature_direction(distance_m);

CREATE TABLE IF NOT EXISTS region_directional_element_summary (
  region_code TEXT NOT NULL,
  direction_code TEXT NOT NULL,
  wood_score REAL DEFAULT 0,
  fire_score REAL DEFAULT 0,
  earth_score REAL DEFAULT 0,
  metal_score REAL DEFAULT 0,
  water_score REAL DEFAULT 0,
  nearest_mountain_m REAL,
  nearest_river_m REAL,
  nearest_water_m REAL,
  nearest_coast_m REAL,
  nearest_forest_m REAL,
  top_features_json TEXT,
  confidence REAL DEFAULT 0.0,
  PRIMARY KEY (region_code, direction_code)
);
