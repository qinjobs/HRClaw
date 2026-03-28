import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import boss_auth


class BossAuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.storage_state_path = Path(self.tmpdir.name) / "boss_storage_state.json"
        patcher = mock.patch.dict(
            os.environ,
            {"SCREENING_BROWSER_STORAGE_STATE_PATH": str(self.storage_state_path)},
            clear=False,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sync_boss_storage_state_writes_playwright_storage_file(self):
        summary = boss_auth.sync_boss_storage_state(
            cookies=[
                {
                    "name": "wt2",
                    "value": "abc123",
                    "domain": ".zhipin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "no_restriction",
                    "expirationDate": 1893456000,
                }
            ],
            current_url="https://www.zhipin.com/web/chat/index",
            source="chrome_extension",
            browser="chrome",
        )

        self.assertTrue(summary["ok"])
        self.assertTrue(self.storage_state_path.exists())
        payload = json.loads(self.storage_state_path.read_text("utf-8"))
        self.assertEqual(len(payload["cookies"]), 1)
        self.assertEqual(payload["cookies"][0]["sameSite"], "None")
        self.assertEqual(payload["cookies"][0]["domain"], ".zhipin.com")

    def test_save_boss_storage_state_reports_missing_synced_session(self):
        summary = boss_auth.save_boss_storage_state()

        self.assertFalse(summary["ok"])
        self.assertFalse(summary["login_detected"])
        self.assertTrue(summary["manual_login_required"])
        self.assertIn("Chrome", summary["message"])

    def test_save_boss_storage_state_validates_synced_session(self):
        boss_auth.sync_boss_storage_state(
            cookies=[
                {
                    "name": "wt2",
                    "value": "abc123",
                    "domain": ".zhipin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "lax",
                }
            ],
            current_url="https://www.zhipin.com/web/chat/index",
        )

        fake_response = mock.Mock()
        fake_response.url = "https://www.zhipin.com/web/chat/index"
        fake_response.text = "职位管理 推荐牛人 沟通 牛人管理"
        with mock.patch("src.screening.boss_auth.requests.Session.get", return_value=fake_response):
            summary = boss_auth.save_boss_storage_state()

        self.assertTrue(summary["ok"])
        self.assertTrue(summary["login_detected"])
        self.assertEqual(summary["reason"], "recruiter_ui_detected")

    def test_save_boss_storage_state_prefers_browser_snapshot_for_logged_in_recruiter_page(self):
        boss_auth.sync_boss_storage_state(
            cookies=[
                {
                    "name": "wt2",
                    "value": "abc123",
                    "domain": ".zhipin.com",
                    "path": "/",
                }
            ],
            current_url="https://www.zhipin.com/web/chat/index",
            browser_snapshot={
                "current_url": "https://www.zhipin.com/web/chat/index",
                "page_title": "BOSS直聘",
                "body_text": "消息中心 候选人列表 简历详情 继续沟通",
            },
        )

        summary = boss_auth.save_boss_storage_state()

        self.assertTrue(summary["ok"])
        self.assertTrue(summary["login_detected"])
        self.assertEqual(summary["reason"], "recruiter_page_detected")
