BEGIN;


CREATE TABLE IF NOT EXISTS entity_import_status (
    entity_type VARCHAR(50) NOT NULL,
    entity_id BIGINT NOT NULL,

    data_type VARCHAR(50) NOT NULL,

    source VARCHAR(50) NOT NULL DEFAULT 'api-football',

    status VARCHAR(20) NOT NULL,

    rows_received INTEGER NOT NULL DEFAULT 0,

    raw_payload JSONB,

    error_message TEXT,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        entity_type,
        entity_id,
        data_type,
        source
    ),

    CONSTRAINT entity_import_status_status_check
        CHECK (
            status IN (
                'success',
                'failed'
            )
        )
);


CREATE INDEX IF NOT EXISTS idx_entity_import_status_type
ON entity_import_status (
    entity_type,
    data_type,
    status
);


CREATE INDEX IF NOT EXISTS idx_entity_import_status_entity
ON entity_import_status (
    entity_id
);


COMMIT;