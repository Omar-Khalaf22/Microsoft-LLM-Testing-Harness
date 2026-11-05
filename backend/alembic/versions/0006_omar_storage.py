"""P3 saved definitions, pinned suites, reservations, ownership and evidence integrity.

Revision ID: 0006_omar_storage
Revises: 0005_lina_reviews
"""

from alembic import op

revision = "0006_omar_storage"
down_revision = "0005_lina_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE tests ADD COLUMN project_id text NOT NULL DEFAULT 'prototype',
      ADD COLUMN creator_id text;
    ALTER TABLE human_reviews ADD COLUMN attribution jsonb;
    CREATE INDEX ix_tests_project_id ON tests(project_id);
    ALTER TABLE test_versions ADD COLUMN definition_hash text, ADD COLUMN approval jsonb;
    CREATE TABLE version_criteria (
      test_version_id bigint REFERENCES test_versions(id), criterion_id text NOT NULL,
      maximum_points numeric(5,2) NOT NULL CHECK(maximum_points BETWEEN 0 AND 100),
      definition jsonb NOT NULL, PRIMARY KEY(test_version_id,criterion_id));
    CREATE TABLE suites(id text PRIMARY KEY, project_id text NOT NULL, creator_id text NOT NULL);
    CREATE INDEX ix_suites_project_id ON suites(project_id);
    CREATE TABLE suite_revisions(suite_id text REFERENCES suites(id),
      revision integer CHECK(revision>0), name text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(suite_id,revision));
    CREATE TABLE suite_items(suite_id text, revision integer, position integer CHECK(position>0),
      test_version_id bigint NOT NULL REFERENCES test_versions(id),
      PRIMARY KEY(suite_id,revision,position),
      FOREIGN KEY(suite_id,revision) REFERENCES suite_revisions(suite_id,revision));
    CREATE INDEX ix_suite_items_test_version_id ON suite_items(test_version_id);
    CREATE TABLE executions(id text PRIMARY KEY, project_id text NOT NULL, actor_id text NOT NULL,
      idempotency_key text, request_hash text NOT NULL, snapshot jsonb NOT NULL,
      status text NOT NULL CHECK(status IN ('pending','running','completed','failed')),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(project_id,actor_id,idempotency_key));
    CREATE INDEX ix_executions_project_id ON executions(project_id);
    CREATE TABLE previews(id text PRIMARY KEY, project_id text NOT NULL, actor_id text NOT NULL,
      test_version_id bigint NOT NULL REFERENCES test_versions(id),
      configuration_hash text NOT NULL,
      profile jsonb NOT NULL,
      status text NOT NULL CHECK(status IN ('completed','technical_error')),
      actual_model text, interpretation jsonb NOT NULL, error_category text,
      created_at timestamptz NOT NULL DEFAULT now());
    CREATE INDEX ix_previews_project_id ON previews(project_id);
    CREATE INDEX ix_previews_test_version_id ON previews(test_version_id);
    ALTER TABLE test_runs ALTER COLUMN started_at DROP NOT NULL;
    ALTER TABLE test_runs ADD COLUMN project_id text NOT NULL DEFAULT 'prototype',
      ADD COLUMN execution_id text REFERENCES executions(id),
      ADD COLUMN rerun_of_run_id text REFERENCES test_runs(id),
      ADD COLUMN suite_position integer, ADD COLUMN model_position integer,
      ADD COLUMN lease_token text, ADD COLUMN lease_until timestamptz, ADD COLUMN evidence jsonb;
    CREATE INDEX ix_test_runs_execution_id ON test_runs(execution_id);
    CREATE INDEX ix_test_runs_rerun_of_run_id ON test_runs(rerun_of_run_id);
    CREATE INDEX ix_history_scope_created ON test_runs(project_id,created_at DESC,id DESC);
    CREATE UNIQUE INDEX uq_attempt_position
      ON test_runs(execution_id,suite_position,model_position);
    ALTER TABLE test_runs ADD CONSTRAINT ck_reserved_attempt CHECK(execution_id IS NULL OR (
      suite_position>0 AND model_position>0 AND
      ((status='pending' AND started_at IS NULL AND completed_at IS NULL) OR
       (status='running' AND started_at IS NOT NULL AND completed_at IS NULL) OR
       (status IN ('completed','failed') AND completed_at IS NOT NULL))));
    ALTER TABLE evaluation_results ADD COLUMN test_version_id bigint;
    ALTER TABLE evaluation_results ADD CONSTRAINT fk_evaluation_membership
      FOREIGN KEY(test_version_id,criterion_id)
      REFERENCES version_criteria(test_version_id,criterion_id);

    CREATE FUNCTION p3_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Immutable historical evidence' USING ERRCODE='23514'; END $$;
    CREATE TRIGGER immutable_versions BEFORE UPDATE OR DELETE ON test_versions
      FOR EACH ROW WHEN (OLD.definition_hash IS NOT NULL) EXECUTE FUNCTION p3_immutable();
    CREATE TRIGGER immutable_criteria BEFORE UPDATE OR DELETE ON version_criteria
      FOR EACH ROW EXECUTE FUNCTION p3_immutable();
    CREATE TRIGGER immutable_suite_revisions BEFORE UPDATE OR DELETE ON suite_revisions
      FOR EACH ROW EXECUTE FUNCTION p3_immutable();
    CREATE TRIGGER immutable_suite_items BEFORE UPDATE OR DELETE ON suite_items
      FOR EACH ROW EXECUTE FUNCTION p3_immutable();
    CREATE TRIGGER immutable_previews BEFORE UPDATE OR DELETE ON previews
      FOR EACH ROW EXECUTE FUNCTION p3_immutable();
    CREATE TRIGGER immutable_reviews BEFORE UPDATE OR DELETE ON human_reviews
      FOR EACH ROW EXECUTE FUNCTION p3_immutable();

    CREATE FUNCTION p3_version_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE v test_versions; n integer; total numeric;
    BEGIN
      IF TG_TABLE_NAME='test_versions' THEN
        SELECT * INTO v FROM test_versions WHERE id=NEW.id;
      ELSE
        SELECT * INTO v FROM test_versions WHERE id=NEW.test_version_id;
      END IF;
      IF v.definition_hash IS NULL THEN RETURN NULL; END IF;
      SELECT count(*),sum(maximum_points) INTO n,total FROM version_criteria
        WHERE test_version_id=v.id;
      IF n=0 OR total<>100 OR (v.evaluation_definition->'criteria' <> 'null'::jsonb AND
        EXISTS(SELECT 1 FROM version_criteria WHERE test_version_id=v.id AND maximum_points<=0))
      THEN RAISE EXCEPTION 'Invalid rubric allocation' USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER valid_rubric AFTER INSERT ON version_criteria
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION p3_version_integrity();
    CREATE CONSTRAINT TRIGGER valid_saved_rubric AFTER INSERT ON test_versions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION p3_version_integrity();

    CREATE FUNCTION p3_suite_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE n integer; hi integer;
    BEGIN
      SELECT count(*),max(position) INTO n,hi FROM suite_items
        WHERE suite_id=NEW.suite_id AND revision=NEW.revision;
      IF n=0 OR n<>hi THEN RAISE EXCEPTION 'Suite positions must be contiguous'
        USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER valid_suite AFTER INSERT ON suite_revisions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION p3_suite_integrity();

    CREATE FUNCTION p3_run_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.execution_id IS NULL THEN RETURN COALESCE(NEW,OLD); END IF;
      IF TG_OP='DELETE' OR OLD.status IN ('completed','failed') THEN
        RAISE EXCEPTION 'Terminal attempt is immutable' USING ERRCODE='23514'; END IF;
      IF (NEW.test_version_id,NEW.model_id,NEW.execution_id,NEW.project_id,
          NEW.input_prompt,NEW.suite_position,NEW.model_position,NEW.rerun_of_run_id,
          NEW.created_at,NEW.configuration->'snapshot') IS DISTINCT FROM
         (OLD.test_version_id,OLD.model_id,OLD.execution_id,OLD.project_id,
          OLD.input_prompt,OLD.suite_position,OLD.model_position,OLD.rerun_of_run_id,
          OLD.created_at,OLD.configuration->'snapshot') THEN
        RAISE EXCEPTION 'Frozen execution membership' USING ERRCODE='23514'; END IF;
      IF NEW.status<>OLD.status AND NOT
        ((OLD.status='pending' AND NEW.status IN ('running','failed')) OR
         (OLD.status='running' AND NEW.status IN ('completed','failed'))) THEN
        RAISE EXCEPTION 'Invalid attempt transition' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER guarded_attempt BEFORE UPDATE OR DELETE ON test_runs
      FOR EACH ROW EXECUTE FUNCTION p3_run_guard();

    CREATE FUNCTION p3_evaluation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r test_runs; m numeric;
    BEGIN
      SELECT * INTO r FROM test_runs WHERE id=COALESCE(NEW.run_id,OLD.run_id);
      IF r.execution_id IS NULL THEN RETURN COALESCE(NEW,OLD); END IF;
      IF TG_OP<>'INSERT' OR r.status IN ('completed','failed') THEN
        RAISE EXCEPTION 'Immutable evaluation' USING ERRCODE='23514'; END IF;
      SELECT maximum_points INTO m FROM version_criteria
        WHERE test_version_id=r.test_version_id AND criterion_id=NEW.criterion_id;
      IF m IS NULL OR NEW.test_version_id IS DISTINCT FROM r.test_version_id OR
        NEW.maximum_points IS DISTINCT FROM m THEN
        RAISE EXCEPTION 'Criterion does not belong to run version' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER guarded_evaluation BEFORE INSERT OR UPDATE OR DELETE ON evaluation_results
      FOR EACH ROW EXECUTE FUNCTION p3_evaluation_guard();

    CREATE FUNCTION p3_execution_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' OR (NEW.id,NEW.project_id,NEW.actor_id,NEW.idempotency_key,
        NEW.request_hash,NEW.snapshot,NEW.created_at) IS DISTINCT FROM
        (OLD.id,OLD.project_id,OLD.actor_id,OLD.idempotency_key,
        OLD.request_hash,OLD.snapshot,OLD.created_at) THEN
        RAISE EXCEPTION 'Immutable execution snapshot' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER guarded_execution BEFORE UPDATE OR DELETE ON executions
      FOR EACH ROW EXECUTE FUNCTION p3_execution_guard();
    CREATE FUNCTION p3_response_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS(SELECT 1 FROM test_runs WHERE id=OLD.run_id AND execution_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Immutable target evidence' USING ERRCODE='23514'; END IF;
      RETURN COALESCE(NEW,OLD);
    END $$;
    CREATE TRIGGER immutable_responses BEFORE UPDATE OR DELETE ON model_responses
      FOR EACH ROW EXECUTE FUNCTION p3_response_guard();
    """)


def downgrade():
    # Restoring an audited backup is safer than deleting P3 evidence to downgrade.
    raise RuntimeError("P3 evidence migration is forward-only. Restore a verified backup.")
