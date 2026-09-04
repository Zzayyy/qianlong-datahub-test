# -*- coding: utf-8 -*-
"""
接口定义：create（创建云条件单）
=================================
字段来源：../请求接口字段.txt 2.2.4
         + ../请求接口doc.txt 1.(1) 委托服务器 -> 数据中台 的真实 create 样本

2026-09 更新：原来用的 FAccount=300130000461、合约 10011297、价格 0.0675 均为占位，
线上建不出单。现全部改用真实数据：
  - 账号：_common.REAL_ACCOUNT（010100011300，客户号 7 / 期权 6 / 内嵌 0）
  - 委托 / 超价 / 下单设置 / 各类条件：_common.REAL_ENTRUST ... REAL_COND_TARGET_PROFIT
    （取值来自 doc 真实样本：合约 90007939(深)、委托价 0.7434、超价 15、数量 20、
      触发价 0.234、幅度 5.25、标的 510050 等；定时日期已顺延到未过期）

报文复杂（Account + CondType + Entrust + 各类 Cfg + 各类 Cond）。
Excel 用扁平列名 + 前缀映射嵌套结构："Entrust_ContractCode" -> Entrust.ContractCode。
每个用例只下发与 CondType 对应的那一个 Cond 对象（其余 Cond* 列留空即不下发）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, build_account, to_typed, REAL_ACCOUNT, REAL_VALID_DATE,
                     REAL_ENTRUST, REAL_CFG_EXCEED, REAL_CFG_AUTO_WITHDRAW,
                     REAL_CFG_FIXED_SPLIT, REAL_CFG_RAND_SPLIT, REAL_CFG_APPEND,
                     REAL_COND_PRICE, REAL_COND_PERCENT, REAL_COND_TIME,
                     REAL_COND_LOSS, REAL_COND_PROFIT,
                     REAL_COND_TARGET_LOSS, REAL_COND_TARGET_PROFIT,
                     STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL,
                     gen_account_variety, gen_fuzz, gen_cross)

NAME = "create"
TITLE = "创建云条件单(create)"

FACCOUNT = REAL_ACCOUNT["FAccount"]

HEADERS = [
    ("case_no", "用例编号"),
    ("case_type", "用例类型\n(normal/probe/error/destroy)"),
    ("case_desc", "用例说明"),
    ("Model", "云单运行模式(0内嵌/1独立)"),
    ("AccountType", "账号类型(1资金/7客户号)"),
    ("AccAtt", "渠道(0股票/6期权)"),
    ("FAccount", "云单账号"),
    ("CondType", "云单类型(1价格/2时间/3幅度/4合约止盈损/5标的止盈损)"),
    ("CondName", "云单名称"),
    ("CondDesc", "策略描述"),
    ("ValidDate", "到期日期(空=永久)"),
    # ---- Entrust 委托 ----
    ("Entrust_ContractCode", "合约代码"),
    ("Entrust_ExchangeNum", "市场(1沪/2深)"),
    ("Entrust_EntrustPrice", "委托价格"),
    ("Entrust_MarketOrderType", "委托方式(0限价/1对手价/15超价...)"),
    ("Entrust_CoveredType", "备兑"),
    ("Entrust_BSType", "买卖(1买/2卖)"),
    ("Entrust_OCType", "仓位(1开/2平)"),
    ("Entrust_PriceUnit", "价格最小变动单位"),
    ("Entrust_EntrustAmount", "委托数量"),
    # ---- CfgExceedPrice 超价设置 ----
    ("CfgExceedPrice_ExchangeNum", "超价-市场"),
    ("CfgExceedPrice_StockCode", "超价-标的代码"),
    ("CfgExceedPrice_StockName", "超价-标的名称"),
    ("CfgExceedPrice_PriceStepBuy", "超价-买入滑点"),
    ("CfgExceedPrice_PriceStepSell", "超价-卖出滑点"),
    ("CfgExceedPrice_PriceType", "超价-基准价类型"),
    ("CfgExceedPrice_PriceUnit", "超价-价格变动单位"),
    ("CfgExceedPrice_Decimals", "超价-小数位数"),
    # ---- CfgAutoWithdraw 自动撤单 ----
    ("CfgAutoWithdraw_WithdrawSec", "撤单-等待秒数"),
    # ---- CfgFixedSplit 固定拆单 ----
    ("CfgFixedSplit_LimitBase", "固拆-限价起始"),
    ("CfgFixedSplit_LimitStep", "固拆-限价每笔"),
    ("CfgFixedSplit_LimitInterval", "固拆-限价间隔ms"),
    ("CfgFixedSplit_MarketBase", "固拆-市价起始"),
    ("CfgFixedSplit_MarketStep", "固拆-市价每笔"),
    ("CfgFixedSplit_MarketInterval", "固拆-市价间隔ms"),
    # ---- CfgRandSplit 随机拆单 ----
    ("CfgRandSplit_LimitBase", "随拆-限价起始"),
    ("CfgRandSplit_LimitMin", "随拆-限价最小"),
    ("CfgRandSplit_LimitMax", "随拆-限价最大"),
    ("CfgRandSplit_LimitInterval", "随拆-限价间隔ms"),
    ("CfgRandSplit_MarketBase", "随拆-市价起始"),
    ("CfgRandSplit_MarketMin", "随拆-市价最小"),
    ("CfgRandSplit_MarketMax", "随拆-市价最大"),
    ("CfgRandSplit_MarketInterval", "随拆-市价间隔ms"),
    # ---- CfgAppend 追单 ----
    ("CfgAppend_MarketOrderType", "追单-委托方式"),
    ("CfgAppend_Tick", "追单-滑点"),
    ("CfgAppend_IntervalSec", "追单-间隔秒"),
    ("CfgAppend_Repeat", "追单-重复次数"),
    ("CfgAppend_EndWithdraw", "追单-未完成撤单"),
    # ---- CondPrice 价格条件 ----
    ("CondPrice_ContractCode", "价格条件-合约代码"),
    ("CondPrice_ExchangeNum", "价格条件-市场"),
    ("CondPrice_Op", "价格条件-操作符"),
    ("CondPrice_TriggerPrice", "价格条件-触发价"),
    # ---- CondPercent 幅度条件 ----
    ("CondPercent_ContractCode", "幅度条件-合约代码"),
    ("CondPercent_ExchangeNum", "幅度条件-市场"),
    ("CondPercent_Op", "幅度条件-操作符"),
    ("CondPercent_TriggerPercent", "幅度条件-触发比例"),
    # ---- CondTime 定时条件 ----
    ("CondTime_ContractCode", "时间条件-合约代码"),
    ("CondTime_ExchangeNum", "时间条件-市场"),
    ("CondTime_TriggerDate", "时间条件-触发日期YYYYMMDD"),
    ("CondTime_TriggerTime", "时间条件-触发时间HHMMSS"),
    # ---- CondLoss 按合约止损 ----
    ("CondLoss_ContractCode", "合约止损-合约代码"),
    ("CondLoss_ExchangeNum", "合约止损-市场"),
    ("CondLoss_Method", "合约止损-方式"),
    ("CondLoss_ValueType", "合约止损-值类型"),
    ("CondLoss_Value", "合约止损-值"),
    # ---- CondProfit 按合约止盈 ----
    ("CondProfit_ContractCode", "合约止盈-合约代码"),
    ("CondProfit_ExchangeNum", "合约止盈-市场"),
    ("CondProfit_Method", "合约止盈-方式"),
    ("CondProfit_ValueType", "合约止盈-值类型"),
    ("CondProfit_Value", "合约止盈-值"),
    ("CondProfit_WithdrawType", "合约止盈-回撤类型"),
    ("CondProfit_Withdraw", "合约止盈-回撤值"),
    # ---- CondTargetLoss 按标的止损 ----
    ("CondTargetLoss_StockCode", "标的止损-标的代码"),
    ("CondTargetLoss_ExchangeNum", "标的止损-市场"),
    ("CondTargetLoss_Method", "标的止损-方式"),
    ("CondTargetLoss_ValueType", "标的止损-值类型"),
    ("CondTargetLoss_Value", "标的止损-值"),
    # ---- CondTargetProfit 按标的止盈 ----
    ("CondTargetProfit_StockCode", "标的止盈-标的代码"),
    ("CondTargetProfit_ExchangeNum", "标的止盈-市场"),
    ("CondTargetProfit_Method", "标的止盈-方式"),
    ("CondTargetProfit_ValueType", "标的止盈-值类型"),
    ("CondTargetProfit_Value", "标的止盈-值"),
    ("CondTargetProfit_WithdrawType", "标的止盈-回撤类型"),
    ("CondTargetProfit_Withdraw", "标的止盈-回撤值"),
    ("expected", "预期结果(备注)"),
]

_HEAD_KEYS = [k for k, _ in HEADERS]

# ==================== 真实数据基线（doc 真实 create 样本）====================
BASE = {
    "Model": REAL_ACCOUNT["Model"],
    "AccountType": REAL_ACCOUNT["AccountType"],
    "AccAtt": REAL_ACCOUNT["AccAtt"],
    "FAccount": FACCOUNT,
    "CondType": 2,
    "CondName": "name1",
    "CondDesc": "desc1",
    "ValidDate": REAL_VALID_DATE,
}
for _blk, _vals in (("Entrust", REAL_ENTRUST), ("CfgExceedPrice", REAL_CFG_EXCEED),
                    ("CfgAutoWithdraw", REAL_CFG_AUTO_WITHDRAW),
                    ("CfgFixedSplit", REAL_CFG_FIXED_SPLIT),
                    ("CfgRandSplit", REAL_CFG_RAND_SPLIT),
                    ("CfgAppend", REAL_CFG_APPEND),
                    ("CondPrice", REAL_COND_PRICE), ("CondPercent", REAL_COND_PERCENT),
                    ("CondTime", REAL_COND_TIME), ("CondLoss", REAL_COND_LOSS),
                    ("CondProfit", REAL_COND_PROFIT),
                    ("CondTargetLoss", REAL_COND_TARGET_LOSS),
                    ("CondTargetProfit", REAL_COND_TARGET_PROFIT)):
    for _k, _v in _vals.items():
        BASE[f"{_blk}_{_k}"] = _v

_COND_BLOCKS = ("CondPrice", "CondPercent", "CondTime", "CondLoss", "CondProfit",
               "CondTargetLoss", "CondTargetProfit")
_CFG_BLOCKS = ("CfgExceedPrice", "CfgAutoWithdraw", "CfgFixedSplit", "CfgRandSplit", "CfgAppend")


def _row(no, ctype, desc, expected="", keep_cond=(), drop_cfg=(), **kw):
    """按 HEADERS 顺序生成一行。keep_cond: 保留的 Cond 块；其余 Cond* 列留空。
    drop_cfg: 不下发的下单设置块。kw: 覆盖任意字段（空串表示清空该字段）。"""
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
    # ---------- normal：压测池，5 类云单各一条真实数据 ----------
    _row("C001", "normal", "价格条件单(买开/超价,真实合约90007939)", "主用例：模板行，期望 Err>=0 返回 Ref",
         keep_cond=("CondPrice",), CondType=1, CondName="name1", CondDesc="价格触发策略"),
    _row("C002", "normal", "时间条件单(真实定时条件)", "期望 Err>=0 返回 Ref",
         keep_cond=("CondTime",), CondType=2, CondName="name2", CondDesc="定时触发"),
    _row("C003", "normal", "幅度条件单(真实幅度5.25)", "期望 Err>=0 返回 Ref",
         keep_cond=("CondPercent",), CondType=3, CondName="name3", CondDesc="幅度触发"),
    _row("C004", "normal", "按合约止盈止损(10011743)", "期望 Err>=0 返回 Ref",
         keep_cond=("CondLoss", "CondProfit"), CondType=4, CondName="name4",
         CondDesc="合约止盈止损"),
    _row("C005", "normal", "按标的止盈止损(510050)", "期望 Err>=0 返回 Ref",
         keep_cond=("CondTargetLoss", "CondTargetProfit"), CondType=5, CondName="name5",
         CondDesc="标的止盈止损"),
    # ---------- probe：字段变体，成败取决于账户状态/必填性，不计入压测指标 ----------
    _row("C006", "probe", "价格条件单 卖平(BSType=2/OCType=2)", "覆盖买卖/仓位，需持仓",
         keep_cond=("CondPrice",), CondType=1, CondName="name6",
         Entrust_BSType=2, Entrust_OCType=2),
    _row("C007", "probe", "价格条件单 不带 Model", "省略 Model，看是否必填",
         keep_cond=("CondPrice",), CondType=1, CondName="name7", Model=""),
    _row("C008", "probe", "价格条件单 Model=1(独立运行模式)", "覆盖 Model",
         keep_cond=("CondPrice",), CondType=1, CondName="name8", Model=1),
    _row("C009", "probe", "价格条件单 不带到期日(永久有效)", "ValidDate 留空，看是否必填",
         keep_cond=("CondPrice",), CondType=1, CondName="name9", ValidDate=""),
    _row("C010", "probe", "价格条件单 不带下单设置", "Cfg* 全部留空，看是否必填",
         keep_cond=("CondPrice",), CondType=1, CondName="name10",
         drop_cfg=_CFG_BLOCKS),
    _row("C011", "probe", "价格条件单 备兑(CoveredType=true)", "覆盖备兑标志，需持仓",
         keep_cond=("CondPrice",), CondType=1, CondName="name11",
         Entrust_CoveredType=True),
    # ---------- 错误 ----------
    _row("C101", "error", "CondType 非法值99", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=99, CondName="err1"),
    _row("C102", "error", "Entrust_ExchangeNum 非法值5", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName="err2", Entrust_ExchangeNum=5),
    _row("C103", "error", "CondName 为空", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName=""),
    _row("C104", "error", "价格条件 缺触发价", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName="err4", CondPrice_TriggerPrice=""),
    _row("C105", "error", "EntrustAmount 为0", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName="err5", Entrust_EntrustAmount=0),
    _row("C106", "error", "EntrustPrice 非法值abc", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName="err6", Entrust_EntrustPrice="abc"),
    _row("C107", "error", "AccountType 非法值99", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName="err7", AccountType=99),
    _row("C108", "error", "FAccount 为空", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName="err8", FAccount=""),
    _row("C109", "error", "时间条件 触发日期非法", "期望被拒绝/Err<0",
         keep_cond=("CondTime",), CondType=2, CondName="err9", CondTime_TriggerDate="2026-13-40"),
    _row("C110", "error", "ValidDate 早于今天", "期望被拒绝/Err<0",
         keep_cond=("CondPrice",), CondType=1, CondName="err10", ValidDate="2020-01-01"),
    # ---------- 破坏 ----------
    _row("C201", "destroy", "CondName 超长1000字符", "超长名称",
         keep_cond=("CondPrice",), CondName="__LONG__"),
    _row("C202", "destroy", "EntrustPrice 非法小数0.0.0", "非法价格",
         keep_cond=("CondPrice",), CondType=1, Entrust_EntrustPrice="__NAN__"),
    _row("C203", "destroy", "CondName 含emoji", "emoji名称",
         keep_cond=("CondPrice",), CondType=1, CondName="__EMOJI__"),
    _row("C204", "destroy", "ContractCode 含控制字符", "控制字符合约代码",
         keep_cond=("CondPrice",), CondType=1, Entrust_ContractCode="__CTRL__"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], accounts=STRESS_ACCOUNT_POOL,
                                  type_tag="normal", start=500)
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "CondType": [99, 9999, -1, 0, "abc", "__MAXINT__", "__HUGE__", "__HEX__"],
    "CondName": ["", "__LONG__", "__SQL__", "__XSS__"],
    "CondDesc": ["", "__LONG__", "__SQL__"],
    "ValidDate": ["__DATE_13__", "__DATE_ZERO__", "2026/01/01"],
    "Entrust_ContractCode": ["", "__LONG__", "__SQL__", "__CTRL__"],
    "Entrust_ExchangeNum": [5, 99, -1, "abc", "__MAXINT__"],
    "Entrust_EntrustPrice": ["__NAN__", "abc", "__PRICE_NEG__", "__PRICE_HUGE__", "__PRICE_SCI__"],
    "Entrust_MarketOrderType": [99, -1, "abc", "__MAXINT__"],
    "Entrust_BSType": [3, 99, -1, "abc"],
    "Entrust_OCType": [3, 99, -1, "abc"],
    "Entrust_EntrustAmount": [0, -1, "abc", "__HUGE__"],
    "CfgExceedPrice_PriceStepBuy": ["abc", "__HUGE__", "__SCI__"],
    "CfgExceedPrice_Decimals": [-1, "abc", "__HUGE__"],
    "CfgAutoWithdraw_WithdrawSec": [0, -1, "abc", "__HUGE__"],
    "CondPrice_Op": ["??", "#", ""],
    "CondPrice_TriggerPrice": ["", "__NAN__", "__PRICE_NEG__"],
    "CondPercent_TriggerPercent": ["", "abc", "__PRICE_HUGE__"],
    "CondTime_TriggerDate": ["__DATE_13__", "__DATE_ZERO__", "abc"],
    "CondTime_TriggerTime": ["999999", "abc", "25:00:00"],
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
    "CfgExceedPrice_StockCode": ["__LONG__", "__CTRL__", "__SQL__", "__EMOJI2__"],
    "CfgExceedPrice_PriceStepBuy": ["__HUGE__", "__SCI__", "__NEG__"],
    "CfgFixedSplit_LimitInterval": ["__HUGE__", "__NEG__", "abc"],
    "CfgRandSplit_LimitMax": ["__HUGE__", "abc"],
    "CfgAppend_Repeat": ["__HUGE__", "__NEG__", "abc"],
    "CondPrice_Op": ["__SQL__", "__XSS__", "__EMOJI__"],
    "CondPrice_TriggerPrice": ["__PRICE_NEG__", "__PRICE_HUGE__", "__PRICE_NAN__"],
    "CondPercent_TriggerPercent": ["__PRICE_NAN__", "__PRICE_NEG__", "__EMOJI2__"],
    "CondTime_TriggerDate": ["__DATE_13__", "__DATE_FAR__", "__DATE_TIME__"],
    "CondTime_TriggerTime": ["__LONG__", "__CTRL__", "__SQL__"],
    "CondLoss_Value": ["__PRICE_NAN__", "__PRICE_NEG__", "abc"],
    "CondTargetProfit_Value": ["__PRICE_NAN__", "__PRICE_NEG__", "abc"],
    "ValidDate": ["__DATE_13__", "__DATE_FAR__", "__DATE_TIME__"],
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__", "__XSS__", "__EMOJI2__", "__JSON__"],
    "AccountType": ["__HUGE__", "__SCI__"],
    "AccAtt": ["__HUGE__"],
}, type_tag="destroy", start=900)
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], accounts=REAL_ACCOUNT_POOL, injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("CondName", "__LONG__"), ("CondName", "__SQL__"), ("Entrust_ContractCode", "__SQL__"),
    ("Entrust_EntrustPrice", "__PRICE_NAN__"), ("AccountType", "__HUGE__"),
    ("Entrust_ExchangeNum", 99), ("CondPrice_TriggerPrice", "__PRICE_NEG__"),
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
