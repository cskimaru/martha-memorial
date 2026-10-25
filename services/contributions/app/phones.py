import hashlib
import re

_KE = re.compile(r"^254(7|1)\d{8}$")


def normalize_ke_phone(raw: str) -> str | None:
    """Return 2547XXXXXXXX / 2541XXXXXXXX, or None if not a Kenyan mobile number."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    return digits if _KE.match(digits) else None


def mask(phone: str) -> str:
    return f"{phone[:5]}****{phone[-3:]}"


def phone_hash(phone: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}:{phone}".encode()).hexdigest()
