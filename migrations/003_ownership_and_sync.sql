-- Ownership is enforced by the Flask API after Supabase Auth verifies the user.
-- Legacy rows remain unassigned until the first signed-in account claims them.
ALTER TABLE vehicles ADD COLUMN owner_id UUID;
CREATE INDEX vehicles_owner ON vehicles(owner_id, is_active, id);

-- Automatic prices are shared reference data; manually supplied prices belong
-- to the account that entered them. Keep the existing source_url='manual'.
ALTER TABLE fuel_prices ADD COLUMN owner_id UUID;
ALTER TABLE fuel_prices DROP CONSTRAINT fuel_prices_fuel_type_id_price_zone_effective_at_source_url_key;
CREATE UNIQUE INDEX fuel_price_manual_unique ON fuel_prices(owner_id,fuel_type_id,price_zone,effective_at)
    WHERE source_url='manual' AND owner_id IS NOT NULL;
CREATE UNIQUE INDEX fuel_price_legacy_manual_unique ON fuel_prices(fuel_type_id,price_zone,effective_at)
    WHERE source_url='manual' AND owner_id IS NULL;
CREATE UNIQUE INDEX fuel_price_shared_unique ON fuel_prices(fuel_type_id,price_zone,effective_at,source_url)
    WHERE source_url<>'manual';
CREATE INDEX fuel_price_owner ON fuel_prices(owner_id,effective_at DESC) WHERE owner_id IS NOT NULL;

CREATE TABLE price_sync_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_date DATE NOT NULL,
    trigger TEXT NOT NULL CHECK(trigger IN ('manual','cron')),
    status TEXT NOT NULL CHECK(status IN ('running','success','failed','skipped')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    observed_rows INTEGER NOT NULL DEFAULT 0,
    inserted_rows INTEGER NOT NULL DEFAULT 0,
    changed_rows INTEGER NOT NULL DEFAULT 0,
    unchanged_rows INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    CHECK(finished_at IS NULL OR finished_at>=started_at)
);
CREATE UNIQUE INDEX price_sync_once_per_day ON price_sync_runs(run_date) WHERE trigger='cron';
CREATE INDEX price_sync_recent ON price_sync_runs(started_at DESC);

INSERT INTO schema_migrations(version) VALUES('003_ownership_and_sync');
