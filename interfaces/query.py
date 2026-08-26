# -*- coding: utf-8 -*-
"""
接口定义：query（查询云条件单）
================================
字段来源：../请求接口字段.txt + 192.168.1.137 Redis DataHub_req_stream 真实样本

真实 query 报文格式：
  {"query":{"Account":{"AccountType":1,"AccAtt":6,"FAccount":"999994"},
            "BeginDate":"20260101","EndDate":"20261231"}}

每个接口文件需提供：
  NAME    - 接口名（用于生成器/发送器定位）
  HEADERS - Excel 表头 [(key, 中文说明), ...]
  ROWS    - 测试数据（make_excel.py 用它生成 xlsx）
  build_payload(row) -> dict  - 把 Excel 一行转成报文字典（发送器用）
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import expand, gen_account_variety, gen_fuzz, gen_cross

NAME = "query"
TITLE = "查询云条件单(query)"

HEADERS = [
    ("case_no",       "用例编号"),
    ("case_type",     "用例类型\n(normal/error/destroy)"),
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
    # ---------- 正常数据 ----------
    ("Q001", "normal",  "资金账号999993 查询全年(带横线日期)", "", 1, 6, "999993", "2026-01-01", "2026-12-31", "期望 Err>=0 返回条件单列表"),
    ("Q002", "normal",  "资金账号999992 查询全年",             "", 1, 6, "999992", "2026-01-01", "2026-12-31", "期望 Err>=0"),
    ("Q003", "normal",  "资金账号999997 查询全年",             "", 1, 6, "999997", "2026-01-01", "2026-12-31", "期望 Err>=0"),
    ("Q004", "normal",  "资金账号999989 查询全年",             "", 1, 6, "999989", "2026-01-01", "2026-12-31", "期望 Err>=0"),
    ("Q005", "normal",  "资金账号300130000461 查询",           "", 1, 6, "300130000461", "2026-01-01", "2026-12-31", "真实签到账号"),
    ("Q006", "normal",  "资金账号999993 查询全年(无横线日期)",  "", 1, 6, "999993", "20260101", "20261231", "验证无横线日期格式"),
    ("Q007", "normal",  "资金账号1000004 查询",                "", 1, 6, "1000004", "2026-01-01", "2026-12-31", ""),
    ("Q008", "normal",  "资金账号999994 查指定日期",           "", 1, 6, "999994", "2026-08-01", "2026-08-31", "只查当月"),
    ("Q009", "normal",  "资金账号888888 查询",                 "", 1, 6, "888888", "2026-01-01", "2026-12-31", ""),
    ("Q010", "normal",  "资金账号999993 不限制日期",           "", 1, 6, "999993", "", "", "BeginDate/EndDate 留空"),
    ("Q011", "normal",  "客户号12345679 查询全年(AccAtt=7)",   "", 7, 7, "12345679", "2026-01-01", "2026-12-31", "客户号类型"),
    ("Q012", "normal",  "客户号12345679 账户查询(AccAtt=7)",   "", 7, 7, "12345679", "", "", "acc_query 类型(无日期)"),
    ("Q013", "normal",  "客户号999997 查询全年(AccAtt=0)",     "", 7, 0, "999997", "2026-01-01", "2026-12-31", "客户号+股票渠道"),
    ("Q014", "normal",  "客户号999990 查询全年(AccAtt=0)",     "", 7, 0, "999990", "2026-01-01", "2026-12-31", ""),
    ("Q015", "normal",  "客户号999989 查询全年(AccAtt=0)",     "", 7, 0, "999989", "2026-01-01", "2026-12-31", ""),
    ("Q016", "normal",  "客户号1000001 查询全年(AccAtt=0)",    "", 7, 0, "1000001", "2026-01-01", "2026-12-31", ""),
    ("Q017", "normal",  "资金账号999993 带Model=0查询",        "0", 1, 6, "999993", "2026-01-01", "2026-12-31", "覆盖 Model 字段"),
    ("Q018", "normal",  "客户号12345679 带Model=0(AccAtt=7)",  "0", 7, 7, "12345679", "2026-01-01", "2026-12-31", "覆盖 Model 字段(线上出现)"),
    # ---------- 错误数据（接口校验）----------
    ("Q101", "error",   "AccountType 非法值99",              "", 99, 6, "999993", "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q102", "error",   "AccAtt 非法值9",                    "", 1, 9, "999993", "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q103", "error",   "FAccount 为空",                     "", 1, 6, "", "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q104", "error",   "日期格式非法 2026/01/01",           "", 1, 6, "999993", "2026/01/01", "2026-12-31", "期望被拒绝/Err<0"),
    ("Q105", "error",   "BeginDate 晚于 EndDate",            "", 1, 6, "999993", "2026-12-31", "2026-01-01", "期望被拒绝/Err<0"),
    ("Q106", "error",   "AccountType 传字符串'abc'",         "", "abc", 6, "999993", "2026-01-01", "2026-12-31", "期望被拒绝/Err<0"),
    # ---------- 破坏测试（极端/畸形，用 token 占位，build 时展开成真实数据）----------
    ("Q201", "destroy", "FAccount 超长1000字符",             "", 1, 6, "__LONG__", "2026-01-01", "2026-12-31", "超长字段压测"),
    ("Q202", "destroy", "FAccount 含特殊控制字符",           "", 1, 6, "__CTRL__", "2026-01-01", "2026-12-31", "特殊字符"),
    ("Q203", "destroy", "FAccount 含非ASCII中文",            "", 1, 6, "__UNI__", "2026-01-01", "2026-12-31", "非ASCII"),
    ("Q204", "destroy", "AccountType 极大值2147483647",      "", "__MAXINT__", 6, "999993", "2026-01-01", "2026-12-31", "极大数值"),
]

# ==================== 批量扩展：更多正常/错误/破坏数据（让多线程压测更有意义）====================
_ROWS_BULK = []
# 多账号正常查询，制造并发负载
_ROWS_BULK += gen_account_variety(HEADERS, ROWS[0], type_tag="normal", start=500)
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
_ROWS_BULK += gen_cross(HEADERS, ROWS[0], injects=[
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
