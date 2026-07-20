"""与界面框架无关的展示层常量：应用身份、窗口尺寸、结果表列与排序序、免责声明。仅依赖标准库。

**颜色的权威真源是 `loop/product/tokens.json`**（带 WCAG 对比度实测），Qt 侧经 `qt_app/theme/tokens.py`
读取它生成 QSS。这里只留少数几个仍被非 Qt 路径用到的色值（说明书 HTML、纯函数格式化）——它们必须
与 tokens.json 一致，新增颜色一律加进 tokens.json 而不是这里，否则就又出现两个色源。

WI-023 删除 Tkinter 生产层后，本模块曾遗留 38 个只有 Tk 用过的常量（控件悬停/按下底色、滚动条三态、
表头底色、可见行数上下限、详情页导航分节、样例输入等）。它们无人引用，且作为第二套调色板与
tokens.json 构成分叉风险，已随 WI-029 清理。
"""

from __future__ import annotations

from pathlib import Path

MAX_SYMBOLS = 30
APP_TITLE = "股市锦囊"
APP_ICON_FILENAME = "a_stock_strategy.ico"
INFO_WINDOW_SIZE = (880, 580)
# 主窗口在「屏幕工作区」内居中，四周（含底部任务栏一侧）留出同样宽度的均匀空隙；
# 受 WINDOW_MAX_SIZE 上限与 MAIN_MIN_SIZE 下限夹制，避免大屏空旷或小屏挤压。
MAIN_MIN_SIZE = (1000, 680)
WINDOW_MAX_SIZE = (1600, 1600)
WINDOW_WORKAREA_MARGIN = 72
# 内容最大宽度 + 四边统一外边距：常规窗口下内容填满且四边均匀留白，仅在超宽屏才居中收窄，
# 避免组件被拉得过长。
MAX_CONTENT_WIDTH = 1520
CONTENT_MARGIN = 28

UI_FONT = "Microsoft YaHei UI"

PAGE_BG = "#f4f2ed"
CARD_BG = "#fffdf9"

INK = "#17212b"
MUTED_INK = "#626d7a"

ACCENT = "#173a5e"
DANGER_COLOR = "#9a4b1f"

COMMAND_BG = "#142b3d"
COMMAND_INK = "#f7f5ef"
COMMAND_MUTED_INK = "#b8c4cf"

# A股本土配色：红=涨/买/积极，绿=跌/卖/谨慎（全局统一，红即看多）。
POS_COLOR = "#b4232c"  # 涨 / 买入 / 积极 / 正分
NEG_COLOR = "#167044"  # 跌 / 卖出 / 谨慎 / 负分
FLAT_COLOR = "#65717d"  # 中性 / 观望
ACTION_BUTTON_LABELS = ("开始分析", "停止", "输入工具")
ASSET_DIR = Path(__file__).resolve().parents[2] / "assets"
# 核心措辞须与 models.CORE_DISCLAIMER（policy.py 每条决策 risks 追加的免责句）保持一致，
# 仅在此基础上加交易前核验提醒的页脚长文案；本模块为保持"仅依赖标准库"不 import models，
# 一致性由 tests/test_policy.py::DisclaimerConsistencyTests 兜底校验。
DISCLAIMER = "模型仅供研究和辅助决策，不构成投资建议；交易前请自行核验行情、公告和风险。"
DETAIL_SECTION_TITLES = {
    "核心结论",
    "看懂结果",
    "判断拆解",
    "为什么这样判断",
    "需要注意",
    "快照特征",
}
TABLE_COLUMNS = ("code", "name", "action", "score", "confidence", "last", "change", "risk")
TABLE_COLUMN_INDEX = {column: index for index, column in enumerate(TABLE_COLUMNS)}
RISK_ORDER = {"低": 0.0, "中": 1.0, "高": 2.0}
ACTION_ORDER = {"买入/加仓": 0.0, "继续持有/观望": 1.0, "卖出/减仓": 2.0}
