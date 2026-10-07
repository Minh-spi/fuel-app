-- Applied in one transaction by scripts/migrate.py. Existing IDs keep their numeric suffix.
SET LOCAL search_path TO fuel_app, pg_catalog;
LOCK TABLE vehicles, fuel_prices, fuel_logs, metadata IN ACCESS EXCLUSIVE MODE;

CREATE SEQUENCE fuel_types_id_seq;
CREATE TABLE fuel_types (
    id TEXT PRIMARY KEY DEFAULT ('F' || nextval('fuel_app.fuel_types_id_seq')) CHECK (id ~ '^F[1-9][0-9]*$'),
    code TEXT NOT NULL UNIQUE CHECK (length(code)>0),
    name TEXT NOT NULL UNIQUE CHECK (length(name)>0),
    category TEXT NOT NULL CHECK (category IN ('gasoline','diesel','other')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER SEQUENCE fuel_types_id_seq OWNED BY fuel_types.id;
INSERT INTO fuel_types(code,name,category) VALUES
 ('E10_RON95_III','E10 RON 95-III','gasoline'),
 ('E10_RON95_V','E10 RON 95-V','gasoline'),
 ('E5_RON92_II','E5 RON 92-II','gasoline'),
 ('RON95_III','RON 95-III','gasoline');
-- Preserve any user/imported product names outside the original catalog.
INSERT INTO fuel_types(code,name,category)
 SELECT 'LEGACY_'||md5(name),name,'other' FROM (
   SELECT fuel_type AS name FROM vehicles UNION SELECT fuel_type FROM fuel_prices UNION SELECT fuel_type FROM fuel_logs
 ) names WHERE NOT EXISTS (SELECT 1 FROM fuel_types f WHERE f.name=names.name) ORDER BY name;

ALTER TABLE fuel_logs DROP CONSTRAINT fuel_logs_vehicle_id_fkey;
ALTER TABLE fuel_logs DROP CONSTRAINT fuel_logs_price_id_fkey;
-- Preserve sequence high-water marks, including deleted IDs and consumed values.
DO $$ DECLARE t TEXT; prefix TEXT; last_id BIGINT; max_id BIGINT; next_id BIGINT; called BOOLEAN; BEGIN
 FOR t,prefix IN SELECT * FROM (VALUES ('vehicles','V'),('fuel_prices','P'),('fuel_logs','R')) AS ids(t,prefix) LOOP
  EXECUTE format('SELECT last_value,is_called FROM fuel_app.%I', t||'_id_seq') INTO last_id,called;
  EXECUTE format('SELECT COALESCE(max(id),0) FROM fuel_app.%I',t) INTO max_id;
  next_id := greatest(last_id+called::int,max_id+1);
  EXECUTE format('ALTER TABLE fuel_app.%I ALTER COLUMN id DROP IDENTITY',t);
  EXECUTE format('ALTER TABLE fuel_app.%I DROP CONSTRAINT %I',t,t||'_id_check');
  EXECUTE format('ALTER TABLE fuel_app.%I ALTER COLUMN id TYPE TEXT USING %L || id::text',t,prefix);
  EXECUTE format('CREATE SEQUENCE fuel_app.%I',t||'_id_seq');
  EXECUTE format('ALTER SEQUENCE fuel_app.%I RESTART WITH %s',t||'_id_seq',next_id);
  EXECUTE format('ALTER SEQUENCE fuel_app.%I OWNED BY fuel_app.%I.id',t||'_id_seq',t);
  EXECUTE format('ALTER TABLE fuel_app.%I ALTER COLUMN id SET DEFAULT %L || nextval(%L)',t,prefix,'fuel_app.'||t||'_id_seq');
  EXECUTE format('ALTER TABLE fuel_app.%I ADD CHECK (id ~ %L)',t,'^'||prefix||'[1-9][0-9]*$');
 END LOOP;
END $$;
ALTER TABLE fuel_logs ALTER COLUMN vehicle_id TYPE TEXT USING 'V'||vehicle_id::text;
ALTER TABLE fuel_logs ALTER COLUMN price_id TYPE TEXT USING 'P'||price_id::text;
ALTER TABLE fuel_logs ADD FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE RESTRICT;
ALTER TABLE fuel_logs ADD FOREIGN KEY(price_id) REFERENCES fuel_prices(id) ON DELETE RESTRICT;

ALTER TABLE vehicles ADD COLUMN default_fuel_type_id TEXT REFERENCES fuel_types(id) ON DELETE RESTRICT;
UPDATE vehicles v SET default_fuel_type_id=f.id FROM fuel_types f WHERE f.name=v.fuel_type;
ALTER TABLE vehicles ALTER COLUMN default_fuel_type_id SET NOT NULL;
ALTER TABLE vehicles ALTER COLUMN default_fuel_type_id SET DEFAULT 'F1';
ALTER TABLE vehicles DROP COLUMN fuel_type;
ALTER TABLE vehicles ADD COLUMN vehicle_type TEXT NOT NULL DEFAULT 'unknown' CHECK(vehicle_type IN ('motorcycle','car','other','unknown'));
ALTER TABLE vehicles ADD COLUMN transmission_type TEXT NOT NULL DEFAULT 'unknown' CHECK(transmission_type IN ('automatic','semi_automatic','manual','other','unknown'));
ALTER TABLE vehicles ADD COLUMN brand TEXT;
ALTER TABLE vehicles ADD COLUMN model TEXT;
ALTER TABLE vehicles ADD COLUMN model_year SMALLINT CHECK(model_year BETWEEN 1886 AND 9999);
ALTER TABLE vehicles ADD COLUMN engine_displacement_cc INTEGER CHECK(engine_displacement_cc>0);
ALTER TABLE vehicles ADD COLUMN purchased_on DATE;
ALTER TABLE vehicles ADD COLUMN notes TEXT;
ALTER TABLE vehicles ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE vehicles ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE vehicles ALTER COLUMN tank_capacity_liters DROP NOT NULL;
ALTER TABLE vehicles ALTER COLUMN tank_capacity_liters DROP DEFAULT;
ALTER TABLE vehicles ALTER COLUMN license_plate DROP NOT NULL;
ALTER TABLE vehicles ALTER COLUMN license_plate DROP DEFAULT;
UPDATE vehicles SET license_plate=NULL WHERE license_plate='';

ALTER TABLE fuel_prices ADD COLUMN fuel_type_id TEXT REFERENCES fuel_types(id) ON DELETE RESTRICT;
UPDATE fuel_prices p SET fuel_type_id=f.id FROM fuel_types f WHERE f.name=p.fuel_type;
ALTER TABLE fuel_prices ALTER COLUMN fuel_type_id SET NOT NULL;
UPDATE fuel_prices SET source_url=CASE WHEN source='manual' THEN 'manual' WHEN source_url='' THEN 'https://www.petrolimex.com.vn/' ELSE source_url END;
ALTER TABLE fuel_prices DROP COLUMN fuel_type;
ALTER TABLE fuel_prices DROP COLUMN source;
ALTER TABLE fuel_prices RENAME COLUMN unit_price_vnd TO unit_price_vnd_per_liter;
ALTER TABLE fuel_prices RENAME COLUMN fetched_at TO updated_at;
ALTER TABLE fuel_prices ADD COLUMN created_at TIMESTAMPTZ;
UPDATE fuel_prices SET created_at=updated_at;
ALTER TABLE fuel_prices ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE fuel_prices ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE fuel_prices ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE fuel_prices ALTER COLUMN source_url DROP DEFAULT;
ALTER TABLE fuel_prices ADD CHECK(source_url='manual' OR source_url ~ '^https?://[^/[:space:]]+');
ALTER TABLE fuel_prices ADD UNIQUE(fuel_type_id,price_zone,effective_at,source_url);

ALTER TABLE fuel_logs ADD COLUMN fuel_type_id TEXT REFERENCES fuel_types(id) ON DELETE RESTRICT;
UPDATE fuel_logs l SET fuel_type_id=f.id FROM fuel_types f WHERE f.name=l.fuel_type;
ALTER TABLE fuel_logs ALTER COLUMN fuel_type_id SET NOT NULL;
ALTER TABLE fuel_logs DROP COLUMN fuel_type;
ALTER TABLE fuel_logs DROP COLUMN price_source;
ALTER TABLE fuel_logs DROP COLUMN volume_source;
ALTER TABLE fuel_logs DROP COLUMN is_full_tank;
ALTER TABLE fuel_logs RENAME COLUMN filled_on TO refueled_on;
ALTER TABLE fuel_logs RENAME COLUMN filled_time TO refueled_time;
ALTER TABLE fuel_logs RENAME COLUMN price_id TO fuel_price_id;
ALTER TABLE fuel_logs RENAME TO refueling_logs;
ALTER SEQUENCE fuel_logs_id_seq RENAME TO refueling_logs_id_seq;
ALTER TABLE metadata RENAME TO app_metadata;
CREATE INDEX price_history_v2 ON fuel_prices(fuel_type_id,price_zone,effective_at DESC);
CREATE INDEX vehicle_fuel_type ON vehicles(default_fuel_type_id);
CREATE INDEX refueling_fuel_type ON refueling_logs(fuel_type_id);
REVOKE ALL ON fuel_types FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fuel_app FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='fuel_runtime') THEN
  GRANT SELECT ON fuel_types TO fuel_runtime;
  GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA fuel_app TO fuel_runtime;
 END IF;
END $$;
INSERT INTO schema_migrations(version) VALUES('002_fuel_catalog');
