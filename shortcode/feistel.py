"""Feistel 网络 —— 构造双射置换的另一条路子。

和 :mod:`shortcode.permutation` 里的模幂方案目标完全一样:在 ``[0, N)`` 上造一个
双射,把自增 ID 变成看似随机的短码。区别只在构造方式。

一轮 Feistel 就是一行::

    (L, R)  ->  (R, L XOR F(R, K))

把数据劈成左右两半:新的左半取旧的右半,新的右半取"旧左半异或 F(旧右半, 轮密钥)"。

妙处在于 **F 不需要可逆**。反推:

    (L', R') = (R, L XOR F(R, K))
    R = L'                  <- 新的左半就是旧的右半
    L = R' XOR F(L', K)     <- 用刚还原的 R 算出 F,再异或回去

所以 F 可以是查表、可以是 hash、可以随便写 —— 每一轮都必然是置换。
多跑几轮,整体行为就与随机置换不可区分(Luby-Rackoff:3 轮即可抵抗选择明文,
4 轮抵抗选择密文,这也是本模块强制 ``rounds >= 3`` 的原因)。

**相比模幂方案的两个差别**

- 优势:能作用在**任意大小**的区间上。模幂要求模数是两个素数之积,为了塞进
  62^6 得现找素数,只能用到 99.6% 的码空间;Feistel 通过 cycle walking 做到
  100%。
- 代价:还原要把每一轮倒着跑一遍,没有闭式解。模幂那边 ``x = y^D mod N``
  一步到位。

**关于安全性** —— 和模幂模块一样,这里的参数是按 6 位短码的容量挑的,不是密码学
强度。轮函数用的是 BLAKE2b,但轮数和块宽都不足以抵御有决心的攻击者。真要用于
安全场景,请用经过审查的保格式加密实现(NIST SP 800-38G 的 FF1 / FF3-1)。
"""

from __future__ import annotations

import hashlib
import secrets

from . import base62

__all__ = ["FeistelPermutation", "default_round_fn"]

DEFAULT_ROUNDS = 4
"""默认轮数。Luby-Rackoff 下界是 3,取 4 兼顾选择密文安全性。"""

MIN_ROUNDS = 3
"""低于这个轮数不具备伪随机性,构造期直接拒绝。"""


def default_round_fn(right: int, key: bytes, half_bits: int) -> int:
    """默认轮函数:对右半块做一次带密钥的 BLAKE2b,取低 ``half_bits`` 位。

    刻意选了不可逆的构造 —— 这正是 Feistel 想说明的一点:F 不需要可逆。
    """
    digest = hashlib.blake2b(
        right.to_bytes(8, "big"), key=key[:64], digest_size=16
    ).digest()
    return int.from_bytes(digest, "big") & ((1 << half_bits) - 1)


def _derive_round_keys(key: bytes, rounds: int) -> list[bytes]:
    """从主密钥派生 ``rounds`` 个独立的轮密钥。

    每轮用不同的密钥,否则同一轮的 F 会被重复利用,置换的随机性会明显退化。
    """
    return [
        hashlib.blake2b(key + i.to_bytes(4, "big"), digest_size=16).digest()
        for i in range(rounds)
    ]


def _even_block_bits(capacity: int) -> int:
    """取能容纳 ``capacity`` 个值的最小偶数位宽。

    必须偶数,否则无法劈成等宽的两半。Feistel 只能作用在 2 的幂大小的空间上,
    这正是后面需要 cycle walking 的原因。
    """
    bits = max(2, (capacity - 1).bit_length())
    return bits if bits % 2 == 0 else bits + 1


class FeistelPermutation:
    """``[0, capacity)`` 上的双射置换,基于多轮 Feistel 网络 + cycle walking。

    Feistel 本身作用在 ``[0, 2^block_bits)`` 上。要让它的作用域正好落在
    ``[0, capacity)``,用 cycle walking:算出来的值若越界,就把它再喂回去算一次,
    直到落进区间。这是一个可以证明仍是置换的操作,平均迭代次数量级为
    ``2^block_bits / capacity``(6 位短码下约 1.21)。
    """

    __slots__ = (
        "capacity",
        "block_bits",
        "half_bits",
        "rounds",
        "_half_mask",
        "_block_mask",
        "_keys",
        "_round_fn",
    )

    def __init__(
        self,
        capacity: int,
        key: bytes | int | None = None,
        *,
        rounds: int = DEFAULT_ROUNDS,
        round_fn=None,
    ) -> None:
        if capacity < 4:
            raise ValueError(f"capacity must be at least 4, got {capacity}")
        if rounds < MIN_ROUNDS:
            raise ValueError(
                f"rounds must be >= {MIN_ROUNDS} (Luby-Rackoff bound), got {rounds}"
            )

        if key is None:
            key = secrets.token_bytes(32)
        elif isinstance(key, int):
            if key < 0:
                raise ValueError("key must be non-negative")
            key = key.to_bytes(max(8, (key.bit_length() + 7) // 8), "big")
        if not key:
            raise ValueError("key must not be empty")

        self.capacity = capacity
        self.block_bits = _even_block_bits(capacity)
        self.half_bits = self.block_bits // 2
        self.rounds = rounds
        self._half_mask = (1 << self.half_bits) - 1
        self._block_mask = (1 << self.block_bits) - 1
        self._keys = _derive_round_keys(key, rounds)
        self._round_fn = round_fn or default_round_fn

    @classmethod
    def for_code_length(
        cls,
        length: int = 6,
        *,
        key: bytes | int | None = None,
        rounds: int = DEFAULT_ROUNDS,
        round_fn=None,
    ) -> "FeistelPermutation":
        """构造一个置换,作用域正好是 ``length`` 位 base62 的全部码空间。"""
        return cls(
            base62.capacity(length), key, rounds=rounds, round_fn=round_fn
        )

    @property
    def expected_walk_steps(self) -> float:
        """cycle walking 的期望迭代次数,等于 ``2^block_bits / capacity``。

        Feistel 只能作用在 2 的幂大小的空间上,目标区间 ``capacity`` 通常小于它,
        缺口靠重复计算补齐。这个比值就是平均要算几遍:6 位短码下约 1.21,
        即平均多跑 0.21 遍。

        注意别和"容量利用率"混淆 —— 后者指能发出的码占 ``62^length`` 的比例。
        Feistel 因为可以精确覆盖目标区间,容量利用率是 100%;
        模幂受困于模数必须是两素数之积,只有 99.6%。
        """
        return (1 << self.block_bits) / self.capacity

    def _encrypt_block(self, value: int) -> int:
        """跑完整的一遍 Feistel(不处理越界)。"""
        left = value >> self.half_bits
        right = value & self._half_mask
        for key in self._keys:
            left, right = right, left ^ self._round_fn(right, key, self.half_bits)
        return (left << self.half_bits) | right

    def _decrypt_block(self, value: int) -> int:
        """倒着跑一遍 Feistel —— 这就是"没有闭式解"的含义。"""
        left = value >> self.half_bits
        right = value & self._half_mask
        for key in reversed(self._keys):
            left, right = right ^ self._round_fn(left, key, self.half_bits), left
        return (left << self.half_bits) | right

    def shuffle(self, value: int) -> int:
        """自增 ID -> 短码数值。"""
        if not 0 <= value < self.capacity:
            raise ValueError(f"value {value} out of range [0, {self.capacity})")
        while True:
            value = self._encrypt_block(value)
            if value < self.capacity:
                return value

    def unshuffle(self, value: int) -> int:
        """短码数值 -> 自增 ID。"""
        if not 0 <= value < self.capacity:
            raise ValueError(f"value {value} out of range [0, {self.capacity})")
        while True:
            value = self._decrypt_block(value)
            if value < self.capacity:
                return value

    def __repr__(self) -> str:
        return (
            f"FeistelPermutation(capacity={self.capacity}, "
            f"block={self.block_bits} bits, rounds={self.rounds})"
        )
