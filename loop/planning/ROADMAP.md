# 路线图

## MS-00 基线与规格冻结（进行中）

退出：Loop 校验绿；ADR-0001/0002/0005 明确；现有功能、Tk 测试和风险 100% 盘点。

## MS-01 PySide6 基础与打包 spike

QApplication、Microsoft YaHei、QMainWindow、资源/QSS、offscreen、最小 onefile。测量包体、启动、插件、许可。

退出：最小 QApplication/QMainWindow 外壳可运行（`minimal Qt app works`，offscreen 冒烟通过，标题栏图标/标题不重复）；Microsoft YaHei 字体经 QFontInfo 验证通过或记录文档化回退（`font verified`）；最小 onefile 打包体积/启动时间证据与 Qt 依赖许可证已审查（`packaging evidence reviewed`）。

## MS-02 科学与数据合同加固

数据 envelope、完整度、deadline、黄金向量、性质测试、模型卡和研究协议落地；不改模型口径。

退出：所有结果对象携带 provenance/获取时间/完整度/新鲜度字段（`data envelope`）；黄金数值、性质、回测前视和 NaN/Inf 防御测试 100% 通过独立核算基准（`golden vectors`）；VALIDATION_RESEARCH_PROTOCOL 中的模型卡与研究门禁满足（`research protocol gates`）。

## MS-03 个股工作台迁移

输入、批量结果、切档、K线、因子、仓位、回测、停止和降级。

退出：个股页与既有 Tk 版本功能对等，包括输入、结果、证据、K线、切档、仓位与回测（`individual feature parity`）；对应 offscreen Qt 测试（TEST-QT-AN-001/002、TEST-MODEL-001、TEST-POS-001、TEST-BT-002）全部通过（`Qt tests`）；空/加载/部分/错误/降级/停止等视觉状态均验证（`visual states`）。

## MS-04 全市场筛选迁移

六预设、参数、市场完整度、增量表格、深度分析和入选检查器。

退出：六个既有筛选预设与参数校验、TopN 5–30 稳定排序全部迁移（`six presets`）；市场完整度快照的完整/部分/失败语义验证（`complete snapshot semantics`）；入选个股的深度分析联动可用（`deep analysis`）。

## MS-05 组合/预警/深度工具迁移

自选持仓、横向对比、预警、资金流、帮助/策略说明。

退出：自选、持仓成本/股数、浮动盈亏与横向对比可用（`watchlist/compare`）；价格/涨跌幅/综合分边沿触发预警正确生成（`alerts`）；独立资金流页面与帮助/策略说明（含免责声明、导出安全）落地（`fund flow/help`）。

## MS-06 网络与并发收敛

故障矩阵、deadline、取消、迟到、生命周期、监控竞争、结构化日志。

退出：离线故障注入矩阵（分页不完整/429/5xx/DNS/TLS/超时/截断/字段漂移）全部覆盖（`fault matrix`）；取消、迟到结果丢弃、控件销毁竞态与重复启动收敛测试通过、迟到结果覆盖数为 0（`cancellation/late results`）；结构化日志落地（`observability`）。

## MS-07 UI/可访问性/性能收敛

DPI/分辨率、字体、焦点、对比度、视觉基准、表格与图表性能、内存。

退出：目标 DPI/分辨率截图矩阵验证通过（`DPI matrix`）；字体解析与键盘/焦点/tooltip/颜色冗余可访问性检查通过（`font/accessibility`）；批量分析、5000 行滚动、冷启动和闲置 RSS 满足 performance-budgets.json 数值预算（`performance budgets`）。

## MS-08 打包、发布与回滚

clean build、EXE self-test、Windows 冒烟、SBOM/许可/漏洞/哈希、连续五次全绿和人工发布门禁。

退出：干净环境 Qt onefile 构建成功且产物清单精确（`clean EXE`）；依赖许可证、SBOM、漏洞扫描与哈希记录完整（`license/SBOM`）；连续五次完整发布门禁全绿（`five green runs`）；人工发布门禁（HG-PACKAGING/HG-RELEASE）批准（`human release gate`）。

