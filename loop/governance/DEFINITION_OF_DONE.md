# 完成定义

工作项只有同时满足以下条件才能标为 `accepted`。

## 需求

- scope-in 全部完成，scope-out 未被误改。
- 每个验收条件有直接证据。
- 所有假设已验证或明确保留为风险。

## 设计与代码

- 架构边界未破坏；重大选择有 accepted ADR。
- 公共合同、错误语义和迁移兼容已记录。
- 无无主 TODO/FIXME、死代码、调试输出或秘密。

## 科学与数据

- 公式、单位、范围、版本、样本要求和缺失处理已测试。
- 无 NaN/Inf 泄漏、前视偏差或虚构降级。
- 结果包含来源、时间、完整度和限制说明。

## UI 与可访问性

- Microsoft YaHei 实际解析验证通过。
- 1366×768@100%、1920×1080@125/150%、2560×1440@200% 无关键裁切/重叠。
- 键盘、焦点、accessibleName、tooltip 和颜色冗余表达通过。
- 原生标题栏与内容区无重复品牌标题。

## 验证

- format → lint → type → unit → integration → Qt GUI → fault injection → performance → build → packaged self-test 顺序门禁通过。
- 必需测试 0 failure、0 error、0 未批准 skip。
- 相关门禁由独立验证者复核。
- 证据记录含命令、环境、退出码、提交与产物哈希。

## 发布

- 依赖许可、SBOM、漏洞和 Qt 插件完整性已审查。
- `dist/` 只含批准交付物。
- EXE `--self-test` 与 Windows GUI 冒烟通过。
- 回滚步骤可执行。
- 人工发布门禁已签署。

任一项缺失，状态最多为 `implemented` 或 `verifying`，不得写成完成。

