"""Organization and membership management API routes (M1-05)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import require_authenticated_user
from ubuntubio.api.schemas import AddMemberRequest, CreateOrgRequest, MemberResponse, OrgResponse
from ubuntubio.auth.authz import AuthorizationService
from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import MembershipModel, OrganizationModel, UserModel
from ubuntubio.db.session import get_db_session

router = APIRouter(prefix="/api/orgs", tags=["Organizations"])
logger = get_logger("ubuntubio.api.orgs")
authz_service = AuthorizationService()


async def _get_org_by_slug(slug: str, session: AsyncSession) -> OrganizationModel:
    stmt = select(OrganizationModel).where(OrganizationModel.slug == slug)
    res = await session.execute(stmt)
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization '{slug}' not found.",
        )
    return org


@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: CreateOrgRequest,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrgResponse:
    """Create a new research organization or consortium."""
    stmt = select(OrganizationModel).where(OrganizationModel.slug == payload.slug)
    res = await session.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization '{payload.slug}' already exists.",
        )

    org = OrganizationModel(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
    )
    session.add(org)
    await session.flush()

    # The creator is immediately granted the 'admin' role
    membership = MembershipModel(
        user_id=user.id,
        org_id=org.id,
        role="admin",
    )
    session.add(membership)
    await session.commit()
    await session.refresh(org)

    logger.info(
        "Created organization",
        extra={"org_id": org.id, "org_slug": org.slug, "founder_user_id": user.id},
    )

    return OrgResponse.model_validate(org)


@router.get("/{slug}", response_model=OrgResponse)
async def get_organization(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> OrgResponse:
    """Fetch organization public profile."""
    org = await _get_org_by_slug(slug, session)
    return OrgResponse.model_validate(org)


@router.get("/{slug}/members", response_model=list[MemberResponse])
async def list_org_members(
    slug: str,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemberResponse]:
    """List members and their roles within the organization."""
    org = await _get_org_by_slug(slug, session)

    # Check caller has at least read role in org
    caller_role = await authz_service.is_org_member(session, user.id, org.slug)
    if not caller_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You are not a member of organization '{slug}'.",
        )

    stmt = (
        select(MembershipModel, UserModel)
        .join(UserModel, MembershipModel.user_id == UserModel.id)
        .where(MembershipModel.org_id == org.id)
    )
    res = await session.execute(stmt)
    rows = res.all()

    members: list[MemberResponse] = []
    for membership, member_user in rows:
        members.append(
            MemberResponse(
                id=membership.id,
                user_id=membership.user_id,
                org_id=membership.org_id,
                role=membership.role,
                created_at=membership.created_at,
                user_name=member_user.name,
                user_orcid=member_user.orcid_id,
            )
        )
    return members


@router.post("/{slug}/members", response_model=MemberResponse)
async def add_or_update_member(
    slug: str,
    payload: AddMemberRequest,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Add or update an organization member's role (admin only)."""
    org = await _get_org_by_slug(slug, session)

    caller_role = await authz_service.is_org_member(session, user.id, org.slug)
    if caller_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required to manage organization members.",
        )

    # Verify target user exists
    user_stmt = select(UserModel).where(UserModel.id == payload.user_id)
    u_res = await session.execute(user_stmt)
    target_user = u_res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{payload.user_id}' not found.",
        )

    # Check existing membership
    mem_stmt = select(MembershipModel).where(
        MembershipModel.org_id == org.id,
        MembershipModel.user_id == payload.user_id,
    )
    mem_res = await session.execute(mem_stmt)
    membership = mem_res.scalar_one_or_none()

    if membership:
        membership.role = payload.role
    else:
        membership = MembershipModel(
            org_id=org.id,
            user_id=payload.user_id,
            role=payload.role,
        )
        session.add(membership)

    await session.commit()
    await session.refresh(membership)

    logger.info(
        "Updated organization member",
        extra={
            "org_slug": org.slug,
            "member_user_id": payload.user_id,
            "role": payload.role,
        },
    )

    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        created_at=membership.created_at,
        user_name=target_user.name,
        user_orcid=target_user.orcid_id,
    )


@router.delete("/{slug}/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    slug: str,
    target_user_id: str,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Remove a member from the organization (admin only)."""
    org = await _get_org_by_slug(slug, session)

    caller_role = await authz_service.is_org_member(session, user.id, org.slug)
    if caller_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required to remove organization members.",
        )

    mem_stmt = select(MembershipModel).where(
        MembershipModel.org_id == org.id,
        MembershipModel.user_id == target_user_id,
    )
    mem_res = await session.execute(mem_stmt)
    membership = mem_res.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{target_user_id}' is not a member of '{slug}'.",
        )

    # Prevent removing the last admin
    if membership.role == "admin":
        count_admins_stmt = select(MembershipModel).where(
            MembershipModel.org_id == org.id, MembershipModel.role == "admin"
        )
        admins = (await session.execute(count_admins_stmt)).scalars().all()
        if len(admins) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the sole administrator of an organization.",
            )

    await session.delete(membership)
    await session.commit()
    logger.info(
        "Removed organization member",
        extra={"org_slug": org.slug, "member_user_id": target_user_id},
    )
