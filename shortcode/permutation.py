"""模幂双射置换 —— 短码生成的核心算法。

算法就是两次模幂::

    y = x^E mod N      生成:自增 ID → 短码数值
    x = y^D mod N      还原:短码数值 → 自增 ID

其中 ``N = p * q``(p、q 为素数),``λ(N) = lcm(p-1, q-1)``,
``D = E^-1 mod λ(N)``(E 关于 λ(N) 的模逆元)。

当 ``gcd(E, λ(N)) = 1`` 时,映射 ``x → x^E mod N`` 是 ``[0, N)`` 上的**双射**:
每个输入恰好对应一个输出,不重不漏。这个性质由数论保证,不需要任何冲突检测
或重试 —— 这正是它相对 hash 截断的根本优势。

同时模幂高度非线性,输入 +1 会让输出在整个 ``[0, N)`` 上无规律跳变,
短码因而看起来杂乱无章、不可枚举。

需要说明的是:这里的 N 只有 36 比特左右,是为了塞进 6 位短码而刻意选小的。
把它当密码学强度使用是错的 —— 这个量级的 N 可以被瞬间分解。它抗的是"枚举
推断"(看到短码猜不出下一个、猜不出总量),不是"暴力破解"。
"""

from __future__ import annotations

import random
from math import gcd, isqrt

from . import base62

__all__ = ["ModPowPermutation", "default_min_gap", "generate_keys", "is_prime"]

# Miller-Rabin 确定性判素的一组底数,对 n < 3.3e24 全部正确。
# 本模块的模数在 1e11 量级,远低于该上限。
_MR_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)

_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def is_prime(n: int) -> bool:
    """Miller-Rabin 确定性判素,对 n < 3.3e24 无误判。"""
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p

    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1

    for a in _MR_BASES:
        if a >= n:
            continue
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _prev_prime(n: int) -> int:
    """返回不超过 n 的最大素数。"""
    if n < 2:
        raise ValueError(f"no prime <= {n}")
    if n == 2:
        return 2
    candidate = n if n % 2 else n - 1
    while candidate >= 3:
        if is_prime(candidate):
            return candidate
        candidate -= 2
    return 2


def _carmichael(p: int, q: int) -> int:
    """λ(N) = lcm(p-1, q-1)。"""
    return (p - 1) * (q - 1) // gcd(p - 1, q - 1)


def _pick_exponent(lam: int, rng: random.Random) -> int:
    """挑一个与 λ(N) 互素的加密指数 E。

    优先用 65537 —— 二进制只有一个"1 加一截零",模幂最快。不满足互素条件时
    再随机找一个奇指数。
    """
    if gcd(65537, lam) == 1:
        return 65537
    while True:
        candidate = rng.randrange(1 << 16, 1 << 17) | 1
        if gcd(candidate, lam) == 1:
            return candidate


def default_min_gap(capacity: int) -> int:
    """默认素数间距,随容量缩放。

    取 ``sqrt(capacity) // 8``:小容量下也能挤得出素数对,同时 p、q 的间距
    与自身量级同阶,远离 Fermat 分解的射程。
    """
    return max(1, isqrt(capacity) // 8)


def generate_keys(
    capacity: int,
    *,
    min_gap: int | None = None,
    rng: random.Random | None = None,
) -> tuple[int, int, int]:
    """生成一组 ``(p, q, E)`` 密钥,使 ``p * q <= capacity`` 且逼近 capacity。

    ``min_gap`` 约束 ``|p - q|`` 的下界,默认由 :func:`default_min_gap` 按容量
    推算。这不是可选项:p、q 若靠得太近,``N`` 可以用 Fermat 分解瞬间破解 ——
    把 ``N`` 写成 ``((p+q)/2)^2 - ((p-q)/2)^2`` 后开方即可。所以取素数时必须
    拉开距离。

    返回的 ``p * q`` 通常能达到 ``capacity`` 的 99% 以上。
    """
    rng = rng or random.SystemRandom()
    if min_gap is None:
        min_gap = default_min_gap(capacity)

    root = isqrt(capacity)
    if root < min_gap * 4:
        raise ValueError(
            f"capacity {capacity} too small for min_gap {min_gap}"
        )

    for _ in range(1000):
        # q 取在 sqrt(capacity) 以下,则 capacity // q 落在 sqrt(capacity) 以上,
        # p、q 天然分居两侧,间距约等于 2 * offset。
        offset = rng.randrange(min_gap, min_gap * 2)
        q = _prev_prime(root - offset)
        p = _prev_prime(capacity // q)

        if p <= 1 or q <= 1 or p == q:
            continue
        if abs(p - q) < min_gap:
            continue
        if p * q > capacity:
            continue
        return p, q, _pick_exponent(_carmichael(p, q), rng)

    raise RuntimeError("key generation failed; try a larger capacity or smaller min_gap")


class ModPowPermutation:
    """``[0, N)`` 上的双射置换,基于模幂。

    构造时校验全部前置条件,任何一条不满足都直接失败 —— 参数错了会让双射
    性质失效,而失效的双射会产生碰撞,是线上最难查的问题,必须在构造期拦掉。
    """

    __slots__ = ("p", "q", "e", "n", "lam", "d")

    def __init__(self, p: int, q: int, e: int) -> None:
        if p == q:
            raise ValueError("p and q must differ")
        if not is_prime(p) or not is_prime(q):
            raise ValueError(
                "p and q must be prime — the bijection proof relies on "
                "λ(N) = lcm(p-1, q-1), which only holds for primes"
            )

        lam = _carmichael(p, q)
        if gcd(e, lam) != 1:
            raise ValueError(
                f"gcd(E, λ(N)) = {gcd(e, lam)} ≠ 1 — x → x^E would not be "
                "a bijection and the codes would collide"
            )

        self.p = p
        self.q = q
        self.e = e
        self.n = p * q
        self.lam = lam
        self.d = pow(e, -1, lam)

    @classmethod
    def for_code_length(
        cls,
        length: int = 6,
        *,
        min_gap: int | None = None,
        rng: random.Random | None = None,
    ) -> "ModPowPermutation":
        """构造一个置换,使输出恰好能装进 ``length`` 位 base62 短码。

        ``min_gap`` 省略时由 :func:`default_min_gap` 按容量推算。
        """
        p, q, e = generate_keys(base62.capacity(length), min_gap=min_gap, rng=rng)
        return cls(p, q, e)

    @property
    def capacity(self) -> int:
        """可用的互不相同的输出个数。"""
        return self.n

    def shuffle(self, value: int) -> int:
        """自增 ID → 短码数值。"""
        if not 0 <= value < self.n:
            raise ValueError(f"value {value} out of range [0, {self.n})")
        return pow(value, self.e, self.n)

    def unshuffle(self, value: int) -> int:
        """短码数值 → 自增 ID。"""
        if not 0 <= value < self.n:
            raise ValueError(f"value {value} out of range [0, {self.n})")
        return pow(value, self.d, self.n)

    def __repr__(self) -> str:
        bits = self.n.bit_length()
        return (
            f"ModPowPermutation(N={self.n}, {bits} bits, "
            f"E={self.e}, D={self.d})"
        )
