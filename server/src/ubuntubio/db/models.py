"""SQLAlchemy 2.0 database models for UbuntuBio Hub."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def generate_uuid() -> str:
    """Generate a random UUID4 string."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base declarative class with type annotation support."""

    pass


class UserModel(Base):
    """User account linked to ORCID."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    orcid_id: Mapped[str] = mapped_column(String(19), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    memberships: Mapped[list[MembershipModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tokens: Mapped[list[PersonalAccessTokenModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    access_requests: Mapped[list[AccessRequestModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OrganizationModel(Base):
    """Research organization, institute, or consortium."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    memberships: Mapped[list[MembershipModel]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    tokens: Mapped[list[PersonalAccessTokenModel]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class MembershipModel(Base):
    """User membership and role within an organization."""

    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Literal["admin", "write", "read"]] = mapped_column(
        String(16), nullable=False, default="read"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[UserModel] = relationship(back_populates="memberships")
    organization: Mapped[OrganizationModel] = relationship(back_populates="memberships")

    __table_args__ = (Index("idx_user_org_unique", "user_id", "org_id", unique=True),)


class PersonalAccessTokenModel(Base):
    """Hashed personal access token or service-account token."""

    __tablename__ = "personal_access_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[Literal["read", "write", "admin"]] = mapped_column(
        String(16), nullable=False, default="read"
    )

    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserModel | None] = relationship(back_populates="tokens")
    organization: Mapped[OrganizationModel | None] = relationship(back_populates="tokens")


class RepositoryModel(Base):
    """Bioinformatics dataset repository."""

    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_type: Mapped[Literal["user", "org"]] = mapped_column(String(8), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    access: Mapped[Literal["public", "gated", "private"]] = mapped_column(
        String(16), nullable=False, default="public", index=True
    )
    license: Mapped[str] = mapped_column(String(64), nullable=False, default="cc-by-4.0")
    is_verified_african: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    access_requests: Mapped[list[AccessRequestModel]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    lfs_objects: Mapped[list[LfsObjectModel]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    samples: Mapped[list[SampleModel]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class XetFileModel(Base):
    """Mapping between standard SHA-256 and OpenXet content-addressable hash."""

    __tablename__ = "xet_files"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    xet_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LfsObjectModel(Base):
    """Git LFS object registered under a specific repository."""

    __tablename__ = "lfs_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    oid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # SHA-256
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    repository: Mapped[RepositoryModel] = relationship(back_populates="lfs_objects")

    __table_args__ = (Index("idx_repo_oid_unique", "repo_id", "oid", unique=True),)


class AccessRequestModel(Base):
    """Request by an authenticated user for access to a Gated dataset."""

    __tablename__ = "access_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[Literal["pending", "approved", "rejected"]] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    user: Mapped[UserModel] = relationship(back_populates="access_requests")
    repository: Mapped[RepositoryModel] = relationship(back_populates="access_requests")

    __table_args__ = (Index("idx_user_repo_request_unique", "user_id", "repo_id", unique=True),)


class DuaAcceptanceModel(Base):
    """Record of a user accepting a Data Use Agreement."""

    __tablename__ = "dua_acceptances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dua_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1.0")
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (Index("idx_user_repo_dua_unique", "user_id", "repo_id", unique=True),)


class AuditLogModel(Base):
    """Immutable audit trail of gated/controlled dataset access."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    repo_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # download, clone, token_mint
    resource_path: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class SampleModel(Base):
    """Biological sample metadata record extracted from samples.tsv."""

    __tablename__ = "samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sample_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    taxon_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    genus: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    family: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    country: Mapped[str] = mapped_column(String(2), index=True, nullable=False)
    collection_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    admin1: Mapped[str | None] = mapped_column(String(128), nullable=True)
    host: Mapped[str | None] = mapped_column(String(128), nullable=True)
    isolation_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extra_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    repository: Mapped[RepositoryModel] = relationship(back_populates="samples")

    __table_args__ = (
        Index("idx_repo_sample_unique", "repo_id", "sample_id", unique=True),
        Index("idx_sample_country_taxon", "country", "taxon_id"),
    )


class DatasetSearchRecordModel(Base):
    """Pre-aggregated search index record for a repository."""

    __tablename__ = "dataset_search_records"

    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    access: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    license: Mapped[str] = mapped_column(String(64), nullable=False)
    countries_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    taxa_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    genus_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    family_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_verified_african: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    owner_type: Mapped[str] = mapped_column(String(8), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    samples_count: Mapped[int] = mapped_column(Integer, default=0)
    benefit_sharing: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
