# -*- coding: utf-8 -*-
"""
接口定义：modify（修改云条件单）
=================================
字段来源：../请求接口字段.txt 2.2.6
结构同 create，另加 Ref（云单引用）+ ChangedFields（修改字段数组）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, build_account, to_typed, gen_account_variety, gen_fuzz, gen_cross

NAME = "modify"
TITLE = "修改云条件单(modify)"

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("Ref", "云单引用"),
    ("CondType", "云单类型"),
    ("CondName", "云单名称"),
    ("CondDesc", "策略描述"),
    ("ValidDate", "到期日期"),
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
    ("ChangedFields", "修改字段数组(逗号分隔)"),
    ("expected", "预期结果(备注)"),
]

_BASE = ["", 1, 6, "300130000461"]

ROWS = [
    # 正常
    ["M001", "normal", "改触发价", *_BASE, "26319550", 1, "云单1", "改价", "2026-12-31",
     "10011297", 1, "0.0700", 1, False, 1, 1, 1,
     ">", "0.0700", "CondPrice.TriggerPrice", "期望 Err>=0"],
    ["M002", "normal", "改名+改价", *_BASE, "26319551", 1, "云单改名", "改", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "CondName,CondDesc", "期望 Err>=0"],
    # 错误
    ["M101", "error", "Ref 为空", *_BASE, "", 1, "云单", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "期望被拒绝"],
    ["M102", "error", "Ref 不存在", *_BASE, "99999999", 1, "云单", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "期望 Err<0"],
    # 破坏
    ["M201", "destroy", "CondName 超长", *_BASE, "26319550", 1, "__LONG__", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "超长名称"],
    ["M202", "destroy", "Ref 超长", *_BASE, "R" * 1000, 1, "云单", "描述", "",
     "10011297", 1, "0.0675", 1, False, 1, 1, 1,
     ">", "0.0675", "", "超长Ref"],
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "Ref": ["", "__SQL__", "99999999", "__CTRL__", "__EMOJI__"],
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
    "Ref": ["__LONG__", "__REFS_MANY__", "__REFS_SQL__", "__EMOJI2__"],
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
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("Ref", "__SQL__"),
    ("CondName", "__LONG__"), ("Entrust_ContractCode", "__SQL__"),
    ("Entrust_EntrustPrice", "__PRICE_NAN__"), ("AccountType", "__HUGE__"), ("Entrust_ExchangeNum", 99),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK


def build_payload(row: dict) -> dict:
    account = build_account(row)
    payload = {"modify": {"Account": account}}

    for leaf in ("Ref", "CondType", "CondName", "CondDesc", "ValidDate"):
        v = expand(row.get(leaf))
        if v is None or str(v).strip() == "":
            continue
        payload["modify"][leaf] = to_typed(leaf, v)

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
        node = payload["modify"].setdefault(prefix_map[prefix], {})
        node[leaf] = to_typed(leaf, val)

    # ChangedFields 数组
    cf = expand(row.get("ChangedFields"))
    if cf is not None and str(cf).strip() != "":
        payload["modify"]["ChangedFields"] = [s.strip() for s in str(cf).split(",") if s.strip()]
    return payload
