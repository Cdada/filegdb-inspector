# GitHub 保管与发布

只将独立的 `filegdb-inspector` 目录作为仓库根目录。不要把上层工作目录初始化为仓库，不要上传历史工程、原始资料或运行结果。

## 首次保管

1. 在 GitHub 创建名为 `filegdb-inspector` 的空仓库。公开/私有由你决定；开源许可证与仓库可见性是两个设置。
2. 在本目录运行以下命令，替换远程地址中的账户名。提交前检查不通过时先处理原因，不绕过检查。

```bash
git init
git config core.hooksPath .githooks
python3 scripts/check_release.py
git add .
python3 scripts/check_release.py --staged
git diff --cached --stat
git commit -m "Initial open-source release"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/filegdb-inspector.git
git push -u origin main
```

本包没有 Git 历史、远程地址或账户信息。若 Git 提示缺少提交身份，由你配置适当的姓名及邮箱。

`git add .` 只应在这个独立目录执行。`.gitignore` 排除数据与运行产物，`--staged` 再检查暂存区文件名和实际内容；GitHub CI 检查已跟踪文件。不要用 `git add -f` 提交数据。

## 制作源码包

```bash
python3 scripts/check_release.py
python3 scripts/build_release.py --output-dir ../release
```

打包器只取 `RELEASE_FILES.txt` 白名单中的文件，拒绝符号链接、禁入扩展名与已跟踪的白名单外文件。输出 ZIP 和 SHA256 校验文件，已有同名包时拒绝覆盖。

上传 Release 时只选择打包器生成的源码 ZIP 及其 SHA256 文件，不选择 runtime、导出JSON或其他目录。

## 验证检查确实生效

```bash
python3 scripts/check_release.py --staged
git status --short --ignored
```

`.gitignore` 不会移除已经跟踪的文件，因此检查脚本会额外核验暂存区。若曾误推送敏感文件，简单删除最新版本不能清除旧历史；停止继续发布，按实际暴露情况处理仓库历史与访问权限。
