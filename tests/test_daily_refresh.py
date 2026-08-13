import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import ensure_daily_refresh


class DailyRefreshTest(unittest.TestCase):
    def test_runs_today_uses_beijing_calendar_day(self):
        records = [
            {"createdAt": "2026-08-12T23:30:00Z", "status": "completed", "conclusion": "success"},
            {"createdAt": "2026-08-12T15:59:00Z", "status": "completed", "conclusion": "success"},
        ]
        now = datetime(2026, 8, 13, 2, 0, tzinfo=timezone.utc)
        selected = ensure_daily_refresh.runs_today(records, now)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["createdAt"], "2026-08-12T23:30:00Z")

    @patch("ensure_daily_refresh._run_gh")
    def test_successful_run_does_not_dispatch(self, run_gh):
        run_gh.return_value = '[{"createdAt":"2026-08-13T00:17:00Z","status":"completed","conclusion":"success","url":"ok"}]'
        result = ensure_daily_refresh.ensure_refresh(
            datetime(2026, 8, 13, 9, 0, tzinfo=ensure_daily_refresh.BEIJING)
        )
        self.assertEqual(result["status"], "already_refreshed")
        self.assertEqual(run_gh.call_count, 1)

    @patch("ensure_daily_refresh._run_gh")
    def test_active_run_does_not_dispatch(self, run_gh):
        run_gh.return_value = '[{"createdAt":"2026-08-13T01:00:00Z","status":"in_progress","conclusion":""}]'
        result = ensure_daily_refresh.ensure_refresh(
            datetime(2026, 8, 13, 9, 0, tzinfo=ensure_daily_refresh.BEIJING)
        )
        self.assertEqual(result["status"], "already_running")
        self.assertEqual(run_gh.call_count, 1)

    @patch("ensure_daily_refresh._run_gh")
    def test_missing_run_dispatches_once(self, run_gh):
        run_gh.side_effect = ["[]", ""]
        result = ensure_daily_refresh.ensure_refresh(
            datetime(2026, 8, 13, 9, 0, tzinfo=ensure_daily_refresh.BEIJING)
        )
        self.assertEqual(result["status"], "dispatched")
        self.assertEqual(run_gh.call_count, 2)
        dispatch = run_gh.call_args_list[1].args[0]
        self.assertEqual(dispatch[:3], ["workflow", "run", "publish.yml"])


if __name__ == "__main__":
    unittest.main()
