"""Password hashing: standard-library scrypt (memory-hard KDF) with a random salt per password, no
extra dependencies.

Stored as scrypt$n$r$p$salt_hex$hash_hex; parameters are saved with the hash so strength can be
raised later.
"""

import hashlib
import hmac
import secrets

N, R, P, DKLEN = 2**14, 8, 1, 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex)),
        )
    except (ValueError, TypeError):
        return False
    # constant-time comparison against timing attacks
    return hmac.compare_digest(digest.hex(), hash_hex)


# Do an equally expensive check for unknown usernames, so response times can't reveal whether an
# account exists
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
