# 输出结构与接口

此文档只描述字段，不附带 JSON 文件或真实检查记录。每次运行的完整结果保存为 `runtime/exports/<任务ID>.json`，实际目录可由环境变量指定。

## 顶层

| 字段 | 含义 |
|---|---|
| task_id | 本次任务随机标识 |
| created_time / finished_time | 任务创建、结束时间，ISO格式并带本机时区 |
| status | completed、completed_with_errors；失败任务通过状态接口报告 failed |
| gdal_version / environment | GDAL版本与本机运行环境，包含本机路径 |
| scan_root | 扫描根目录的绝对路径 |
| gdbs | 所选 GDB 结果列表 |
| errors | 异常列表 |
| null_definition | 本次空值定义 |

## GDB 与图层

GDB：`gdb_index`、`path`、`directory`、`name`、`driver`、`status`、`read_time`、`finished_time`、`layers`、`errors`、`summary`。读取前路径校验失败的条目可能缺少时间或汇总字段。

图层：`layer_index`、`layer_name`、`object_type`、`geometry_type`、`feature_count`、`reported_feature_count`、`fields`、`status`、`read_time`、`errors`。`object_type` 区分空间图层与非空间表。读取失败时要素数为 null；部分读取量单列为 `partial_records_read`。

## 字段统计

| 字段 | 含义 |
|---|---|
| field_index | GDAL字段索引；FID为-1，几何字段使用几何字段索引 |
| field_name / field_alias / field_type | 源名称、源别名、GDAL类型 |
| field_category | 系统字段或普通属性字段 |
| role | attribute、fid、geometry |
| null_count / null_rate | NULL或未设置值的数量与比例 |
| empty_string_count | 空字符串数量 |
| whitespace_string_count | 非空但全为空白字符的字符串数量 |
| blank_string_count | 上述两类字符串数量之和 |
| blank_rate | (NULL数＋两类空白字符串数)／记录数 |
| status / reason | 状态及未统计/失败原因 |

空图层比例为 null，原因为 `empty_layer`。几何不参加空值统计，原因为 `geometry_not_counted`。统计失败为 `read_failed`；未完整统计时不输出看似有效的部分比例。

## HTTP API

所有接口只允许从本机页面调用。页面通过 `X-Local-Token` 携带每次启动生成的令牌；不要将令牌保存到文档或脚本配置。

| 方法及路径 | 用途 |
|---|---|
| GET /api/environment | 运行环境及可用状态 |
| GET /api/select-folder | macOS原生目录选择器 |
| POST /api/scan | 请求体包含 root 字符串，递归发现GDB |
| POST /api/analyze | 请求体包含 scan_id、paths 列表，启动读取 |
| GET /api/tasks/&lt;id&gt; | 进度、状态、最近日志 |
| GET /api/tasks/&lt;id&gt;/results | 完整统计结果 |

任务完成与“无异常”并非同一状态；应同时检查任务、GDB、图层及字段层面的状态与异常。
