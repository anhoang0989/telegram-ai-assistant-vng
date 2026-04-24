from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import UserApproval


async def get(session: AsyncSession, user_id: int) -> UserApproval | None:
    result = await session.execute(select(UserApproval).where(UserApproval.user_id == user_id))
    return result.scalar_one_or_none()


async def create_pending(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    full_name: str | None,
    email_or_domain: str,
) -> UserApproval:
    row = await get(session, user_id)
    if row is None:
        row = UserApproval(
            user_id=user_id,
            username=username,
            full_name=full_name,
            email_or_domain=email_or_domain,
            status="pending",
        )
        session.add(row)
    else:
        row.email_or_domain = email_or_domain
        row.username = username
        row.full_name = full_name
        row.status = "pending"
    await session.commit()
    await session.refresh(row)
    return row


async def set_status(session: AsyncSession, user_id: int, status: str) -> UserApproval | None:
    row = await get(session, user_id)
    if row:
        row.status = status
        await session.commit()
    return row


async def is_approved(session: AsyncSession, user_id: int) -> bool:
    row = await get(session, user_id)
    return row is not None and row.status == "approved"
