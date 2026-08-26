# -*- coding: utf-8 -*-
"""接口定义的公共辅助工具"""

# 破坏测试 token -> 真实数据（Excel 存不了控制字符/超长串）
TOKEN_MAP = {
    "__LONG__": "F" * 1000,
    "__LONG_PWD__": "P" * 1000,
    "__CTRL__": "999993\x00\x01\x02",
    "__CTRL_NAME__": "张\x00\x01三",
    "__UNI__": "账号测试中文",
    "__MAXINT__": "2147483647",
    "__NEGINT__": "-2147483648",
    "__NAN__": "0.0.0",
    "__NULL_STR__": "None",
    "__EMOJI__": "\U0001F600" * 10,
}

# ===== 扩展破坏 token：越多越畸形越好 =====
TOKEN_MAP.update({
    # 超长类
    "__LONG10__": "F" * 10000,
    "__LONG100__": "F" * 32000,  # 接近 Excel 单元格 32767 字符上限（再大 openpyxl 会报错）
    "__LONG_PWD10__": "P" * 10000,
    # 控制字符 / 不可见字符
    "__NULLBYTE__": "abc\x00def",
    "__TAB__": "a\tb\tc",
    "__NEWLINE__": "line1\nline2\r\nline3",
    "__RTL__": "\u202e\u202dmoc.qq\u202c",
    "__ZWSP__": "a\u200bb\u200cc",
    "__BOM__": "\ufeffhello",
    # 注入类（SQL / XSS / 格式化）
    "__SQL__": "'; DROP TABLE users; --",
    "__SQL2__": "1 OR 1=1 --",
    "__XSS__": "<script>alert(1)</script>",
    "__XSS2__": "\"><img src=x onerror=alert(1)>",
    "__FMT__": "%s%n%p%n",
    "__PATH__": "../../etc/passwd",
    # 数值畸形
    "__ZERO__": "0",
    "__NEG__": "-999999",
    "__HUGE__": "999999999999999999999999999999",
    "__HEX__": "0x1F",
    "__OCT__": "0o17",
    "__SCI__": "1e100",
    "__LEAD0__": "007",
    "__FLOATINF__": "inf",
    "__FLOATNAN__": "NaN",
    "__FLOATNEG__": "-inf",
    "__SPACE__": "   ",
    "__BOOL_WEIRD__": "2",
    "__BOOL_STR__": "TRUE",
    "__BOOL_CN__": "是",
    # 文本特殊
    "__EMOJI2__": "\U0001F4A9" * 50,
    "__UNICODE__": "\U0001D54F\U0001D550\U0001D551",
    "__JSON__": '{"bad":"json"}',
    "__REPLACE_NULL__": "null",
    "__XML__": "<?xml version='1.0'?><a>",
    # 日期畸形
    "__DATE_13__": "2026-13-40",
    "__DATE_ZERO__": "00000000",
    "__DATE_NINE__": "99999999",
    "__DATE_SLASH__": "2026/01/01",
    "__DATE_UNIX0__": "19700101",
    "__DATE_FAR__": "99991231",
    "__DATE_YEAR__": "2026-00-00",
    "__DATE_TIME__": "2026-01-01 99:99:99",
    # 价格畸形
    "__PRICE_NEG__": "-0.050",
    "__PRICE_HUGE__": "999999999999.99",
    "__PRICE_SCI__": "1e50",
    "__PRICE_NAN__": "NaN",
    "__PRICE_INF__": "inf",
    "__PRICE_NEGINF__": "-inf",
    "__PRICE_STR__": "abc",
    # Refs 数组畸形
    "__REFS_MANY__": ",".join([f"26319{i:04d}" for i in range(500)]),
    "__REFS_DUP__": "26319550,26319550,26319550,26319550",
    "__REFS_SPACE__": " 26319550 , 26319551 , 26319552 ",
    "__REFS_SQL__": "26319550'; DROP TABLE x;--",
    "__REFS_EMOJI__": "\U0001F600" * 20,
})

# 按叶子名区分的 int 字段
INT_LEAVES = {
    "Model", "AccountType", "AccAtt", "ExchangeNum", "CondType",
    "MarketOrderType", "BSType", "OCType", "EntrustAmount",
    "PriceStepBuy", "PriceStepSell", "PriceType", "Decimals",
    "WithdrawSec", "LimitBase", "LimitStep", "LimitInterval",
    "MarketBase", "MarketStep", "MarketInterval",
    "LimitMin", "LimitMax", "MarketMin", "MarketMax",
    "Tick", "IntervalSec", "Repeat", "Method", "ValueType",
    "WithdrawType", "Mode", "NtType", "Count", "Start", "End",
}

# 按叶子名区分的 bool 字段
BOOL_LEAVES = {"CoveredType", "EndWithdraw", "Removed"}


def expand(v):
    """token 展开成破坏数据；普通值原样返回。"""
    if v is None:
        return None
    s = str(v).strip()
    return TOKEN_MAP.get(s, v)


def to_typed(leaf, v):
    """按字段名将值转为 int/bool/str。"""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    if leaf in BOOL_LEAVES:
        if s.lower() in ("true", "1", "yes"):
            return True
        if s.lower() in ("false", "0", "no"):
            return False
        return s
    if leaf in INT_LEAVES:
        try:
            return int(s)
        except (ValueError, TypeError):
            return s
    return s


def build_account(row):
    """从行构造 Account 对象。空值省略；非法数字保留字符串。"""
    account = {}
    for leaf in ("Model", "AccountType", "AccAtt", "FAccount"):
        v = expand(row.get(leaf))
        if v is None or str(v).strip() == "":
            continue
        if leaf in INT_LEAVES:
            try:
                account[leaf] = int(v)
            except (ValueError, TypeError):
                account[leaf] = str(v)
        else:
            account[leaf] = str(v)
    return account


def set_path(obj, dotted_key, value):
    """按点路径设置嵌套字段，如 "Entrust.ContractCode" -> obj["Entrust"]["ContractCode"]"""
    parts = str(dotted_key).split(".")
    node = obj
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def apply_dotted(row, payload_root, top_key, skip_keys=()):
    """把行里所有带 '.' 的列按路径写入报文。skip_keys 用于排除已在别处处理的列。"""
    for key, v in row.items():
        if key in skip_keys or not key or "." not in str(key):
            continue
        if v is None or str(v).strip() == "":
            continue
        leaf = str(key).rsplit(".", 1)[1]
        set_path(payload_root.setdefault(top_key, {}), key, to_typed(leaf, expand(v)))


# ==================== 批量数据生成（让多线程压测更有意义）====================

# 多账号池：覆盖资金/客户号、股票/期权、真实与虚拟账号，用于制造并发负载
ACCOUNT_POOL = [
    ("999993", 1, 6, ""),
    ("999992", 1, 6, ""),
    ("999997", 1, 6, ""),
    ("999989", 1, 6, ""),
    ("999994", 1, 6, ""),
    ("1000004", 1, 6, ""),
    ("888888", 1, 6, ""),
    ("600100", 1, 6, ""),
    ("200001", 1, 6, ""),
    ("300130000461", 1, 6, ""),
    ("12345679", 7, 7, ""),
    ("12345679", 7, 0, ""),
    ("999997", 7, 0, ""),
    ("999990", 7, 0, ""),
    ("999989", 7, 0, ""),
    ("1000001", 7, 0, ""),
    ("555555", 1, 6, "0"),
    ("666666", 7, 7, "0"),
]


def _col_index(headers, key):
    for i, (k, _) in enumerate(headers):
        if k == key:
            return i
    raise KeyError(f"列 {key} 不在表头中")


def gen_account_variety(headers, template, accounts=ACCOUNT_POOL,
                        type_tag="normal", start=500):
    """多账号用例：把 template 中账号相关列替换为池子里的值，制造并发负载。

    accounts: [(FAccount, AccountType, AccAtt, Model), ...]
    返回完整宽度的行列表（元组）。
    """
    base = list(template)
    keys = dict(headers)
    out = []
    n = start
    for facct, at, aa, model in accounts:
        row = base[:]
        row[_col_index(headers, "case_no")] = f"{type_tag[0].upper()}{n:03d}"
        row[_col_index(headers, "case_type")] = type_tag
        row[_col_index(headers, "case_desc")] = f"{type_tag} 账号{facct}"
        for key, v in (("FAccount", facct), ("AccountType", at),
                       ("AccAtt", aa), ("Model", model)):
            if key in keys:
                row[_col_index(headers, key)] = v
        out.append(tuple(row))
        n += 1
    return out


def gen_fuzz(headers, template, fuzz_by_key, type_tag="destroy", start=900):
    """字段级破坏/错误：对 template 的每一个 fuzz 字段逐一替换其值。

    fuzz_by_key: {列名: [值 或 (值, 描述), ...]}
    每 (字段, 值) 生成一行（基于 template 拷贝，只改该列），用于覆盖大量畸形输入。
    """
    base = list(template)
    out = []
    n = start
    for col, vals in fuzz_by_key.items():
        ci = _col_index(headers, col)
        for item in vals:
            if isinstance(item, tuple):
                val, desc = item
            else:
                val, desc = item, f"{col}={item!r}"
            row = base[:]
            row[_col_index(headers, "case_no")] = f"{type_tag[0].upper()}{n:03d}"
            row[_col_index(headers, "case_type")] = type_tag
            row[_col_index(headers, "case_desc")] = desc
            row[ci] = val
            out.append(tuple(row))
            n += 1
    return out


def gen_cross(headers, template, accounts=ACCOUNT_POOL, injects=(),
              type_tag="destroy", start=300):
    """交叉破坏：对每个 (账号, 注入) 生成一行，在账号模板上替换指定列。

    injects: [(列名, 值), ...]  例如 [("FAccount", "__LONG__"), ("CondName", "__SQL__")]
    返回 len(accounts) * len(injects) 行，体积大且破坏性强。
    """
    base = list(template)
    keys = dict(headers)
    out = []
    n = start
    for facct, at, aa, model in accounts:
        for col, val in injects:
            row = base[:]
            row[_col_index(headers, "case_no")] = f"{type_tag[0].upper()}{n:03d}"
            row[_col_index(headers, "case_type")] = type_tag
            row[_col_index(headers, "case_desc")] = f"{type_tag} 账号{facct} 注入{col}={val}"
            for key, v in (("FAccount", facct), ("AccountType", at),
                           ("AccAtt", aa), ("Model", model)):
                if key in keys:
                    row[_col_index(headers, key)] = v
            row[_col_index(headers, col)] = val
            out.append(tuple(row))
            n += 1
    return out
