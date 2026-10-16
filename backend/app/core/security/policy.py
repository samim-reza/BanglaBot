"""Password policy for every password a person sets (owners, admins, admin-set owner passwords)."""

from __future__ import annotations

MIN_LENGTH = 10
MAX_LENGTH = 200

#: Passwords that pass the length rule but top every breach list.
COMMON_PASSWORDS = frozenset(
    {
        "1234567890", "12345678910", "0123456789", "1111111111", "0000000000", "9876543210",
        "password1", "password12", "password123", "password1234", "password!", "password@123",
        "passw0rd123", "p@ssw0rd123", "qwertyuiop", "qwerty1234", "qwerty12345", "1q2w3e4r5t",
        "1qaz2wsx3edc", "asdfghjkl1", "zxcvbnm123", "iloveyou12", "iloveyou123", "letmein123",
        "welcome123", "welcome@123", "admin12345", "admin@1234", "admin@12345", "administrator",
        "changeme123", "changeme!!", "football123", "baseball123", "monkey12345", "dragon12345",
        "sunshine123", "princess123", "abc1234567", "abcdefghij", "abcd123456", "aa12345678",
        "bangladesh", "bangladesh1", "bangladesh123", "dhaka12345", "banglabot123", "callisa123", "callisa1234",
    }
)


class PasswordPolicyError(ValueError):
    """The password breaks the policy; the message is safe to show the user."""


def validate_new_password(password: str, *, username: str = "", email: str = "") -> None:
    value = str(password or "")
    if len(value) < MIN_LENGTH:
        raise PasswordPolicyError(f"Use at least {MIN_LENGTH} characters")
    if len(value) > MAX_LENGTH:
        raise PasswordPolicyError(f"Use at most {MAX_LENGTH} characters")
    lowered = value.strip().lower()
    identities = {str(username or "").strip().lower(), str(email or "").strip().lower()}
    if "@" in str(email or ""):
        identities.add(str(email).split("@", 1)[0].strip().lower())
    if lowered in {item for item in identities if item}:
        raise PasswordPolicyError("The password can't be your username or email")
    if lowered in COMMON_PASSWORDS or len(set(lowered)) <= 2:
        raise PasswordPolicyError("That password is too common — choose another")


def is_weak(password: str, *, username: str = "") -> bool:
    try:
        validate_new_password(password, username=username)
    except PasswordPolicyError:
        return True
    return False


__all__ = ["COMMON_PASSWORDS", "MIN_LENGTH", "PasswordPolicyError", "is_weak", "validate_new_password"]
