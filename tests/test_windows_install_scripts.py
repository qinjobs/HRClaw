import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON_PS1 = ROOT / "install" / "windows" / "common.ps1"
INSTALL_PS1 = ROOT / "install" / "windows" / "install.ps1"
START_SERVER_PS1 = ROOT / "install" / "windows" / "start_server.ps1"
INSTALL_UV_PS1 = ROOT / "install" / "windows" / "install_uv.ps1"
INSTALL_KIMI_PS1 = ROOT / "install" / "windows" / "install_kimi_cli.ps1"
BUNDLE_SCRIPT = ROOT / "scripts" / "build_windows_offline_bundle.sh"


class WindowsInstallScriptTests(unittest.TestCase):
    def test_common_script_can_resolve_existing_python312(self):
        common_script = COMMON_PS1.read_text(encoding="utf-8")
        self.assertIn("function Try-GetInstallRoot", common_script)
        self.assertIn("function Resolve-SystemPython312", common_script)
        self.assertIn("function Test-PythonVersionMatch", common_script)
        self.assertIn("Python312", common_script)
        self.assertIn('Programs\\Python\\Launcher\\py.exe', common_script)

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

    def test_bundle_start_server_bat_redirects_output_to_server_log(self):
        bundle_script = BUNDLE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('set "LOG_DIR=%~dp0data\\logs"', bundle_script)
        self.assertIn('set "SERVER_LOG=%LOG_DIR%\\server.log"', bundle_script)
        self.assertIn('>> "%SERVER_LOG%" 2>&1', bundle_script)

    def test_windows_start_server_launches_visible_chrome_recommend_page(self):
        start_server_script = START_SERVER_PS1.read_text(encoding="utf-8")
        self.assertIn("Try-GetInstallRoot", start_server_script)
        self.assertIn('https://www.zhipin.com/web/chat/recommend', start_server_script)
        self.assertIn('"--new-window"', start_server_script)
        self.assertIn('"--no-first-run"', start_server_script)
        self.assertIn('Write-Stage "launching Chrome with CDP port $Port"', start_server_script)
        self.assertIn('Join-Path $env:USERPROFILE ".hrclaw-chrome-cdp-$chromeCdpPort"', start_server_script)
        self.assertIn('Start-Process -FilePath $chromeExe', start_server_script)
        self.assertIn('"--remote-debugging-port=$Port"', start_server_script)
        self.assertIn('"--user-data-dir=$ProfileDir"', start_server_script)

    def test_installer_script_pins_non_small_sfx_module(self):
        installer_script = (ROOT / "scripts" / "build_windows_installer_exe.sh").read_text(encoding="utf-8")
        self.assertIn('SDK_ARCHIVE_URL="https://7-zip.org/a/lzma${SEVENZIP_VERSION}.7z"', installer_script)
        self.assertIn('local candidate="$sdk_dir/bin/7zSD.sfx"', installer_script)
        self.assertNotIn('"$sdk_dir/bin/7zS2.sfx"', installer_script)
        self.assertNotIn('"$sdk_dir/bin/7zS2con.sfx"', installer_script)
        self.assertIn('using SFX module: $(basename "$SFX_MODULE")', installer_script)

    def test_installer_launcher_allows_user_to_choose_install_directory(self):
        installer_script = (ROOT / "scripts" / "build_windows_installer_exe.sh").read_text(encoding="utf-8")
        self.assertIn("FolderBrowserDialog", installer_script)
        self.assertIn("SelectedPath", installer_script)
        self.assertIn('$installBat = Join-Path $targetDir "INSTALL.BAT"', installer_script)
        self.assertIn("Start-Process -FilePath $installBat", installer_script)
        self.assertIn("Choose the HRClaw installation folder", installer_script)

    def test_installer_script_uses_configurable_stable_compression_level(self):
        installer_script = (ROOT / "scripts" / "build_windows_installer_exe.sh").read_text(encoding="utf-8")
        self.assertIn('SEVENZIP_COMPRESSION_LEVEL="${SEVENZIP_COMPRESSION_LEVEL:-1}"', installer_script)
        self.assertIn('"$SEVENZIP_BIN" a -t7z "-mx=$SEVENZIP_COMPRESSION_LEVEL"', installer_script)


if __name__ == "__main__":
    unittest.main()
