# 发布计划

## 候选条件

- AC-001..AC-010 证据齐全。
- P0/P1/P2 = 0，未过期豁免 = 0。
- 全门禁连续 5 次绿色。
- 源码提交、锁文件、构建环境、EXE 和报告可追溯。

## 产物

- `dist/股市锦囊/股市锦囊.exe` 及整个应用目录（onedir，ADR-0004）
- `dist/使用说明.html`
- `dist/RELEASE_MANIFEST.json`：除清单自身外的完整交付文件 SHA-256
- `dist/SBOM.json`、`dist/THIRD_PARTY_NOTICES.md`、`dist/licenses/`
- 构建元数据、self-test 和 Windows 冒烟报告

## 人工门禁

HG-LICENSE → HG-PACKAGING → HG-RELEASE。自动化不得替代这些签署。

## 发布后

监控崩溃、启动、上游接口漂移和用户可恢复问题；不收集持仓隐私。重大问题按 POSTMORTEM 模板复盘并触发回滚。

