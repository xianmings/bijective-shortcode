"""三种短码生成方案的横向对比演示。

运行::

    python demo.py

三个方案跑同一批自增 ID,对比出码形态、碰撞数、可猜测性和耗时。
"""

from __future__ import annotations

import random
import sys
import time

from shortcode import BijectiveScheme, HashScheme, ModPowPermutation, SequentialScheme, base62

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
    print("=" * 72)
    print(title)
    print("=" * 72)


def build_schemes(length: int = 6) -> list:
    """三个方案,同一个 ID 空间。"""
    permutation = ModPowPermutation.for_code_length(length, rng=random.Random(SEED))
    return [
        SequentialScheme(length),
        HashScheme(length),
        BijectiveScheme(permutation, length),
    ]


def part1_code_shape() -> None:
    section("1. 同一批 ID,三种方案出码形态")
    schemes = build_schemes()
    width = 14

    header = "  " + pad("ID", 8) + "".join(pad(s.label, width) for s in schemes)
    print(header)
    print("  " + "-" * (8 + width * len(schemes)))

    for identifier in range(1, 13):
        row = "  " + pad(str(identifier), 8)
        row += "".join(pad(s.encode(identifier), width) for s in schemes)
        print(row)

    print()
    print("  自增列的短码是连续递增的;另外两列毫无规律 ——")
    print("  ID 只差 1,短码在 62^6 的空间里随机跳。")
    print()
    print("  注意双射列没有出现 hhhhhh / hhhhhL:0 和 1 是置换的不动点")
    print("  (1^E 恒等于 1),BijectiveScheme 默认带一个偏移把它们绕开了。")


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
        print(f"      {pad(scheme.label, 12)} 碰撞 {hits:>7,} 个")

    print()
    print(f"  2b. 真实规模(6 位码,容量 {space_big:,},投喂 {SAMPLE_SIZE:,} 个 ID)")
    print()
    for scheme in build_schemes(6):
        hits = count_collisions(scheme, SAMPLE_SIZE)
        print(f"      {pad(scheme.label, 12)} 碰撞 {hits:>7,} 个")

    print()
    print("  自增和模幂双射的碰撞数恒为 0 —— 前者显然,后者由双射性质保证,")
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
        print(f"      {pad(scheme.label, 12)} 数值差 {delta:>14,}")

    print()
    print("  自增方案的差值恒为 1:拿到任意一个短码,把它 +1 就能拿到下一条记录的短码,")
    print("  从 aaaaaa 一路试到 aaaaaZ 即可爬完整个站点。另外两个方案的差值在数十亿")
    print("  量级且毫无规律,无法这样推断。")

    print()
    print("  业务量泄漏:抓到两个短码,相减能读出什么?")
    print()
    for scheme in schemes:
        low = base62.decode(scheme.encode(1000))
        high = base62.decode(scheme.encode(2000))
        gap = abs(high - low)
        note = "← 直接读出两者相差 1000 条记录" if scheme.name == "sequential" else ""
        print(f"      {pad(scheme.label, 12)} 差 {gap:>14,}  {note}")


def part4_roundtrip() -> None:
    section("4. 可逆性:短码能否还原成 ID")
    schemes = build_schemes()
    probes = [1, 2, 999, 1000, 123456, 50_000_000]

    for scheme in schemes:
        if not scheme.invertible:
            print(f"  {pad(scheme.label, 12)} 不可逆 —— hash 是单向的,"
                  "要还原必须查 code→url 映射表")
            continue
        ok = all(scheme.decode(scheme.encode(i)) == i for i in probes)
        detail = ", ".join(f"{i}->{scheme.encode(i)}->{scheme.decode(scheme.encode(i))}"
                           for i in probes[:3])
        print(f"  {pad(scheme.label, 12)} 可逆({ok})   {detail}")

    print()
    print("  模幂双射的还原靠 D = E^-1 mod λ(N),不需要任何存储 ——")
    print("  这是它比 hash 方案少维护一张表的关键。")


def part5_performance() -> None:
    section("5. 生成耗时")
    schemes = build_schemes()

    for scheme in schemes:
        start = time.perf_counter()
        for identifier in range(PERF_SIZE):
            scheme.encode(identifier)
        elapsed = time.perf_counter() - start
        rate = PERF_SIZE / elapsed
        print(f"      {pad(scheme.label, 12)} {elapsed * 1000:>8.1f} ms  "
              f"({rate:,.0f} 次/秒)")

    print()
    print("  模幂比另两者慢 —— 每个 ID 要做一次模幂运算。但这个量级")
    print("  (每秒数十万次)对短链场景完全够用,而且短码只在创建时生成一次,")
    print("  后续命中都走缓存。")


def main() -> None:
    _configure_stdout()
    print("bijective-shortcode —— 短码生成方案对比")
    print(f"随机种子 {SEED},结果可复现")

    part1_code_shape()
    part2_collisions()
    part3_guessability()
    part4_roundtrip()
    part5_performance()

    section("结论")
    print("  自增      :零碰撞、容量满、快 —— 但可枚举、暴露业务量")
    print("  hash 截断 :不可枚举 —— 但碰撞无法消除,且不可逆,要额外存表")
    print("  模幂双射  :零碰撞(数学保证)+ 不可枚举 + 可逆且无需存表")
    print()
    print("  它把自增的'不重不漏'和 hash 的'杂乱无章'合到了一起。")


if __name__ == "__main__":
    main()
