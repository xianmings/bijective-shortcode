"""四种短码生成方案的横向对比演示。

运行::

    python demo.py

四个方案跑同一批自增 ID,对比出码形态、碰撞数、可猜测性和耗时。
"""

from __future__ import annotations

import random
import sys
import time

from shortcode import (
    BijectiveScheme,
    FeistelPermutation,
    FeistelScheme,
    HashScheme,
    ModPowPermutation,
    SequentialScheme,
    base62,
)

SEED = 20240428
SAMPLE_SIZE = 1_000_000
SMALL_LENGTH = 4
SMALL_SAMPLE = 200_000
PERF_SIZE = 200_000


def _configure_stdout() -> None:
    """把标准输出切到 UTF-8。

    Windows 上输出被重定向到管道或文件时,Python 会退回本地编码(简体中文
    环境是 GBK),遇到 GBK 装不下的字符会直接抛 UnicodeEncodeError 中断脚本。
    ``errors="replace"`` 保证即使切换失败也不会崩。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def _display_width(text: str) -> int:
    """终端显示宽度,中日韩字符按 2 列算。"""
    return sum(2 if ord(char) > 0x2E80 else 1 for char in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def section(title: str) -> None:
    print()
    print("=" * 76)
    print(title)
    print("=" * 76)


def build_schemes(length: int = 6) -> list:
    """四个方案,同一个 ID 空间、同一组固定密钥(结果可复现)。"""
    modpow = ModPowPermutation.for_code_length(length, rng=random.Random(SEED))
    feistel = FeistelPermutation.for_code_length(length, key=str(SEED).encode())
    return [
        SequentialScheme(length),
        HashScheme(length),
        BijectiveScheme(modpow, length),
        FeistelScheme(feistel, length),
    ]


def part1_code_shape() -> None:
    section("1. 同一批 ID,四种方案出码形态")
    schemes = build_schemes()
    width = 14

    header = "  " + pad("ID", 8) + "".join(pad(s.label, width) for s in schemes)
    print(header)
    print("  " + "-" * (8 + width * len(schemes)))

    for identifier in range(1, 13):
        row = "  " + pad(str(identifier), 8)
        row += "".join(pad(s.encode(identifier), width) for s in schemes)
        print(row)

    pad_char = base62.ALPHABET[0]
    print()
    print("  自增列的短码是连续递增的;另外三列毫无规律 ——")
    print("  ID 只差 1,短码在 62^6 的空间里随机跳。")
    print()
    print(f"  两个双射列都没出现 {pad_char * 6} 这种退化短码:0 和 1 是模幂置换的")
    print("  不动点(1^E 恒等于 1),默认偏移把它们绕开了。")


def count_collisions(scheme, count: int, start: int = 1) -> int:
    seen: set[str] = set()
    collisions = 0
    for identifier in range(start, start + count):
        code = scheme.encode(identifier)
        if code in seen:
            collisions += 1
        else:
            seen.add(code)
    return collisions


def part2_collisions() -> None:
    section("2. 碰撞实测")
    space_small = base62.capacity(SMALL_LENGTH)
    space_big = base62.capacity(6)

    print(f"  2a. 小空间对照({SMALL_LENGTH} 位码,容量 {space_small:,},"
          f"投喂 {SMALL_SAMPLE:,} 个 ID)")
    print("      用小空间是为了让 hash 的碰撞在可观测的规模内暴露出来。")
    print()
    for scheme in build_schemes(SMALL_LENGTH):
        hits = count_collisions(scheme, SMALL_SAMPLE)
        print(f"      {pad(scheme.label, 14)} 碰撞 {hits:>7,} 个")

    print()
    print(f"  2b. 真实规模(6 位码,容量 {space_big:,},投喂 {SAMPLE_SIZE:,} 个 ID)")
    print()
    for scheme in build_schemes(6):
        hits = count_collisions(scheme, SAMPLE_SIZE)
        print(f"      {pad(scheme.label, 14)} 碰撞 {hits:>7,} 个")

    print()
    print("  自增和两个双射方案的碰撞数恒为 0 —— 自增显然,双射由构造保证,")
    print("  是数学结论而不是实测结果。hash 的碰撞无法消除,只能靠额外存表去重试。")


def part3_guessability() -> None:
    section("3. 可猜测性:拿到一个短码能推出什么")
    schemes = build_schemes()
    anchor = 1000

    print(f"  以 ID={anchor} 为锚点,看相邻 ID 的短码在这 62^6 空间里跳多远:")
    print()
    for scheme in schemes:
        current = base62.decode(scheme.encode(anchor))
        following = base62.decode(scheme.encode(anchor + 1))
        delta = abs(following - current)
        print(f"      {pad(scheme.label, 14)} 数值差 {delta:>14,}")

    print()
    print("  自增方案的差值恒为 1:拿到任意一个短码,把它 +1 就能拿到下一条记录的短码,")
    print("  一路试下去即可爬完整个站点。另外三个方案的差值在数十亿量级且毫无规律,")
    print("  无法这样推断。")

    print()
    print("  业务量泄漏:抓到两个短码,相减能读出什么?")
    print()
    for scheme in schemes:
        low = base62.decode(scheme.encode(1000))
        high = base62.decode(scheme.encode(2000))
        gap = abs(high - low)
        note = " <- 直接读出两者相差 1000 条记录" if scheme.name == "sequential" else ""
        print(f"      {pad(scheme.label, 14)} 差 {gap:>14,}  {note}")


def part4_roundtrip() -> None:
    section("4. 可逆性:短码能否还原成 ID")
    schemes = build_schemes()
    probes = [1, 2, 999, 1000, 123456, 50_000_000]

    for scheme in schemes:
        if not scheme.invertible:
            print(f"  {pad(scheme.label, 14)} 不可逆 —— hash 是单向的,"
                  "要还原必须查 code->url 映射表")
            continue
        ok = all(scheme.decode(scheme.encode(i)) == i for i in probes)
        detail = ", ".join(f"{i}->{scheme.encode(i)}->{scheme.decode(scheme.encode(i))}"
                           for i in probes[:3])
        print(f"  {pad(scheme.label, 14)} 可逆({ok})   {detail}")

    print()
    print("  两个双射方案的还原都不需要存储。区别在实现方式:")
    print("    模幂    —— 再算一次模幂,x = y^D mod N,D 提前算好")
    print("    Feistel —— 把每一轮倒着跑一遍,没有闭式解")


def part5_performance() -> None:
    section("5. 生成耗时")
    schemes = build_schemes()

    for scheme in schemes:
        start = time.perf_counter()
        for identifier in range(PERF_SIZE):
            scheme.encode(identifier)
        elapsed = time.perf_counter() - start
        rate = PERF_SIZE / elapsed
        print(f"      {pad(scheme.label, 14)} {elapsed * 1000:>8.1f} ms  "
              f"({rate:,.0f} 次/秒)")

    print()
    print("  两个双射方案都慢于自增和 hash —— 每个 ID 都要做一次置换运算。")
    print("  但这个量级对短链场景完全够用:短码只在创建时生成一次,后续命中走缓存。")


def part6_two_bijections() -> None:
    section("6. 两种双射实现的取舍")
    modpow = ModPowPermutation.for_code_length(6, rng=random.Random(SEED))
    feistel = FeistelPermutation.for_code_length(6, key=str(SEED).encode())
    space = base62.capacity(6)

    print(f"  6 位 base62 的码空间: {space:,}")
    print()
    print(f"  {pad('模幂', 14)} 可用 {modpow.capacity:>16,}  "
          f"({modpow.capacity / space:.4%} of 码空间)")
    print(f"  {pad('Feistel', 14)} 可用 {feistel.capacity:>16,}  "
          f"({feistel.capacity / space:.4%} of 码空间)")
    print()
    print(f"  模幂浪费了 {space - modpow.capacity:,} 个码位。原因:模数必须是两个素数")
    print("  之积,为了塞进 62^6 只能取比它小的素数对。Feistel 按位宽工作,不受此限。")

    print()
    print(f"  Feistel 的 cycle walking 期望迭代: {feistel.expected_walk_steps:.4f} 次")
    print(f"  (位宽 {feistel.block_bits} 位 -> 空间 {1 << feistel.block_bits:,},")
    print(f"   比目标区间大,平均多跑 {feistel.expected_walk_steps - 1:.4f} 遍补上缺口)")
    print()
    print(f"  轮数与块宽: {feistel.rounds} 轮 / {feistel.block_bits} 位 / "
          f"半块 {feistel.half_bits} 位")
    print("  轮数下界是 3(Luby-Rackoff),低于此不具备伪随机性,构造期会拒绝。")

    waste = 1 - modpow.capacity / space
    print()
    print("  选哪个:")
    print("    要容量吃满、能接受还原多跑一遍        -> Feistel")
    print(f"    要还原一步到位、能接受 {waste:.4%} 浪费 -> 模幂")


def main() -> None:
    _configure_stdout()
    print("bijective-shortcode —— 短码生成方案对比")
    print(f"随机种子 {SEED},结果可复现")

    part1_code_shape()
    part2_collisions()
    part3_guessability()
    part4_roundtrip()
    part5_performance()
    part6_two_bijections()

    section("结论")
    print("  自增      :零碰撞、容量满、快 —— 但可枚举、暴露业务量")
    print("  hash 截断 :不可枚举 —— 但碰撞无法消除,且不可逆,要额外存表")
    print("  模幂双射  :零碰撞(数学保证)+ 不可枚举 + 还原一步到位")
    print("  Feistel   :零碰撞(数学保证)+ 不可枚举 + 容量利用率 100%")
    print()
    print("  后两者把自增的'不重不漏'和 hash 的'杂乱无章'合到了一起,")
    print("  区别只在置换怎么构造。")


if __name__ == "__main__":
    main()
