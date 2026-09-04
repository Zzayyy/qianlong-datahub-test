# -*- coding: utf-8 -*-
"""
接口定义：acc_query（云条件单账号查询）
=====================================
字段来源：../请求接口字段.txt 2.2.2 + 192.168.1.137 Redis 真实样本

真实 acc_query 报文格式：
  {"acc_query": {"Account": {"Model": 0, "AccountType": 7, "AccAtt": 6,
                             "FAccount": "010100011300"},
                 "TradePwd": "123123"}}

2026-09 更新：原来用的 300130000461 / 12345679 均为占位账号，线上查不到。
现统一改用线上真实账号（_common.REAL_ACCOUNT / REAL_SIGN，与 acc_sign.py 一致）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, build_account, REAL_ACCOUNT, REAL_SIGN,
                     STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL,
                     gen_account_variety, gen_fuzz, gen_cross)

NAME = "acc_query"
TITLE = "云条件单账号查询(acc_query)"

FACCOUNT = REAL_ACCOUNT["FAccount"]
PWD = REAL_SIGN["TradePwd"]

HEADERS = [
    ("case_no",    "用例编号"),
    ("case_type",  "用例类型\n(normal/probe/error/destroy)"),
    ("case_desc",  "用例说明"),
    ("Model",      "云单运行模式(0内嵌/1独立)"),
    ("AccountType","账号类型(1资金/7客户号)"),
    ("AccAtt",     "渠道(0股票/6期权)"),
    ("FAccount",   "云单账号"),
    ("TradePwd",   "交易密码"),
    ("expected",   "预期结果(备注)"),
]

# ==================== 测试数据（全部基于真实账号，只改被测字段）====================
ROWS = [
    # ---------- normal：压测池（账号四要素与真实账号完全匹配）----------
    ("AQ01", "normal",  "正确账号 带密码查询",           0, 7, 6, FACCOUNT, PWD, "主用例：模板行，字段值勿改"),
    # ---------- probe：兼容性探测，结果不确定，不计入压测指标 ----------
    ("AQ02", "probe",   "正确账号 不带 Model",           "", 7, 6, FACCOUNT, PWD, "省略 Model，看是否必填"),
    ("AQ03", "probe",   "正确账号 不带密码",             0, 7, 6, FACCOUNT, "", "TradePwd 留空，看是否必填"),
    ("AQ04", "probe",   "正确账号 Model=1(独立运行模式)", 1, 7, 6, FACCOUNT, PWD, "覆盖 Model 字段"),
    ("AQ05", "probe",   "正确账号 AccAtt=0(股票渠道)",   0, 7, 0, FACCOUNT, PWD, "渠道变体"),
    ("AQ06", "probe",   "正确账号 AccountType=1(资金账号)", 0, 1, 6, FACCOUNT, PWD, "账号类型变体"),
    ("AQ07", "probe",   "正确账号 FAccount 带前导空格",   0, 7, 6, " " + FACCOUNT, PWD, "对照：看中台是否 trim"),
    # ---------- 错误 ----------
    ("AQ11", "error",   "TradePwd 错误",                0, 7, 6, FACCOUNT, "000000", "错误密码，期望 Err<0"),
    ("AQ12", "error",   "AccountType 非法值99",          0, 99, 6, FACCOUNT, PWD, "期望被拒绝/Err<0"),
    ("AQ13", "error",   "AccAtt 非法值9",                0, 7, 9, FACCOUNT, PWD, "期望被拒绝/Err<0"),
    ("AQ14", "error",   "FAccount 为空",                 0, 7, 6, "", PWD, "期望被拒绝/Err<0"),
    ("AQ15", "error",   "FAccount 不存在",               0, 7, 6, "000000000000", PWD, "未签署过的账号，期望 Err<0 或空结果"),
    # ---------- 破坏 ----------
    ("AQ21", "destroy", "FAccount 超长1000字符",         0, 7, 6, "__LONG__", PWD, "超长账号"),
    ("AQ22", "destroy", "TradePwd 含控制字符",           0, 7, 6, FACCOUNT, "__CTRL__", "控制字符"),
    ("AQ23", "destroy", "AccountType 极大值",            0, "__MAXINT__", 6, FACCOUNT, PWD, "极大值"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], accounts=STRESS_ACCOUNT_POOL,
                                  type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "AccountType": [99, 9999, -1, 0, "abc", "1.5", "__MAXINT__", "__NEGINT__", "__HUGE__",
                    "__HEX__", "__OCT__", "__SCI__", "__LEAD0__", "__ZERO__", "__BOOL_WEIRD__",
                    "__FLOATINF__", "__FLOATNAN__"],
    "AccAtt": [9, 99, -1, "abc", "__MAXINT__", "__ZERO__", "__BOOL_WEIRD__"],
    "FAccount": ["", "__LONG__", "__CTRL__", "__UNI__", "__SQL__", "__XSS__",
                 "__NULL_STR__", "__JSON__", "__EMOJI__", "abc", "__NULLBYTE__"],
    "TradePwd": ["", "__LONG_PWD__", "__SQL__", "__XSS__"],
    "Model": ["abc", "__MAXINT__", "__BOOL_WEIRD__", "__ZERO__"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__TAB__",
                 "__NEWLINE__", "__RTL__", "__ZWSP__", "__BOM__", "__SQL__", "__XSS__",
                 "__FMT__", "__PATH__", "__EMOJI2__", "__UNICODE__", "__JSON__",
                 "__REPLACE_NULL__", FACCOUNT + "\x00\x01"],
    "AccountType": ["__HUGE__", "__SCI__", "__HEX__", "__FLOATINF__", "__FLOATNAN__", "__NEG__"],
    "AccAtt": ["__HUGE__", "__SCI__", "__NEGINT__"],
    "TradePwd": ["__LONG_PWD10__", "__CTRL__", "__SQL__", "__XSS__", "__FMT__", "__TAB__", "__NEWLINE__", "__EMOJI2__"],
    "Model": ["__MAXINT__", "__NEGINT__", "__HUGE__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], accounts=REAL_ACCOUNT_POOL, injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("TradePwd", "__LONG_PWD__"), ("AccountType", "__HUGE__"), ("AccAtt", 99), ("Model", "__MAXINT__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    payload = {"acc_query": {"Account": account}}
    pwd = expand(row.get("TradePwd"))
    if pwd is not None and str(pwd).strip() != "":
        payload["acc_query"]["TradePwd"] = str(pwd)
    return payload
