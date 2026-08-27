#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper-collage-animation 产出校验器。
检查创作方案的硬约束：
  - 7 个必需部分齐全（钩子/口播/视觉隐喻/分镜/提示词/制作指引/自检）
  - 分镜表：行数、表头字段（时长/提示词）、时长可解析且总和合理
  - 核心手法：纯色背景、首帧过渡 必须出现
  - 语速匹配：口播字数 vs 总时长（按 4-5 字/秒）
用法： python scripts/validate.py <方案文件.md>
退出码 0 = 通过；非 0 = 有问题。
注：启发式检查，隐喻质量与事实准确性仍需人工复核。
"""
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = ["开场钩子", "口播", "视觉隐喻", "分镜", "提示词", "制作指引", "自检"]
MIN_SHOTS_HARD = 3       # 镜头数硬下限
MIN_SHOTS_SOFT = 5       # 默认 5，低于则提醒
SPECS = 4.5              # 中文口播基准语速 字/秒
SPEED_LOW, SPEED_HIGH = 2.5, 6.5  # 容差区间


def sections(text):
    """按 markdown 标题切分，返回 [(标题, 正文)]。"""
    out = []
    cur_title, buf = None, []
    for line in text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            if cur_title is not None:
                out.append((cur_title, "\n".join(buf)))
            cur_title, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    if cur_title is not None:
        out.append((cur_title, "\n".join(buf)))
    return out


def cjk_count(s):
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/validate.py <方案文件.md>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"✗ 文件不存在: {path}")
        return 2
    text = path.read_text(encoding="utf-8")
    problems, notes = [], []

    secs = sections(text)
    all_titles = " | ".join(t for t, _ in secs)

    # 1. 七部分齐全
    missing = [k for k in REQUIRED_SECTIONS if k not in all_titles]
    if missing:
        problems.append(f"缺少必需部分：{missing}（需含：{REQUIRED_SECTIONS}）")

    # 2. 分镜表
    sb = [(t, b) for t, b in secs if "分镜" in t]
    sb_body = sb[0][1] if sb else ""
    rows = [l for l in sb_body.splitlines() if l.strip().startswith("|")]
    header = rows[0] if rows else ""
    data_rows = [l for l in rows[1:] if not re.match(r"^\|[\s\-|]+\|$", l.strip())]
    if not data_rows:
        problems.append("分镜表无数据行")
    else:
        if "时长" not in header or "提示词" not in header:
            problems.append(f"分镜表表头缺字段（需含 时长、提示词）：{header.strip()}")
        if len(data_rows) < MIN_SHOTS_HARD:
            problems.append(f"镜头数 {len(data_rows)} < {MIN_SHOTS_HARD}，太少")
        elif len(data_rows) < MIN_SHOTS_SOFT:
            notes.append(f"镜头数 {len(data_rows)} 少于默认 5，确认是否为短主题")

    # 3. 时长解析与总和
    durs = []
    for r in data_rows:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:秒|s\b)", r)
        durs.append(float(m.group(1)) if m else None)
    unparsed = sum(1 for d in durs if d is None)
    if unparsed:
        problems.append(f"{unparsed} 行镜头时长无法解析（应为 '8s' 或 '8秒'）")
    total = sum(d for d in durs if d is not None)
    if total and not (15 <= total <= 120):
        notes.append(f"总时长 {total:g}s 超出常规 15-120s，确认是否符合预期")

    # 4. 核心手法：纯色背景 + 首帧过渡（硬约束）
    if "纯色" not in text and ("背景" not in text or "色背景" not in text):
        problems.append("未出现「纯色背景」规范——这是强制核心手法")
    elif "纯色" not in text:
        problems.append("未出现「纯色」字样——每个场景提示词必须带纯色背景规范")
    if "首帧" not in text:
        problems.append("未出现「首帧」过渡设计——每个场景首帧须为纯色背景帧")

    # 5. 语速匹配：口播字数 vs 总时长
    kb = [(t, b) for t, b in secs if "口播" in t]
    if kb and total:
        chars = cjk_count(kb[0][1])
        expect = total * SPECS
        if chars and not (total * SPEED_LOW <= chars <= total * SPEED_HIGH):
            notes.append(
                f"口播 {chars} 字 vs 总时长 {total:g}s（基准 {expect:.0f} 字 @ {SPECS}字/s）——"
                f"{'信息点可能过密' if chars > total * SPEED_HIGH else '信息量可能偏少'}"
            )

    # 6. 一帧一动作（启发式：提示词单元格内出现"并/同时/且"+≥2个动作词）
    multi = 0
    for r in data_rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        prompt_cell = cells[-2] if len(cells) >= 2 else ""
        if re.search(r"同时|并且|一边.{1,12}一边", prompt_cell):
            multi += 1
    if multi:
        problems.append(f"{multi} 条提示词疑似一帧多动作（含'同时/并且'）——应拆帧")

    if problems:
        print("✗ 创作方案校验未通过：")
        for p in problems:
            print(f"  - {p}")
    if notes:
        print("△ 提醒（非阻断）：")
        for n in notes:
            print(f"  - {n}")
    if not problems:
        print(f"✓ 通过：7 部分齐全｜镜头 {len(data_rows)} 个｜总时长 {total:g}s")
        if not notes:
            print("注：启发式通过 ≠ 隐喻质量与事实准确性合格，仍需人工复核。")
        return 0
    print("\n注：启发式检查。隐喻质量与事实准确性仍需人工复核。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
