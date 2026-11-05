"""Fresh install and populated P2 migration preserve actual historical evidence."""

from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.config import get_settings
from app.database import SessionLocal


def test_upgrade_populated_p2_preserves_old_meaning_and_one_head():
    schema = "migration_" + uuid4().hex
    with SessionLocal.begin() as s:
        s.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        get_settings().database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        with engine.begin() as connection:
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "0004_prototype2")
            connection.execute(
                text("""
                INSERT INTO tests(id,name) VALUES ('legacy','Original name');
                INSERT INTO test_versions(test_id,version,name,prompt,evaluation_definition)
                  VALUES ('legacy',1,'Original name','Original  prompt', '{}');
                INSERT INTO models(id,name) VALUES ('legacy-model','legacy-model');
                INSERT INTO test_runs(id,test_version_id,model_id,status,configuration,
                  input_prompt,started_at,completed_at,latency_ms,input_tokens,output_tokens)
                  SELECT 'legacy-run',id,'legacy-model','completed','{"overall_score": 0}',
                  'Original  prompt','2026-09-01T00:00:00Z','2026-09-01T00:00:01Z',1000,0,NULL
                  FROM test_versions;
                INSERT INTO model_responses(run_id,content)
                  VALUES ('legacy-run','Original response');
                INSERT INTO evaluation_results(run_id,method,passed,score)
                  VALUES ('legacy-run','legacy-method',false,0);
            """)
            )
            before = connection.execute(text("SELECT row_to_json(r) FROM test_runs r")).scalar_one()
            command.upgrade(cfg, "head")
            after = connection.execute(text("SELECT row_to_json(r) FROM test_runs r")).scalar_one()
            assert {key: after[key] for key in before} == before
            evaluation = connection.execute(
                text("SELECT score,maximum_points,normalized_score FROM evaluation_results")
            ).one()
            assert (
                evaluation.score == 0
                and evaluation.maximum_points is None
                and evaluation.normalized_score is None
            )
            assert (
                connection.scalar(text("SELECT content FROM model_responses"))
                == "Original response"
            )
            assert connection.scalar(text("SELECT approval FROM test_versions")) is None
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all() == ["0006_omar_storage"]
    finally:
        engine.dispose()
        with SessionLocal.begin() as s:
            s.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
