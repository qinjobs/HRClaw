import os
import signal
import socket
import subprocess
import time
import unittest
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = ROOT / "scripts" / "start_phase1_server.sh"
STOP_SCRIPT = ROOT / "scripts" / "stop_phase1_server.sh"


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class Phase1ServerScriptTests(unittest.TestCase):
    def test_start_script_keeps_server_alive_after_script_exits(self):
        port = _free_port()
        temp_dir = ROOT / "snapshots" / "tmp" / "phase1-script-test"
        temp_dir.mkdir(parents=True, exist_ok=True)
        pid_file = temp_dir / "phase1_server.pid"
        log_file = temp_dir / "phase1_server.log"
        label_file = temp_dir / "phase1_server.label"
        for path in (pid_file, log_file, label_file):
            if path.exists():
                path.unlink()

        env = os.environ.copy()
        env["SCREENING_SERVER_HOST"] = "127.0.0.1"
        env["SCREENING_SERVER_PORT"] = str(port)
        env["SCREENING_PUBLIC_BASE_URL"] = f"http://127.0.0.1:{port}"
        env["SCREENING_SERVER_PID_FILE"] = str(pid_file)
        env["SCREENING_SERVER_LOG_FILE"] = str(log_file)
        env["SCREENING_SERVER_LABEL_FILE"] = str(label_file)
        env["SCREENING_SERVER_LABEL"] = f"com.hrclaw.phase1.test.{port}"

        result = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(pid_file.exists(), msg=result.stdout + result.stderr)

        pid = int(pid_file.read_text(encoding="utf-8").strip())
        try:
            time.sleep(1.0)
            os.kill(pid, 0)
            with urllib_request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read().decode("utf-8"), '{"status": "ok"}')
        finally:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            if pid_file.exists():
                pid_file.unlink()
            if label_file.exists():
                label = label_file.read_text(encoding="utf-8").strip()
                if label:
                    subprocess.run(
                        ["launchctl", "remove", label],
                        cwd=ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                label_file.unlink()

    def test_stop_script_respects_custom_pid_and_label_files(self):
        port = _free_port()
        temp_dir = ROOT / "snapshots" / "tmp" / "phase1-script-stop-test"
        temp_dir.mkdir(parents=True, exist_ok=True)
        pid_file = temp_dir / "phase1_server.pid"
        log_file = temp_dir / "phase1_server.log"
        label_file = temp_dir / "phase1_server.label"
        for path in (pid_file, log_file, label_file):
            if path.exists():
                path.unlink()

        env = os.environ.copy()
        env["SCREENING_SERVER_HOST"] = "127.0.0.1"
        env["SCREENING_SERVER_PORT"] = str(port)
        env["SCREENING_PUBLIC_BASE_URL"] = f"http://127.0.0.1:{port}"
        env["SCREENING_SERVER_PID_FILE"] = str(pid_file)
        env["SCREENING_SERVER_LOG_FILE"] = str(log_file)
        env["SCREENING_SERVER_LABEL_FILE"] = str(label_file)
        env["SCREENING_SERVER_LABEL"] = f"com.hrclaw.phase1.test.stop.{port}"

        start_result = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(start_result.returncode, 0, msg=start_result.stdout + start_result.stderr)
        self.assertTrue(pid_file.exists(), msg=start_result.stdout + start_result.stderr)
        self.assertTrue(label_file.exists(), msg=start_result.stdout + start_result.stderr)

        stop_result = subprocess.run(
            ["bash", str(STOP_SCRIPT)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(stop_result.returncode, 0, msg=stop_result.stdout + stop_result.stderr)
        time.sleep(1.0)
        self.assertFalse(pid_file.exists(), msg=stop_result.stdout + stop_result.stderr)
        self.assertFalse(label_file.exists(), msg=stop_result.stdout + stop_result.stderr)
        with self.assertRaises(urllib_error.URLError):
            urllib_request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)


if __name__ == "__main__":
    unittest.main()
