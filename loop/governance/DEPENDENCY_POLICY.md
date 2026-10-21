# 依赖政策

## 分类

| 类别 | 示例 | 规则 |
|---|---|---|
| 运行期 | PySide6 | 必须批准、精确锁定、记录许可证和包体影响 |
| 构建期 | PyInstaller | 精确锁定，和 Python/PySide6 组合验证 |
| 开发期 | Ruff、pyright、coverage 等 | 不进入运行产物，仍需精确锁定和安全审查 |

## 引入门禁

新增依赖必须记录：

1. 解决的问题与标准库替代方案。
2. 精确版本、来源、哈希和支持的 Python/OS。
3. 直接/传递依赖、维护活跃度和已知漏洞。
4. 许可证、NOTICE/动态链接/重新链接等交付义务。
5. EXE 大小、冷启动、内存和 Qt 插件影响。
6. 升级和回滚方案。

## PySide6 特别规则

- 已是生产运行依赖：`PySide6-Essentials==6.12.0`，带入同版本 shiboken6，版本真源为 `pyproject.toml`。
- 已完成隔离 spike；后续升级仍须单独复核。禁止使用无上界的 `>=` 作为发布锁定。
- 必须验证 platform plugin、styles、imageformats、translations、QSS、图标和 offscreen 插件。
- 必须用干净虚拟环境防止 PyInstaller 混用系统 PySide6/Shiboken。
- 在 LGPL/GPL/商业许可方案批准前，不得对外发布 Qt 构建。

## 锁定与更新

- `pyproject.toml` 钉住直接依赖；`requirements/build-windows.lock`（9 个发行包）与 `dev-windows.lock`（29 个）固定 Windows x64 / CPython 3.14 全部解析依赖和 wheel SHA-256。安装强制 `--require-hashes --only-binary=:all:`，构建使用一次性项目内环境。锁定不等于逐字节可复现，也不等于无漏洞。
- 自动升级只能提出变更，不能自动合并或发布。
- 依赖更新必须跑完整门禁，并比较包体、启动、内存和视觉结果。


## 2026-10-21 依赖复核

- Qt 6.11.1 受上游新公告影响，升级官方 PySide6-Essentials/shiboken6 6.12.0（同许可方案，不新增运行依赖）。依据 Qt 官方 [CVE-2026-8168](https://www.qt.io/blog/security-advisory-cve-2026-8168)、[CVE-2026-76151](https://www.qt.io/blog/security-advisory-cve-2026-76151)、[CVE-2026-101201](https://www.qt.io/blog/security-advisory-cve-2026-101201) 的受影响/修复范围；6.12.0 已在 PyPI 有正式 Windows wheel。
- 29 个锁定发行包的 PyPI 版本元数据已逐个读取，本日返回的漏洞条目均为空。这是该信息源当日结果，不是无漏洞保证；Qt 原生公告另行核对。
- 成品新增 Python 运行时与 PyInstaller bootloader 许可正文、版本及原生文件哈希清单。现有 CycloneDX 只列两个 Python 运行发行包；静态嵌入的完整第三方组件仍需上游 SBOM 审查，不能以文件清单冒充。
- CI 的 checkout/setup-python/upload/download actions 固定到本日官方正式版本对应 commit，避免可移动版本标签漂移。
