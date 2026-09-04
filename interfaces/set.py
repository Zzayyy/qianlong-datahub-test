# -*- coding: utf-8 -*-
"""
接口定义：set（运行/停止云条件单）
=================================
字段来源：../请求接口字段.txt 2.2.7

真实 set 报文：
  {"set": {"Account": {"Model": 0, "AccountType": 7, "AccAtt": 6,
                       "FAccount": "010100011300"},
           "Mode": 1,
           "Refs": ["20260528000010", "20260604000001"]}}

2026-09 更新：原来用的 FAccount=300130000461、Refs=26319550 均为占位，线上跑不起来。
现统一改用线上真实账号（_common.REAL_ACCOUNT）+ doc 真实样本里的云单引用
（_common.REAL_REFS）。注意：Ref 必须是该账号下真实存在的云单，可用 query 回填。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, build_account, to_typed, REAL_ACCOUNT, REAL_REFS, FAKE_REF,
                     STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL,
                     gen_account_variety, gen_fuzz, gen_cross)

NAME = "set"
TITLE = "运行/停止云条件单(set)"

FACCOUNT = REAL_ACCOUNT["FAccount"]
REF1, REF2 = REAL_REFS[0], REAL_REFS[1]

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/probe/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("Mode", "云单状态(0停止/1运行)"),
    ("Refs", "云单引用数组(逗号分隔)"),
    ("expected", "预期结果(备注)"),
]

# ==================== 测试数据（全部基于真实账号+真实云单引用，只改被测字段）====================
ROWS = [
    # ---------- normal：压测池（账号四要素与真实账号完全匹配）----------
    ["S001", "normal", "运行一个云单(Mode=1)", 0, 7, 6, FACCOUNT, 1, REF1, "主用例：模板行，字段值勿改"],
    ["S002", "normal", "运行多个云单(Mode=1)", 0, 7, 6, FACCOUNT, 1, f"{REF1},{REF2}", "两个真实引用"],
    ["S003", "normal", "停止一个云单(Mode=0)", 0, 7, 6, FACCOUNT, 0, REF1, "期望 Err>=0, Mode=0"],
    ["S004", "normal", "停止多个云单(Mode=0)", 0, 7, 6, FACCOUNT, 0, f"{REF1},{REF2}", "两个真实引用"],
    # ---------- probe：兼容性探测，结果不确定，不计入压测指标 ----------
    ["S005", "probe", "正确账号 不带 Model", "", 7, 6, FACCOUNT, 1, REF1, "省略 Model，看是否必填"],
    ["S006", "probe", "正确账号 AccAtt=0(股票渠道)", 0, 7, 0, FACCOUNT, 1, REF1, "渠道变体"],
    # ---------- 错误 ----------
    ["S101", "error", "Refs 为空", 0, 7, 6, FACCOUNT, 1, "", "期望被拒绝/Err<0"],
    ["S102", "error", "Mode 非法值99", 0, 7, 6, FACCOUNT, 99, REF1, "期望被拒绝/Err<0"],
    ["S103", "error", "Refs 不存在", 0, 7, 6, FACCOUNT, 1, FAKE_REF, "云单不存在，期望 Err<0"],
    ["S104", "error", "FAccount 为空", 0, 7, 6, "", 1, REF1, "期望被拒绝/Err<0"],
    ["S105", "error", "Mode 为空", 0, 7, 6, FACCOUNT, "", REF1, "Mode 缺失，期望被拒绝"],
    ["S106", "error", "AccountType 非法值99", 0, 99, 6, FACCOUNT, 1, REF1, "期望被拒绝/Err<0"],
    # ---------- 破坏 ----------
    ["S201", "destroy", "Refs 超长1000字符", 0, 7, 6, FACCOUNT, 1, "__LONG__", "超长引用"],
    ["S202", "destroy", "Refs 含控制字符", 0, 7, 6, FACCOUNT, 1, "__CTRL__", "控制字符"],
    ["S203", "destroy", "Mode 极大值", 0, 7, 6, FACCOUNT, "__MAXINT__", REF1, "极大值"],
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], accounts=STRESS_ACCOUNT_POOL,
                                  type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "Mode": [99, -1, 0, "abc", "__MAXINT__", "__HUGE__", "__HEX__", "__BOOL_WEIRD__"],
    "Refs": ["", "__SQL__", FAKE_REF, "__CTRL__", "__EMOJI__", "   "],
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
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], accounts=REAL_ACCOUNT_POOL, injects=[
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
