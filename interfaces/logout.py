# -*- coding: utf-8 -*-
"""
接口定义：logout（账号登出）
=================================
字段来源：../请求接口字段.txt 2.2.9
报文：{"logout": {"Account": {...}}}
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, build_account, gen_account_variety, gen_fuzz, gen_cross

NAME = "logout"
TITLE = "账号登出(logout)"

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("expected", "预期结果(备注)"),
]

_BASE = ["", 1, 6, "300130000461"]

ROWS = [
    # 正常
    ["L001", "normal", "张国昌登出", *_BASE, "期望 Err>=0"],
    ["L002", "normal", "客户号登出", "", 7, 7, "12345679", "期望 Err>=0"],
    ["L003", "normal", "其他账号登出", "", 1, 6, "999993", "期望 Err>=0"],
    # 错误
    ["L101", "error", "FAccount 为空", "", 1, 6, "", "期望被拒绝"],
    ["L102", "error", "AccountType 非法99", "", 99, 6, "300130000461", "期望被拒绝"],
    # 破坏
    ["L201", "destroy", "FAccount 超长", "", 1, 6, "__LONG__", "超长账号"],
    ["L202", "destroy", "FAccount 含控制字符", "", 1, 6, "300130000461\x00\x01", "控制字符"],
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "AccountType": [99, -1, "abc", "__MAXINT__", "__HUGE__"],
    "AccAtt": [9, -1, "abc"],
    "FAccount": ["", "__LONG__", "__CTRL__", "__SQL__", "__UNI__", "__EMOJI__", "abc"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__TAB__",
                 "__NEWLINE__", "__RTL__", "__ZWSP__", "__BOM__", "__SQL__", "__XSS__",
                 "__FMT__", "__PATH__", "__EMOJI2__", "__UNICODE__", "__JSON__",
                 "__REPLACE_NULL__", "300130000461\x00\x01"],
    "AccountType": ["__HUGE__", "__SCI__", "__HEX__", "__FLOATINF__", "__FLOATNAN__", "__NEG__"],
    "AccAtt": ["__HUGE__", "__SCI__", "__NEGINT__"],
    "Model": ["__MAXINT__", "__NEGINT__", "__HUGE__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("AccountType", "__HUGE__"), ("AccAtt", 99), ("Model", "__MAXINT__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    return {"logout": {"Account": account}}
