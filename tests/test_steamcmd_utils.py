import os
import tempfile
import unittest

from steamcmd_utils import (
    build_workshop_download_command,
    classify_workshop_items,
    ensure_console_language_file,
    parse_steamcmd_output_line,
    should_log_noisy_line,
)


class SteamCmdUtilsTests(unittest.TestCase):
    def test_ensure_console_language_file_creates_expected_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            steamcmd_path = os.path.join(temp_dir, "steamcmd.exe")
            with open(steamcmd_path, "w", encoding="utf-8") as handle:
                handle.write("stub")

            cfg_path = ensure_console_language_file(steamcmd_path)
            self.assertTrue(os.path.exists(cfg_path))
            with open(cfg_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), '@Language "english"\n')

    def test_build_workshop_download_command(self):
        cmd = build_workshop_download_command("steamcmd.exe", "cache", "301650", ["1", "2"])
        self.assertEqual(
            cmd,
            [
                "steamcmd.exe",
                "+force_install_dir",
                "cache",
                "+login",
                "anonymous",
                "+workshop_download_item",
                "301650",
                "1",
                "+workshop_download_item",
                "301650",
                "2",
                "+quit",
            ],
        )

    def test_classify_workshop_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            appid = "301650"
            existing = os.path.join(temp_dir, "steamapps", "workshop", "content", appid, "1")
            os.makedirs(existing)

            def build_mod_cache_path(cache_root, resolved_appid, mid):
                return os.path.join(cache_root, "steamapps", "workshop", "content", resolved_appid, mid)

            result = classify_workshop_items(temp_dir, appid, ["1", "2"], build_mod_cache_path)
            self.assertEqual(result, [("1", True), ("2", False)])

    def test_parse_steamcmd_output_line(self):
        self.assertEqual(parse_steamcmd_output_line(""), {"kind": "empty", "message": ""})
        self.assertEqual(parse_steamcmd_output_line("Success. Downloaded item 123")["kind"], "success")
        self.assertEqual(parse_steamcmd_output_line("ERROR! Failed to install")["kind"], "error")
        self.assertEqual(parse_steamcmd_output_line("progress: 42.50")["value"], 42.5)
        self.assertEqual(parse_steamcmd_output_line("Verifying installation")["kind"], "verifying")
        self.assertEqual(parse_steamcmd_output_line("Update state (0x61)")["kind"], "ignore")
        self.assertEqual(parse_steamcmd_output_line("Downloading item...")["kind"], "noisy")
        self.assertEqual(parse_steamcmd_output_line("Random status")["kind"], "info")

    def test_should_log_noisy_line(self):
        self.assertFalse(should_log_noisy_line(10.5, 10.0))
        self.assertTrue(should_log_noisy_line(11.1, 10.0))


if __name__ == "__main__":
    unittest.main()
