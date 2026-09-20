"""Base62 编解码:打乱字母表 + 定长输出。

字母表不是标准顺序的 ``0-9a-zA-Z``,而是打乱过的。这样即便两个短码的数值
只差 1,字符层面也看不出任何相邻关系 —— 是"不规则感"的第一层来源。

定长输出用 ``ALPHABET[0]`` 补位(值为 0 的字符),不是字面量 ``'0'``。
这两者在打乱字母表下不是同一个字符,用错会导致解码错位。
"""

from __future__ import annotations

ALPHABET = "oQSCZMzXgrkvi4Pwy7dFGKq9eB1u06OTL38YbasVDEntlHfUAImWJ2cN5pxhRj"
"""打乱后的 62 个字符,索引即数值(0-61)。

这是一次随机洗牌的结果,不是标准顺序的 ``0-9a-zA-Z``。顺序本身可以按部署
自定义:换成任意一个 62 字符的排列都不影响正确性,但换掉之后所有已发出的
短码都会解错,所以它和密钥一样属于需要持久化的配置。
"""

BASE = len(ALPHABET)
"""进制数,固定为 62。"""

_PAD = ALPHABET[0]
"""补位字符,对应数值 0。"""

_INDEX = {char: value for value, char in enumerate(ALPHABET)}
"""反向查表,避免解码时反复扫描字符串。"""


def capacity(length: int) -> int:
    """``length`` 位 base62 能表示的最大容量(不重复的短码个数)。"""
    return BASE**length


def encode(value: int, length: int = 6) -> str:
    """把非负整数编码成定长 base62 字符串。

    值超出 ``length`` 位能表示的范围时抛 ``ValueError``,而不是静默截断 ——
    短码服务里悄悄丢高位是最难排查的一类故障。
    """
    if value < 0:
        raise ValueError(f"value must be non-negative, got {value}")
    if value >= capacity(length):
        raise ValueError(
            f"value {value} does not fit in {length} base62 digits "
            f"(max {capacity(length) - 1})"
        )

    digits = []
    for _ in range(length):
        value, remainder = divmod(value, BASE)
        digits.append(ALPHABET[remainder])
    return "".join(reversed(digits))


def decode(code: str) -> int:
    """把 base62 字符串还原成整数。

    只接受字母表内的字符。非字母表字符直接报错,不做跳过或替换 ——
    短码是外部输入,宽松解析等于把错误推迟到更难定位的地方。
    """
    if not code:
        raise ValueError("code must not be empty")

    value = 0
    for char in code:
        try:
            digit = _INDEX[char]
        except KeyError:
            raise ValueError(f"invalid base62 character: {char!r}") from None
        value = value * BASE + digit
    return value


def is_valid(code: str) -> bool:
    """判断字符串是否是合法的 base62 短码。"""
    return bool(code) and all(char in _INDEX for char in code)
