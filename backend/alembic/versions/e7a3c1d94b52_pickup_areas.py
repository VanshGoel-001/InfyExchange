"""pickup areas: replace free-text listing location with an admin-editable area plus block number

Backward compatible with the previous revision's code: it only adds a table and two nullable
columns, and `listings.location` stays (now the display text, e.g. "ECC - 87") so the old code
keeps reading and writing it during a rollout.

Existing locations are converted: "ECC87" / "ECC 92" become area ECC with that block, and text
that matches no area becomes "Other" (the original wording is dropped, by decision).

Revision ID: e7a3c1d94b52
Revises: d5b2e9a14c70
Create Date: 2026-11-16 12:00:00

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7a3c1d94b52'
down_revision: Union[str, Sequence[str], None] = 'd5b2e9a14c70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, has_blocks). The position in the list is the sort order.
SEED_AREAS = [
    ("ECC", True),
    ("GEC 1", False),
    ("GEC 2", False),
    ("Recreational Center", False),
    ("Food Court", False),
    ("Other", False),
]

# How each area is spelled in old free text. The earliest match in a string wins.
_AREA_PATTERNS = [
    ("ECC", re.compile(r"(?<![a-z])ecc(?![a-z])")),
    ("GEC 1", re.compile(r"(?<![a-z])gec\s*-?\s*1(?!\d)")),
    ("GEC 2", re.compile(r"(?<![a-z])gec\s*-?\s*2(?!\d)")),
    ("Recreational Center", re.compile(r"(?<![a-z])rec(?:reational)?\.?\s*cent(?:er|re)")),
    ("Food Court", re.compile(r"food\s*court")),
]
_BLOCK_AFTER_ECC = re.compile(r"\s*[-:,]?\s*(?:block\s*(?:no\.?|number)?\s*)?(\d{1,3})(?!\d)")


def parse_legacy_location(text: str) -> tuple[str, int | None]:
    """Turn old free text into (area name, block number or None)."""
    lowered = " ".join((text or "").lower().split())
    best = None
    for name, pattern in _AREA_PATTERNS:
        found = pattern.search(lowered)
        if found and (best is None or found.start() < best[1].start()):
            best = (name, found)
    if best is None:
        return "Other", None

    name, found = best
    if name != "ECC":
        return name, None
    block = _BLOCK_AFTER_ECC.match(lowered, found.end())
    if block and 1 <= int(block.group(1)) <= 100:
        return name, int(block.group(1))
    return name, None


def display_location(area: str, block: int | None) -> str:
    return f"{area} - {block}" if block else area


def upgrade() -> None:
    op.create_table(
        'pickup_areas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('has_blocks', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    areas = sa.table(
        'pickup_areas',
        sa.column('name', sa.String),
        sa.column('has_blocks', sa.Boolean),
        sa.column('is_active', sa.Boolean),
        sa.column('sort_order', sa.Integer),
    )
    op.bulk_insert(areas, [
        {'name': name, 'has_blocks': has_blocks, 'is_active': True, 'sort_order': position}
        for position, (name, has_blocks) in enumerate(SEED_AREAS, start=1)
    ])

    # batch mode: plain ALTER on PostgreSQL, table rebuild on SQLite.
    with op.batch_alter_table('listings') as batch_op:
        batch_op.add_column(sa.Column('pickup_area_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('block_no', sa.SmallInteger(), nullable=True))
        batch_op.create_foreign_key('fk_listings_pickup_area_id', 'pickup_areas', ['pickup_area_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_listings_pickup_area_id'), ['pickup_area_id'], unique=False)

    bind = op.get_bind()
    area_ids = dict(bind.execute(sa.text("SELECT name, id FROM pickup_areas")).fetchall())
    for listing_id, location in bind.execute(sa.text("SELECT id, location FROM listings")).fetchall():
        area, block = parse_legacy_location(location)
        bind.execute(
            sa.text(
                "UPDATE listings SET pickup_area_id = :area_id, block_no = :block, location = :location "
                "WHERE id = :id"
            ),
            {
                'area_id': area_ids[area],
                'block': block,
                'location': display_location(area, block),
                'id': listing_id,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table('listings') as batch_op:
        batch_op.drop_index(batch_op.f('ix_listings_pickup_area_id'))
        batch_op.drop_constraint('fk_listings_pickup_area_id', type_='foreignkey')
        batch_op.drop_column('block_no')
        batch_op.drop_column('pickup_area_id')
    op.drop_table('pickup_areas')
