import subprocess
import unittest
from pathlib import Path


class BrowserExtensionTests(unittest.TestCase):
    def test_node_extension_suite(self):
        root = Path(__file__).resolve().parents[1]
        test_file = root / "tests" / "extension" / "plugin.test.js"
        completed = subprocess.run(
            ["node", "--test", str(test_file)],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            self.fail(
                "Node extension tests failed.\n"
                f"STDOUT:\n{completed.stdout}\n"
                f"STDERR:\n{completed.stderr}"
            )
