CREATE TABLE beacons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    canonic_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    device_type TEXT,
    manufacturer TEXT,
    model TEXT,
    image_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    first_seen_at INTEGER NOT NULL CHECK (first_seen_at >= 0),
    last_discovered_at INTEGER NOT NULL CHECK (last_discovered_at >= first_seen_at),
    created_at INTEGER NOT NULL CHECK (created_at >= 0),
    updated_at INTEGER NOT NULL CHECK (updated_at >= created_at)
);

CREATE TABLE location_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beacon_id INTEGER NOT NULL REFERENCES beacons(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('POINT', 'SEMANTIC')),
    latitude REAL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude REAL CHECK (longitude BETWEEN -180.0 AND 180.0),
    altitude INTEGER,
    accuracy REAL CHECK (accuracy IS NULL OR accuracy >= 0),
    semantic_name TEXT,
    observed_at INTEGER NOT NULL CHECK (observed_at >= 0),
    status TEXT NOT NULL CHECK (
        status IN ('SEMANTIC', 'LAST_KNOWN', 'CROWDSOURCED', 'AGGREGATED')
    ),
    is_own_report INTEGER NOT NULL CHECK (is_own_report IN (0, 1)),
    dedup_key TEXT NOT NULL UNIQUE,
    received_at INTEGER NOT NULL CHECK (received_at >= 0),
    CHECK (
        (kind = 'POINT' AND latitude IS NOT NULL AND longitude IS NOT NULL)
        OR
        (kind = 'SEMANTIC' AND semantic_name IS NOT NULL)
    )
);

CREATE TABLE sync_runs (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK (
        operation IN ('CONNECT', 'SYNC_DEVICES', 'REFRESH_ONE', 'REFRESH_ALL')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'TIMED_OUT', 'CANCELLED')
    ),
    beacon_public_id TEXT,
    started_at INTEGER CHECK (started_at IS NULL OR started_at >= 0),
    finished_at INTEGER CHECK (finished_at IS NULL OR finished_at >= started_at),
    devices_discovered INTEGER NOT NULL DEFAULT 0 CHECK (devices_discovered >= 0),
    reports_received INTEGER NOT NULL DEFAULT 0 CHECK (reports_received >= 0),
    reports_inserted INTEGER NOT NULL DEFAULT 0 CHECK (reports_inserted >= 0),
    reports_duplicated INTEGER NOT NULL DEFAULT 0 CHECK (reports_duplicated >= 0),
    error_code TEXT,
    error_message TEXT
);
