"""
CRUD encrypted user API keys. Uses Fernet symmetric encryption.
ENCRYPTION_KEY env var must be a valid Fernet key (generate via `Fernet.generate_key()`).
"""
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.db.models import UserApiKey

_fernet = Fernet(settings.encryption_key.encode())


def _encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


async def get(session: AsyncSession, user_id: int) -> UserApiKey | None:
    result = await session.execute(select(UserApiKey).where(UserApiKey.user_id == user_id))
    return result.scalar_one_or_none()


async def get_decrypted_keys(
    session: AsyncSession, user_id: int
) -> tuple[str | None, str | None, str | None]:
    """Returns (gemini_key, groq_key, claude_key) plaintext, None nếu chưa có."""
    row = await get(session, user_id)
    if row is None:
        return None, None, None
    gemini = _decrypt(row.gemini_key_encrypted) if row.gemini_key_encrypted else None
    groq = _decrypt(row.groq_key_encrypted) if row.groq_key_encrypted else None
    claude = _decrypt(row.claude_key_encrypted) if row.claude_key_encrypted else None
    return gemini, groq, claude


async def set_keys(
    session: AsyncSession,
    user_id: int,
    gemini_key: str | None = None,
    groq_key: str | None = None,
    claude_key: str | None = None,
) -> None:
    """Upsert. Passing None leaves that field unchanged; to clear, use remove()."""
    row = await get(session, user_id)
    if row is None:
        row = UserApiKey(
            user_id=user_id,
            gemini_key_encrypted=_encrypt(gemini_key) if gemini_key else None,
            groq_key_encrypted=_encrypt(groq_key) if groq_key else None,
            claude_key_encrypted=_encrypt(claude_key) if claude_key else None,
        )
        session.add(row)
    else:
        if gemini_key is not None:
            row.gemini_key_encrypted = _encrypt(gemini_key)
        if groq_key is not None:
            row.groq_key_encrypted = _encrypt(groq_key)
        if claude_key is not None:
            row.claude_key_encrypted = _encrypt(claude_key)
    await session.commit()


async def remove(session: AsyncSession, user_id: int) -> bool:
    row = await get(session, user_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True
