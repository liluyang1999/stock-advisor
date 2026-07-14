"""UI 常量单一真源:颜色、尺寸、表列、排序序、免责声明、样例输入。仅依赖标准库。"""

from __future__ import annotations

from pathlib import Path

MAX_SYMBOLS = 30
MONITOR_INTERVAL_MS = 60000  # 实时预警轮询间隔（毫秒）
APP_TITLE = "股市锦囊"
APP_ICON_FILENAME = "a_stock_strategy.ico"
INFO_WINDOW_SIZE = (880, 580)
# 主窗口在「屏幕工作区」内居中，四周（含底部任务栏一侧）留出同样宽度的均匀空隙；
# 受 WINDOW_MAX_SIZE 上限与 MAIN_MIN_SIZE 下限夹制，避免大屏空旷或小屏挤压。
MAIN_MIN_SIZE = (1000, 680)
WINDOW_MAX_SIZE = (1600, 1600)
WINDOW_WORKAREA_MARGIN = 72
# 子窗口仍相对主窗居中，但在首选尺寸超过屏幕时为外框保留一圈可见安全边距。
CHILD_WINDOW_WORKAREA_MARGIN = 24
# 整窗不透明：不创建分层（半透明）窗口，省去逐帧合成开销，桌面底色也不再透出。
WINDOW_ALPHA = 1.0
# 内容最大宽度 + 四边统一外边距：常规窗口下内容填满且四边均匀留白，仅在超宽屏才居中收窄，
# 避免组件被拉得过长。
MAX_CONTENT_WIDTH = 1520
CONTENT_MARGIN = 28
HEADER_LOGO_SIZE = 48
MENU_BUTTON_SHORT_WIDTH = 6
MENU_BUTTON_TOOL_WIDTH = 8

# 视觉基调：暖灰纸面 + 墨蓝工作带。市场红/绿只表达行情语义，不承担普通交互强调。
# 所有常用表面、边界和状态色集中在这里，避免 app.py 中同义颜色漂移。
UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"

PAGE_BG = "#f4f2ed"
CARD_BG = "#fffdf9"
SURFACE_ALT = "#f8f6f1"
CONTROL_BG = "#f0eee8"
CONTROL_HOVER_BG = "#e5ebef"
CONTROL_DISABLED_BG = "#e7e5e0"
CARD_BORDER = "#d9d5cc"
BORDER_SOFT = "#e7e3da"
GRID_COLOR = "#ece8df"

INK = "#17212b"
INK_SOFT = "#344250"
MUTED_INK = "#626d7a"
MUTED_LIGHT = "#89939d"

ACCENT = "#173a5e"
ACCENT_HOVER = "#214d76"
ACCENT_PRESSED = "#102d49"
ACCENT_SOFT = "#e8eef2"
ACCENT_SOFT_HOVER = "#dce7ed"
SELECTION_BG = "#dbe7ee"
DANGER_COLOR = "#9a4b1f"
DANGER_BG = "#fff1e8"

COMMAND_BG = "#142b3d"
COMMAND_SURFACE = "#203b4e"
COMMAND_BORDER = "#355267"
COMMAND_INK = "#f7f5ef"
COMMAND_MUTED_INK = "#b8c4cf"
COMMAND_SELECTED_BG = CARD_BG
COMMAND_SELECTED_INK = COMMAND_BG

TABLE_HEADER_BG = "#ece9e2"
SCROLLBAR_BG = "#bcc3c7"
SCROLLBAR_ACTIVE_BG = "#9da9b1"
SCROLLBAR_PRESSED_BG = "#89969f"

# A股本土配色：红=涨/买/积极，绿=跌/卖/谨慎（全局统一，红即看多）。
POS_COLOR = "#b4232c"  # 涨 / 买入 / 积极 / 正分
NEG_COLOR = "#167044"  # 跌 / 卖出 / 谨慎 / 负分
FLAT_COLOR = "#65717d"  # 中性 / 观望
POS_BG = "#fbefef"  # 买入行底色（淡红）
NEG_BG = "#edf7f1"  # 卖出行底色（淡绿）
HOLD_BG = "#f5f3ee"  # 观望行底色
ACTION_BUTTON_LABELS = ("开始分析", "停止", "输入工具")
TABLE_MIN_VISIBLE_ROWS = 4
TABLE_MAX_VISIBLE_ROWS = 7
TABLE_EMPTY_VISIBLE_ROWS = 1
DETAIL_NAV_SECTIONS = (
    ("结论", "核心结论"),
    ("依据", "判断拆解"),
    ("风险", "需要注意"),
    ("操作", "仓位 / 风控计算器"),
)
ASSET_DIR = Path(__file__).resolve().parents[2] / "assets"
SAMPLE_INPUT = "600519, 000001, 300750, 688981"
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
