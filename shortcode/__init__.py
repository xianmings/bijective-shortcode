"""bijective-shortcode —— 6 位短码生成的四种方案对比。

核心思路是**双射置换**:把自增 ID 打乱成看似随机的短码,既拿到自增"零碰撞、
天然一一对应"的好处,又拿到 hash"不规则、不可枚举"的好处。两种实现:

- :class:`ModPowPermutation` —— 模幂 ``y = x^E mod N``,逆元有闭式解
- :class:`FeistelPermutation` —— 多轮 Feistel 网络,容量利用率 100%

快速上手::

    from shortcode import BijectiveScheme, FeistelScheme

    scheme = BijectiveScheme()      # 或 FeistelScheme()
    code = scheme.encode(10086)     # 例如 't2rtfl'
    scheme.decode(code)             # 回到 10086
"""

from . import base62, feistel, permutation, schemes
from .feistel import FeistelPermutation
from .permutation import (
    ModPowPermutation,
    default_min_gap,
    generate_keys,
    is_prime,
)
from .schemes import (
    DEFAULT_SEED,
    BijectiveScheme,
    FeistelScheme,
    HashScheme,
    PermutationScheme,
    Scheme,
    SequentialScheme,
)

__all__ = [
    "base62",
    "feistel",
    "permutation",
    "schemes",
    "BijectiveScheme",
    "DEFAULT_SEED",
    "FeistelPermutation",
    "FeistelScheme",
    "HashScheme",
    "ModPowPermutation",
    "PermutationScheme",
    "Scheme",
    "SequentialScheme",
    "default_min_gap",
    "generate_keys",
    "is_prime",
]

__version__ = "1.0.0"
