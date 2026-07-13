import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.data.data_provider import parse_fund_flow_payload


def payload(klines):
    return json.dumps({"data": {"klines": klines}})


class FundFlowParseTests(unittest.TestCase):
    def test_parse_basic(self):
        flow = parse_fund_flow_payload(
            payload(
                [
                    "2026-06-20,100000000,0,0,0,0,0",
                    "2026-06-23,-200000000,0,0,0,0,0",
                    "2026-06-24,300000000,0,0,0,0,0",
                ]
            ),
            limit=3,
        )
        self.assertEqual(flow.today_main, 300000000.0)
        self.assertEqual(flow.main_5d, 200000000.0)  # 1e8 - 2e8 + 3e8
        self.assertEqual(len(flow.recent), 3)
        self.assertEqual(flow.recent[-1], ("2026-06-24", 300000000.0))

    def test_empty_returns_none(self):
        self.assertIsNone(parse_fund_flow_payload(payload([])))

    def test_non_dict_data_returns_none(self):
        self.assertIsNone(parse_fund_flow_payload(json.dumps({"data": None})))

    def test_skips_malformed_lines(self):
        flow = parse_fund_flow_payload(payload(["bad", "2026-06-24,500000000,0"]), limit=5)
        self.assertEqual(flow.today_main, 500000000.0)
        self.assertEqual(len(flow.recent), 1)

    def test_limit_trims_recent(self):
        lines = [f"2026-06-{d:02d},{d * 1000000},0" for d in range(1, 10)]
        flow = parse_fund_flow_payload(payload(lines), limit=3)
        self.assertEqual(len(flow.recent), 3)
        self.assertEqual(flow.today_main, 9000000.0)

    def test_non_finite_limit_uses_default_recent_window(self):
        lines = [f"2026-06-{d:02d},{d * 1000000},0" for d in range(1, 10)]

        flow = parse_fund_flow_payload(payload(lines), limit=float("nan"))

        self.assertEqual(len(flow.recent), 5)
        self.assertEqual(flow.recent[0], ("2026-06-05", 5000000.0))


if __name__ == "__main__":
    unittest.main()
