# FileGDB Inspector

本机运行的 FileGDB 批量扫描与字段质量检查工具。选择本地目录，在浏览器中查看 GDB、图层、普通表、字段名称、源别名及空值统计，并导出完整 JSON。

**开源仓库只包含源码、文档和测试代码，不包含任何业务数据、GDB 文件、JSON 文件、历史扫描结果或运行日志。** JSON 是程序运行后保存在用户本机的输出格式，不是仓库附带资料。

## 功能

- 递归发现 `.gdb` 目录，勾选后批量读取。
- 按“GDB → 图层／普通表 → 字段”展示名称、类型、别名和要素数。
- 区分 NULL、空字符串、纯空白字符串，计算空值率和空白率。
- 支持按名称、别名、空值、异常和系统字段筛选，排序及分页。
- 展示进度和异常；保存完整 JSON，不因当前筛选或分页裁剪输出。
- 数据集显式以只读方式打开，不提供增删改接口；结果不包含要素属性原值或几何坐标。

这是一款字段检查工具，不是地图浏览器，不提供地图渲染、属性值编辑、Excel 导出或坐标转换。

## 快速启动：macOS + QGIS

1. 安装 [QGIS](https://qgis.org/download/)，下载本仓库并解压。
2. 双击 `start.command`，或在仓库目录运行：

   ```bash
   bash start.command
   ```

3. 浏览器打开 `http://127.0.0.1:8765`。选择文件夹 → 开始扫描 → 勾选 GDB → 提交读取。
4. 完成后点击“保存完整 JSON”。程序也会自动写入 `runtime/exports/`。
5. 保持终端窗口打开；在终端按 `Ctrl+C` 停止。无需启动 QGIS GUI 或 QGIS MCP。

QGIS 安装位置不同时：

```bash
QGIS_APP_PATH='/Applications/QGIS-LTR.app' bash start.command
```

文件选择器不可用时：

```bash
GDB_INSPECTOR_MANUAL_PATH=1 bash start.command
```

## 使用已有 GDAL 环境

要求 Python 3.10+、GDAL 3.6+、匹配的 `osgeo` Python 绑定及 OpenFileGDB 驱动。`requirements.txt` 不会安装这些原生组件；不要在 QGIS 自带环境中混装不同版本的 GDAL。

Ubuntu/Debian 示例（由使用者安装依赖）：

```bash
sudo apt-get install python3-gdal gdal-bin
GDB_INSPECTOR_PYTHON=/usr/bin/python3 bash start.sh
```

非 macOS 平台默认启用手工输入路径。无图形桌面的环境可以增加 `--no-browser`，但页面仍只允许本机访问。Windows 未完成验证，不提供专用启动器。

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `QGIS_APP_PATH` | 自动查找常见 macOS 安装位置 | 指定 QGIS 应用路径 |
| `GDB_INSPECTOR_PYTHON` | macOS 使用 QGIS，其他系统使用 python3 | `start.sh` 使用的解释器 |
| `GDB_INSPECTOR_PORT` | `8765` | 本机端口 |
| `GDB_INSPECTOR_MANUAL_PATH` | macOS 为0，其他系统为1 | 是否启用手工路径输入 |
| `GDB_INSPECTOR_RUNTIME_DIR` | 仓库内的 runtime | 日志和结果保存目录 |

## 数据与统计口径

- NULL 和未设置值计为空值；`0`、`0.0`、`False` 不为空值。
- 空白率包含 NULL、空字符串和纯空白字符串；JSON 中率为0—1，网页显示为百分比。
- 空图层、未统计的几何字段及失败统计使用 `null`，不会伪装为0。
- 别名仅来自 GDAL 源字段接口，没有别名时显示“—”，不根据字段名猜测。
- FID、几何字段与普通属性字段分开识别；不承诺恢复 ArcGIS 全部字段的混合物理顺序。
- 统计需要逐要素遍历；不保存要素原值，但会读取字段值以计算计数。
- 图层读取失败时继续其他图层，记录异常，不把不完整计数当完整结果。

详细输出字段与接口见 [docs/OUTPUT.md](docs/OUTPUT.md)。

## 本地数据边界

仅监听 `127.0.0.1`，检查 Host、Origin 和每次启动随机生成的本地令牌。不访问外部地图服务，不上传 GDB，不依赖账号、云服务或密钥。

**导出的 JSON 和日志仍可能包含本机路径、数据库名、图层名及字段名，应作为本地资料保存。** 不要上传它们，也不要把它们粘贴到公开 Issue。安全边界及问题报告方式见 [SECURITY.md](SECURITY.md)。

运行中的任务不支持恢复、取消或断点续跑。浏览器显示最近300条日志，内存保留最近10个任务；完整结果保存在本机。未提供 Feature Dataset 层级还原、字段域解析或几何质量检查。

## 测试

测试只在临时目录创建人工合成数据，检查读取前后文件哈希、修改时间和文件清单，不读取业务目录：

```bash
# macOS
/Applications/QGIS.app/Contents/MacOS/python -B -m unittest discover -s . -p 'test_*.py' -v

# 已安装匹配的 GDAL Python 绑定
python3 -B -m unittest discover -s . -p 'test_*.py' -v

# 不依赖 GDAL 的源码发布检查
python3 scripts/check_release.py
```

GitHub Actions 配置检查发布文件边界、语法并在 Ubuntu 上运行合成数据/API 测试。配置已提供不代表远程 CI 已实际执行；本地验证结果见 [docs/VALIDATION.md](docs/VALIDATION.md)。

## 保管到 GitHub

只将本仓库目录上传，不要上传上层工作目录。参见 [docs/PUBLISH.md](docs/PUBLISH.md)。发布工具按 `RELEASE_FILES.txt` 精确列出的源码文件打包，不递归收集整个目录；所有 `.json`、`.jsonl`、`.gdb` 及运行产物都禁止进入发布包。

## 许可证

本项目源码按 [MIT License](LICENSE) 开源。QGIS、GDAL、Python 等由使用者单独安装，本仓库不分发这些组件，它们适用各自许可证。任何输入数据均不因使用本工具而获得公开授权。

技术参考：[GDAL OpenFileGDB 官方文档](https://gdal.org/en/stable/drivers/vector/openfilegdb.html)、[MIT 许可证正文](https://opensource.org/license/mit)。
