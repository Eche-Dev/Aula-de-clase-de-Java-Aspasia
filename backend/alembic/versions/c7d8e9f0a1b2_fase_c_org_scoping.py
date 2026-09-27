"""Fase C: aislamiento por organización.

- course_categories / cohorts / custom_roles: columna organization_id (FK, backfill org 1)
- unicidades globales (courses.code, slug, code de cohorte, name de rol) → compuestas por org
- system_settings: PK (key) → PK (key, organization_id)

Revision ID: c7d8e9f0a1b2
Revises: f4e5d6c7b8a9
Create Date: 2026-09-27 23:21:44.623788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'f4e5d6c7b8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_org_column(table: str, fk_name: str, ix_name: str) -> None:
    """Añade organization_id (NOT NULL, backfill org 1) + FK + índice, en modo batch.

    SQLite no permite ALTER TABLE ... ADD COLUMN con REFERENCES NOT NULL cuando
    foreign_keys está activo, así que recreamos la tabla (recreate="always").
    Los índices únicos globales previos se dropean ANTES (fuera del batch) y los
    compuestos se crean DESPUÉS, para evitar colisiones de nombre por fase.
    """
    with op.batch_alter_table(table, recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "organization_id",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_index(ix_name, ["organization_id"])
        batch_op.create_foreign_key(
            fk_name,
            "organizations",
            ["organization_id"],
            ["id"],
        )


def _drop_org_column(table: str, fk_name: str, ix_name: str) -> None:
    with op.batch_alter_table(table, recreate="always") as batch_op:
        batch_op.drop_constraint(fk_name, type_="foreignkey")
        batch_op.drop_index(ix_name)
        batch_op.drop_column("organization_id")


def upgrade() -> None:
    # --- courses: code único global → code + organization_id -----------------
    op.drop_index(op.f('ix_courses_code'), table_name='courses')
    op.create_index(
        'uq_courses_code_org', 'courses', ['code', 'organization_id'], unique=True
    )

    # --- course_categories ----------------------------------------------------
    op.drop_index(op.f('ix_course_categories_slug'), table_name='course_categories')
    _add_org_column(
        "course_categories",
        fk_name="fk_course_categories_organization_id_organizations",
        ix_name="ix_course_categories_organization_id",
    )
    op.create_index(
        op.f('ix_course_categories_slug'), 'course_categories', ['slug']
    )
    op.create_index(
        'uq_course_categories_slug_org',
        'course_categories',
        ['slug', 'organization_id'],
        unique=True,
    )

    # --- cohorts --------------------------------------------------------------
    op.drop_index(op.f('ix_cohorts_code'), table_name='cohorts')
    _add_org_column(
        "cohorts",
        fk_name="fk_cohorts_organization_id_organizations",
        ix_name="ix_cohorts_organization_id",
    )
    op.create_index(op.f('ix_cohorts_code'), 'cohorts', ['code'])
    op.create_index(
        'uq_cohorts_code_org', 'cohorts', ['code', 'organization_id'], unique=True
    )

    # --- custom_roles ---------------------------------------------------------
    op.drop_index(op.f('ix_custom_roles_name'), table_name='custom_roles')
    _add_org_column(
        "custom_roles",
        fk_name="fk_custom_roles_organization_id_organizations",
        ix_name="ix_custom_roles_organization_id",
    )
    op.create_index(op.f('ix_custom_roles_name'), 'custom_roles', ['name'])
    op.create_index(
        'uq_custom_roles_name_org',
        'custom_roles',
        ['name', 'organization_id'],
        unique=True,
    )

    # --- system_settings: PK (key) → PK (key, organization_id) ---------------
    # Rebuild explícito: SQLite no puede cambiar una PRIMARY KEY con ALTER.
    op.create_table(
        "system_settings_new",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("value", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_system_settings_organization_id_organizations",
        ),
        sa.PrimaryKeyConstraint("key", "organization_id", name="pk_system_settings"),
    )
    op.execute(
        "INSERT INTO system_settings_new (key, organization_id, value, updated_at) "
        "SELECT key, 1, value, updated_at FROM system_settings"
    )
    op.drop_table("system_settings")
    op.rename_table("system_settings_new", "system_settings")


def downgrade() -> None:
    # --- system_settings: vuelve a PK (key); filas de orgs ≠ 1 se eliminan ---
    op.execute("DELETE FROM system_settings WHERE organization_id <> 1")
    op.create_table(
        "system_settings_old",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_system_settings"),
    )
    op.execute(
        "INSERT INTO system_settings_old (key, value, updated_at) "
        "SELECT key, value, updated_at FROM system_settings"
    )
    op.drop_table("system_settings")
    op.rename_table("system_settings_old", "system_settings")

    # --- custom_roles ---------------------------------------------------------
    op.drop_index('uq_custom_roles_name_org', table_name='custom_roles')
    _drop_org_column(
        "custom_roles",
        fk_name="fk_custom_roles_organization_id_organizations",
        ix_name="ix_custom_roles_organization_id",
    )
    op.drop_index(op.f('ix_custom_roles_name'), table_name='custom_roles')
    op.create_index(
        op.f('ix_custom_roles_name'), 'custom_roles', ['name'], unique=True
    )

    # --- cohorts --------------------------------------------------------------
    op.drop_index('uq_cohorts_code_org', table_name='cohorts')
    _drop_org_column(
        "cohorts",
        fk_name="fk_cohorts_organization_id_organizations",
        ix_name="ix_cohorts_organization_id",
    )
    op.drop_index(op.f('ix_cohorts_code'), table_name='cohorts')
    op.create_index(op.f('ix_cohorts_code'), 'cohorts', ['code'], unique=True)

    # --- course_categories ----------------------------------------------------
    op.drop_index('uq_course_categories_slug_org', table_name='course_categories')
    _drop_org_column(
        "course_categories",
        fk_name="fk_course_categories_organization_id_organizations",
        ix_name="ix_course_categories_organization_id",
    )
    op.drop_index(op.f('ix_course_categories_slug'), table_name='course_categories')
    op.create_index(
        op.f('ix_course_categories_slug'), 'course_categories', ['slug'], unique=True
    )

    # --- courses --------------------------------------------------------------
    op.drop_index('uq_courses_code_org', table_name='courses')
    op.create_index(op.f('ix_courses_code'), 'courses', ['code'], unique=True)
