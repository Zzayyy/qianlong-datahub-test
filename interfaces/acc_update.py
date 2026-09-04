# -*- coding: utf-8 -*-
"""
接口定义：acc_update（更新云条件单账号信息）
=====================================
字段来源：../请求接口字段.txt 2.2.3 + 192.168.1.137 Redis 真实样本

真实 acc_update 报文格式：
  {"acc_update": {"Account": {"Model": 0, "AccountType": 7, "AccAtt": 6,
                              "FAccount": "010100011300"},
                  "TradePwd": "123123", "BranchNO": "123456",
                  "ClientName": "张国昌", "TradeAccount": "010100011300",
                  "Shareholders": [{"SAccount": "A442523077", "ExchangeNum": 1},
                                   {"SAccount": "0199908393", "ExchangeNum": 2}]}}

2026-09 更新：原来用的 300130000461 / 999993 / 李四 等均为占位，线上签不了。
现统一改用线上真实签署数据（_common.REAL_ACCOUNT / REAL_SIGN / REAL_SHAREHOLDERS）。
BranchNO：协议文档 2.2.3 未列该字段，但真实签署报文带，故一并按真实值下发
（AU04 与 AU13 对照验证它是否必填）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, build_account, to_typed, REAL_ACCOUNT, REAL_SIGN,
                     REAL_SHAREHOLDERS, STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL,
                     gen_account_variety, gen_fuzz, gen_cross)

NAME = "acc_update"
TITLE = "更新云条件单账号信息(acc_update)"

FACCOUNT = REAL_ACCOUNT["FAccount"]
PWD = REAL_SIGN["TradePwd"]
BRANCH = REAL_SIGN["BranchNO"]
CLIENT = REAL_SIGN["ClientName"]
TRADE_ACC = REAL_SIGN["TradeAccount"]
SH1, EX1 = REAL_SHAREHOLDERS[0]
SH2, EX2 = REAL_SHAREHOLDERS[1]

HEADERS = [
    ("case_no",     "用例编号"),
    ("case_type",   "用例类型\n(normal/probe/error/destroy)"),
    ("case_desc",   "用例说明"),
    ("Model",       "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt",      "渠道(0股票/6期权)"),
    ("FAccount",    "云单账号"),
    ("TradePwd",    "交易密码"),
    ("BranchNO",    "营业部号"),
    ("ClientName",  "客户名称"),
    ("TradeAccount","交易账号"),
    ("SH_SAccount1","股东号1"),
    ("SH_ExNum1",   "市场1(1沪/2深)"),
    ("SH_SAccount2","股东号2"),
    ("SH_ExNum2",   "市场2(1沪/2深)"),
    ("expected",    "预期结果(备注)"),
]

# ==================== 测试数据（全部基于真实签署数据，只改被测字段）====================
ROWS = [
    # ---------- normal：压测池（账号四要素与真实账号完全匹配，字段完整）----------
    ("AU01", "normal", "正确账号 全量更新(双股东号)", 0, 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "主用例：模板行，字段值勿改"),
    # ---------- probe：兼容性探测，结果不确定，不计入压测指标 ----------
    ("AU02", "probe",  "正确账号 不带 Model",  "", 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "省略 Model，看是否必填"),
    ("AU03", "probe",  "正确账号 单股东号(沪)", 0, 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, "", "", "只更新沪市股东号"),
    ("AU04", "probe",  "正确账号 不带 BranchNO", 0, 7, 6, FACCOUNT, PWD, "", CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "与 AU13 对照，判断 BranchNO 必填性"),
    ("AU05", "probe",  "正确账号 Model=1(独立运行模式)", 1, 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "覆盖 Model 字段"),
    ("AU06", "probe",  "正确账号 AccAtt=0(股票渠道)", 0, 7, 0, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "渠道变体"),
    # ---------- 错误 ----------
    ("AU11", "error", "TradePwd 为空", 0, 7, 6, FACCOUNT, "", BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "期望被拒绝/Err<0"),
    ("AU12", "error", "股东号为空", 0, 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     "", "", "", "", "Shareholders 为空，期望被拒绝"),
    ("AU13", "error", "BranchNO 为空", 0, 7, 6, FACCOUNT, PWD, "", CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "与 AU04 对照，判断必填性"),
    ("AU14", "error", "FAccount 为空", 0, 7, 6, "", PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "期望被拒绝/Err<0"),
    ("AU15", "error", "ExchangeNum 非法值5", 0, 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, 5, SH2, EX2, "期望被拒绝/Err<0"),
    ("AU16", "error", "TradeAccount 与 FAccount 不一致", 0, 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, "010100011399",
     SH1, EX1, SH2, EX2, "交易账号不存在，期望 Err<0"),
    ("AU17", "error", "ClientName 为空", 0, 7, 6, FACCOUNT, PWD, BRANCH, "", TRADE_ACC,
     SH1, EX1, SH2, EX2, "期望被拒绝/Err<0"),
    # ---------- 破坏 ----------
    ("AU21", "destroy", "ClientName 含控制字符", 0, 7, 6, FACCOUNT, PWD, BRANCH, "__CTRL_NAME__", TRADE_ACC,
     SH1, EX1, SH2, EX2, "控制字符"),
    ("AU22", "destroy", "FAccount 超长1000字符", 0, 7, 6, "__LONG__", PWD, BRANCH, CLIENT, TRADE_ACC,
     SH1, EX1, SH2, EX2, "超长账号"),
    ("AU23", "destroy", "SAccount 非ASCII", 0, 7, 6, FACCOUNT, PWD, BRANCH, CLIENT, TRADE_ACC,
     "__UNI__", EX1, SH2, EX2, "非ASCII股东号"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], accounts=STRESS_ACCOUNT_POOL,
                                  type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "TradePwd": ["", "   ", "__LONG_PWD__", "__SQL__", "__XSS__", "__CTRL__"],
    "BranchNO": ["", "   ", "__LONG__", "__SQL__", "__XSS__", "__UNI__", "abc"],
    "AccountType": [99, 9999, -1, "abc", "__MAXINT__", "__HUGE__", "__HEX__", "__SCI__"],
    "AccAtt": [9, 99, -1, "abc", "__MAXINT__"],
    "FAccount": ["", "__LONG__", "__CTRL__", "__SQL__", "__UNI__", "__EMOJI__", "__NULL_STR__", "abc"],
    "ClientName": ["", "__CTRL_NAME__", "__SQL__", "__XSS__", "__LONG__", "__EMOJI__"],
    "TradeAccount": ["010100011399", "", "__LONG__", "__SQL__"],
    "SH_SAccount1": ["", "__LONG__", "__SQL__", "__UNI__", "__CTRL__"],
    "SH_ExNum1": [5, 99, -1, "abc", "__MAXINT__", "__ZERO__", "__BOOL_WEIRD__"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "TradePwd": ["__LONG_PWD10__", "__CTRL__", "__SQL__", "__XSS__", "__FMT__", "__TAB__", "__NEWLINE__", "__EMOJI2__"],
    "BranchNO": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__",
                 "__XSS__", "__EMOJI2__", "__UNICODE__", "__JSON__"],
    "ClientName": ["__CTRL_NAME__", "__LONG__", "__UNICODE__", "__EMOJI2__", "__XSS__", "__SQL__", "__RTL__"],
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__", "__XSS__",
                 "__RTL__", "__EMOJI2__", "__UNICODE__", "__JSON__"],
    "AccountType": ["__HUGE__", "__SCI__", "__HEX__", "__FLOATINF__", "__FLOATNAN__"],
    "AccAtt": ["__HUGE__", "__SCI__"],
    "SH_SAccount1": ["__LONG__", "__CTRL__", "__SQL__", "__UNI__", "__EMOJI2__", "__JSON__"],
    "SH_ExNum1": ["__HUGE__", "__SCI__", "__FLOATINF__", "__NEG__"],
    "TradeAccount": ["__LONG__", "__SQL__", "__EMOJI2__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], accounts=REAL_ACCOUNT_POOL, injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("TradePwd", "__LONG_PWD__"), ("ClientName", "__CTRL_NAME__"), ("SH_SAccount1", "__SQL__"),
    ("AccountType", "__HUGE__"), ("SH_ExNum1", 99), ("TradeAccount", "__EMOJI2__"),
    ("BranchNO", "__LONG__"), ("BranchNO", "__SQL__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    payload = {"acc_update": {"Account": account}}
    for leaf in ("TradePwd", "BranchNO", "ClientName", "TradeAccount"):
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
