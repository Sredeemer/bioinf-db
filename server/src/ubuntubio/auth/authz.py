"""Centralized authorization engine enforcing dataset access control (M1-07)."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import (
    AccessRequestModel,
    DuaAcceptanceModel,
    MembershipModel,
    RepositoryModel,
    UserModel,
)

logger = get_logger("ubuntubio.auth.authz")


class RepoAction(StrEnum):
    """Actions subject to repository authorization."""

    READ_METADATA = "read_metadata"
    DOWNLOAD_DATA = "download_data"
    WRITE_COMMIT = "write_commit"
    MANAGE_SETTINGS = "manage_settings"


class AuthorizationService:
    """Evaluates repository permissions across public, gated, and private access tiers."""

    @staticmethod
    async def is_org_member(
        session: AsyncSession,
        user_id: str | None,
        org_id_or_slug: str,
    ) -> str | None:
        """Check if user belongs to an org by ID or slug, returning their role or None."""
        if not user_id:
            return None
        from sqlalchemy import or_

        from ubuntubio.db.models import OrganizationModel

        stmt = (
            select(MembershipModel.role)
            .join(OrganizationModel, MembershipModel.org_id == OrganizationModel.id)
            .where(
                MembershipModel.user_id == user_id,
                or_(
                    OrganizationModel.id == org_id_or_slug,
                    OrganizationModel.slug == org_id_or_slug,
                ),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def has_approved_gated_access(
        session: AsyncSession,
        user_id: str | None,
        repo_id: str,
    ) -> bool:
        """Verify if user has accepted the DUA and received approved access for Gated repos."""
        if not user_id:
            return False

        # 1. Check DUA acceptance
        dua_stmt = select(DuaAcceptanceModel.id).where(
            DuaAcceptanceModel.user_id == user_id,
            DuaAcceptanceModel.repo_id == repo_id,
        )
        dua_res = await session.execute(dua_stmt)
        if not dua_res.scalar_one_or_none():
            return False

        # 2. Check Approved Access Request
        req_stmt = select(AccessRequestModel.id).where(
            AccessRequestModel.user_id == user_id,
            AccessRequestModel.repo_id == repo_id,
            AccessRequestModel.status == "approved",
        )
        req_res = await session.execute(req_stmt)
        return req_res.scalar_one_or_none() is not None

    async def can_perform_action(
        self,
        session: AsyncSession,
        user: UserModel | None,
        repo: RepositoryModel,
        action: RepoAction,
    ) -> bool:
        """Evaluate if user (or anonymous) is permitted to execute action on repository."""
        user_id = user.id if user else None

        # Check ownership or organization membership
        is_owner = False
        org_role: str | None = None

        if user_id:
            if repo.owner_type == "user" and repo.owner_id == user_id:
                is_owner = True
            elif repo.owner_type == "org":
                org_role = await self.is_org_member(session, user_id, repo.owner_id)
                if org_role == "admin":
                    is_owner = True

        allowed = False
        # Owners have unconditional permission
        if is_owner:
            allowed = True
        elif action == RepoAction.MANAGE_SETTINGS:
            allowed = False
        elif action == RepoAction.WRITE_COMMIT:
            allowed = org_role in ("admin", "write")
        elif repo.access == "public":
            allowed = action in (RepoAction.READ_METADATA, RepoAction.DOWNLOAD_DATA)
        elif repo.access == "gated":
            if action == RepoAction.READ_METADATA:
                allowed = True  # Metadata card & sample table are publicly discoverable
            elif action == RepoAction.DOWNLOAD_DATA:
                if org_role in ("admin", "write", "read"):
                    allowed = True
                else:
                    allowed = await self.has_approved_gated_access(session, user_id, repo.id)
            else:
                allowed = False
        elif repo.access == "private":
            if user_id and org_role in ("admin", "write", "read"):
                allowed = action in (RepoAction.READ_METADATA, RepoAction.DOWNLOAD_DATA)
            else:
                allowed = False

        if not allowed:
            logger.warning(
                "Repository access denied",
                extra={
                    "user_id": user_id,
                    "repo_slug": repo.slug,
                    "access_tier": repo.access,
                    "action": action.value,
                },
            )
        else:
            logger.debug(
                "Repository access granted",
                extra={
                    "user_id": user_id,
                    "repo_slug": repo.slug,
                    "access_tier": repo.access,
                    "action": action.value,
                },
            )
        return allowed
