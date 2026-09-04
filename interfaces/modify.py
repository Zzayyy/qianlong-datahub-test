# -*- coding: utf-8 -*-
"""
接口定义：modify（修改云条件单）
=================================
字段来源：../请求接口字段.txt 2.2.6 + ../请求接口doc.txt 1.(2)

结构同 create，另加 Ref（云单引用）+ ChangedFields（修改字段数组）。

2026-09 更新：原来用的 FAccount=300130000461、Ref=26319550/26319551 均为占位，
线上改不动单。现全部改用真实数据：
  - 账号与委托/条件字段：同 create.py（_common.REAL_ACCOUNT + 真实合约 90007939 等）
  - Ref：_common.REAL_REFS[0]（doc 真实样本中 create 返回的 20260528000010）
    注意：Ref 必须是该账号下真实存在的云单，若中台报"云单不存在"，用 query 的返回回填。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, build_account, to_typed, REAL_ACCOUNT, REAL_REFS, FAKE_REF,
                     REAL_ENTRUST, STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL,
                     gen_account_variety, gen_fuzz, gen_cross)
import create as _create

NAME = "modify"
TITLE = "修改云条件单(modify)"

FACCOUNT = REAL_ACCOUNT["FAccount"]
REF1 = REAL_REFS[0]

# 表头 = create 的表头 + Ref（FAccount 之后）+ ChangedFields（末尾）
HEADERS = (_create.HEADERS[:7]
           + [("Ref", "云单引用")]
           + _create.HEADERS[7:-1]
           + [("ChangedFields", "修改字段数组(逗号分隔)"),
              ("expected", "预期结果(备注)")])

_HEAD_KEYS = [k for k, _ in HEADERS]

# 基线 = create 的真实数据基线 + Ref + ChangedFields
BASE = dict(_create.BASE)
BASE["Ref"] = REF1
BASE["ChangedFields"] = "CondPrice.TriggerPrice"

_COND_BLOCKS = _create._COND_BLOCKS
_CFG_BLOCKS = _create._CFG_BLOCKS


def _row(no, ctype, desc, expected="", keep_cond=(), drop_cfg=(), **kw):
    """按 HEADERS 顺序生成一行（同 create._row，表头多了 Ref/ChangedFields）。"""
    d = dict(BASE)
    for b in _COND_BLOCKS:
        if b in keep_cond:
            continue
        for k in list(d):
            if k.startswith(b + "_"):
                d[k] = ""
    for b in _CFG_BLOCKS:
        if b in drop_cfg:
            for k in list(d):
                if k.startswith(b + "_"):
                    d[k] = ""
    d.update(kw)
    d["case_no"], d["case_type"], d["case_desc"], d["expected"] = no, ctype, desc, expected
    return tuple(d.get(k, "") for k in _HEAD_KEYS)


# ==================== 测试数据 ====================
ROWS = [
    # ---------- normal：压测池（改真实存在的云单，账号四要素与真实账号完全匹配）----------
    _row("M001", "normal", "改触发价 CondPrice.TriggerPrice",
         "主用例：模板行，期望 Err>=0 返回 Ref", keep_cond=("CondPrice",), CondType=1,
         CondName="name1", CondPrice_TriggerPrice="0.2300",
         Entrust_EntrustPrice="0.2300", ChangedFields="CondPrice.TriggerPrice"),
    _row("M002", "normal", "改委托价 Entrust.EntrustPrice", "期望 Err>=0",
         keep_cond=("CondPrice",), CondType=1, CondName="name1",
         Entrust_EntrustPrice=REAL_ENTRUST["EntrustPrice"],
         ChangedFields="Entrust.EntrustPrice"),
    _row("M003", "normal", "改名+改描述 CondName,CondDesc", "期望 Err>=0",
         keep_cond=("CondPrice",), CondType=1, CondName="name1_mod",
         CondDesc="desc1_mod", ChangedFields="CondName,CondDesc"),
    _row("M004", "normal", "改到期日 ValidDate", "期望 Err>=0",
         keep_cond=("CondPrice",), CondType=1, CondName="name1",
         ValidDate="2026-12-31", ChangedFields="ValidDate"),
    _row("M005", "normal", "改委托数量 Entrust.EntrustAmount", "期望 Err>=0",
         keep_cond=("CondPrice",), CondType=1, CondName="name1",
         Entrust_EntrustAmount=10, ChangedFields="Entrust.EntrustAmount"),
    _row("M006", "normal", "改时间条件 CondTime", "期望 Err>=0",
         keep_cond=("CondTime",), CondType=2, CondName="name2",
         ChangedFields="CondTime.TriggerDate,CondTime.TriggerTime"),
    # ---------- 错误 ----------
    _row("M101", "error", "Ref 为空", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, Ref=""),
    _row("M102", "error", "Ref 不存在", "云单不存在，期望 Err<0",
         keep_cond=("CondPrice",), CondType=1, Ref=FAKE_REF),
    _row("M103", "error", "ChangedFields 为空", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, ChangedFields=""),
    _row("M104", "error", "CondType 非法值99", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=99),
    _row("M105", "error", "FAccount 为空", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, FAccount=""),
    _row("M106", "error", "价格条件 触发价为空", "与 ChangedFields 不一致，期望 Err<0",
         keep_cond=("CondPrice",), CondType=1, CondPrice_TriggerPrice=""),
    # ---------- 破坏 ----------
    _row("M201", "destroy", "CondName 超长1000字符", "超长名称",
         keep_cond=("CondPrice",), CondName="__LONG__"),
    _row("M202", "destroy", "Ref 超长1000字符", "超长Ref",
         keep_cond=("CondPrice",), Ref="__LONG__"),
    _row("M203", "destroy", "Ref 含SQL注入", "注入Ref",
         keep_cond=("CondPrice",), Ref="__SQL__"),
    _row("M204", "destroy", "ChangedFields 含控制字符", "控制字符字段路径",
         keep_cond=("CondPrice",), ChangedFields="__CTRL__"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], accounts=STRESS_ACCOUNT_POOL,
                                  type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "Ref": ["", "__SQL__", FAKE_REF, "__CTRL__", "__EMOJI__"],
    "ChangedFields": ["", "abc", "NotExist.Field", "__SQL__"],
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
    "ChangedFields": ["__LONG__", "__CTRL__", "__EMOJI2__", "__JSON__"],
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
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], accounts=REAL_ACCOUNT_POOL, injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("Ref", "__SQL__"),
    ("CondName", "__LONG__"), ("Entrust_ContractCode", "__SQL__"),
    ("Entrust_EntrustPrice", "__PRICE_NAN__"), ("AccountType", "__HUGE__"),
    ("Entrust_ExchangeNum", 99), ("ChangedFields", "__CTRL__"),
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
