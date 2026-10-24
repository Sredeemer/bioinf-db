"""Pydantic API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# -------------------------------------------------------------------------
# Repositories
# -------------------------------------------------------------------------


class CreateRepoRequest(BaseModel):
    """Payload to create a new dataset repository."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    owner_slug: str = Field(..., min_length=2, max_length=64)
    owner_type: Literal["user", "org"] = "user"
    description: str | None = None
    domain: str
    access: Literal["public", "gated", "private"] = "public"
    license: str = "cc-by-4.0"


class UpdateRepoRequest(BaseModel):
    """Payload to update repository settings."""

    model_config = ConfigDict(strict=True)

    description: str | None = None
    domain: str | None = None
    access: Literal["public", "gated", "private"] | None = None
    license: str | None = None


class RepoResponse(BaseModel):
    """Serialized repository details."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    owner_type: str
    owner_id: str
    description: str | None
    domain: str
    access: str
    license: str
    is_verified_african: bool
    created_at: datetime
    updated_at: datetime
    countries: list[str] = Field(default_factory=list)
    taxon_ids: list[int] = Field(default_factory=list)
    genus: list[str] = Field(default_factory=list)
    family: list[str] = Field(default_factory=list)
    samples_count: int = 0
    total_size_bytes: int = 0
    files_count: int = 0


# -------------------------------------------------------------------------
# Organizations & Memberships
# -------------------------------------------------------------------------


class CreateOrgRequest(BaseModel):
    """Payload to create a new organization."""

    model_config = ConfigDict(strict=True)

    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None


class OrgResponse(BaseModel):
    """Serialized organization details."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    description: str | None
    created_at: datetime


class AddMemberRequest(BaseModel):
    """Payload to add or update a member in an organization."""

    model_config = ConfigDict(strict=True)

    user_id: str = Field(..., min_length=1)
    role: Literal["admin", "write", "read"] = "read"


class MemberResponse(BaseModel):
    """Serialized organization member details."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    org_id: str
    role: str
    created_at: datetime
    user_name: str | None = None
    user_orcid: str | None = None


# -------------------------------------------------------------------------
# Personal Access Tokens
# -------------------------------------------------------------------------


class CreateTokenRequest(BaseModel):
    """Payload to create a personal access token."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=1, max_length=128)
    scope: Literal["read", "write", "admin"] = "read"
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


class TokenCreatedResponse(BaseModel):
    """Response returned once when a PAT is created containing raw secret."""

    id: str
    name: str
    scope: str
    raw_token: str
    expires_at: datetime | None
    created_at: datetime


# -------------------------------------------------------------------------
# Device Authorization (RFC 8628)
# -------------------------------------------------------------------------


class DeviceCodeResponse(BaseModel):
    """Response when a device flow is initiated."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int = 2


class DeviceVerifyRequest(BaseModel):
    """User code verification payload submitted by authenticated browser."""

    model_config = ConfigDict(strict=True)

    user_code: str = Field(..., min_length=4, max_length=16)


class DeviceTokenRequest(BaseModel):
    """Polling payload sent by CLI client."""

    model_config = ConfigDict(strict=True)

    device_code: str = Field(..., min_length=16, max_length=128)


# -------------------------------------------------------------------------
# OpenXet CAS & Commits
# -------------------------------------------------------------------------


class PreuploadRequest(BaseModel):
    """Pre-upload inquiry for pushing files into OpenXet."""

    model_config = ConfigDict(strict=True)

    filenames: list[str] = Field(..., min_length=1)


class PreuploadResponse(BaseModel):
    """Authorization response granting an ephemeral CAS write token."""

    repo_slug: str
    cas_url: str
    cas_write_token: str
    expires_in_seconds: int


class CommitFilePayload(BaseModel):
    """Individual file metadata mapping."""

    model_config = ConfigDict(strict=True)

    path: str
    sha256: str = Field(..., min_length=64, max_length=64)
    xet_hash: str = Field(..., min_length=64, max_length=64)
    size_bytes: int = Field(..., gt=0)


class CommitRequest(BaseModel):
    """Request finalizing an HTTP commit after files are pushed to OpenXet."""

    model_config = ConfigDict(strict=True)

    branch: str = "main"
    message: str = Field(..., min_length=1, max_length=255)
    files: list[CommitFilePayload] = Field(..., min_length=1)


# -------------------------------------------------------------------------
# Git Trees and Commits Read API
# -------------------------------------------------------------------------


class CommitLogItem(BaseModel):
    """Single commit summary."""

    commit_hash: str
    author: str
    date: str
    message: str


class TreeItem(BaseModel):
    """Directory tree entry."""

    mode: str
    type: str  # blob or tree
    oid: str
    size: int | None = None
    path: str


class TreeResponse(BaseModel):
    """Listing of files at a given revision."""

    ref: str
    items: list[TreeItem]


# -------------------------------------------------------------------------
# Git LFS Batch Protocol
# -------------------------------------------------------------------------


class LfsObject(BaseModel):
    """Object requested in Git LFS batch."""

    oid: str
    size: int


class LfsBatchRequest(BaseModel):
    """Git LFS batch API request payload."""

    operation: Literal["download", "upload"]
    transfers: list[str] = ["basic"]
    objects: list[LfsObject]
    ref: dict[str, str] | None = None
    hash_algo: str = "sha256"


class LfsAction(BaseModel):
    """Action href and headers for LFS transfer."""

    href: str
    header: dict[str, str] = Field(default_factory=dict)
    expires_at: str | None = None


class LfsObjectResponse(BaseModel):
    """Object response in Git LFS batch."""

    oid: str
    size: int
    authenticated: bool = True
    actions: dict[str, LfsAction] | None = None
    error: dict[str, Any] | None = None


class LfsBatchResponse(BaseModel):
    """Git LFS batch API response payload."""

    transfer: str = "basic"
    objects: list[LfsObjectResponse]
    hash_algo: str = "sha256"


# -------------------------------------------------------------------------
# Gated Datasets & DUA
# -------------------------------------------------------------------------


class DuaAcceptRequest(BaseModel):
    """Payload acknowledging and accepting a repository's Data Use Agreement."""

    dua_version: str = "1.0"


class DuaAcceptanceResponse(BaseModel):
    """Confirmation of DUA acceptance."""

    id: str
    repo_slug: str
    dua_version: str
    accepted_at: datetime


class CreateAccessRequestPayload(BaseModel):
    """Request justification for accessing a gated dataset."""

    justification: str = Field(..., min_length=10, max_length=2000)


class AccessRequestResponse(BaseModel):
    """Serialized access request status."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    repo_id: str
    user_id: str
    status: str
    justification: str
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class AccessRequestDecisionPayload(BaseModel):
    """Decision (approve/deny) by dataset owner."""

    decision: Literal["approved", "rejected"]
    reason: str | None = None


class AuditLogResponse(BaseModel):
    """Serialized audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    repo_id: str
    user_id: str | None
    action: str
    resource_path: str
    ip_hash: str
    timestamp: datetime
