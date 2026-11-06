"""Alembic history stays linear: unique revision ids and a single head (no database needed)."""

import ast
from collections import Counter
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _revision_ids() -> list[str]:
    ids = []
    for path in VERSIONS.glob("*.py"):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "revision":
                ids.append(node.value.value)
    return ids


def test_revision_ids_are_unique():
    duplicates = [rev for rev, count in Counter(_revision_ids()).items() if count > 1]

    assert not duplicates, f"Several migrations use the revision id {duplicates}"


def test_history_has_a_single_head():
    config = Config(str(VERSIONS.parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(VERSIONS.parent))

    assert len(ScriptDirectory.from_config(config).get_heads()) == 1
