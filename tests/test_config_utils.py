import json
import os
import tempfile
import unittest

from config_utils import (
    build_storage_config,
    get_user_config_dir,
    load_config,
    make_rel_to_base,
    save_config,
)


class ConfigUtilsTests(unittest.TestCase):
    def test_get_user_config_dir_windows_prefers_appdata(self):
        result = get_user_config_dir(
            is_windows=True,
            is_linux=False,
            env={"APPDATA": r"C:\Users\Test\AppData\Roaming"},
            home=r"C:\Users\Test",
        )
        self.assertIn("BattlezoneModEngine", result)
        self.assertIn("AppData", result)

    def test_get_user_config_dir_linux_prefers_xdg(self):
        result = get_user_config_dir(
            is_windows=False,
            is_linux=True,
            env={"XDG_CONFIG_HOME": "/tmp/xdg"},
            home="/home/test",
        )
        normalized = result.replace("\\", "/")
        self.assertEqual(normalized, "/tmp/xdg/BattlezoneModEngine")

    def test_make_rel_to_base_same_drive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = temp_dir
            path = os.path.join(temp_dir, "mods")
            result = make_rel_to_base(path, base)
            self.assertEqual(result, "mods")

    def test_build_storage_config_relativizes_path_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "cache_path": os.path.join(temp_dir, "cache"),
                "steamcmd_path": os.path.join(temp_dir, "bin", "steamcmd.exe"),
                "advanced_mode": True,
            }
            storage = build_storage_config(config, temp_dir)
            self.assertEqual(storage["cache_path"], "cache")
            self.assertEqual(storage["steamcmd_path"], os.path.join("bin", "steamcmd.exe"))
            self.assertTrue(storage["advanced_mode"])

    def test_save_and_load_config_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, "cfg")
            config_path = os.path.join(config_dir, "bz_mod_config.json")
            legacy_path = os.path.join(temp_dir, "legacy.json")
            config = {
                "cache_path": os.path.join(temp_dir, "cache"),
                "path_BZ98R": os.path.join(temp_dir, "game"),
                "advanced_mode": False,
            }

            save_config(config_path, config_dir, temp_dir, config)
            loaded = load_config(config_path, legacy_path, temp_dir)
            self.assertEqual(loaded["cache_path"], os.path.join(temp_dir, "cache"))
            self.assertEqual(loaded["path_BZ98R"], os.path.join(temp_dir, "game"))
            self.assertFalse(loaded["advanced_mode"])

    def test_load_config_uses_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "missing.json")
            legacy_path = os.path.join(temp_dir, "bz_mod_config.json")
            with open(legacy_path, "w", encoding="utf-8") as handle:
                json.dump({"cache_path": "cache"}, handle)

            loaded = load_config(config_path, legacy_path, temp_dir)
            self.assertEqual(loaded["cache_path"], os.path.join(temp_dir, "cache"))


if __name__ == "__main__":
    unittest.main()
