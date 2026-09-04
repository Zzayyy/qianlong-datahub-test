# -*- coding: utf-8 -*-
"""
接口定义：logout（账号登出）
=================================
字段来源：../请求接口字段.txt 2.2.9

真实 logout 报文：
  {"logout": {"Account": {"Model": 0, "AccountType": 7, "AccAtt": 6,
                          "FAccount": "010100011300"}}}

2026-09 更新：原来用的 300130000461 / 12345679 均为占位账号，线上登出不了。
现统一改用线上真实账号（_common.REAL_ACCOUNT，与 acc_sign.py 一致）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, build_account, REAL_ACCOUNT,
                     STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL,
                     gen_account_variety, gen_fuzz, gen_cross)

NAME = "logout"
TITLE = "账号登出(logout)"

FACCOUNT = REAL_ACCOUNT["FAccount"]

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/probe/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("expected", "预期结果(备注)"),
]

# ==================== 测试数据（全部基于真实账号，只改被测字段）====================
ROWS = [
    # ---------- normal：压测池（账号四要素与真实账号完全匹配）----------
    ["L001", "normal", "正确账号 登出", 0, 7, 6, FACCOUNT, "主用例：模板行，字段值勿改"],
    # ---------- probe：兼容性探测，结果不确定，不计入压测指标 ----------
    ["L002", "probe", "正确账号 不带 Model", "", 7, 6, FACCOUNT, "省略 Model，看是否必填"],
    ["L003", "probe", "正确账号 Model=1(独立运行模式)", 1, 7, 6, FACCOUNT, "覆盖 Model 字段"],
    ["L004", "probe", "正确账号 AccAtt=0(股票渠道)", 0, 7, 0, FACCOUNT, "渠道变体"],
    ["L005", "probe", "正确账号 AccountType=1(资金账号)", 0, 1, 6, FACCOUNT, "账号类型变体"],
    ["L006", "probe", "正确账号 FAccount 带前导空格", 0, 7, 6, " " + FACCOUNT, "对照：看中台是否 trim"],
    # ---------- 错误 ----------
    ["L101", "error", "FAccount 为空", 0, 7, 6, "", "期望被拒绝/Err<0"],
    ["L102", "error", "AccountType 非法值99", 0, 99, 6, FACCOUNT, "期望被拒绝/Err<0"],
    ["L103", "error", "AccAtt 非法值9", 0, 7, 9, FACCOUNT, "期望被拒绝/Err<0"],
    ["L104", "error", "FAccount 不存在", 0, 7, 6, "000000000000", "未签署过的账号，期望 Err<0"],
    # ---------- 破坏 ----------
    ["L201", "destroy", "FAccount 超长1000字符", 0, 7, 6, "__LONG__", "超长账号"],
    ["L202", "destroy", "FAccount 含控制字符", 0, 7, 6, "__CTRL__", "控制字符"],
    ["L203", "destroy", "AccountType 极大值", 0, "__MAXINT__", 6, FACCOUNT, "极大值"],
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], accounts=STRESS_ACCOUNT_POOL,
                                  type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "AccountType": [99, -1, "abc", "__MAXINT__", "__HUGE__"],
    "AccAtt": [9, -1, "abc"],
    "FAccount": ["", "__LONG__", "__CTRL__", "__SQL__", "__UNI__", "__EMOJI__", "abc"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__TAB__",
                 "__NEWLINE__", "__RTL__", "__ZWSP__", "__BOM__", "__SQL__", "__XSS__",
                 "__FMT__", "__PATH__", "__EMOJI2__", "__UNICODE__", "__JSON__",
                 "__REPLACE_NULL__", FACCOUNT + "\x00\x01"],
    "AccountType": ["__HUGE__", "__SCI__", "__HEX__", "__FLOATINF__", "__FLOATNAN__", "__NEG__"],
    "AccAtt": ["__HUGE__", "__SCI__", "__NEGINT__"],
    "Model": ["__MAXINT__", "__NEGINT__", "__HUGE__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], accounts=REAL_ACCOUNT_POOL, injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("AccountType", "__HUGE__"), ("AccAtt", 99), ("Model", "__MAXINT__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    return {"logout": {"Account": account}}
