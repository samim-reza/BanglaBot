from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class AdminUser(Base):
    """A platform admin who signs in to the admin console.

    ``role``: superadmin (everything, manages admins) | support | finance.
    ``totp_secret`` is ``enc:<fernet>`` of the base32 secret; 2FA is enforced at
    login once ``totp_enabled``. ``totp_last_step`` refuses a code used twice.
    ``token_version`` is bumped to revoke every session of this admin.
    """

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16), default="support")
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_step: Mapped[int] = mapped_column(BigInteger, default=0)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
