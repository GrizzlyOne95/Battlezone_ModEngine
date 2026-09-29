import io
import os
import tempfile
import unittest
import zipfile

from steamcmd_utils import (
    build_workshop_download_command,
    classify_workshop_items,
    ensure_console_language_file,
    parse_steamcmd_output_line,
    safe_extract_zip,
    should_log_noisy_line,
    summarize_download_batch,
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

    def test_real_steamcmd_failure_lines_are_errors(self):
        for line in [
            "ERROR! Download item 1234567 failed (Failure).",
            "ERROR! Timeout downloading item 1234567",
            "ERROR! Download item 1234567 failed (File Not Found).",
        ]:
            self.assertEqual(parse_steamcmd_output_line(line)["kind"], "error", line)

    def test_benign_startup_noise_is_not_an_error(self):
        for line in [
            'ILocalize::AddFile() failed to load file "public/steambootstrapper_english.txt".',
            "Failed to init SDL priority manager: SDL not found",
            "Loading Steam API...OK",
        ]:
            self.assertEqual(parse_steamcmd_output_line(line)["kind"], "info", line)

    def test_success_line_yields_bare_item_id(self):
        event = parse_steamcmd_output_line(
            'Success. Downloaded item 1234567 to "/cache/steamapps/workshop/content/301650/1234567" (4096 bytes)'
        )
        self.assertEqual(event["kind"], "success")
        self.assertEqual(event["item"], "1234567")

    def test_ensure_console_language_file_tolerates_unwritable_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_dir = os.path.join(temp_dir, "not-a-dir", "steamcmd")
            self.assertIsNone(ensure_console_language_file(missing_dir))

    def test_safe_extract_zip_rejects_path_traversal(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evil.txt", "x")
        with tempfile.TemporaryDirectory() as temp_dir:
            target = os.path.join(temp_dir, "target")
            os.makedirs(target)
            with zipfile.ZipFile(buffer) as archive:
                with self.assertRaises(ValueError):
                    safe_extract_zip(archive, target)
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "evil.txt")))

    def test_safe_extract_zip_extracts_normal_archive(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("steamcmd.exe", "x")
            archive.writestr("package/readme.txt", "y")
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(buffer) as archive:
                safe_extract_zip(archive, temp_dir)
            self.assertTrue(os.path.isfile(os.path.join(temp_dir, "package", "readme.txt")))

    def test_summarize_download_batch(self):
        on_disk = {"1", "2"}
        all_ok = summarize_download_batch(["1", "2"], {"1", "2"}, on_disk.__contains__)
        self.assertEqual(all_ok["status"], "DEPLOYED")

        mixed = summarize_download_batch(["1", "2", "3"], {"1"}, on_disk.__contains__)
        self.assertEqual(mixed["downloaded"], ["1"])
        self.assertEqual(mixed["stale"], ["2"])
        self.assertEqual(mixed["missing"], ["3"])
        self.assertEqual(mixed["status"], "PARTIAL")

        none = summarize_download_batch(["3"], set(), on_disk.__contains__)
        self.assertEqual(none["status"], "FAILED")

    def test_should_log_noisy_line(self):
        self.assertFalse(should_log_noisy_line(10.5, 10.0))
        self.assertTrue(should_log_noisy_line(11.1, 10.0))


if __name__ == "__main__":
    unittest.main()
