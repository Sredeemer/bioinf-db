"""Username handle generation and uniqueness resolution for UbuntuBio researchers."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy import select

from ubuntubio.db.models import UserModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


TITLES_PATTERN = re.compile(r"^(dr|prof|professor|mr|mrs|ms)\.?\s+", re.IGNORECASE)


def slugify_researcher_name(name: str) -> str:
    """Convert researcher display name into a clean, lowercase alphanumeric handle."""
    clean = TITLES_PATTERN.sub("", name.strip())
    # Replace non-alphanumeric characters with hyphens
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", clean).strip("-").lower()
    # Truncate to a reasonable length
    if len(slug) > 32:
        slug = slug[:32].rstrip("-")
    return slug or "researcher"


def extract_orcid_suffix(orcid_id: str) -> str:
    """Extract a 4-character lowercase identifier from the end of an ORCID iD."""
    clean = re.sub(r"[^a-zA-Z0-9]", "", orcid_id).lower()
    return clean[-4:] if len(clean) >= 4 else "bio"


async def generate_unique_username(session: AsyncSession, name: str, orcid_id: str) -> str:
    """Generate a unique researcher handle, appending ORCID discriminator if needed."""
    base_slug = slugify_researcher_name(name)
    orcid_suffix = extract_orcid_suffix(orcid_id)

    # 1. First attempt: clean base name (e.g. 'redeemer')
    stmt = select(UserModel).where(UserModel.username == base_slug)
    res = await session.execute(stmt)
    if res.scalar_one_or_none() is None:
        return base_slug

    # 2. Second attempt: base name + orcid suffix (e.g. 'redeemer-592x')
    candidate = f"{base_slug}-{orcid_suffix}"
    stmt = select(UserModel).where(UserModel.username == candidate)
    res = await session.execute(stmt)
    if res.scalar_one_or_none() is None:
        return candidate

    # 3. Fallback: incremental index
    counter = 2
    while True:
        candidate = f"{base_slug}-{orcid_suffix}-{counter}"
        stmt = select(UserModel).where(UserModel.username == candidate)
        res = await session.execute(stmt)
        if res.scalar_one_or_none() is None:
            return candidate
        counter += 1
