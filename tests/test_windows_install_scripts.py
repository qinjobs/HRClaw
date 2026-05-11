import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON_PS1 = ROOT / "install" / "windows" / "common.ps1"
INSTALL_PS1 = ROOT / "install" / "windows" / "install.ps1"
INSTALL_UV_PS1 = ROOT / "install" / "windows" / "install_uv.ps1"
INSTALL_KIMI_PS1 = ROOT / "install" / "windows" / "install_kimi_cli.ps1"
BUNDLE_SCRIPT = ROOT / "scripts" / "build_windows_offline_bundle.sh"


class WindowsInstallScriptTests(unittest.TestCase):
    def test_common_script_can_resolve_existing_python312(self):
        common_script = COMMON_PS1.read_text(encoding="utf-8")
        self.assertIn("function Resolve-SystemPython312", common_script)
        self.assertIn("function Test-PythonVersionMatch", common_script)
        self.assertIn("Python312", common_script)

    def test_install_script_reuses_existing_python_when_installer_returns_1638(self):
        install_script = INSTALL_PS1.read_text(encoding="utf-8")
        self.assertIn("Resolve-SystemPython312", install_script)
        self.assertIn("$installerProcess.ExitCode -eq 1638", install_script)
        self.assertIn("reusing existing system Python 3.12", install_script)

    def test_install_script_handles_missing_wheel_package_in_offline_mode(self):
        install_script = INSTALL_PS1.read_text(encoding="utf-8")
        self.assertIn('Get-ChildItem $wheelhouseDir -Filter "wheel-*.whl"', install_script)
        self.assertIn("local wheel package not found; continuing with setuptools only", install_script)

    def test_uv_and_kimi_install_scripts_exist(self):
        self.assertTrue(INSTALL_UV_PS1.exists())
        self.assertTrue(INSTALL_KIMI_PS1.exists())
        uv_script = INSTALL_UV_PS1.read_text(encoding="utf-8")
        self.assertIn('Join-Path $uvRuntimeDir "uv.exe"', uv_script)
        self.assertIn("Get-ChildItem -Path $uvRuntimeDir -Recurse -Filter \"uv.exe\"", uv_script)
        kimi_script = INSTALL_KIMI_PS1.read_text(encoding="utf-8")
        self.assertIn("--no-deps", kimi_script)
        self.assertIn("runtime dependency set", kimi_script)
        self.assertIn("The Windows runtime only needs the CLI bridge", kimi_script)
        kimi_requirements = (ROOT / "install" / "packages" / "windows" / "kimi-cli" / "requirements-kimi-cli-win-py312.txt").read_text(encoding="utf-8")
        self.assertNotIn("kimi-cli==1.35.0", kimi_requirements)
        self.assertNotIn("fastmcp", kimi_requirements)
        self.assertNotIn("openapi-spec-validator", kimi_requirements)
        self.assertNotIn("openapi-core", kimi_requirements)

    def test_bundle_script_includes_uv_and_kimi_entries(self):
        bundle_script = BUNDLE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("install/packages/windows/uv/uv-x86_64-pc-windows-msvc.zip", bundle_script)
        self.assertIn("install/packages/windows/kimi-cli/kimi_cli-*.whl", bundle_script)
        self.assertIn("install/packages/windows/kimi-cli/pywin32_ctypes-*.whl", bundle_script)
        self.assertIn("install/packages/windows/kimi-cli/ripgrepy-*.whl", bundle_script)
        self.assertIn("install/packages/windows/kimi-cli/win32_setctime-*.whl", bundle_script)
        self.assertIn("install/packages/windows/kimi-cli/pywin32-*.whl", bundle_script)
        self.assertIn("install/packages/windows/kimi-cli/tzdata-*.whl", bundle_script)
        self.assertIn('zip -qr -X', bundle_script)
        self.assertNotIn("ditto -c -k", bundle_script)
        self.assertIn("INSTALL_UV.BAT", bundle_script)
        self.assertIn("INSTALL_KIMI_CLI.BAT", bundle_script)


if __name__ == "__main__":
    unittest.main()
