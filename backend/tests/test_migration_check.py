"""deploy.sh asks for confirmation before any migration that could delete data."""
from __future__ import annotations

from app.ops.migration_check import destructive_reasons, main


def test_additive_changes_pass():
    src = '''def upgrade():
    op.create_table("x", sa.Column("id", sa.Integer()))
    op.add_column("y", sa.Column("note", sa.Text(), nullable=True))
    op.create_index("ix", "y", ["note"])
    op.drop_index("old_ix", table_name="y")
    op.alter_column("y", "note", nullable=False)
'''
    assert destructive_reasons(src) == []


def test_data_removing_changes_are_flagged():
    assert destructive_reasons('def upgrade():\n    op.drop_table("payments")') == ["drops a table"]
    assert destructive_reasons('def upgrade():\n    with op.batch_alter_table("t") as batch_op:\n        batch_op.drop_column("c")') == ["drops a column"]
    assert destructive_reasons('def upgrade():\n    op.alter_column("t", "c", type_=sa.Integer())') == ["changes a column type"]
    # existing_type before type_ (the usual autogenerate order) used to slip through
    assert destructive_reasons('def upgrade():\n    batch_op.alter_column("c", existing_type=sa.VARCHAR(length=120), type_=sa.Integer())') == ["changes a column type"]
    # widening to TEXT cannot lose data
    assert destructive_reasons('def upgrade():\n    batch_op.alter_column("c", existing_type=sa.VARCHAR(length=120), type_=sa.Text(), existing_nullable=True)') == []
    assert destructive_reasons('def upgrade():\n    op.execute("DELETE FROM sessions")') == ["runs DELETE/TRUNCATE/DROP SQL"]
    assert destructive_reasons("def upgrade():\n    op.execute('truncate audit_logs')") == ["runs DELETE/TRUNCATE/DROP SQL"]


# Revisions whose upgrade() removes data on purpose, after review (deploy.sh still asks before applying them).
REVIEWED_DESTRUCTIVE: set[str] = set()


def test_the_projects_own_migrations_are_all_additive():
    """Every shipped migration's upgrade() only adds (drops exist only in downgrade()). A new destructive migration
    fails this test until its revision is added to REVIEWED_DESTRUCTIVE: a deliberate second look."""
    import inspect

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.core.config import BASE_DIR

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    flagged = {rev.revision: destructive_reasons(inspect.getsource(rev.module.upgrade))
               for rev in ScriptDirectory.from_config(cfg).walk_revisions()}
    assert {k: v for k, v in flagged.items() if v and k not in REVIEWED_DESTRUCTIVE} == {}


def test_command_reports_up_to_date(db, capsys):
    """Whatever the test database holds, the shipped migrations never trigger the confirmation."""
    code = main([])
    out = capsys.readouterr().out
    assert code == 0 and ("up to date" in out or "migration(s) to apply" in out)
    assert "removes or rewrites data" not in out
