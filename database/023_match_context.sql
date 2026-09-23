BEGIN;

CREATE TABLE IF NOT EXISTS venue_locations (
    venue_id BIGINT PRIMARY KEY REFERENCES venues(venue_id),
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    source_url TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fixture_attendance_sources (
    fixture_id BIGINT PRIMARY KEY REFERENCES fixtures(fixture_id),
    attendance INTEGER NOT NULL CHECK (attendance >= 0),
    source_url TEXT NOT NULL,
    historical_capacity INTEGER CHECK (historical_capacity > 0),
    capacity_source_url TEXT,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (historical_capacity IS NULL OR capacity_source_url IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS fixture_weather (
    fixture_id BIGINT PRIMARY KEY REFERENCES fixtures(fixture_id),
    venue_id BIGINT NOT NULL REFERENCES venues(venue_id),
    kickoff_at TIMESTAMPTZ NOT NULL,
    sampled_at TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    temperature_c DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    wind_kmh DOUBLE PRECISION,
    weather_code INTEGER,
    source_url TEXT NOT NULL,
    model TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
