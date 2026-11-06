# 参与开发

保持本机运行、源数据只读和结果不含逐要素原值这三项边界。功能修改应配套合成数据测试，不要使用业务资料作为测试夹具。

提交前运行：

```bash
python3 scripts/check_release.py
python3 -B -m unittest discover -s . -p 'test_*.py' -v
```

第二条命令需要 GDAL 3.6+ 的匹配 Python 环境；macOS 可使用 QGIS 附带的解释器。

新增源码文件必须同时加入 `RELEASE_FILES.txt`。不得加入 GDB、JSON、JSONL、已扫描数据、运行日志或业务文档；即使是样例 JSON 也不纳入发布文件。输出格式使用 Markdown 中的字段说明表达。

在独立仓库中可启用提交检查：

```bash
git config core.hooksPath .githooks
```

该设置只影响当前仓库。钩子检查 Git 暂存区；CI 进一步检查已跟踪文件。请在 PR 中说明行为变化、测试结果及已知限制。
