import unittest

from src.screening.api import _task_runner_page_html


class TaskRunnerPageTests(unittest.TestCase):
    def test_fallback_page_includes_keyword_filter_hint(self):
        html = _task_runner_page_html("admin")
        self.assertIn('id="keyword"', html)
        self.assertIn(
            "\u4f8b\u5982\uff1a\u5b57\u8282\uff1bAI\uff1b\u4ea7\u54c1\u7ecf\u7406",
            html,
        )


if __name__ == "__main__":
    unittest.main()
