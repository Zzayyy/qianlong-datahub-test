# -*- coding: utf-8 -*-
"""
接口定义：acc_query（云条件单账号查询）
=====================================
字段来源：../请求接口字段.txt 2.2.2

报文格式：
  {"acc_query": {"Account": {...}, "TradePwd": "123123"}}
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, build_account, INT_LEAVES, gen_account_variety, gen_fuzz, gen_cross

NAME = "acc_query"
TITLE = "云条件单账号查询(acc_query)"

HEADERS = [
    ("case_no",    "用例编号"),
    ("case_type",  "用例类型\n(normal/error/destroy)"),
    ("case_desc",  "用例说明"),
    ("Model",      "云单运行模式(0内嵌/1独立)"),
    ("AccountType","账号类型(1资金/7客户号)"),
    ("AccAtt",     "渠道(0股票/6期权)"),
    ("FAccount",   "云单账号"),
    ("TradePwd",   "交易密码"),
    ("expected",   "预期结果(备注)"),
]

# 张国昌数据
ROWS = [
    # ---------- 正常 ----------
    ("AQ01", "normal",  "张国昌资金账号查询",         "", 1, 6, "300130000461", "123123", "期望 Err>=0"),
    ("AQ02", "normal",  "客户号查询",                 "", 7, 7, "12345679", "123123", "期望 Err>=0"),
    ("AQ03", "normal",  "无密码查询",                 "", 1, 6, "300130000461", "", "TradePwd 可空"),
    ("AQ04", "normal",  "另一资金账号查询",           "", 1, 6, "999993", "123456", "期望 Err>=0"),
    # ---------- 错误 ----------
    ("AQ11", "error",   "账号不存在",                 "", 1, 6, "000000000", "123123", "期望 Err<0"),
    ("AQ12", "error",   "AccountType 非法99",         "", 99, 6, "300130000461", "123123", "期望被拒绝"),
    ("AQ13", "error",   "AccAtt 非法9",               "", 1, 9, "300130000461", "123123", "期望被拒绝"),
    ("AQ14", "error",   "FAccount 为空",              "", 1, 6, "", "123123", "期望被拒绝"),
    # ---------- 破坏 ----------
    ("AQ21", "destroy", "FAccount 超长",              "", 1, 6, "__LONG__", "123123", "超长账号"),
    ("AQ22", "destroy", "密码含控制字符",             "", 1, 6, "300130000461", "123\x00\x01\x02", "控制字符"),
    ("AQ23", "destroy", "AccountType 极大值",         "", "__MAXINT__", 6, "300130000461", "123123", "极大值"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
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
                 "__REPLACE_NULL__", "300130000461\x00\x01"],
    "AccountType": ["__HUGE__", "__SCI__", "__HEX__", "__FLOATINF__", "__FLOATNAN__", "__NEG__"],
    "AccAtt": ["__HUGE__", "__SCI__", "__NEGINT__"],
    "TradePwd": ["__LONG_PWD10__", "__CTRL__", "__SQL__", "__XSS__", "__FMT__", "__TAB__", "__NEWLINE__", "__EMOJI2__"],
    "Model": ["__MAXINT__", "__NEGINT__", "__HUGE__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], injects=[
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
