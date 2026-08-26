# -*- coding: utf-8 -*-
"""
接口定义：acc_update（更新云条件单账号信息）
=====================================
字段来源：../请求接口字段.txt 2.2.3

报文格式：
  {"acc_update": {"Account": {...}, "TradePwd": "123123", "ClientName": "张国昌",
                  "TradeAccount": "300130000461",
                  "Shareholders": [{"SAccount": "A442523077", "ExchangeNum": 1}, ...]}}
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, build_account, to_typed, gen_account_variety, gen_fuzz, gen_cross

NAME = "acc_update"
TITLE = "更新云条件单账号信息(acc_update)"

HEADERS = [
    ("case_no",     "用例编号"),
    ("case_type",   "用例类型\n(normal/error/destroy)"),
    ("case_desc",   "用例说明"),
    ("Model",       "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt",      "渠道(0股票/6期权)"),
    ("FAccount",    "云单账号"),
    ("TradePwd",    "交易密码"),
    ("ClientName",  "客户名称"),
    ("TradeAccount","交易账号"),
    ("SH_SAccount1","股东号1"),
    ("SH_ExNum1",   "市场1(1沪/2深)"),
    ("SH_SAccount2","股东号2"),
    ("SH_ExNum2",   "市场2(1沪/2深)"),
    ("expected",    "预期结果(备注)"),
]

ROWS = [
    # ---------- 正常 ----------
    ("AU01", "normal", "张国昌更新(双股东号)", "", 1, 6, "300130000461", "123123", "张国昌", "300130000461",
     "A442523077", 1, "0199908393", 2, "期望 Err>=0"),
    ("AU02", "normal", "更新客户名", "", 1, 6, "999993", "123456", "李四", "999993",
     "A123456789", 1, "", "", "期望 Err>=0"),
    ("AU03", "normal", "单股东号更新", "", 1, 6, "300130000461", "123123", "张国昌", "300130000461",
     "A442523077", 1, "", "", "期望 Err>=0"),
    # ---------- 错误 ----------
    ("AU11", "error", "TradePwd 为空", "", 1, 6, "300130000461", "", "张国昌", "300130000461",
     "A442523077", 1, "", "", "期望被拒绝"),
    ("AU12", "error", "股东号为空", "", 1, 6, "300130000461", "123123", "张国昌", "300130000461",
     "", 1, "", "", "期望被拒绝"),
    ("AU13", "error", "FAccount 为空", "", 1, 6, "", "123123", "张国昌", "300130000461",
     "A442523077", 1, "", "", "期望被拒绝"),
    ("AU14", "error", "ExchangeNum 非法5", "", 1, 6, "300130000461", "123123", "张国昌", "300130000461",
     "A442523077", 5, "", "", "期望被拒绝"),
    # ---------- 破坏 ----------
    ("AU21", "destroy", "ClientName 含控制字符", "", 1, 6, "300130000461", "123123", "__CTRL_NAME__", "300130000461",
     "A442523077", 1, "", "", "控制字符"),
    ("AU22", "destroy", "FAccount 超长", "", 1, 6, "__LONG__", "123123", "张国昌", "300130000461",
     "A442523077", 1, "", "", "超长账号"),
    ("AU23", "destroy", "SAccount 非ASCII", "", 1, 6, "300130000461", "123123", "张国昌", "300130000461",
     "__UNI__", 1, "", "", "非ASCII"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "TradePwd": ["", "   ", "__LONG_PWD__", "__SQL__", "__XSS__", "__CTRL__"],
    "AccountType": [99, 9999, -1, "abc", "__MAXINT__", "__HUGE__", "__HEX__", "__SCI__"],
    "AccAtt": [9, 99, -1, "abc", "__MAXINT__"],
    "FAccount": ["", "__LONG__", "__CTRL__", "__SQL__", "__UNI__", "__EMOJI__", "__NULL_STR__", "abc"],
    "ClientName": ["", "__CTRL_NAME__", "__SQL__", "__XSS__", "__LONG__", "__EMOJI__"],
    "TradeAccount": ["888888", "", "__LONG__", "__SQL__"],
    "SH_SAccount1": ["", "__LONG__", "__SQL__", "__UNI__", "__CTRL__"],
    "SH_ExNum1": [5, 99, -1, "abc", "__MAXINT__", "__ZERO__", "__BOOL_WEIRD__"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "TradePwd": ["__LONG_PWD10__", "__CTRL__", "__SQL__", "__XSS__", "__FMT__", "__TAB__", "__NEWLINE__", "__EMOJI2__"],
    "ClientName": ["__CTRL_NAME__", "__LONG__", "__UNICODE__", "__EMOJI2__", "__XSS__", "__SQL__", "__RTL__"],
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__", "__XSS__",
                 "__RTL__", "__EMOJI2__", "__UNICODE__", "__JSON__"],
    "AccountType": ["__HUGE__", "__SCI__", "__HEX__", "__FLOATINF__", "__FLOATNAN__"],
    "AccAtt": ["__HUGE__", "__SCI__"],
    "SH_SAccount1": ["__LONG__", "__CTRL__", "__SQL__", "__UNI__", "__EMOJI2__", "__JSON__"],
    "SH_ExNum1": ["__HUGE__", "__SCI__", "__FLOATINF__", "__NEG__"],
    "TradeAccount": ["__LONG__", "__SQL__", "__EMOJI2__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("TradePwd", "__LONG_PWD__"), ("ClientName", "__CTRL_NAME__"), ("SH_SAccount1", "__SQL__"),
    ("AccountType", "__HUGE__"), ("SH_ExNum1", 99), ("TradeAccount", "__EMOJI2__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    payload = {"acc_update": {"Account": account}}
    for leaf in ("TradePwd", "ClientName", "TradeAccount"):
        v = expand(row.get(leaf))
        if v is not None and str(v).strip() != "":
            payload["acc_update"][leaf] = str(v)
    shareholders = []
    for idx in (1, 2):
        sacct = expand(row.get(f"SH_SAccount{idx}"))
        if sacct is None or str(sacct).strip() == "":
            continue
        item = {"SAccount": str(sacct)}
        ex = expand(row.get(f"SH_ExNum{idx}"))
        if ex is not None and str(ex).strip() != "":
            item["ExchangeNum"] = to_typed("ExchangeNum", ex)
        shareholders.append(item)
    if shareholders:
        payload["acc_update"]["Shareholders"] = shareholders
    return payload
