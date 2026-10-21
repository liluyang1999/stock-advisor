# 打包与部署

## 当前实现与合同

- 已验证目标为 Windows x64 / Python 3.14.4；开发源码要求 Python 3.14+，成品不需 Python 安装。依赖及完整 Windows wheel 哈希锁在 `pyproject.toml` 与 `requirements/`。
- `python -B scripts/package_app.py` 是统一入口；build.bat/build.sh 仅转交。构建临时环境在 `build/package-env-*`，不修改全局或已有 `.venv`。
- 仅清理命名的 PyInstaller 中间目录，其他 `build/` 文件保留。拒绝脏源码、构建中提交变化、被本地忽略规则隐藏的可执行构建输入与链接目录。
- 旧 dist 校验后临时保留；新构建/校验失败则恢复。恢复失败保留备份并报告路径。成功后才清理旧备份。
- ADR-0004 保持 **onedir、windowed**；完整 dist 包含应用目录、HTML 说明、1.1 清单、SBOM、第三方声明及 LGPL/GPL 正文。应用内另带 Python/bootloader 许可和 RUNTIME_INVENTORY.json。

## 构建与核验

1. 完成产品与工程门禁，提交源码；版本哈希锁必须同时一致。
2. 统一入口创建临时环境，安装完整 hash-locked 构建依赖，执行 pip check，然后构建及生成清单。可用 `--wheelhouse <path>` 离线安装已下载 wheel。
3. 构建子进程限制 DLL 搜索 PATH，避免混入其他工具的同名库。BUILD_INFO 记录源码提交、Python 及构建锁摘要。
4. 拷贝完整交付到中文空格路径；移除 Python/Qt 环境与开发 PATH，运行 EXE `--self-test` 一次、`--smoke-test` 两次，检查退出码、成功标记和 stderr。smoke 使用真实 Qt 事件循环遍历五页，不替代人工视觉验收。
5. 独立运行前后均校验清单，确认程序不往安装目录写文件。测试配置在临时隔离目录。
6. 成功输出 PACKAGE_OK；暂存环境自动回收。最后按本次创建清单清理剩余 build 中间产物，保留 dist 成品与必要工程证据。
7. CI 先跑八个严格开发门禁，再全新 Windows job 打包，再由无源码 checkout/无 Qt 安装的另一个 runner 下载产物、验 hash 并运行。这不等同于干净物理目标机人工验收。

## Qt 资产与预算

图标与 tokens.json 随包收集，QSS 由代码和 token 生成；Windows platform、imageformats、styles 等插件按实际产物检查。项目没有单独的 resources.qrc，不捆绑系统微软雅黑字体。

包体预算沿用 `quality/performance-budgets.json`，实际统计整个 onedir 应用目录；不能用小 EXE 的大小代替运行库总大小。启动和内存预算以实际 Windows 测量为准。

## 分发状态与人工验收

当前构建未作 Authenticode 签名。README 与操作说明必须披露；用户应核实来源与 SHA-256，不能引导关闭系统防护。签名方案、证书及密钥管理尚未实现，归 WI-025 和人工发布门禁。

PySide6 与 shiboken6 的组件记录、LGPL/GPL 正文及 THIRD_PARTY_NOTICES 已由清单脚本生成。文件存在不等于许可方案已经签署，也不等于漏洞审查已完成；完整 wheel 哈希锁与当日已公开漏洞核对已补齐；原生 EXE/DLL/PYD 的文件清单与摘要随包保存。静态嵌入第三方组件仍需上游 SBOM 复核，现有两个 Python 发行包 SBOM 不冒充完整原生库 SBOM。

HG-LICENSE → HG-PACKAGING → HG-RELEASE 的人工签署不由代码审查代替。当前缺口集中在 `quality/RELEASE_READINESS.md`。

## 回滚

保留上一份已验证的应用目录、说明书和完整配套清单；用对应清单核验后切换目录。配置兼容性单测不等于在干净目标机完成升级/回滚演练；用户自选、持仓不得因回滚被删除。
