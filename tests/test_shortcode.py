"""测试。

两种跑法都支持::

    pytest                            # 装了 pytest 时
    python tests/test_shortcode.py    # 没装 pytest 也能跑

重点覆盖双射性质 —— 它是整个方案的地基,一旦失效短码就会碰撞,
而且这种故障很难在线上定位,必须在测试里用穷举证明。
"""

from __future__ import annotations

import math
import random
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shortcode import (  # noqa: E402
    DEFAULT_SEED,
    BijectiveScheme,
    HashScheme,
    ModPowPermutation,
    SequentialScheme,
    base62,
    generate_keys,
    is_prime,
)

# 小容量便于穷举。62^3 = 238328,全量验证耗时约 1 秒。
EXHAUSTIVE_LENGTH = 3


# --------------------------------------------------------------------------
# base62
# --------------------------------------------------------------------------

def test_alphabet_is_permutation_of_alnum():
    """字母表必须是 62 个字符的完整置换,否则会有数值映射不到。"""
    assert len(base62.ALPHABET) == 62
    assert len(set(base62.ALPHABET)) == 62
    assert sorted(base62.ALPHABET) == sorted(string.digits + string.ascii_letters)


def test_base62_roundtrip_boundaries():
    for length in (1, 4, 6):
        cap = base62.capacity(length)
        for value in sorted({0, 1, min(61, cap - 1), min(62, cap - 1), cap - 1}):
            code = base62.encode(value, length)
            assert len(code) == length
            assert base62.decode(code) == value


def test_base62_pads_with_alphabet_zero_not_literal_zero():
    """补位要用字母表里值为 0 的字符,不能用字面量 '0'。

    打乱字母表后这两者不是同一个字符,用错会让解码错位。
    """
    zero_char = base62.ALPHABET[0]
    assert base62.encode(0, 6) == zero_char * 6
    assert base62.encode(1, 6) == zero_char * 5 + base62.ALPHABET[1]
    assert base62.decode(base62.encode(0, 6)) == 0


def test_base62_rejects_bad_input():
    for bad in ("", "h" * 6 + "!", "中文", "hhhhh "):
        try:
            base62.decode(bad)
        except ValueError:
            continue
        raise AssertionError(f"should have rejected {bad!r}")

    try:
        base62.encode(-1)
    except ValueError:
        pass
    else:
        raise AssertionError("should have rejected negative value")

    try:
        base62.encode(base62.capacity(6))
    except ValueError:
        pass
    else:
        raise AssertionError("should have rejected overflow")


# --------------------------------------------------------------------------
# 模幂双射
# --------------------------------------------------------------------------

def test_permutation_rejects_composite_modulus():
    try:
        ModPowPermutation(5, 8, 3)
    except ValueError as exc:
        assert "prime" in str(exc)
    else:
        raise AssertionError("composite q should be rejected")


def test_permutation_rejects_bad_exponent():
    """gcd(E, λ) != 1 时必须拒绝构造。

    这是最容易踩的坑:参数看起来没问题,但双射性质已经失效,产出的短码
    会静默碰撞。
    """
    p, q = 237821, 237901
    lam = (p - 1) * (q - 1) // math.gcd(p - 1, q - 1)
    bad_e = 3
    assert math.gcd(bad_e, lam) != 1, "test fixture assumption broken"
    try:
        ModPowPermutation(p, q, bad_e)
    except ValueError as exc:
        assert "bijection" in str(exc)
    else:
        raise AssertionError("non-coprime E should be rejected")


def test_permutation_is_bijective_exhaustively():
    """穷举小容量,证明每个输入都映射到唯一输出且不重不漏。"""
    perm = ModPowPermutation.for_code_length(EXHAUSTIVE_LENGTH, rng=random.Random(7))
    outputs = {perm.shuffle(x) for x in range(perm.capacity)}
    assert len(outputs) == perm.capacity
    assert outputs == set(range(perm.capacity))


def test_permutation_roundtrip_exhaustively():
    perm = ModPowPermutation.for_code_length(EXHAUSTIVE_LENGTH, rng=random.Random(7))
    assert all(perm.unshuffle(perm.shuffle(x)) == x for x in range(perm.capacity))


def test_permutation_roundtrip_at_real_size():
    perm = ModPowPermutation.for_code_length(6, rng=random.Random(42))
    rng = random.Random(42)
    for _ in range(5000):
        x = rng.randrange(perm.capacity)
        assert perm.unshuffle(perm.shuffle(x)) == x


def test_permutation_rejects_out_of_range():
    perm = ModPowPermutation.for_code_length(EXHAUSTIVE_LENGTH, rng=random.Random(7))
    for bad in (-1, perm.capacity, perm.capacity + 1):
        try:
            perm.shuffle(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"should have rejected {bad}")


# --------------------------------------------------------------------------
# 密钥生成
# --------------------------------------------------------------------------

def test_generate_keys_invariants():
    for length in (3, 6):
        capacity = base62.capacity(length)
        p, q, e = generate_keys(capacity, rng=random.Random(1))
        lam = (p - 1) * (q - 1) // math.gcd(p - 1, q - 1)

        assert is_prime(p) and is_prime(q)
        assert p != q
        assert p * q <= capacity
        assert math.gcd(e, lam) == 1


def test_generate_keys_keeps_primes_far_apart():
    """p、q 必须拉开距离,否则 N 能被 Fermat 分解秒破。

    原始实现用 ``p.nextProbablePrime()`` 取相邻素数,|p-q| 极小,
    ``N = ((p+q)/2)^2 - ((p-q)/2)^2`` 一开方就出结果。
    """
    capacity = base62.capacity(6)
    p, q, _ = generate_keys(capacity, min_gap=1 << 14, rng=random.Random(2))
    assert abs(p - q) >= (1 << 14)


def test_generate_keys_scales_gap_to_capacity():
    """不传 min_gap 时,小容量也必须能生成密钥。

    间距若写死成常量,容量小的短码长度会直接构造失败 —— 默认值必须随容量缩放。
    """
    for length in (1, 2, 3, 4, 6):
        capacity = base62.capacity(length)
        p, q, e = generate_keys(capacity, rng=random.Random(5))
        assert p * q <= capacity
        assert p != q
        assert is_prime(p) and is_prime(q)


def test_generate_keys_utilizes_capacity():
    for length in (3, 4, 6):
        capacity = base62.capacity(length)
        p, q, _ = generate_keys(capacity, rng=random.Random(3))
        assert p * q > capacity * 0.99, f"length {length} wasted too much space"


def test_is_prime_basics():
    assert not is_prime(0) and not is_prime(1)
    assert is_prime(2) and is_prime(3)
    assert not is_prime(4) and not is_prime(9)
    assert is_prime(237821) and is_prime(237901)
    assert not is_prime(237821 * 237901)


# --------------------------------------------------------------------------
# 三种方案
# --------------------------------------------------------------------------

def _schemes(length: int = 6) -> list:
    return [
        SequentialScheme(length),
        HashScheme(length),
        BijectiveScheme(
            ModPowPermutation.for_code_length(length, rng=random.Random(11)), length
        ),
    ]


def test_all_schemes_emit_fixed_length_codes():
    count = 2000
    for scheme in _schemes():
        for i in range(count):
            code = scheme.encode(i)
            assert len(code) == 6, f"{scheme.name} emitted {code!r}"
            assert base62.is_valid(code)


def test_sequential_and_bijective_never_collide():
    """自增和双射在各自容量内都不该产生碰撞。"""
    count = 5000
    for scheme in _schemes():
        if not scheme.collision_free:
            continue
        codes = [scheme.encode(i) for i in range(count)]
        assert len(set(codes)) == count, f"{scheme.name} collided"


def test_hash_scheme_does_collide():
    """hash 必然碰撞 —— 这不是实现缺陷,是"射入"而非"射到"的数学后果。

    用小空间把碰撞压到可观测规模:62^4 空间投喂 5 万个 ID,
    生日碰撞期望值约 85 个。
    """
    scheme = HashScheme(length=4)
    codes = [scheme.encode(i) for i in range(50_000)]
    assert len(set(codes)) < len(codes), "hash should collide at this scale"


def test_bijective_scheme_roundtrip():
    scheme = BijectiveScheme(
        ModPowPermutation.for_code_length(6, rng=random.Random(11)), 6
    )
    for i in (0, 1, 2, 999, 123456, 50_000_000):
        assert scheme.decode(scheme.encode(i)) == i


def test_default_seed_avoids_degenerate_codes():
    """默认偏移要绕开 0、1 这两个不动点。

    不动点 ``x^E mod N == x`` 会让短码退化成全补位字符,或只差最后一位。
    """
    scheme = BijectiveScheme()
    degenerate = {base62.encode(0, 6), base62.encode(1, 6)}
    for i in range(0, 1000):
        assert scheme.encode(i) not in degenerate, f"id {i} hit a fixed point"


def test_bijective_output_looks_unrelated_for_neighbours():
    """相邻 ID 的短码数值要在整个空间里跳,不能有可推断的规律。

    自增方案的差值恒为 1,是可以逐位枚举的。
    """
    length = 3
    capacity = base62.capacity(length)

    sequential = SequentialScheme(length)
    seq_delta = base62.decode(sequential.encode(1001)) - base62.decode(sequential.encode(1000))
    assert seq_delta == 1

    bijective = BijectiveScheme(
        ModPowPermutation.for_code_length(length, rng=random.Random(11)), length
    )
    deltas = [
        abs(
            base62.decode(bijective.encode(i + 1001))
            - base62.decode(bijective.encode(i + 1000))
        )
        for i in range(50)
    ]
    assert all(delta != 1 for delta in deltas)
    assert max(deltas) > capacity * 0.1


def test_sequential_leaks_business_volume_bijective_does_not():
    """抓到两个短码相减,自增方案会直接泄漏记录数。"""
    length = 6
    sequential = SequentialScheme(length)
    assert (
        base62.decode(sequential.encode(2000)) - base62.decode(sequential.encode(1000))
        == 1000
    )

    bijective = BijectiveScheme(
        ModPowPermutation.for_code_length(length, rng=random.Random(11)), length
    )
    gap = abs(
        base62.decode(bijective.encode(2000)) - base62.decode(bijective.encode(1000))
    )
    assert gap != 1000
    assert gap > 1_000_000


def test_default_seed_constant_is_used():
    """默认偏移取自常量,改了要能被测试发现。"""
    assert BijectiveScheme().seed == DEFAULT_SEED
    assert DEFAULT_SEED != 0


def _run_all() -> int:
    tests = sorted(
        (name, obj)
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    )
    failures = []
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - 报告全部失败,不中断
            failures.append((name, exc))
            print(f"FAIL  {name}")
            print(f"      {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {name}")

    print()
    print(f"{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
