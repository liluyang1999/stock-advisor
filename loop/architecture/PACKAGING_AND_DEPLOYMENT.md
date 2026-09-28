# 打包与部署

## 当前实现与合同

- Python 3.14+；运行依赖 PySide6-Essentials，构建依赖 PyInstaller，精确版本见 `pyproject.toml`。
- `.venv/` 是项目内构建环境；开发测试使用仓库配置的 Python。不得修改全局环境。
- `build/` 仅中间产物。构建会重建 `build/`、`dist/`，执行前核对路径并确认无用户文件。
- ADR-0004 已选择 **onedir、windowed**：`dist/股市锦囊/股市锦囊.exe` 与独立 Qt 运行库。
- 配套交付包含 `使用说明.html`、`RELEASE_MANIFEST.json`、`SBOM.json`、`THIRD_PARTY_NOTICES.md` 和 `licenses/` 两份正文。
- 教材在 `docs/`，操作说明由 `src/ui/manual.py` 生成。不能只分发 EXE。

## 构建与核验

1. 在隔离构建环境按 `pyproject.toml` 的 gui/build 组安装依赖；记录 Python、Qt、PyInstaller 版本。
2. 运行产品与工程门禁。当前仅直接依赖精确钉版，尚无完整传递依赖哈希锁，不能声称完全可复现。
3. `python scripts/build_exe.py` 生成应用与说明书；仅 Windows 打包子进程限制额外 DLL 搜索 PATH，避免混入其它工具的 ICU/CRT/OpenSSL。
4. 在**同一构建环境**运行 `python scripts/make_release_manifest.py`，生成元数据、许可副本与文件摘要。
5. 运行 `python scripts/make_release_manifest.py --verify`：文件改动、缺失或多出均失败。1.1 清单覆盖配套许可与元数据；旧清单须核实来源后重建。
6. EXE `--self-test` 应退出 0 且含 `SELF_TEST_OK`；另行启动原生 Windows GUI 并检查 stderr、字体与交互。自检不加载完整 Qt 界面。
7. 独立核对 BUILD_INFO、清单中的来源提交和真实构建提交；回滚核验允许旧提交，哈希通过本身不表示等于当前源码。
8. 清理本轮临时配置、日志、截图草稿和构建缓存，保留最终 dist 与最小有效证据。

## Qt 资产与预算

图标与 tokens.json 随包收集，QSS 由代码和 token 生成；Windows platform、imageformats、styles 等插件按实际产物检查。项目没有单独的 resources.qrc，不捆绑系统微软雅黑字体。

包体预算沿用 `quality/performance-budgets.json`，实际统计整个 onedir 应用目录；不能用小 EXE 的大小代替运行库总大小。启动和内存预算以实际 Windows 测量为准。

## 分发状态与人工验收

当前构建未作 Authenticode 签名。README 与操作说明必须披露；用户应核实来源与 SHA-256，不能引导关闭系统防护。签名方案、证书及密钥管理尚未实现，归 WI-025 和人工发布门禁。

PySide6 与 shiboken6 的组件记录、LGPL/GPL 正文及 THIRD_PARTY_NOTICES 已由清单脚本生成。文件存在不等于许可方案已经签署，也不等于漏洞审查已完成；Qt 及打包原生库的完整组件清点、漏洞复核、完整解析锁仍须在正式发布前补证。现有 SBOM 只声明两个 Python 发行组件，不冒充完整原生库 SBOM。

HG-LICENSE → HG-PACKAGING → HG-RELEASE 的人工签署不由代码审查代替。当前缺口集中在 `quality/RELEASE_READINESS.md`。

## 回滚

保留上一份已验证的应用目录、说明书和完整配套清单；用对应清单核验后切换目录。配置兼容性单测不等于在干净目标机完成升级/回滚演练；用户自选、持仓不得因回滚被删除。
