# -*- coding: utf-8 -*-
"""
接口定义：create（创建云条件单）
=================================
字段来源：../请求接口字段.txt 2.2.4
报文复杂（Account + CondType + Entrust + 各类 Cfg + 各类 Cond）。
Excel 用扁平列名 + 前缀映射嵌套结构："Entrust_ContractCode" -> Entrust.ContractCode。

列序（29 列）：
0 case_no | 1 case_type | 2 case_desc | 3 Model | 4 AccountType | 5 AccAtt | 6 FAccount
| 7 CondType | 8 CondName | 9 CondDesc | 10 ValidDate
| 11 Entrust_ContractCode | 12 Entrust_ExchangeNum | 13 Entrust_EntrustPrice
| 14 Entrust_MarketOrderType | 15 Entrust_CoveredType | 16 Entrust_BSType
| 17 Entrust_OCType | 18 Entrust_EntrustAmount
| 19 CondPrice_Op | 20 CondPrice_TriggerPrice
| 21 CondPercent_Op | 22 CondPercent_TriggerPercent
| 23 CondTime_TriggerDate | 24 CondTime_TriggerTime
| 25 CfgExceedPrice_StockCode | 26 CfgExceedPrice_PriceStepBuy
| 27 CfgExceedPrice_PriceStepSell | 28 expected
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, build_account, to_typed, gen_account_variety, gen_fuzz, gen_cross

NAME = "create"
TITLE = "创建云条件单(create)"

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("CondType", "云单类型(1价格/2时间/3幅度/4合约止盈损/5标止盈损)"),
    ("CondName", "云单名称"),
    ("CondDesc", "策略描述"),
    ("ValidDate", "到期日期(空=永久)"),
    ("Entrust_ContractCode", "合约代码"),
    ("Entrust_ExchangeNum", "市场"),
    ("Entrust_EntrustPrice", "委托价格"),
    ("Entrust_MarketOrderType", "委托方式"),
    ("Entrust_CoveredType", "备兑"),
    ("Entrust_BSType", "买卖(1买/2卖)"),
    ("Entrust_OCType", "仓位(1开/2平)"),
    ("Entrust_EntrustAmount", "委托数量"),
    ("CondPrice_Op", "价格条件操作符"),
    ("CondPrice_TriggerPrice", "触发价"),
    ("CondPercent_Op", "幅度操作符"),
    ("CondPercent_TriggerPercent", "触发比例"),
    ("CondTime_TriggerDate", "触发日期"),
    ("CondTime_TriggerTime", "触发时间"),
    ("CfgExceedPrice_StockCode", "标的代码"),
    ("CfgExceedPrice_PriceStepBuy", "买入滑点"),
    ("CfgExceedPrice_PriceStepSell", "卖出滑点"),
    ("expected", "预期结果(备注)"),
]

# 张国昌账号基础行：Model="", AccountType=1, AccAtt=6, FAccount=300130000461
_BASE = ["", 1, 6, "300130000461"]

ROWS = [
    # 价格条件单(正常)
    ["C001", "normal", "价格条件单(买/开)", *_BASE, 1, "云单1", "价格触发策略", "2026-12-31",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "", "", "",
     "510050", -1, 1, "期望 Err>=0 返回 Ref"],
    # 时间条件单(正常)
    ["C002", "normal", "时间条件单", *_BASE, 2, "云单2", "定时触发", "",
     "10011297", 1, "0.0675", 0, False, 2, 1, 1,
     "", "", ">", "5.25", "20260509", "150522",
     "510050", 0, 0, "期望 Err>=0"],
    # 幅度条件单(正常)
    ["C003", "normal", "幅度条件单", *_BASE, 3, "云单3", "幅度触发", "2026-12-31",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     "", "", ">", "5.25", "", "",
     "510050", 0, 0, "期望 Err>=0"],
    # 错误
    ["C101", "error", "CondType 非法99", *_BASE, 99, "云单", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "", "", "",
     "510050", 0, 0, "期望被拒绝"],
    ["C102", "error", "ExchangeNum 非法5", *_BASE, 1, "云单", "描述", "",
     "10011297", 5, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "", "", "",
     "510050", 0, 0, "期望被拒绝"],
    ["C103", "error", "CondName 为空", *_BASE, 1, "", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "", "", "",
     "510050", 0, 0, "期望被拒绝"],
    ["C104", "error", "价格条件缺触发价", *_BASE, 1, "云单", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "", "", "", "", "",
     "510050", 0, 0, "期望被拒绝"],
    # 破坏
    ["C201", "destroy", "CondName 超长", *_BASE, 1, "__LONG__", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "", "", "",
     "510050", 0, 0, "超长名称"],
    ["C202", "destroy", "EntrustPrice 非法小数", *_BASE, 1, "云单", "描述", "",
     "10011297", 1, "__NAN__", 1, False, 1, 1, 1,
     ">", "0.0675", "", "", "", "",
     "510050", 0, 0, "非法价格"],
    ["C203", "destroy", "CondName 含emoji", *_BASE, 1, "__EMOJI__", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "", "", "",
     "510050", 0, 0, "emoji名称"],
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "CondType": [99, 9999, -1, 0, "abc", "__MAXINT__", "__HUGE__", "__HEX__"],
    "CondName": ["", "__LONG__", "__SQL__", "__XSS__"],
    "CondDesc": ["", "__LONG__", "__SQL__"],
    "ValidDate": ["__DATE_13__", "__DATE_ZERO__", "2026/01/01"],
    "Entrust_ContractCode": ["", "__LONG__", "__SQL__", "__CTRL__"],
    "Entrust_ExchangeNum": [5, 99, -1, "abc", "__MAXINT__"],
    "Entrust_EntrustPrice": ["__NAN__", "abc", "__PRICE_NEG__", "__PRICE_HUGE__", "__PRICE_SCI__"],
    "Entrust_BSType": [3, 99, -1, "abc"],
    "Entrust_OCType": [3, 99, -1, "abc"],
    "Entrust_EntrustAmount": [0, -1, "abc", "__HUGE__"],
    "CondPrice_Op": ["??", "#", ""],
    "CondPrice_TriggerPrice": ["", "__NAN__", "__PRICE_NEG__"],
    "AccountType": [99, -1, "abc"],
    "AccAtt": [9],
    "FAccount": ["", "__LONG__", "__CTRL__", "__SQL__"],
}, type_tag="error", start=700)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "CondName": ["__LONG10__", "__LONG100__", "__CTRL_NAME__", "__EMOJI2__", "__UNICODE__", "__SQL__", "__XSS__", "__RTL__"],
    "CondDesc": ["__LONG10__", "__SQL__", "__XSS__", "__EMOJI2__"],
    "Entrust_ContractCode": ["__LONG__", "__CTRL__", "__SQL__", "__EMOJI2__", "__JSON__"],
    "Entrust_EntrustPrice": ["__PRICE_NEGINF__", "__PRICE_NAN__", "__PRICE_INF__", "__PRICE_SCI__", "__PRICE_STR__"],
    "Entrust_ExchangeNum": ["__HUGE__", "__SCI__", "__FLOATINF__"],
    "Entrust_BSType": ["__HUGE__", "__SCI__"],
    "Entrust_OCType": ["__HUGE__", "__SCI__"],
    "Entrust_EntrustAmount": ["__HUGE__", "__SCI__", "__NEG__"],
    "CondPrice_Op": ["__SQL__", "__XSS__", "__EMOJI__"],
    "CondPrice_TriggerPrice": ["__PRICE_NEG__", "__PRICE_HUGE__", "__PRICE_NAN__"],
    "ValidDate": ["__DATE_13__", "__DATE_FAR__", "__DATE_TIME__"],
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__", "__XSS__", "__EMOJI2__", "__JSON__"],
    "AccountType": ["__HUGE__", "__SCI__"],
    "AccAtt": ["__HUGE__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("CondName", "__LONG__"), ("CondName", "__SQL__"), ("Entrust_ContractCode", "__SQL__"),
    ("Entrust_EntrustPrice", "__PRICE_NAN__"), ("AccountType", "__HUGE__"), ("Entrust_ExchangeNum", 99),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    payload = {"create": {"Account": account}}

    for leaf in ("CondType", "CondName", "CondDesc", "ValidDate"):
        v = expand(row.get(leaf))
        if v is None or str(v).strip() == "":
            continue
        payload["create"][leaf] = to_typed(leaf, v)

    # 嵌套字段：前缀 -> 点路径
    prefix_map = {
        "Entrust_": "Entrust",
        "CfgExceedPrice_": "CfgExceedPrice",
        "CfgAutoWithdraw_": "CfgAutoWithdraw",
        "CfgStopExec_": "CfgStopExec",
        "CfgFixedSplit_": "CfgFixedSplit",
        "CfgRandSplit_": "CfgRandSplit",
        "CfgAppend_": "CfgAppend",
        "CondPrice_": "CondPrice",
        "CondPercent_": "CondPercent",
        "CondTime_": "CondTime",
        "CondLoss_": "CondLoss",
        "CondTargetLoss_": "CondTargetLoss",
        "CondProfit_": "CondProfit",
        "CondTargetProfit_": "CondTargetProfit",
    }
    for key, v in row.items():
        if not key or not str(key).startswith(tuple(prefix_map.keys())):
            continue
        prefix = next(p for p in prefix_map if str(key).startswith(p))
        leaf = str(key)[len(prefix):]
        val = expand(v)
        if val is None or str(val).strip() == "":
            continue
        node = payload["create"].setdefault(prefix_map[prefix], {})
        node[leaf] = to_typed(leaf, val)
    return payload
