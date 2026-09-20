"""四种短码生成方案的统一封装,便于横向对比。

四个方案都实现同一个接口 —— ``encode(identifier) -> code``,其中
``identifier`` 是自增 ID。用同一个 ID 空间横向对比,碰撞率、可猜测性这类
指标才可比。

其中 :class:`BijectiveScheme`(模幂)和 :class:`FeistelScheme`(Feistel)属于
同一类:都是先在 ID 上施加一个双射置换再转 base62,零碰撞由构造保证。

真实的短链服务里 hash 方案通常是对长 URL 做 hash 而不是对 ID。这里对 ID 做
hash 是为了让三者输入一致。对 URL 做 hash 会额外获得"同一 URL 天然去重"的
好处,代价是 URL 一变短码就变、旧码无法复用。
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from . import base62
from .feistel import FeistelPermutation
from .permutation import ModPowPermutation

__all__ = [
    "Scheme",
    "SequentialScheme",
    "HashScheme",
    "PermutationScheme",
    "BijectiveScheme",
    "FeistelScheme",
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
"""默认起始偏移。"""


def _default_seed(capacity: int) -> int:
    """按容量缩放起始偏移,最多占掉 1% 的 ID 空间。

    偏移会挤占可用的 ID 范围,固定值在短码位数很少时能把空间挤没
    (2 位码总共才 3844 个位置)。按比例收窄即可。
    """
    return min(DEFAULT_SEED, capacity // 100)


class PermutationScheme:
    """双射置换类方案的公共部分,两个具体实现共用。

    ``seed`` 是施加置换前的偏移,用来把输入推离 0、1 这类退化值 ——
    它们在某些置换下会映射到自己,产出 ``oooooo`` 这种无意义的短码。
    """

    invertible = True
    collision_free = True
    name = ""
    label = ""

    def __init__(self, permutation, length: int = 6, *, seed: int | None = None) -> None:
        self.length = length
        self.permutation = permutation
        self.seed = _default_seed(permutation.capacity) if seed is None else seed
        if not 0 <= self.seed < permutation.capacity:
            raise ValueError(
                f"seed {self.seed} out of range [0, {permutation.capacity})"
            )

    def encode(self, identifier: int) -> str:
        return base62.encode(
            self.permutation.shuffle(identifier + self.seed), self.length
        )

    def decode(self, code: str) -> int:
        return self.permutation.unshuffle(base62.decode(code)) - self.seed


class BijectiveScheme(PermutationScheme):
    """方案三:模幂双射置换。

    先对自增 ID 施加一个双射,再转 base62。双射保证零碰撞(有数学证明,
    不靠重试),置换保证输出无规律(相邻 ID 的短码毫不相干)。

    偏移在这个方案里尤其必要:模幂有两个已知不动点,``x=0`` 和 ``x=1``
    (``1^E`` 恒为 1),不加偏移的话前两个 ID 会直接得到 ``oooooo`` 和
    ``oooooo`` + 第二字符。另外密钥(p、q、E)必须持久化,否则重启后
    历史短码全部失效。
    """

    name = "bijective"
    label = "模幂双射"

    def __init__(self, permutation=None, length: int = 6, *, seed: int | None = None) -> None:
        super().__init__(
            permutation or ModPowPermutation.for_code_length(length), length, seed=seed
        )


class FeistelScheme(PermutationScheme):
    """方案四:Feistel 网络。

    和模幂方案目标完全相同,但作用域可以精确覆盖整个码空间 ——
    容量利用率 100%,模幂受限于"模数必须是两素数之积"只有 99.6%。

    代价是还原要把每一轮倒着跑一遍,没有 ``x = y^D mod N`` 那样的闭式解。
    """

    name = "feistel"
    label = "Feistel 网络"

    def __init__(self, permutation=None, length: int = 6, *, seed: int | None = None) -> None:
        super().__init__(
            permutation or FeistelPermutation.for_code_length(length), length, seed=seed
        )
