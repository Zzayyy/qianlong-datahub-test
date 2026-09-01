# DataHub 数据中台压测工具

针对云条件单（DataHub）的压测与破坏测试工具集。通过 Redis Stream + 动态库插件发送条件单请求，统计性能与容错表现。

## 结构

| 文件/目录 | 说明 |
|---|---|
| `gui_test.py` | GUI 主程序（封装两个命令行工具） |
| `send_test.py` | 多线程发送引擎（正常/错误/破坏测试 + 性能统计） |
| `make_excel.py` | 测试数据生成器（生成 `data/{接口}.xlsx`） |
| `mock_datahub.py` | 模拟数据中台应答器 |
| `perf_stats.py` | 性能统计（吞吐/延迟分位数/CPU） |
| `interfaces/` | 接口定义（每个协议一个 py） |
| `data/` `out/` | 测试数据、日志与性能输出 |

## 快速开始

```bash
python make_excel.py --interface create          # 生成测试数据
python send_test.py --interface create --no-send # 预览报文
python send_test.py --interface create --workers 8 --max 1000 --quiet  # 压测（Linux）
python send_test.py --interface create --type destroy --destroy-mode mixed  # 破坏测试
```

依赖：Python 3.8+，`pip install openpyxl PySide6 paramiko redis`。走插件的压测需在 Linux（.so 库）；破坏测试直写 Redis，仅需网络可达。

## 测试数据来源

由 `make_excel.py` 按 `interfaces/{接口}.py` 中定义的 `ROWS` 生成到 `data/{接口}.xlsx`，包含三部分：

1. 手写用例（C001~C203 等）：正常/错误/破坏各若干
2. 批量正常：模板行 × 18 个账号池账号
3. 批量 fuzz / 交叉破坏：字段 × 畸形值循环展开（`__LONG__`、`__SQL__`、`__CTRL__` 等 token 占位，生成报文时展开为真实内容）

## 用例类型

中台处理链路：①来源/路由 → ②JSON解析 → ③协议分发 → ④业务校验。

| case_type | 通道 | 目的 |
|---|---|---|
| `normal` | 插件 | 性能基线 |
| `error` | 插件 | 业务校验容错（字段值畸形） |
| `destroy` | 直写 Redis | 路由/解析/分发容错，不等待回复 |

## 破坏类型（destroy_mode）

| mode | 核心字段 | task 内容 | 测什么 |
|---|---|---|---|
| `type1` | 乱填 | 畸形 | 双重破坏 |
| `type2` | 乱填 | 正确 | 误路由 |
| `type3` | 正常 | 非法 JSON | 解析容错 |
| `type4` | 正常 | 非协议 JSON | 分发容错 |
| `mixed` | — | — | 四类轮发（默认） |

指定优先级：命令行 `--destroy-mode` > Excel `destroy_mode` 列 > 默认轮发。

## 常用参数（send_test.py）

| 参数 | 默认 | 说明 |
|---|---|---|
| `--interface` | 必填 | 接口名（对应 interfaces/ 下的文件名） |
| `--excel` | data/{接口}.xlsx | 测试数据路径 |
| `--so` | 自动查找 | 插件 .so 路径 |
| `--workers` | 4 | 并发线程数 |
| `--max` | 0（全部） | 最多发送条数，超出时循环复用 Excel 用例 |
| `--type` | 全部 | 用例类型过滤：normal,error,destroy |
| `--wait` | 3.0 | 发完后等待回复秒数（收齐即提前结束） |
| `--destroy-mode` | 空（轮发） | 破坏类型，见上表 |
| `--destroy-via-plugin` | 关 | 破坏数据也走插件 SendMQ |
| `--destroy-server-id` | 12345 | type3/4 用的 server_id |
| `--mock` / `--no-mock` | 开 | 模拟数据中台应答器 |
| `--init-wait` | 5.0 | 等待插件 inited 兜底超时 |
| `--no-send` | 关 | 只生成报文不发送（预览模式） |
| `--quiet` | 关 | 安静模式（大批量压测减少日志） |
| `--no-stats` / `--stats-out` / `--stats-interval` | 开/默认 | 性能统计开关、输出目录、采样间隔 |

## GUI

```bash
python gui_test.py    # venv 环境下运行
```

左侧主流程：勾选接口 → 批量生成 Excel → 配置并发参数 → 运行测试。右侧支持远程 Redis 配置读写、SSH 远程执行（自动上传脚本与数据）。下方实时日志 + `*_stats.json` 批量汇总导出 Excel，配置记忆于 `config.ini`。

## 输出

- `out/logs/`：运行完整日志
- `out/performance/`：`*_stats.json`（汇总）与 `*.xlsx`（吞吐/字节/CPU/延迟分位数明细）
- `out/{接口}_requests.jsonl`：预览报文

## 注意

- .so 是 Linux 库，Windows 只能预览报文
- Windows 控制台打印畸形字符可能报编码错，建议 `PYTHONIOENCODING=utf-8`（GUI 已自动设置）
- 破坏直写会真实写入 Redis 流，仅限测试环境；type1/2 的 reply 流名不存在，不污染正常回复
