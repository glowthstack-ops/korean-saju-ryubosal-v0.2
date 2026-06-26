-- Region spatial engine P0 schema
-- Main tables: region_unit, emd_direction_probe, external_feature, region_feature_direction

CREATE TABLE region_unit (
  _seq_id INTEGER PRIMARY KEY,
  region_code TEXT NOT NULL,
  region_level TEXT NOT NULL,
  parent_code TEXT,
  sido_code TEXT,
  sigungu_code TEXT,
  emd_code TEXT,
  sido_name_ko TEXT,
  sigungu_name_ko TEXT,
  emd_name_ko TEXT,
  region_name_ko TEXT,
  region_name_en TEXT,
  full_name_ko TEXT,
  area_m2 REAL,
  centroid_x_5179 REAL, centroid_y_5179 REAL, centroid_lon REAL, centroid_lat REAL,
  anchor_x_5179 REAL, anchor_y_5179 REAL, anchor_lon REAL, anchor_lat REAL,
  bbox_minx_5179 REAL, bbox_miny_5179 REAL, bbox_maxx_5179 REAL, bbox_maxy_5179 REAL,
  bbox_width_m REAL, bbox_height_m REAL, geometry_type TEXT, geometry_valid INTEGER
);

CREATE TABLE emd_direction_probe (
  probe_id INTEGER PRIMARY KEY,
  region_code TEXT NOT NULL,
  region_level TEXT NOT NULL,
  full_name_ko TEXT,
  direction_code TEXT NOT NULL,
  direction_ko TEXT NOT NULL,
  bearing_deg REAL NOT NULL,
  radius_m INTEGER NOT NULL,
  probe_x_5179 REAL, probe_y_5179 REAL, probe_lon REAL, probe_lat REAL,
  direction_element_blend TEXT,
  direction_element_houtian TEXT
);

-- Fill this table when mountain/river/lake/coast/DEM datasets are available.
CREATE TABLE external_feature (
  feature_id TEXT PRIMARY KEY,
  feature_type TEXT NOT NULL, -- mountain|river|lake|coast|forest|elevation_peak|...
  feature_name TEXT,
  source_name TEXT,
  source_feature_code TEXT,
  x_5179 REAL, y_5179 REAL, lon REAL, lat REAL,
  elevation_m REAL, length_m REAL, area_m2 REAL,
  confidence REAL,
  extra_json TEXT
);

-- Calculated relation from region anchor to external feature.
CREATE TABLE region_feature_direction (
  region_code TEXT NOT NULL,
  feature_id TEXT NOT NULL,
  feature_type TEXT NOT NULL,
  feature_name TEXT,
  direction_code TEXT NOT NULL,
  bearing_deg REAL,
  distance_m REAL,
  within_region_yn INTEGER,
  within_radius_m INTEGER,
  element_signal TEXT, -- 木/火/土/金/水 or composite
  signal_weight REAL,
  source_name TEXT,
  calculated_at TEXT
);
