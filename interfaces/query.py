# -*- coding: utf-8 -*-
"""
接口定义：query（查询云条件单）
================================
字段来源：../请求接口字段.txt + 192.168.1.137 Redis DataHub_req_stream 真实样本

真实 query 报文格式：
  {"query":{"Account":{"AccountType":1,"AccAtt":6,"FAccount":"999994"},
            "BeginDate":"20260101","EndDate":"20261231"}}

2026-09 更新：下列 999994 等账号均为占位，实际不可查。
现已统一改用线上真实可用的云单账号（见下方 REAL_ACCOUNT，与 acc_sign.py 保持一致）。

每个接口文件需提供：
  NAME    - 接口名（用于生成器/发送器定位）
  HEADERS - Excel 表头 [(key, 中文说明), ...]
  ROWS    - 测试数据（make_excel.py 用它生成 xlsx）
  build_payload(row) -> dict  - 把 Excel 一行转成报文字典（发送器用）
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (expand, gen_account_variety, gen_fuzz, gen_cross,
                     STRESS_ACCOUNT_POOL, REAL_ACCOUNT_POOL)

NAME = "query"
TITLE = "查询云条件单(query)"

# ==================== 正确账号（线上真实可用的云单账号）====================
# 来源：真实 create 报文中抓取的 Account 段，是云单账号的唯一标识。
# 本文件所有用例（含错误/破坏用例的基线）都基于它构造，只改被测字段。
# 注：create 样本里 FAccount 写作 " 010100011300"（带 1 个前导空格），
#     acc_sign 样本里是不带空格的 "010100011300"。以 acc_sign 为准取不带空格，
#     带空格版本作为对照用例 Q008 单独验证中台是否 trim。
REAL_ACCOUNT = {
    "Model": 0,                 # 0：内嵌模式
    "FAccount": "010100011300",  # 云单账号
    "AccountType": 7,           # 7：客户号
    "AccAtt": 6,                # 6：期权
}

FACCOUNT = REAL_ACCOUNT["FAccount"]

# 账号池统一由 _common 提供，本文件不再自带：
#   STRESS_ACCOUNT_POOL - 只含确定合法的组合，供 gen_account_variety 生成 normal 压测数据
#   REAL_ACCOUNT_POOL   - 含属性不匹配变体，供 gen_cross / gen_fuzz 生成 error、destroy
# 两者严禁混用，否则压测池会被"查不到/被拒"的数据污染。

HEADERS = [
    ("case_no",       "用例编号"),
    ("case_type",     "用例类型\n(normal/probe/error/destroy)"),
    ("case_desc",     "用例说明"),
    ("Model",         "云单运行模式(0内嵌/1独立)"),
    ("AccountType",   "账号类型(1资金/7客户号)"),
    ("AccAtt",        "渠道(0股票/6期权)"),
    ("FAccount",      "云单账号"),
    ("BeginDate",     "开始日期(YYYY-MM-DD)"),
    ("EndDate",       "结束日期(YYYY-MM-DD)"),
    ("expected",      "预期结果(备注)"),
]

# ==================== 测试数据 ====================
# case_type: normal=正常, error=错误数据(接口校验), destroy=破坏测试(极端/畸形)
ROWS = [
    # ---------- 正常数据（全部基于 REAL_ACCOUNT）----------
    # ---------- normal：压测池 ----------
    # 账号四要素固定为合法基线（Model=0 / AccountType=7 客户号 / AccAtt=6 期权 /
    # FAccount 无空格），与 REAL_ACCOUNT 完全一致；日期均为合法 YYYY-MM-DD 且 Begin<=End。
    # 压测需要的"变化"只放在日期区间上——改账号属性会让请求走不到业务主链路，
    # 统计出的吞吐/响应时间/字节数全是假的。
    ("Q001", "normal", "全年(基准主用例)",       "0", 7, 6, FACCOUNT, "2026-01-01", "2026-12-31", "模板行：被所有批量用例克隆，字段值勿改"),
    ("Q002", "normal", "上半年",                 "0", 7, 6, FACCOUNT, "2026-01-01", "2026-06-30", "期望 Err>=0 返回条件单列表"),
    ("Q003", "normal", "下半年",                 "0", 7, 6, FACCOUNT, "2026-07-01", "2026-12-31", "期望 Err>=0 返回条件单列表"),
    ("Q004", "normal", "一季度",                 "0", 7, 6, FACCOUNT, "2026-01-01", "2026-03-31", "期望 Err>=0 返回条件单列表"),
    ("Q005", "normal", "二季度",                 "0", 7, 6, FACCOUNT, "2026-04-01", "2026-06-30", "期望 Err>=0 返回条件单列表"),
    ("Q006", "normal", "三季度",                 "0", 7, 6, FACCOUNT, "2026-07-01", "2026-09-30", "期望 Err>=0 返回条件单列表"),
    ("Q007", "normal", "四季度",                 "0", 7, 6, FACCOUNT, "2026-10-01", "2026-12-31", "期望 Err>=0 返回条件单列表"),
    ("Q008", "normal", "当月",                   "0", 7, 6, FACCOUNT, "2026-09-01", "2026-09-30", "期望 Err>=0 返回条件单列表"),
    ("Q009", "normal", "两个月窗口",             "0", 7, 6, FACCOUNT, "2026-08-01", "2026-09-30", "期望 Err>=0 返回条件单列表"),
    ("Q010", "normal", "滚动一年(跨年)",         "0", 7, 6, FACCOUNT, "2025-10-01", "2026-09-30", "期望 Err>=0 返回条件单列表"),
    # ---------- probe：兼容性探测，结果不确定，不计入压测指标 ----------
    ("Q011", "probe",  "无横线日期 20260101(抓包原格式)", "0", 7, 6, FACCOUNT, "20260101", "20261231", "验证中台是否接受无横线格式"),
    ("Q012", "probe",  "不带日期",                "0", 7, 6, FACCOUNT, "", "", "留空，看是否退化为全量查询（返回包会明显偏大）"),
    ("Q013", "probe",  "省略 Model",             "",  7, 6, FACCOUNT, "2026-01-01", "2026-12-31", "看 Model 是否必填"),
    ("Q014", "probe",  "Model=1(独立运行模式)",  "1", 7, 6, FACCOUNT, "2026-01-01", "2026-12-31", "看 Model=1 是否被接受"),
    ("Q015", "probe",  "FAccount 带前导空格",     "0", 7, 6, " " + FACCOUNT, "2026-01-01", "2026-12-31", "对照 create 样本：看中台是否 trim"),
    ("Q016", "probe",  "AccAtt=0(股票渠道)",     "0", 7, 0, FACCOUNT, "2026-01-01", "2026-12-31", "期权账号配股票渠道，大概率空结果"),
    ("Q017", "probe",  "AccountType=1(资金账号)", "0", 1, 6, FACCOUNT, "2026-01-01", "2026-12-31", "客户号配资金账号类型，大概率空结果/被拒"),

    # ---------- 错误数据（接口校验，基线仍是正确账号，只改被测字段）----------
    ("Q101", "error",   "AccountType 非法值99",              "0", 99, 6, FACCOUNT, "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q102", "error",   "AccAtt 非法值9",                    "0", 7, 9, FACCOUNT, "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q103", "error",   "FAccount 为空",                     "0", 7, 6, "", "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q104", "error",   "日期格式非法 2026/01/01",           "0", 7, 6, FACCOUNT, "2026/01/01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q105", "error",   "BeginDate 晚于 EndDate",            "0", 7, 6, FACCOUNT, "2026-12-31", "2026-01-01", "期望被拒绝/Err<0"),
    ("Q106", "error",   "AccountType 传字符串'abc'",         "0", "abc", 6, FACCOUNT, "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    # ---------- 破坏测试（极端/畸形，用 token 占位，build 时展开成真实数据）----------
    ("Q201", "destroy", "FAccount 超长1000字符",             "0", 7, 6, "__LONG__", "2026-01-01", "2026-12-31", "超长字段压测"),
    ("Q202", "destroy", "FAccount 含特殊控制字符",           "0", 7, 6, "__CTRL__", "2026-01-01", "2026-12-31", "特殊字符"),
    ("Q203", "destroy", "FAccount 含非ASCII中文",            "0", 7, 6, "__UNI__", "2026-01-01", "2026-12-31", "非ASCII"),
    ("Q204", "destroy", "AccountType 极大值2147483647",      "0", "__MAXINT__", 6, FACCOUNT, "2026-01-01", "2026-12-31", "极大数值"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
# 正确账号的多变体并发查询，制造并发负载
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], accounts=STRESS_ACCOUNT_POOL,
                                  type_tag="normal", start=500)
# 字段级错误数据（接口校验）
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "AccountType": [99, 9999, -1, 0, "abc", "1.5", "__MAXINT__", "__NEGINT__", "__HUGE__",
                    "__HEX__", "__OCT__", "__SCI__", "__LEAD0__", "__ZERO__", "__BOOL_WEIRD__",
                    "__FLOATINF__", "__FLOATNAN__"],
    "AccAtt": [9, 99, -1, "abc", "__MAXINT__", "__ZERO__", "__BOOL_WEIRD__"],
    "FAccount": ["", "   ", "__LONG__", "__CTRL__", "__UNI__", "__SQL__", "__XSS__",
                 "__NULL_STR__", "__JSON__", "__EMOJI__", "__UNICODE__", "abc", "__NULLBYTE__"],
    "BeginDate": ["__DATE_13__", "__DATE_ZERO__", "__DATE_NINE__", "__DATE_SLASH__",
                  "__DATE_UNIX0__", "__DATE_YEAR__", "__DATE_TIME__", "2026/01/01"],
    "EndDate": ["__DATE_13__", "__DATE_ZERO__", "__DATE_NINE__", "__DATE_SLASH__",
                "__DATE_UNIX0__", "__DATE_YEAR__", "__DATE_TIME__"],
    "Model": ["abc", "__MAXINT__", "__BOOL_WEIRD__", "__ZERO__"],
}, type_tag="error", start=700)
# 字段级破坏数据（极端/畸形）
_ROWS_BULK += gen_fuzz(HEADERS, ROWS[0], {
    "FAccount": ["__LONG10__", "__LONG100__", "__CTRL__", "__NULLBYTE__", "__TAB__",
                 "__NEWLINE__", "__RTL__", "__ZWSP__", "__BOM__", "__SQL__", "__XSS__",
                 "__FMT__", "__PATH__", "__EMOJI2__", "__UNICODE__", "__JSON__",
                 "__REPLACE_NULL__", "999993\x00\x01"],
    "AccountType": ["__HUGE__", "__SCI__", "__HEX__", "__FLOATINF__", "__FLOATNAN__", "__NEG__"],
    "AccAtt": ["__HUGE__", "__SCI__", "__NEGINT__"],
    "BeginDate": ["__DATE_13__", "__DATE_FAR__", "__DATE_TIME__", "__DATE_ZERO__"],
    "EndDate": ["__DATE_13__", "__DATE_FAR__", "__DATE_TIME__", "__DATE_ZERO__"],
    "Model": ["__MAXINT__", "__NEGINT__", "__HUGE__"],
}, type_tag="destroy", start=900)
# 账号 × 注入 交叉破坏，体积大且破坏性强
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], accounts=REAL_ACCOUNT_POOL, injects=[
    ("FAccount", "__LONG__"), ("FAccount", "__CTRL__"), ("FAccount", "__SQL__"),
    ("FAccount", "__EMOJI2__"), ("AccountType", "__HUGE__"), ("AccAtt", 99),
    ("BeginDate", "__DATE_13__"), ("EndDate", "__DATE_FAR__"),
], type_tag="destroy", start=300)
ROWS = ROWS + _ROWS_BULK

# ==================== 报文构造 ====================
_INT_FIELDS = ("Model", "AccountType", "AccAtt")

# 破坏测试 token 统一由 _common.TOKEN_MAP 提供；保留 _expand 别名给 build_payload
_expand = expand


def build_payload(row: dict) -> dict:
    """Excel 一行 -> 报文字典。空值省略；非法数字保留字符串（构造错误/破坏数据）。"""
    account = {}
    for fld in _INT_FIELDS:
        v = _expand(row.get(fld))
        if v is None or str(v).strip() == "":
            continue
        try:
            account[fld] = int(v)
        except (ValueError, TypeError):
            account[fld] = str(v)   # 非法类型原样保留，制造错误数据
    faccount = _expand(row.get("FAccount"))
    if faccount is not None and str(faccount).strip() != "":
        account["FAccount"] = str(faccount)
    payload = {"query": {"Account": account}}
    for fld in ("BeginDate", "EndDate"):
        v = row.get(fld)
        if v is not None and str(v).strip() != "":
            payload["query"][fld] = str(v)
    return payload
