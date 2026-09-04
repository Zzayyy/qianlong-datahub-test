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
    # Refs 数组畸形（基于真实 Ref 变形）
    "__REFS_MANY__": ",".join([f"2026052800{i:04d}" for i in range(500)]),
    "__REFS_DUP__": "20260528000010,20260528000010,20260528000010,20260528000010",
    "__REFS_SPACE__": " 20260528000010 , 20260604000001 ",
    "__REFS_SQL__": "20260528000010'; DROP TABLE x;--",
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

# ==================== 线上真实数据（与 acc_sign.py / query.py 保持一致）====================
# 来源：192.168.1.137 Redis DataHub_req_stream 真实签署报文 + 请求接口doc.txt 真实 create 样本
REAL_ACCOUNT = {
    "Model": 0,                  # 0：内嵌模式
    "AccountType": 7,            # 7：客户号
    "AccAtt": 6,                 # 6：期权
    "FAccount": "010100011300",  # 云单账号
}

# 签署主体信息（与 Account 配套的密码/营业部/姓名/交易账号）
REAL_SIGN = {
    "TradePwd": "123123",
    "BranchNO": "123456",
    "ClientName": "张国昌",
    "TradeAccount": "010100011300",
}

# 股东号：[ (SAccount, ExchangeNum), ... ]  1=上海 2=深圳
REAL_SHAREHOLDERS = [("A442523077", 1), ("0199908393", 2)]

# 云单引用：doc 真实样本中出现过的 Ref（create 返回 20260528000010 / remove 使用 20260604000001）
# 注意：Ref 必须是该账号下真实存在的云单，若中台返回"不存在"，用 query 结果回填即可。
REAL_REFS = ["20260528000010", "20260604000001"]
# 不存在的引用（错误用例专用，格式与真实 Ref 一致）
FAKE_REF = "20991231000000"

# 真实委托/条件/下单设置：请求接口doc.txt 1.(1) 委托服务器 -> 数据中台 的 create 样本
REAL_ENTRUST = {
    "ContractCode": "90007939",   # 合约代码
    "ExchangeNum": 2,             # 市场 2=深圳
    "EntrustPrice": "0.7434",     # 委托价格
    "MarketOrderType": 15,        # 委托方式 15=超价
    "CoveredType": False,         # 非备兑
    "BSType": 1,                  # 买
    "OCType": 1,                  # 开仓
    "PriceUnit": "0.0001",        # 价格最小变动单位
    "EntrustAmount": 20,          # 委托数量
}
REAL_CFG_EXCEED = {
    "ExchangeNum": 2,
    "StockCode": "90007939",      # 标的代码
    "StockName": "50ETF",         # 标的名称
    "PriceStepBuy": -1,           # 买入滑点
    "PriceStepSell": 1,           # 卖出滑点
    "PriceType": 0,               # 基准价类型 0=限价
    "PriceUnit": "0.0001",
    "Decimals": 4,
}
REAL_CFG_AUTO_WITHDRAW = {"WithdrawSec": 10}
REAL_CFG_FIXED_SPLIT = {"LimitBase": 50, "LimitStep": 50, "LimitInterval": 300,
                        "MarketBase": 10, "MarketStep": 10, "MarketInterval": 300}
REAL_CFG_RAND_SPLIT = {"LimitBase": 1, "LimitMin": 1, "LimitMax": 5, "LimitInterval": 300,
                       "MarketBase": 1, "MarketMin": 1, "MarketMax": 5, "MarketInterval": 300}
REAL_CFG_APPEND = {"MarketOrderType": 15, "Tick": 2, "IntervalSec": 300,
                   "Repeat": 2, "EndWithdraw": False}
REAL_COND_PRICE = {"ContractCode": "90007939", "ExchangeNum": 2,
                   "Op": ">", "TriggerPrice": "0.234"}
REAL_COND_PERCENT = {"ContractCode": "90007939", "ExchangeNum": 2,
                     "Op": ">", "TriggerPercent": "5.25"}
# 定时条件：日期取当前之后（doc 样本 20260813 已过期）
REAL_COND_TIME = {"ContractCode": "90007939", "ExchangeNum": 2,
                  "TriggerDate": "20260910", "TriggerTime": "135100"}
# 按合约止盈止损（doc 样本合约 10011743，沪市）
REAL_COND_LOSS = {"ContractCode": "10011743", "ExchangeNum": 1,
                  "Method": 1, "ValueType": 1, "Value": "0.0675"}
REAL_COND_PROFIT = {"ContractCode": "10011743", "ExchangeNum": 1, "Method": 1,
                    "ValueType": 1, "Value": "0.0675", "WithdrawType": 2, "Withdraw": "0.50"}
# 按标的止盈止损（doc 样本标的 510050，沪市）
REAL_COND_TARGET_LOSS = {"StockCode": "510050", "ExchangeNum": 1,
                         "Method": 1, "ValueType": 1, "Value": "3.216"}
REAL_COND_TARGET_PROFIT = {"StockCode": "510050", "ExchangeNum": 1, "Method": 1,
                           "ValueType": 1, "Value": "3.216", "WithdrawType": 2,
                           "Withdraw": "0.50"}
REAL_VALID_DATE = "2026-12-31"   # 云单到期日期（doc 样本 2026-08-31 已过期，顺延到年末）

# ==================== 账号池：按用途严格分成两个，禁止混用 ====================
# 用例类型约定（四个，各司其职）：
#   normal  - 压测数据：账号四要素必须与真实账号完全匹配，业务字段完整合法。
#             走完整业务主链路，其统计结果（吞吐/响应时间/字节数）才有意义。
#   probe   - 兼容性探测：验证"某字段是否必填/某取值是否接受"（如省略 Model、
#             Model=1、渠道或账号类型错配、FAccount 带空格）。结果不确定，
#             可能走错误路径或返回空，因此【不计入压测指标】，只用于功能确认。
#   error   - 错误数据：接口校验层就该拒绝，期望 Err<0。
#   destroy - 破坏数据：极端/畸形输入，测健壮性（不崩、不泄漏）。
#
# 1) 压测池：只放"确定合法"的账号组合，供 gen_account_variety 生成 normal。
#    压测需要的"变化"应来自业务字段随机化（日期区间、合约代码、价格等），
#    不能靠改账号属性——属性一旦不匹配，中台要么查不到、要么直接拒绝，
#    请求根本走不到业务主链路，测出来的吞吐/耗时/字节数全是假的。
STRESS_ACCOUNT_POOL = [
    (REAL_ACCOUNT["FAccount"], 7, 6, "0"),   # Model=0, AccountType=7, AccAtt=6, 无空格
]

# 2) 破坏/错误池：同一账号的各种不匹配变体，专供 gen_fuzz / gen_cross 造
#    error、destroy 数据。这类数据本来就要"不对"，变体越多覆盖越广。
#    【禁止】用它生成 normal，否则压测池会被污染。
REAL_ACCOUNT_POOL = [
    (REAL_ACCOUNT["FAccount"], 7, 6, "0"),
    (REAL_ACCOUNT["FAccount"], 7, 6, ""),
    (REAL_ACCOUNT["FAccount"], 7, 6, "1"),
    (REAL_ACCOUNT["FAccount"], 7, 0, "0"),
    (REAL_ACCOUNT["FAccount"], 1, 6, "0"),
    (REAL_ACCOUNT["FAccount"], 1, 0, "0"),
    (" " + REAL_ACCOUNT["FAccount"], 7, 6, "0"),
]

# 旧的多账号池：覆盖资金/客户号、股票/期权、真实与虚拟账号（历史占位账号，已不用于默认并发池）
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


def _same_account(headers, template, facct, at, aa, model):
    """账号四要素是否与模板完全一致（完全一致则生成出的行与模板重复）。"""
    keys = dict(headers)
    for key, v in (("FAccount", facct), ("AccountType", at),
                   ("AccAtt", aa), ("Model", model)):
        if key not in keys:
            continue
        if str(template[_col_index(headers, key)]) != str(v):
            return False
    return True


def gen_account_variety(headers, template, accounts=STRESS_ACCOUNT_POOL,
                        type_tag="normal", start=500, skip_same=True):
    """多账号用例：把 template 中账号相关列替换为池子里的值，制造并发负载。

    accounts: [(FAccount, AccountType, AccAtt, Model), ...]
    默认用 STRESS_ACCOUNT_POOL（只含确定合法的组合），生成的是 normal 压测数据。
    若要造 error/destroy，必须显式传 accounts=REAL_ACCOUNT_POOL 并改 type_tag。

    skip_same: 默认 True，跳过与模板账号完全一致的组合——否则会生成一条和
    模板报文逐字节相同的行，压测时等于白占一个名额（--max 循环会把它重复发）。
    压测池只有一条确定合法组合时，本函数返回空列表属正常现象。
    返回完整宽度的行列表（元组）。
    """
    base = list(template)
    keys = dict(headers)
    out = []
    n = start
    for facct, at, aa, model in accounts:
        if skip_same and _same_account(headers, template, facct, at, aa, model):
            continue                       # 与模板重复，跳过（编号 n 不递增）
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


def gen_cross(headers, template, accounts=REAL_ACCOUNT_POOL, injects=(),
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
