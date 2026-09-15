"""Index transmitter satellite ownership fields.

Revision ID: d7e5a9c2b4f1
Revises: f7b4d1e9a2c6
Create Date: 2026-09-15 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d7e5a9c2b4f1"
down_revision: Union[str, None] = "f7b4d1e9a2c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transmitters_norad_cat_id",
        "transmitters",
        ["norad_cat_id"],
        unique=False,
    )
    op.create_index(
        "ix_transmitters_norad_follow_id",
        "transmitters",
        ["norad_follow_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transmitters_norad_follow_id", table_name="transmitters")
    op.drop_index("ix_transmitters_norad_cat_id", table_name="transmitters")
