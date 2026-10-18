"""密码哈希：标准库 scrypt（内存困难型 KDF），每个密码独立随机盐，不引入额外依赖。

存储格式：scrypt$n$r$p$salt_hex$hash_hex，参数随哈希一起保存，日后可平滑提高强度。
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
    return hmac.compare_digest(digest.hex(), hash_hex)  # 常数时间比较，防计时攻击


# 用户名不存在时也做一次同等开销的校验，避免通过响应时间探测账号是否存在
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
