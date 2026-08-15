import unittest
from datetime import datetime
from unittest.mock import patch

import ensure_dev_queue


NOW = datetime(2026, 8, 15, 9, 0, tzinfo=ensure_dev_queue.BEIJING)


class DevQueueRefreshTest(unittest.TestCase):
    @patch("ensure_dev_queue._run_gh")
    def test_successful_schedule_does_not_dispatch(self, run_gh):
        run_gh.return_value = '[{"createdAt":"2026-08-15T01:20:00Z","event":"schedule","status":"completed","conclusion":"success"}]'

        result = ensure_dev_queue.ensure_dev_queue(NOW)

        self.assertEqual(result["status"], "already_checked")
        self.assertEqual(run_gh.call_count, 1)

    @patch("ensure_dev_queue._run_gh")
    def test_active_fallback_does_not_dispatch(self, run_gh):
        run_gh.return_value = '[{"createdAt":"2026-08-15T00:59:00Z","event":"workflow_dispatch","displayTitle":"DEV queue fallback","status":"in_progress","conclusion":""}]'

        result = ensure_dev_queue.ensure_dev_queue(NOW)

        self.assertEqual(result["status"], "already_running")
        self.assertEqual(run_gh.call_count, 1)

    @patch("ensure_dev_queue._run_gh")
    def test_missing_queue_run_dispatches_once(self, run_gh):
        run_gh.side_effect = ["[]", ""]

        result = ensure_dev_queue.ensure_dev_queue(NOW)

        self.assertEqual(result["status"], "dispatched")
        dispatch = run_gh.call_args_list[1].args[0]
        self.assertEqual(dispatch[:3], ["workflow", "run", "publish-dev-guide.yml"])
        self.assertIn("publish_next_due=true", dispatch)

    @patch("ensure_dev_queue._run_gh")
    def test_selected_guide_run_does_not_hide_missing_queue_check(self, run_gh):
        run_gh.side_effect = [
            '[{"createdAt":"2026-08-15T01:00:00Z","event":"workflow_dispatch","displayTitle":"DEV guide grants-gov-monitor","status":"completed","conclusion":"success"}]',
            "",
        ]

        result = ensure_dev_queue.ensure_dev_queue(NOW)

        self.assertEqual(result["status"], "dispatched")
        self.assertEqual(run_gh.call_count, 2)

    @patch("ensure_dev_queue._run_gh")
    def test_failed_fallback_is_not_retried_the_same_day(self, run_gh):
        run_gh.return_value = '[{"createdAt":"2026-08-15T01:00:00Z","event":"workflow_dispatch","displayTitle":"DEV queue fallback","status":"completed","conclusion":"failure"}]'

        result = ensure_dev_queue.ensure_dev_queue(NOW)

        self.assertEqual(result["status"], "fallback_failed")
        self.assertEqual(run_gh.call_count, 1)


if __name__ == "__main__":
    unittest.main()
