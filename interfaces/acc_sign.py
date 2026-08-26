# -*- coding: utf-8 -*-
"""
接口定义：acc_sign（云条件单账号签署）
=====================================
字段来源：../请求接口字段.txt + 192.168.1.137 Redis DataHub_req_stream 真实样本

真实 acc_sign 报文格式：
  {"acc_sign":{"Account":{"Model":0,"AccountType":1,"AccAtt":6,"FAccount":"300130000461"},
               "TradePwd":"123123","ClientName":"张三","TradeAccount":"300130000461",
               "Shareholders":[{"SAccount":"A442523077","ExchangeNum":1},
                               {"SAccount":"0199908393","ExchangeNum":2}]}}

Shareholders 为数组：Excel 中用 SH_SAccount1/SH_ExNum1 ... 表示多个股东号。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, gen_account_variety, gen_fuzz, gen_cross

NAME = "acc_sign"
TITLE = "云条件单账号签署(acc_sign)"

HEADERS = [
    ("case_no",        "用例编号"),
    ("case_type",      "用例类型\n(normal/error/destroy)"),
    ("case_desc",      "用例说明"),
    ("Model",          "云单运行模式(0内嵌/1独立)"),
    ("AccountType",    "账号类型(1资金/7客户号)"),
    ("AccAtt",         "渠道(0股票/6期权)"),
    ("FAccount",       "云单账号"),
    ("TradePwd",       "交易密码"),
    ("ClientName",     "客户名称"),
    ("TradeAccount",   "交易账号"),
    ("SH_SAccount1",   "股东号1"),
    ("SH_ExNum1",      "市场1(1沪/2深)"),
    ("SH_SAccount2",   "股东号2"),
    ("SH_ExNum2",      "市场2(1沪/2深)"),
    ("expected",       "预期结果(备注)"),
]

# ==================== 测试数据 ====================
ROWS = [
    # ---------- 正常数据 ----------
    ("A001", "normal", "资金账号签署(双股东号,真实数据)", 0, 1, 6, "300130000461", "123123", "张三", "300130000461",
     "A442523077", 1, "0199908393", 2, "期望 Err>=0, Msg=account sign success"),
    ("A002", "normal", "资金账号999993 签署",              "", 1, 6, "999993", "123456", "李四", "999993",
     "A123456789", 1, "", "", "期望 Err>=0"),
    ("A003", "normal", "客户号12345679 签署(AccAtt=7)",    "", 7, 7, "12345679", "123456", "王五", "12345679",
     "B111111111", 2, "", "", "客户号类型"),
    ("A004", "normal", "客户号999997 签署(AccAtt=0)",      "", 7, 0, "999997", "123456", "赵六", "999997",
     "C222222222", 1, "", "", "客户号+股票渠道"),
    ("A005", "normal", "带 Model=0 内嵌模式",             0, 1, 6, "999992", "123456", "钱七", "999992",
     "A999999999", 1, "", "", "覆盖 Model 字段"),
    ("A006", "normal", "单股东号签署",                     "", 1, 6, "1000004", "123456", "孙八", "1000004",
     "A888888888", 2, "", "", ""),
    # ---------- 错误数据（接口校验）----------
    ("A101", "error",   "TradePwd 为空",                   "", 1, 6, "300130000461", "", "张三", "300130000461",
     "A442523077", 1, "", "", "期望被拒绝/Err<0"),
    ("A102", "error",   "AccountType 非法值99",            "", 99, 6, "300130000461", "123123", "张三", "300130000461",
     "A442523077", 1, "", "", "期望被拒绝/Err<0"),
    ("A103", "error",   "AccAtt 非法值9",                  "", 1, 9, "300130000461", "123123", "张三", "300130000461",
     "A442523077", 1, "", "", "期望被拒绝/Err<0"),
    ("A104", "error",   "FAccount 为空",                   "", 1, 6, "", "123123", "张三", "300130000461",
     "A442523077", 1, "", "", "期望被拒绝/Err<0"),
    ("A105", "error",   "TradeAccount 与 FAccount 不一致", "", 1, 6, "999993", "123123", "张三", "888888",
     "A442523077", 1, "", "", "期望被拒绝/Err<0"),
    ("A106", "error",   "股东号 SAccount 为空",            "", 1, 6, "999993", "123123", "张三", "999993",
     "", 1, "", "", "期望被拒绝/Err<0"),
    ("A107", "error",   "ExchangeNum 非法值5",             "", 1, 6, "999993", "123123", "张三", "999993",
     "A111111111", 5, "", "", "期望被拒绝/Err<0"),
    # ---------- 破坏测试（极端/畸形，用 token 占位，build 时展开）----------
    ("A201", "destroy", "TradePwd 超长1000字符",           "", 1, 6, "999993", "__LONG__", "张三", "999993",
     "A111111111", 1, "", "", "超长密码"),
    ("A202", "destroy", "ClientName 含控制字符",           "", 1, 6, "999993", "123123", "__CTRL_NAME__", "999993",
     "A111111111", 1, "", "", "特殊控制字符"),
    ("A203", "destroy", "FAccount 超长1000字符",           "", 1, 6, "__LONG__", "123123", "张三", "999993",
     "A111111111", 1, "", "", "超长账号"),
    ("A204", "destroy", "SAccount 含非ASCII中文",          "", 1, 6, "999993", "123123", "张三", "999993",
     "__UNI__", 1, "", "", "非ASCII股东号"),
    ("A205", "destroy", "AccountType 传字符串'abc'",       "", "abc", 6, "999993", "123123", "张三", "999993",
     "A111111111", 1, "", "", "非法类型"),
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

# ==================== 报文构造 ====================
# 破坏测试 token 统一由 _common.TOKEN_MAP 提供；保留 _expand 别名给 build_payload
_expand = expand


def build_payload(row: dict) -> dict:
    """Excel 一行 -> acc_sign 报文字典。空值省略；非法数字保留字符串。"""
    account = {}
    for fld in ("Model", "AccountType", "AccAtt"):
        v = _expand(row.get(fld))
        if v is None or str(v).strip() == "":
            continue
        try:
            account[fld] = int(v)
        except (ValueError, TypeError):
            account[fld] = str(v)
    faccount = _expand(row.get("FAccount"))
    if faccount is not None and str(faccount).strip() != "":
        account["FAccount"] = str(faccount)

    payload = {"acc_sign": {"Account": account}}

    for fld in ("TradePwd", "ClientName", "TradeAccount"):
        v = _expand(row.get(fld))
        if v is not None and str(v).strip() != "":
            payload["acc_sign"][fld] = str(v)

    # Shareholders 数组：最多 2 组
    shareholders = []
    for idx in (1, 2):
        sacct = _expand(row.get(f"SH_SAccount{idx}"))
        if sacct is None or str(sacct).strip() == "":
            continue
        item = {"SAccount": str(sacct)}
        ex = _expand(row.get(f"SH_ExNum{idx}"))
        if ex is not None and str(ex).strip() != "":
            try:
                item["ExchangeNum"] = int(ex)
            except (ValueError, TypeError):
                item["ExchangeNum"] = str(ex)
        shareholders.append(item)
    if shareholders:
        payload["acc_sign"]["Shareholders"] = shareholders
    return payload
