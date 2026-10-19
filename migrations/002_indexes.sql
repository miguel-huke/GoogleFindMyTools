CREATE INDEX idx_locations_beacon_time
    ON location_reports(beacon_id, observed_at DESC);

CREATE INDEX idx_sync_runs_started
    ON sync_runs(started_at DESC);

CREATE VIEW beacon_latest_locations AS
SELECT lr.*
FROM location_reports lr
JOIN (
    SELECT beacon_id, MAX(observed_at) AS max_observed_at
    FROM location_reports
    WHERE kind = 'POINT'
    GROUP BY beacon_id
) latest
ON latest.beacon_id = lr.beacon_id
AND latest.max_observed_at = lr.observed_at
WHERE lr.kind = 'POINT';
