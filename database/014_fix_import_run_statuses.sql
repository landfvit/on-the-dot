ALTER TABLE import_runs
DROP CONSTRAINT IF EXISTS chk_import_runs_status;


ALTER TABLE import_runs
ADD CONSTRAINT chk_import_runs_status
CHECK (
    status IN (
        'running',
        'completed',
        'failed',
        'partial',
        'success'
    )
);