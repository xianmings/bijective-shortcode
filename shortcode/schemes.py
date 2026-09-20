"""三种短码生成方案的统一封装,便于横向对比。

三个方案都实现同一个接口 —— ``encode(identifier) -> code``,其中
``identifier`` 是自增 ID。用同一个 ID 空间横向对比,碰撞率、可猜测性这类
指标才可比。

真实的短链服务里 hash 方案通常是对长 URL 做 hash 而不是对 ID。这里对 ID 做
hash 是为了让三者输入一致。对 URL 做 hash 会额外获得"同一 URL 天然去重"的
好处,代价是 URL 一变短码就变、旧码无法复用。
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from . import base62
from .permutation import ModPowPermutation

__all__ = [
    "Scheme",
    "SequentialScheme",
    "HashScheme",
    "BijectiveScheme",
    "DEFAULT_SEED",
]


class Scheme(Protocol):
    """短码方案的公共接口。"""

    name: str
    label: str
    invertible: bool
    collision_free: bool

    def encode(self, identifier: int) -> str: ...


class SequentialScheme:
    """方案一:自增 ID 直接转 base62。

    零碰撞、容量 100% 利用、写入局部性好 —— 但短码可枚举、可预测,
    且会直接暴露业务量。
    """

    name = "sequential"
    label = "自增"
    invertible = True
    collision_free = True

    def __init__(self, length: int = 6) -> None:
        self.length = length

    def encode(self, identifier: int) -> str:
        return base62.encode(identifier, self.length)

    def decode(self, code: str) -> int:
        return base62.decode(code)


class HashScheme:
    """方案二:对 ID 做 hash 后截断到短码空间。

    输出无规律、不可枚举 —— 但 hash 是"射入"而非"射到",碰撞无法避免。
    生产环境必须额外维护一张 ``code -> url`` 的表来做冲突检测和重试,
    这恰恰是双射方案不需要的东西。
    """

    name = "hash"
    label = "hash 截断"
    invertible = False
    collision_free = False

    def __init__(self, length: int = 6, salt: bytes = b"") -> None:
        self.length = length
        self.salt = salt
        self.modulus = base62.capacity(length)

    def encode(self, identifier: int) -> str:
        digest = hashlib.blake2b(
            self.salt + str(identifier).encode(), digest_size=8
        ).digest()
        return base62.encode(int.from_bytes(digest, "big") % self.modulus, self.length)


DEFAULT_SEED = 100_000
"""默认起始偏移。见 :class:`BijectiveScheme` 对不动点的说明。"""


class BijectiveScheme:
    """方案三:模幂双射置换。

    先对自增 ID 施加一个双射,再转 base62。双射保证零碰撞(有数学证明,
    不靠重试),置换保证输出无规律(相邻 ID 的短码毫不相干)。

    ``seed`` 是施加置换前的偏移,默认非零。原因是不动点:满足
    ``x^E mod N == x`` 的 x 会被映射到自己,其中 ``x=0`` 和 ``x=1``
    (``1^E`` 恒为 1)会让前两个 ID 得到 ``hhhhhh``、``hhhhhL`` 这种退化短码。
    ID 从 1 开始发号是常见做法,偏移一下即可绕开。
    """

    name = "bijective"
    label = "模幂双射"
    invertible = True
    collision_free = True

    def __init__(
        self,
        permutation: ModPowPermutation | None = None,
        length: int = 6,
        *,
        seed: int = DEFAULT_SEED,
    ) -> None:
        self.length = length
        self.permutation = permutation or ModPowPermutation.for_code_length(length)
        self.seed = seed

    def encode(self, identifier: int) -> str:
        return base62.encode(self.permutation.shuffle(identifier + self.seed), self.length)

    def decode(self, code: str) -> int:
        return self.permutation.unshuffle(base62.decode(code)) - self.seed
