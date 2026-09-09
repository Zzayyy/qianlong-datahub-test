# -*- coding: utf-8 -*-
"""
通用测试数据生成器：根据接口定义生成 Excel 测试数据
====================================================
用法：
  python make_excel.py --interface query       # 生成 data/query.xlsx
  python make_excel.py --interface acc_sign    # 生成 data/acc_sign.xlsx

生成的 Excel 统一放在 data/ 目录。
"""
import argparse
import importlib
import os
import re
import sys
import traceback

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INTERFACES_DIR = os.path.join(BASE_DIR, "interfaces")

# 公共列宽度 + 字段列宽度
META_W = {"case_no": 12, "case_type": 14, "case_desc": 36, "expected": 40}


def load_interface(name):
    sys.path.insert(0, INTERFACES_DIR)
    try:
        mod = importlib.import_module(name)
    except ImportError:
        avail = [f[:-3] for f in os.listdir(INTERFACES_DIR)
                 if f.endswith(".py") and not f.startswith(("__", "_"))]
        sys.exit(f"[FAIL] 接口 {name} 不存在。可用接口: {avail}")
    for attr in ("NAME", "HEADERS", "ROWS"):
        if not hasattr(mod, attr):
            sys.exit(f"[FAIL] 接口 {name} 缺少 {attr} 定义")
    return mod


# ==================== 引用云单号区间（set/modify/remove 专用）====================
def _parse_ref_spec(spec):
    """把 --ref-spec 解析成 (起始序号, 条数)。

    支持两种写法（逗号/横线都不会出现在单号本身，可安全用作分隔）：
      "7,100" / "20260904000001,100"          -> 从第 7 号起共 100 条
      "7-106" / "20260904000001-20260904000100" -> 序号区间
    起始可填完整单号(YYYYMMDD+6位序号)或纯 6 位序号。
    注：日期部分仅用于友好提示；Excel 里实际存 __REFn__ token，
        发送时统一按"发送当天"展开，因此只关注其中的序号。
    """
    s = str(spec).strip()
    if not s:
        raise ValueError("为空")

    def _seq(tok):
        t = tok.strip()
        if re.fullmatch(r"\d{14}", t):
            return int(t[8:])
        if re.fullmatch(r"\d{1,6}", t):
            return int(t)
        raise ValueError(f"无法解析云单号/序号: {tok!r}（应为 YYYYMMDD+6位 或 纯 1~6 位序号）")

    if "-" in s and "," not in s:
        a, b = s.split("-", 1)
        start, end = _seq(a), _seq(b)
        if end < start:
            raise ValueError(f"区间结束号 {end} 小于起始号 {start}")
        return start, end - start + 1
    if "," in s:
        left, cnt = s.split(",", 1)
        try:
            count = int(cnt.strip())
        except ValueError:
            raise ValueError(f"条数解析失败: {cnt!r}")
        if count <= 0:
            raise ValueError(f"条数必须 > 0: {count}")
        return _seq(left), count
    raise ValueError("格式应为 起始[,条数] 或 起始-结束，如 7,100 或 7-106")


def load_ref_map(path):
    """读 send_test 落盘的 create 回填 JSON，转成 {账号: Ref}。"""
    import json
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return {str(r.get("account")): str(r.get("ref"))
            for r in rows if r.get("account") and r.get("ref")}


def apply_ref_map(rows, fa_i, ref_i, refmap):
    """把行内账号对应的真实 Ref（静态完整号）写进 Ref(s) 列；未命中保留原 token。"""
    out = []
    miss = 0
    for r in rows:
        row = list(r)
        acct = str(row[fa_i]) if fa_i is not None else ""
        ref = refmap.get(acct)
        if ref:
            row[ref_i] = ref
        else:
            miss += 1
        out.append(tuple(row))
    if miss:
        print(f"[WARN] {miss} 行账号未在回填映射中，保留原 __REF__ token")
    return out


def build_ref_rows(mod, spec):
    """对 set/modify/remove 按区间生成 normal 引用行（每行引用一个单号）。

    返回生成的完整宽度行列表（元组）。仅当接口有 REF_KEY 且 ROWS 里有 normal 模板行时可用。
    """
    keys = [k for k, _ in mod.HEADERS]
    ref_key = getattr(mod, "REF_KEY", "")
    for need in ("case_no", "case_type", "case_desc"):
        if need not in keys:
            raise ValueError(f"接口 {mod.NAME} 表头缺少 {need} 列，不支持引用区间生成")
    if not ref_key or ref_key not in keys:
        raise ValueError(f"接口 {mod.NAME} 未定义 REF_KEY 或表头无 {ref_key} 列")

    start, count = _parse_ref_spec(spec)
    if start + count - 1 > 999999:
        raise ValueError(f"引用结束序号 {start + count - 1} 超过 6 位上限 999999")

    type_i = keys.index("case_type")
    no_i = keys.index("case_no")
    desc_i = keys.index("case_desc")
    ref_i = keys.index(ref_key)
    mode_i = keys.index("Mode") if "Mode" in keys else None

    template = None
    for r in mod.ROWS:
        if isinstance(r, (list, tuple)) and len(r) == len(keys) and str(r[type_i]) == "normal":
            template = list(r)
            break
    if template is None:
        raise ValueError(f"接口 {mod.NAME} 的 ROWS 中没有 normal 模板行")

    prefix = mod.NAME[0].upper() + "G"     # RG/SG/MG，避免与既有 R001/S001 等编号冲突
    out = []
    for i in range(count):
        seq = start + i
        r = list(template)
        r[no_i] = f"{prefix}{i + 1:04d}"
        r[type_i] = "normal"
        r[desc_i] = f"{mod.NAME} 引用当日第 {seq} 号"
        r[ref_i] = f"__REF{seq}__"
        if mode_i is not None:
            # set：停止/运行交替，操作对象是不同单号
            r[mode_i] = 0 if i % 2 == 0 else 1
        out.append(tuple(r))
    return out


def main():
    ap = argparse.ArgumentParser(description="生成接口测试数据 Excel")
    ap.add_argument("--interface", required=True, help="接口名，如 query / acc_sign")
    ap.add_argument("--ref-spec", default="",
                    help="仅对含云单引用的接口(set/modify/remove)生效：把其 normal 行替换为按单号区间"
                         "生成的引用行（每行引用一个号，便于配合 create 造的批单做压测）。"
                         "格式：起始[,条数]  或  起始-结束；起始可填完整单号(YYYYMMDD+6位)或纯序号"
                         "（日期取发送当天，Excel 存 __REFn__ token）。例：7,100 或 20260904000001-20260904000100")
    ap.add_argument("--bulk-normal", type=int, default=0,
                    help="仅对实现了 build_bulk_rows 的接口(如 acc_sign)生效：把 normal 段替换为"
                         "N 行账号各不相同的正常数据（性能测试真实数据、不循环）。例：--bulk-normal 10000")
    ap.add_argument("--bulk-start", type=int, default=0,
                    help="批量账号起始序号（0=取接口默认，acc_sign 默认 011301 避开已签真实账号）")
    ap.add_argument("--ref-seq", type=int, default=1,
                    help="账号维度批量(set/modify/remove)引用的当天全局起始单号（默认 1；"
                         "Ref 按天全局递增，当日此前已建 ref_seq-1 张时传 ref_seq，"
                         "第 i 行引用 __REF{ref_seq+i}__，与 create 行序对齐）")
    ap.add_argument("--ref-map", default="",
                    help="彻底稳回填：传入 create 返回 Ref 的落盘 JSON（账号→Ref 映射），"
                         "set/modify/remove 批量行的 Ref 用真实单号静态填回，不再依赖顺序假设")
    args = ap.parse_args()

    mod = load_interface(args.interface)

    # ---- 引用单号区间：替换 normal 为按号生成的引用行 ----
    if args.ref_spec:
        try:
            extra = build_ref_rows(mod, args.ref_spec)
        except ValueError as e:
            sys.exit(f"[FAIL] 接口 {mod.NAME} --ref-spec {e}")
        keys = [k for k, _ in mod.HEADERS]
        type_i = keys.index("case_type")
        kept = [r for r in mod.ROWS
                if not (isinstance(r, (list, tuple)) and str(r[type_i]) == "normal")]
        mod.ROWS = list(extra) + list(kept)
        start, count = _parse_ref_spec(args.ref_spec)
        print(f"[OK] {mod.NAME}: normal 段已替换为 {len(extra)} 行，"
              f"引用第 {start}~{start + len(extra) - 1} 号（发送时按当天展开）")

    # ---- 批量正常账号：替换 normal 为 N 行各不相同的账号数据 ----
    if args.bulk_normal:
        if args.ref_spec:
            sys.exit("[FAIL] --ref-spec 与 --bulk-normal 互斥，不能同时使用")
        fn = getattr(mod, "build_bulk_rows", None)
        if not callable(fn):
            sys.exit(f"[FAIL] 接口 {mod.NAME} 未实现 build_bulk_rows(count, start)，不支持 --bulk-normal")
        try:
            # 支持第三参 ref_seq（set/modify/remove 账号维度）；旧接口只有两参会自动回退
            try:
                extra = fn(args.bulk_normal, args.bulk_start, args.ref_seq)
            except TypeError:
                extra = fn(args.bulk_normal, args.bulk_start)
        except Exception as e:
            sys.exit(f"[FAIL] 接口 {mod.NAME} --bulk-normal: {e}")
        keys = [k for k, _ in mod.HEADERS]
        # 彻底稳回填：用 create 实际返回的账号→Ref 覆盖生成的 __REF token
        if args.ref_map:
            ref_key = getattr(mod, "REF_KEY", "")
            if not ref_key or "FAccount" not in keys:
                sys.exit(f"[FAIL] 接口 {mod.NAME} 无 REF_KEY/FAccount，不支持 --ref-map")
            extra = apply_ref_map(extra, keys.index("FAccount"), keys.index(ref_key),
                                  load_ref_map(args.ref_map))
            print(f"[OK] {mod.NAME}: 已用 --ref-map 回填真实 Ref")
        type_i = keys.index("case_type")
        kept = [r for r in mod.ROWS
                if not (isinstance(r, (list, tuple)) and str(r[type_i]) == "normal")]
        mod.ROWS = list(extra) + list(kept)
        print(f"[OK] {mod.NAME}: normal 段已替换为 {len(extra)} 行不同账号"
              + (f"（起始序号 {args.bulk_start}）" if args.bulk_start else ""))

    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, f"{mod.NAME}.xlsx")

    wb = Workbook()
    ws = wb.active
    ws.title = mod.NAME

    # 表头
    for col, (key, zh) in enumerate(mod.HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=f"{zh}\n({key})")
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.fill = PatternFill("solid", fgColor="D9E1F2")

    # 数据（非法字符转义，如控制字符）
    def _sanitize(v):
        if isinstance(v, str) and ILLEGAL_CHARACTERS_RE.search(v):
            return ILLEGAL_CHARACTERS_RE.sub("[_]", v)
        return v

    for r, row in enumerate(mod.ROWS, 2):
        for c, v in enumerate(row, 1):
            ws.cell(row=r, column=c, value=_sanitize(v))

    # 列宽：公共列用 META_W，其余按内容定
    for c, (key, zh) in enumerate(mod.HEADERS, 1):
        if key in META_W:
            w = META_W[key]
        else:
            # 按表头中文长度 + 数据里最大长度估
            maxlen = max(len(str(zh)), *[len(str(r[c - 1])) for r in mod.ROWS])
            w = min(max(12, maxlen + 4), 30)
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"

    # 原子保存，被占用则存 v2
    tmp = out + ".tmp"
    wb.save(tmp)
    try:
        os.replace(tmp, out)
    except PermissionError:
        out2 = os.path.join(DATA_DIR, f"{mod.NAME}_v2.xlsx")
        wb.save(out2)
        print(f"[WARN] {out} 正被占用(Excel 可能已打开)，已保存到 {out2}")
        return
    n = len(mod.ROWS)
    print(f"[OK] 已生成 {out}，共 {n} 条用例")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
