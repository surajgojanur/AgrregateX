-- Loader manifest interface (Phase 01A, requested by Codex on Issue #1).
-- Stable contract: `SELECT manifest FROM loader.dataset_manifest` returns zero
-- rows (no activated load) or one jsonb document, manifest_version 1. Fields
-- are only ever added, never renamed or removed, within manifest_version 1.

CREATE TABLE IF NOT EXISTS loader.validations(
 id bigserial PRIMARY KEY,
 run_id text REFERENCES loader.runs ON DELETE SET NULL,
 kind text NOT NULL CHECK (kind IN ('verify-rollups','rebuild-rollups')),
 passed boolean NOT NULL,
 result jsonb NOT NULL,
 validated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE VIEW loader.dataset_manifest AS
WITH r AS (SELECT * FROM loader.runs WHERE state='active' ORDER BY activated_at DESC LIMIT 1),
dist AS (SELECT tenant_id,count(*) AS total_rows,count(*) FILTER (WHERE id<0) AS bulk_rows
         FROM public.orders GROUP BY tenant_id),
v AS (SELECT DISTINCT ON (kind) kind,passed,result,validated_at FROM loader.validations
      ORDER BY kind,validated_at DESC)
SELECT jsonb_build_object(
 'manifest_version',1,
 'official_dataset_compatibility','NOT VERIFIED',
 'run_id',r.run_id,
 'state',r.state,
 'generator',r.spec->>'generator',
 'generator_version',CASE r.spec->>'generator' WHEN 'representative-v1' THEN 1 END,
 'seed',(r.spec->>'seed')::int,
 'target_rows',(r.spec->>'rows')::bigint,
 'spec_tenants',(r.spec->>'tenants')::int,
 'prefix',jsonb_build_object('rows',(r.spec->>'prefix_rows')::bigint,'tenants',(r.spec->>'prefix_tenants')::int,
                             'check',r.activation->>'prefix_check'),
 'batch_size',(r.spec->>'batch_size')::int,
 'loader_commit',r.activation->>'loader_commit',
 'load_completed_at',r.activated_at,
 'source_rows',(SELECT coalesce(sum(total_rows),0) FROM dist),
 'bulk_rows',(SELECT coalesce(sum(bulk_rows),0) FROM dist),
 'api_rows',(SELECT coalesce(sum(total_rows-bulk_rows),0) FROM dist),
 'tenant_count',(SELECT count(*) FROM dist),
 'tenant_distribution',(SELECT jsonb_agg(jsonb_build_object('tenant_id',tenant_id,'rows',total_rows,'bulk_rows',bulk_rows)
                        ORDER BY tenant_id) FROM dist),
 'stage_verification',jsonb_build_object('passed',(r.verification->>'passed')::boolean,'checks',r.verification->'checks'),
 'activation',jsonb_build_object('mode',r.activation->>'mode','inserted',(r.activation->>'inserted')::bigint,
                                 'transaction_seconds',(r.activation->>'transaction_seconds')::numeric,
                                 'wal_bytes',(r.activation->>'wal_bytes')::bigint),
 'validations',coalesce((SELECT jsonb_object_agg(kind,jsonb_build_object(
     'passed',passed,'validated_at',validated_at,'after_load',validated_at>=r.activated_at,
     'source_orders',result->'source_orders',
     'mismatches',jsonb_build_object('daily_product',result->'daily_product'->'mismatches',
                                     'hourly_category',result->'hourly_category'->'mismatches'))) FROM v),'{}'::jsonb)
) AS manifest
FROM r;

INSERT INTO loader.schema_version(version) VALUES (2) ON CONFLICT DO NOTHING;
