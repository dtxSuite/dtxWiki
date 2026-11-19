"""Temporary Alembic targets for testing individual 0.3.1 conversion phases."""

import shutil
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from alembic.config import Config

from backend.app.bootstrap import resolve_migrations_dir
from backend.migrations.revision_modules.v0_3._c3d2e4f601ab_release_0_3_1 import (
    context_content_to_git,
    context_git_bodies,
    document_locator_rollback,
)

RELEASE_023 = "00ba02774c4a"
GIT_SNAPSHOTS = "test_context_git_snapshots"
HISTORICAL_BODIES = "test_context_historical_bodies"
MCP_CALL_LIFECYCLE = "test_context_mcp_lifecycle"
DOCUMENT_IDENTITY = "test_context_document_identity"


def configure_context_migration_phases(config: Config, tmp_path: Path) -> None:
    """Run the shared production phases under stand-alone test revisions.

    Use the real migration environment for transactions and preflight. Synthetic
    IDs let these scoped tests inspect and reverse the individual phases before
    the final release's one-way draft conversion.
    """
    scripts = tmp_path / "context-migration-phases"
    shutil.copytree(
        resolve_migrations_dir(),
        scripts,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    versions = scripts / "versions"
    shutil.rmtree(versions / "v0_3")
    phases = versions / "test_context_phases"
    phases.mkdir()
    parent = RELEASE_023
    for revision, upgrade, downgrade in (
        (GIT_SNAPSHOTS, "add_context_git_snapshots", "remove_context_git_snapshots"),
        (
            HISTORICAL_BODIES,
            "release_historical_context_bodies",
            "remove_historical_context_bodies",
        ),
        (MCP_CALL_LIFECYCLE, "track_mcp_call_lifecycle", "remove_mcp_call_lifecycle"),
        (DOCUMENT_IDENTITY, "convert_document_identity", "remove_document_identity"),
    ):
        (phases / f"{revision}.py").write_text(
            "from backend.migrations.revision_modules.v0_3."
            "_c3d2e4f601ab_release_0_3_1.schema "
            f"import {upgrade} as upgrade\n"
            "from backend.tests.utils.context_migration_phases "
            f"import {downgrade} as downgrade\n"
            f"revision = {revision!r}\n"
            f"down_revision = {parent!r}\n",
            encoding="utf-8",
        )
        parent = revision
    config.set_main_option("script_location", str(scripts))


def remove_context_git_snapshots() -> None:
    context_content_to_git.repository_root(op.get_context().config.attributes)
    context_content_to_git.require_database_bodies(op.get_bind())
    for name in (
        "content_byte_size",
        "encoding",
        "media_type",
        "format_version",
        "content_format",
        "commit_oid",
    ):
        op.drop_column("context_page_version", name)


def remove_historical_context_bodies() -> None:
    root = context_git_bodies.repository_root(op.get_context().config.attributes)
    connection = op.get_bind()
    context_git_bodies.verify(connection, root, require_database_bodies=False)
    context_git_bodies.restore_database_bodies(connection, root)
    with op.batch_alter_table("context_page_version") as batch:
        batch.drop_constraint("context_page_version_body_stored_check", type_="check")
        batch.alter_column("body_md", existing_type=sa.Text(), nullable=False)


def remove_mcp_call_lifecycle() -> None:
    op.drop_index("ix_mcp_tool_call_actor_key_started", table_name="mcp_tool_call")
    op.drop_column("mcp_tool_call", "retryable")
    op.drop_column("mcp_tool_call", "idempotency_key")
    op.drop_column("mcp_tool_call", "actor_id")
    op.drop_column("mcp_tool_call", "actor_kind")


def remove_document_identity() -> None:
    document_locator_rollback.restore(op.get_bind())
    op.drop_table("document_locator_rollback")
