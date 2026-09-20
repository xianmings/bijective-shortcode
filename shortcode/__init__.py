"""bijective-shortcode —— 6 位短码生成的三种方案对比。

核心是 :class:`ModPowPermutation`:用模幂双射把自增 ID 打乱成看似随机的短码,
既拿到自增"零碰撞、天然一一对应"的好处,又拿到 hash"不规则、不可枚举"的好处。

快速上手::

    from shortcode import BijectiveScheme

    scheme = BijectiveScheme()
    scheme.encode(10086)        # 'Zvwkwd' 之类
    scheme.decode('Zvwkwd')     # 回到 10086
"""

from . import base62
from .permutation import (
    ModPowPermutation,
    default_min_gap,
    generate_keys,
    is_prime,
)
from .schemes import (
    DEFAULT_SEED,
    BijectiveScheme,
    HashScheme,
    Scheme,
    SequentialScheme,
)

__all__ = [
    "base62",
    "BijectiveScheme",
    "DEFAULT_SEED",
    "HashScheme",
    "ModPowPermutation",
    "Scheme",
    "SequentialScheme",
    "default_min_gap",
    "generate_keys",
    "is_prime",
]

__version__ = "1.0.0"
