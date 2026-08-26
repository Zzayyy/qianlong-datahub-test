# -*- coding: utf-8 -*-
"""
接口定义：set（运行/停止云条件单）
=================================
字段来源：../请求接口字段.txt 2.2.7
报文：{"set": {"Account": {...}, "Mode": 1, "Refs": ["26319550", ...]}}
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, build_account, to_typed, gen_account_variety, gen_fuzz, gen_cross

NAME = "set"
TITLE = "运行/停止云条件单(set)"

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("Mode", "云单状态(0停止/1运行)"),
    ("Refs", "云单引用数组(逗号分隔)"),
    ("expected", "预期结果(备注)"),
]

_BASE = ["", 1, 6, "300130000461"]

ROWS = [
    # 正常
    ["S001", "normal", "运行一个云单", *_BASE, 1, "26319550", "期望 Err>=0"],
    ["S002", "normal", "运行多个云单", *_BASE, 1, "26319550,26319551,26319552", "期望 Err>=0"],
    ["S003", "normal", "停止一个云单", *_BASE, 0, "26319550", "期望 Err>=0"],
    # 错误
    ["S101", "error", "Refs 为空", *_BASE, 1, "", "期望被拒绝"],
    ["S102", "error", "Mode 非法99", *_BASE, 99, "26319550", "期望被拒绝"],
    ["S103", "error", "Refs 含不存在引用", *_BASE, 1, "99999999", "期望 Err<0"],
    # 破坏
    ["S201", "destroy", "Refs 超长", *_BASE, 1, "R" * 1000, "超长引用"],
    ["S202", "destroy", "Refs 含控制字符", *_BASE, 1, "26319550\x00\x01", "控制字符"],
    ["S203", "destroy", "Mode 极大值", *_BASE, "__MAXINT__", "26319550", "极大值"],
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "Mode": [99, -1, 0, "abc", "__MAXINT__", "__HUGE__", "__HEX__", "__BOOL_WEIRD__"],
    "Refs": ["", "__SQL__", "99999999", "__CTRL__", "__EMOJI__", "   "],
    "AccountType": [99, -1, "abc", "__MAXINT__", "__HUGE__"],
    "AccAtt": [9, -1, "abc"],
    "FAccount": ["", "__LONG__", "__CTRL__", "__SQL__"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "Refs": ["__LONG__", "__REFS_MANY__", "__REFS_DUP__", "__REFS_SPACE__", "__REFS_SQL__",
             "__REFS_EMOJI__", "__CTRL__", "__SQL__", "__EMOJI2__"],
    "Mode": ["__HUGE__", "__SCI__", "__FLOATINF__", "__FLOATNAN__", "__NEG__"],
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__",
                 "__XSS__", "__EMOJI2__", "__JSON__"],
    "AccountType": ["__HUGE__", "__SCI__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], injects=[
    ("Refs", "__LONG__"), ("Refs", "__REFS_MANY__"), ("Refs", "__SQL__"),
    ("Mode", 99), ("FAccount", "__CTRL__"), ("AccountType", "__HUGE__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    payload = {"set": {"Account": account}}

    mode = expand(row.get("Mode"))
    if mode is not None and str(mode).strip() != "":
        payload["set"]["Mode"] = to_typed("Mode", mode)

    refs = expand(row.get("Refs"))
    if refs is not None and str(refs).strip() != "":
        payload["set"]["Refs"] = [s.strip() for s in str(refs).split(",") if s.strip()]
    return payload
