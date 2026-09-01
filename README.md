# DataHub 数据中台压测工具

针对云条件单（DataHub 数据中台）的多线程压力测试与破坏测试工具集。
通过 Redis Stream（`DataHub_req_stream`）+ 动态库插件（`libdatahub_trade_plug.so`）发送
条件单请求（创建/查询/修改/删除/账号签署等），并统计性能指标与破坏容错表现。

## 目录结构

```
datahub_test/
├── gui_test.py          # GUI 主程序（PySide6），封装下面两个命令行工具
├── send_test.py         # 多线程发送引擎（正常/错误/破坏测试 + 性能统计）
├── make_excel.py        # 测试数据生成器（按接口定义生成 data/{接口}.xlsx）
├── mock_datahub.py      # 模拟数据中台应答器（订阅 tradeserver_online 频道应答心跳）
├── perf_stats.py        # 性能统计（采样线程 + SendMQ/XADD 延迟分位数 + 汇总）
├── interfaces/          # 接口定义（每个协议一个 py）
│   ├── _common.py       #   公共工具：fuzz token 池、批量用例生成、Account 构造
│   └── create.py        #   创建云条件单（其余: query/modify/remove/set/acc_* 等）
├── data/                # 生成的 Excel 测试数据（{接口}.xlsx）
└── out/                 # 运行输出
    ├── logs/            #   每次运行的完整日志（{接口}_时间戳.log）
    └── performance/     #   性能统计（{接口}_*_stats.json / .xlsx）
```

## 环境依赖

- Python 3.8+（venv 环境）
- `pip install openpyxl PySide6 paramiko redis`
- 性能测试（走插件）需要 `.so` 动态库，在 Linux 上运行；Windows 本地只能生成报文预览
- 破坏测试（直写 Redis）不依赖 `.so`，有网络可达的 Redis 即可

## 快速开始

```bash
# 1. 生成某接口的测试数据 Excel
python make_excel.py --interface create

# 2. 预览报文（不发送，输出到 out/create_requests.jsonl）
python send_test.py --interface create --no-send

# 3. 真实发送（Linux，走插件 + 破坏直写 Redis）
python send_test.py --interface create --workers 8 --max 1000 --quiet

# 4. 只跑破坏测试（四类轮发）
python send_test.py --interface create --type destroy --destroy-mode mixed
```

## 用例类型（Excel `case_type` 列）

中台处理一条请求要过四道关卡：

```
①来源/路由(核心字段) → ②JSON解析 → ③协议分发(create/query键) → ④业务校验(字段值)
```

| case_type | 通道 | 内容 | 测的关卡 |
|---|---|---|---|
| `normal` | 插件 SendMQ | 全部正确 | 无（性能测试基线） |
| `error` | 插件 SendMQ | task 合法 JSON、协议格式，字段值畸形（`CondType=99` 等） | ④业务校验 |
| `destroy` | 默认直写 Redis（`--destroy-via-plugin` 可改走插件） | 见下表破坏类型 | ①~③ |

destroy 用例不会被中台按正常业务回复，不计入回复统计；error/normal 走插件并等待回复收齐。

## 破坏类型（destroy_mode）

两个维度组合：**核心字段**（request_id/server_id/server_type/reply流）× **task 内容**。

| mode | 核心字段 | task 内容 | 破坏关卡 | 说明 |
|---|---|---|---|---|
| `type1` | 乱填 | 业务数据畸形（Excel fuzz 行报文） | ①+④ | 双重破坏 |
| `type2` | 乱填 | 业务数据正确（自动取 Excel 第一条 normal 报文） | ① | 测误路由：内容对但来源不可信 |
| `type3` | 正常 | 非法 JSON：空串/截断/纯文本/控制字符/二进制垃圾/BOM 前缀（内置 10 模板轮换） | ② | 测解析容错不崩溃 |
| `type4` | 正常 | 合法 JSON 但非协议格式：`{}`/`[]`/`null`/未知顶层键/`create` 不是对象/深嵌套（内置 12 模板轮换） | ③ | 测未知结构的分发容错 |
| `mixed` | — | — | — | 四类按顺序轮发 |

说明：

- type3/4 核心字段**必须正确**——核心字段乱填时消息在①路由就被丢弃，坏 task 到不了解析器；
  同时"完全模仿插件伪造直写"是最危险的威胁场景，必须有对应用例
- type3/4 核心字段正常时中台可能真的回复（Err<0），会混入回复统计（不影响"收齐即停"判断）
- 模板选择按 request_id 稳定哈希/轮换取，可复现

指定方式（优先级从高到低）：

1. 命令行 `--destroy-mode type1|type2|type3|type4|mixed`
2. Excel 行级 `destroy_mode` 列（若有该列）
3. 缺省：四类轮发（mixed）

## send_test.py 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--interface` | 必填 | 接口名（对应 interfaces/ 下的文件名） |
| `--excel` | data/{接口}.xlsx | 测试数据路径 |
| `--so` | 自动查找 | 插件 .so 路径 |
| `--workers` | 4 | 并发线程数 |
| `--max` | 0(全部) | 最多发送条数（超出 Excel 用例数时循环复用扩量） |
| `--type` | 全部 | 用例类型过滤，逗号分隔：normal,error,destroy |
| `--wait` | 3.0 | 发完后等待回复秒数（收齐即提前结束） |
| `--destroy-mode` | 空(轮发) | 破坏类型，见上表 |
| `--destroy-via-plugin` | 关 | 破坏数据也走插件 SendMQ |
| `--destroy-server-id` | 12345 | type3/4（核心字段正常）用的 server_id |
| `--mock` / `--no-mock` | 开 | 模拟数据中台应答器（应答插件心跳） |
| `--init-wait` | 5.0 | 等待插件 inited 兜底超时 |
| `--no-send` | 关 | 只生成报文不发送（预览模式） |
| `--quiet` | 关 | 安静模式（大批量压测减少日志） |
| `--no-stats` / `--stats-out` / `--stats-interval` | 开/默认 | 性能统计开关、输出目录、采样间隔 |

## GUI（gui_test.py）

```bash
python gui_test.py    # venv 环境下运行
```

- 左侧主流程：勾选接口 → 批量生成 Excel → 配置并发参数（并发/条数/等待/安静模式/
  mock/用例类型复选框/破坏类型下拉框）→ 运行发送测试
- 右侧：Redis 配置（可读写远程 DataHub.ini [REDIS] 段）、远程 Linux（SSH 执行，
  自动上传脚本/接口定义/Excel，变更检测增量上传）、结果保存目录
- 下方：运行日志（实时）+ 批量汇总分析（扫描 `*_stats.json` 自动汇总成表，可导出 Excel，
  批量跑完自动导出，含批次参数快照）
- 配置自动记忆（`config.ini`）：连接信息、分栏比例、破坏类型等

## Excel 用例数据

由 `make_excel.py` 按 `interfaces/{接口}.py` 的 `ROWS` 生成，包含三部分：

1. 手写用例（C001~C203 等）：正常/错误/破坏各若干
2. 批量正常（`gen_account_variety`）：模板行 × 18 个账号池账号
3. 批量 fuzz（`gen_fuzz`）/ 交叉破坏（`gen_cross`）：字段 × 畸形值循环展开

畸形值使用 token 占位（`_common.py` 的 `TOKEN_MAP`），如 `__LONG__`(1000字符)、
`__SQL__`(SQL注入)、`__CTRL__`(控制字符)、`__PRICE_NAN__`、`__DATE_13__` 等，
生成报文时展开为真实内容。

## 输出文件

| 文件 | 内容 |
|---|---|
| `out/logs/{接口}_*.log` | 每次运行的完整 stdout（含每条报文/回复，安静模式为关键信息） |
| `out/performance/{接口}_*_stats.json` | 汇总指标（GUI 批量汇总的数据源） |
| `out/performance/{接口}_*.xlsx` | 性能明细（按秒吞吐/字节数/CPU/延迟分位数） |
| `out/{接口}_requests.jsonl` | 预览模式的报文（每行一个 JSON） |

性能指标包括：总请求数/成功失败数/成功率、吞吐（条/s）、请求字节数、客户端 CPU
平均与峰值、SendMQ 延迟（均/p50/p90/p99/max）、XADD 直写延迟、Redis 写入精确计数。

## 注意事项

- 远程执行时脚本通过 SSH 在 Linux 上跑（.so 是 Linux 库）；"批量上传所有接口数据"
  可一次性同步 interfaces/ + data/ + 脚本
- Windows 控制台为 GBK 编码，直接跑 `send_test.py` 打印畸形字符可能报
  UnicodeEncodeError，建议设置 `PYTHONIOENCODING=utf-8`（GUI 已自动设置）
- 破坏直写会真实写入 Redis 流，测试环境专用；type1/2 的 reply 流名是不存在的流，
  不会污染正常回复通道
