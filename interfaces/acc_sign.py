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

2026-09 更新：上面 300130000461 / 张三 等均为占位，实际签不了。
现已改用线上真实签署数据（见下方 REAL_ACCOUNT / REAL_SIGN）。

两处待确认（实测后据 Err/Msg 定）：
  1. 顶层键：协议文档(请求接口字段.txt 2.2.1)写 acc_sign，而 C# 样本写 AccSign。
     统一由 TOP_KEY 控制，改一行即可切换。
  2. BranchNO：协议文档未列该字段，但真实签署报文带。已加入，A003 用例专门验证
     它到底是不是必填。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, gen_account_variety, gen_fuzz, gen_cross,
                     STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL)

NAME = "acc_sign"
TITLE = "云条件单账号签署(acc_sign)"

# 顶层键：协议文档为 acc_sign，C# 样本为 AccSign，实测后按服务端实际接受值调整
TOP_KEY = "acc_sign"

# ==================== 正确账号（线上真实可用的签署数据）====================
REAL_ACCOUNT = {
    "Model": 0,                 # 0：内嵌模式
    "AccountType": 7,           # 7：客户号
    "AccAtt": 6,                # 6：期权
    "FAccount": "010100011300",  # 云单账号
}

# 签署主体信息（与 Account 配套的营业部/密码/姓名/交易账号/股东号）
REAL_SIGN = {
    "TradePwd": "123123",
    "BranchNO": "123456",
    "ClientName": "张国昌",
    "TradeAccount": "010100011300",
}
# 股东号：[ (SAccount, ExchangeNum), ... ]  1=上海 2=深圳
REAL_SHAREHOLDERS = [("A442523077", 1), ("0199908393", 2)]

FACCOUNT = REAL_ACCOUNT["FAccount"]

# 账号池统一由 _common 提供，本文件不再自带：
#   STRESS_ACCOUNT_POOL - 只含确定合法的组合，供 gen_account_variety 生成 normal 压测数据
#   REAL_ACCOUNT_POOL   - 含属性不匹配变体，供 gen_cross / gen_fuzz 生成 error、destroy
# 两者严禁混用，否则压测池会被"签不了/被拒"的数据污染。

HEADERS = [
    ("case_no",        "用例编号"),
    ("case_type",      "用例类型\n(normal/probe/error/destroy)"),
    ("case_desc",      "用例说明"),
    ("Model",          "云单运行模式(0内嵌/1独立)"),
    ("AccountType",    "账号类型(1资金/7客户号)"),
    ("AccAtt",         "渠道(0股票/6期权)"),
    ("FAccount",       "云单账号"),
    ("TradePwd",       "交易密码"),
    ("BranchNO",       "营业部号"),
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
    # ---------- normal：压测池（字段完整，账号四要素与真实账号完全匹配）----------
    #       编号    类型      说明                                Model AT AA FAccount   Pwd      BranchNO 姓名    交易账号         股东1        市1 股东2        市2 预期
    ("A001", "normal", "正确账号 签署(双股东号,完整真实数据)", 0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "主用例：模板行，字段值勿改"),
    # ---------- probe：兼容性探测（缺字段/变体，可能签不了），不计入压测指标 ----------
    ("A002", "probe",  "正确账号 不带 Model",               "", 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "省略 Model，看是否必填"),
    ("A003", "probe",  "正确账号 不带 BranchNO",           0, 7, 6, FACCOUNT, "123123", "", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "验证 BranchNO 是否必填(文档未列此字段)"),
    ("A004", "probe",  "正确账号 单股东号(沪)",            0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "", "", "只签沪市，可能签不了另一市场"),
    ("A005", "probe",  "正确账号 单股东号(深)",            0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "0199908393", 2, "", "", "只签深市"),
    ("A006", "probe",  "正确账号 不带股东号",              0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "", "", "", "", "Shareholders 为空，与 A106 对照"),
    ("A007", "probe",  "正确账号 Model=1(独立运行模式)",   1, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "覆盖 Model 字段"),
    ("A008", "probe",  "正确账号 AccAtt=0(股票渠道)",      0, 7, 0, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "渠道变体"),
    ("A009", "probe",  "正确账号 AccountType=1(资金账号)", 0, 1, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "账号类型变体"),
    ("A010", "probe",  "正确账号 FAccount 带前导空格",     0, 7, 6, " " + FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "对照：create 样本带空格，此样本不带，看中台是否 trim"),
    # ---------- 错误数据（基线仍为正确账号，只改被测字段）----------
    ("A101", "error",   "TradePwd 为空",                   0, 7, 6, FACCOUNT, "", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "期望被拒绝/Err<0"),
    ("A102", "error",   "AccountType 非法值99",            0, 99, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "期望被拒绝/Err<0"),
    ("A103", "error",   "AccAtt 非法值9",                  0, 7, 9, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "期望被拒绝/Err<0"),
    ("A104", "error",   "FAccount 为空",                   0, 7, 6, "", "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "期望被拒绝/Err<0"),
    ("A105", "error",   "TradeAccount 与 FAccount 不一致", 0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", "888888",
     "A442523077", 1, "0199908393", 2, "期望被拒绝/Err<0"),
    ("A106", "error",   "股东号 SAccount 为空",            0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "", 1, "", "", "期望被拒绝/Err<0"),
    ("A107", "error",   "ExchangeNum 非法值5",             0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 5, "0199908393", 2, "期望被拒绝/Err<0"),
    ("A108", "error",   "BranchNO 为空",                   0, 7, 6, FACCOUNT, "123123", "", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "与 A003 对照，判断必填性"),
    ("A109", "error",   "ClientName 为空",                 0, 7, 6, FACCOUNT, "123123", "123456", "", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "期望被拒绝/Err<0"),
    # ---------- 破坏测试（极端/畸形，用 token 占位，build 时展开）----------
    ("A201", "destroy", "TradePwd 超长1000字符",           0, 7, 6, FACCOUNT, "__LONG__", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "超长密码"),
    ("A202", "destroy", "ClientName 含控制字符",           0, 7, 6, FACCOUNT, "123123", "123456", "__CTRL_NAME__", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "特殊控制字符"),
    ("A203", "destroy", "FAccount 超长1000字符",           0, 7, 6, "__LONG__", "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "超长账号"),
    ("A204", "destroy", "SAccount 含非ASCII中文",          0, 7, 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "__UNI__", 1, "0199908393", 2, "非ASCII股东号"),
    ("A205", "destroy", "AccountType 传字符串'abc'",       0, "abc", 6, FACCOUNT, "123123", "123456", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "非法类型"),
    ("A206", "destroy", "BranchNO 超长1000字符",           0, 7, 6, FACCOUNT, "123123", "__LONG__", "张国昌", FACCOUNT,
     "A442523077", 1, "0199908393", 2, "超长营业部号"),
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
    "BranchNO": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__SQL__",
                 "__XSS__", "__EMOJI2__", "__UNICODE__", "__JSON__"],
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

    payload = {TOP_KEY: {"Account": account}}

    # BranchNO 在协议文档里没列，但真实签署报文带；按行值决定是否存在
    for fld in ("TradePwd", "BranchNO", "ClientName", "TradeAccount"):
        v = _expand(row.get(fld))
        if v is not None and str(v).strip() != "":
            payload[TOP_KEY][fld] = str(v)

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
        payload[TOP_KEY]["Shareholders"] = shareholders
    return payload
