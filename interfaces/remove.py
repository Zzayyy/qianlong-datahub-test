# -*- coding: utf-8 -*-
"""
接口定义：remove（删除云条件单）
=================================
字段来源：../请求接口字段.txt 2.2.8
报文：{"remove": {"Account": {...}, "Refs": ["26319550", ...]}}
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, build_account, gen_account_variety, gen_fuzz, gen_cross

NAME = "remove"
TITLE = "删除云条件单(remove)"

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("Refs", "云单引用数组(逗号分隔)"),
    ("expected", "预期结果(备注)"),
]

_BASE = ["", 1, 6, "300130000461"]

ROWS = [
    # 正常
    ["R001", "normal", "删除一个云单", *_BASE, "26319550", "期望 Err>=0"],
    ["R002", "normal", "删除多个云单", *_BASE, "26319550,26319551", "期望 Err>=0"],
    # 错误
    ["R101", "error", "Refs 为空", *_BASE, "", "期望被拒绝"],
    ["R102", "error", "Refs 含不存在引用", *_BASE, "99999999", "期望 Err<0"],
    # 破坏
    ["R201", "destroy", "Refs 超长", *_BASE, "R" * 1000, "超长引用"],
    ["R202", "destroy", "Refs 含emoji", *_BASE, "__EMOJI__", "emoji引用"],
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "Refs": ["", "__SQL__", "99999999", "__CTRL__", "__EMOJI__", "   "],
    "AccountType": [99, -1, "abc", "__MAXINT__", "__HUGE__"],
    "AccAtt": [9, -1, "abc"],
    "FAccount": ["", "__LONG__", "__CTRL__", "__SQL__"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "Refs": ["__LONG__", "__REFS_MANY__", "__REFS_DUP__", "__REFS_SPACE__", "__REFS_SQL__",
             "__REFS_EMOJI__", "__CTRL__", "__SQL__", "__EMOJI2__"],
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__",
                 "__XSS__", "__EMOJI2__", "__JSON__"],
    "AccountType": ["__HUGE__", "__SCI__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], injects=[
    ("Refs", "__LONG__"), ("Refs", "__REFS_MANY__"), ("Refs", "__SQL__"),
    ("FAccount", "__CTRL__"), ("AccountType", "__HUGE__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    payload = {"remove": {"Account": account}}
    refs = expand(row.get("Refs"))
    if refs is not None and str(refs).strip() != "":
        payload["remove"]["Refs"] = [s.strip() for s in str(refs).split(",") if s.strip()]
    return payload
