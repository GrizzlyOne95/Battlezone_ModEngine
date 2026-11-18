"""Regression tests for bugs found in the cross-platform bug hunt."""

import io
import os
import stat
import tarfile
import tempfile
import unittest
from datetime import datetime

from game_discovery import get_linux_heroic_paths, is_valid_game_path
from platform_utils import get_steamcmd_candidates, get_subprocess_env, open_path
from steamcmd_utils import (
    final_batch_status,
    get_steamcmd_download_url,
    safe_extract_tar,
)
from workshop_parser import parse_workshop_datetime, parse_workshop_id


class WorkshopDateTests(unittest.TestCase):
    def test_month_first_dates_parse_like_day_first(self):
        expected = datetime(2016, 10, 23, 15, 47)
        self.assertEqual(parse_workshop_datetime("23 Oct, 2016 @ 3:47pm"), expected)
        self.assertEqual(parse_workshop_datetime("Oct 23, 2016 @ 3:47pm"), expected)

    def test_month_first_without_year_uses_current_year(self):
        now = datetime(2026, 11, 18)
        self.assertEqual(
            parse_workshop_datetime("Oct 23 @ 3:47pm", now=now),
            datetime(2026, 10, 23, 15, 47),
        )

    def test_garbage_is_rejected(self):
        self.assertIsNone(parse_workshop_datetime("Foo 23, 2016 @ 3:47pm"))
        self.assertIsNone(parse_workshop_datetime("Oct Oct, 2016 @ 3:47pm"))


class WorkshopIdTests(unittest.TestCase):
    def test_accepts_ids_web_links_and_steam_links(self):
        self.assertEqual(parse_workshop_id(" 123456 "), "123456")
        self.assertEqual(
            parse_workshop_id("https://steamcommunity.com/sharedfiles/filedetails/?id=123456"),
            "123456",
        )
        self.assertEqual(
            parse_workshop_id("https://steamcommunity.com/sharedfiles/filedetails/?l=english&id=42"),
            "42",
        )
        self.assertEqual(parse_workshop_id("steam://url/CommunityFilePage/987654"), "987654")
        self.assertEqual(parse_workshop_id("{https://steamcommunity.com/sharedfiles/filedetails/?id=7}"), "7")

    def test_does_not_mistake_appid_for_item_id(self):
        self.assertIsNone(parse_workshop_id("https://steamcommunity.com/app/301650/workshop/?appid=301650"))
        self.assertIsNone(parse_workshop_id(""))
        self.assertIsNone(parse_workshop_id(None))


class BatchStatusTests(unittest.TestCase):
    def test_nothing_deployed_is_failed_not_partial(self):
        outcome = {"downloaded": ["1", "2"], "stale": [], "missing": ["3"]}
        self.assertEqual(final_batch_status(outcome, deploy_failures=2), "FAILED")

    def test_some_deployed_is_partial(self):
        outcome = {"downloaded": ["1", "2"], "stale": [], "missing": ["3"]}
        self.assertEqual(final_batch_status(outcome, deploy_failures=0), "PARTIAL")
        outcome = {"downloaded": ["1", "2"], "stale": [], "missing": []}
        self.assertEqual(final_batch_status(outcome, deploy_failures=1), "PARTIAL")

    def test_everything_deployed(self):
        outcome = {"downloaded": ["1"], "stale": [], "missing": []}
        self.assertEqual(final_batch_status(outcome, deploy_failures=0), "DEPLOYED")


class SteamCmdInstallTests(unittest.TestCase):
    def test_each_platform_has_its_own_package(self):
        self.assertTrue(get_steamcmd_download_url(True, False).endswith("steamcmd.zip"))
        self.assertTrue(get_steamcmd_download_url(False, True).endswith("steamcmd_linux.tar.gz"))
        self.assertTrue(get_steamcmd_download_url(False, False).endswith("steamcmd_osx.tar.gz"))

    def _tar(self, members):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for info, data in members:
                archive.addfile(info, io.BytesIO(data) if data is not None else None)
        buffer.seek(0)
        return tarfile.open(fileobj=buffer, mode="r:gz")

    def test_tar_extraction_keeps_executable_bit(self):
        info = tarfile.TarInfo("steamcmd.sh")
        data = b"#!/bin/sh\n"
        info.size = len(data)
        info.mode = 0o755
        with tempfile.TemporaryDirectory() as temp_dir, self._tar([(info, data)]) as archive:
            safe_extract_tar(archive, temp_dir)
            mode = os.stat(os.path.join(temp_dir, "steamcmd.sh")).st_mode
            if os.name != "nt":
                self.assertTrue(mode & stat.S_IXUSR)

    def test_tar_extraction_rejects_traversal_and_links(self):
        escape = tarfile.TarInfo("../evil.sh")
        escape.size = 0
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        relative_escape = tarfile.TarInfo("sub/link")
        relative_escape.type = tarfile.SYMTYPE
        relative_escape.linkname = "../../outside"
        fifo = tarfile.TarInfo("pipe")
        fifo.type = tarfile.FIFOTYPE
        for member in (escape, link, relative_escape, fifo):
            with tempfile.TemporaryDirectory() as temp_dir, self._tar([(member, b"")]) as archive:
                with self.assertRaises(ValueError):
                    safe_extract_tar(archive, temp_dir)
                self.assertEqual(os.listdir(temp_dir), [])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_tar_extraction_allows_internal_relative_links(self):
        target = tarfile.TarInfo("Frameworks/A.framework/Versions/A/A")
        target.size = 1
        current = tarfile.TarInfo("Frameworks/A.framework/Versions/Current")
        current.type = tarfile.SYMTYPE
        current.linkname = "A"
        with tempfile.TemporaryDirectory() as temp_dir, self._tar([(target, b"x"), (current, None)]) as archive:
            safe_extract_tar(archive, temp_dir)
            self.assertTrue(
                os.path.isfile(os.path.join(temp_dir, "Frameworks/A.framework/Versions/Current/A"))
            )

    def test_macos_has_steamcmd_candidates_beyond_bundle(self):
        candidates = get_steamcmd_candidates("/app/bin", False, False, home="/Users/me")
        self.assertIn("/opt/homebrew/bin/steamcmd", candidates)
        self.assertIn(os.path.join("/Users/me", "steamcmd", "steamcmd.sh"), candidates)


class SubprocessEnvTests(unittest.TestCase):
    def test_frozen_linux_restores_original_library_path(self):
        env = get_subprocess_env(
            True,
            True,
            env={"LD_LIBRARY_PATH": "/tmp/_MEI123", "LD_LIBRARY_PATH_ORIG": "/usr/lib/custom", "HOME": "/h"},
        )
        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/lib/custom")
        self.assertNotIn("LD_LIBRARY_PATH_ORIG", env)
        self.assertEqual(env["HOME"], "/h")

    def test_frozen_linux_drops_bundle_library_path(self):
        env = get_subprocess_env(True, True, env={"LD_LIBRARY_PATH": "/tmp/_MEI123"})
        self.assertNotIn("LD_LIBRARY_PATH", env)

    def test_no_change_when_not_needed(self):
        self.assertIsNone(get_subprocess_env(True, False))
        self.assertIsNone(get_subprocess_env(False, True))

    def test_open_path_passes_env(self):
        calls = []

        class FakeSubprocess:
            DEVNULL = object()

            @staticmethod
            def Popen(args, **kwargs):
                calls.append((args, kwargs))

        open_path("steam://rungameid/1", False, True, subprocess_module=FakeSubprocess, env={"A": "1"})
        self.assertEqual(calls[0][0], ["xdg-open", "steam://rungameid/1"])
        self.assertEqual(calls[0][1]["env"], {"A": "1"})


class GameDiscoveryRegressionTests(unittest.TestCase):
    def test_executable_match_is_case_insensitive(self):
        game = {"exe": "battlezone98redux.exe"}
        with tempfile.TemporaryDirectory() as temp_dir:
            open(os.path.join(temp_dir, "Battlezone98Redux.EXE"), "wb").close()
            self.assertTrue(is_valid_game_path(game, temp_dir))
            self.assertFalse(is_valid_game_path({"exe": "battlezone2.exe"}, temp_dir))

    def test_heroic_scan_skips_store_cache(self):
        game = {"name": "Battlezone 98 Redux", "gog_ids": ["1454067812"], "exe": "battlezone98redux.exe"}
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = os.path.join(temp_dir, ".config", "heroic", "store_cache")
            os.makedirs(cache_dir)
            with open(os.path.join(cache_dir, "gog_library.json"), "w", encoding="utf-8") as handle:
                handle.write('{"1454067812": {"install_path": "/from/store/cache"}}')
            paths = get_linux_heroic_paths(game, env={"HOME": temp_dir}, home=temp_dir)
            self.assertNotIn(os.path.normpath("/from/store/cache"), paths)


if __name__ == "__main__":
    unittest.main()
