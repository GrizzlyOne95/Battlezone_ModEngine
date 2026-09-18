import os
import tempfile
import unittest

from game_discovery import (
    discover_game_install,
    discover_steam_game,
    extract_steam_library_paths,
    get_windows_steam_roots,
    is_valid_game_path,
    parse_appmanifest_install_dir,
)


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 0x01
    KEY_WOW64_32KEY = 0x02
    KEY_WOW64_64KEY = 0x04

    def __init__(self, values):
        self.values = values

    def OpenKey(self, hive, path, reserved, access):
        key = (hive, path)
        if key not in self.values:
            raise OSError("missing key")
        return key

    def QueryValueEx(self, key, name):
        values = self.values.get(key, {})
        if name not in values:
            raise OSError("missing value")
        return values[name], 1

    def CloseKey(self, key):
        return None


class GameDiscoveryTests(unittest.TestCase):
    def test_valid_game_path_requires_expected_executable(self):
        game = {"exe": "battlezone98redux.exe"}
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertFalse(is_valid_game_path(game, temp_dir))
            open(os.path.join(temp_dir, game["exe"]), "wb").close()
            self.assertTrue(is_valid_game_path(game, temp_dir))

    def test_extracts_modern_and_legacy_steam_library_paths(self):
        text = r'''
        "libraryfolders"
        {
            "0"
            {
                "path" "C:\\Program Files (x86)\\Steam"
            }
            "1" "D:\\SteamLibrary"
        }
        '''
        paths = extract_steam_library_paths(text)
        self.assertIn(os.path.normpath(r"C:\Program Files (x86)\Steam"), paths)
        self.assertIn(os.path.normpath(r"D:\SteamLibrary"), paths)

    def test_parses_appmanifest_install_dir(self):
        text = '"AppState"\n{\n    "appid" "624970"\n    "installdir" "Battlezone Combat Commander"\n}'
        self.assertEqual(parse_appmanifest_install_dir(text), "Battlezone Combat Commander")

    def test_discovers_game_from_secondary_steam_library(self):
        game = {
            "name": "Battlezone Combat Commander",
            "appid": "624970",
            "exe": "battlezone2.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_root = os.path.join(temp_dir, "Steam")
            library_root = os.path.join(temp_dir, "Library")
            os.makedirs(os.path.join(steam_root, "steamapps"))
            os.makedirs(os.path.join(library_root, "steamapps", "common", "Battlezone Combat Commander"))

            with open(
                os.path.join(steam_root, "steamapps", "libraryfolders.vdf"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(f'"libraryfolders"\n{{\n"1"\n{{\n"path" "{library_root}"\n}}\n}}')

            with open(
                os.path.join(library_root, "steamapps", "appmanifest_624970.acf"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write('"AppState"\n{\n"appid" "624970"\n"installdir" "Battlezone Combat Commander"\n}')

            open(
                os.path.join(
                    library_root,
                    "steamapps",
                    "common",
                    "Battlezone Combat Commander",
                    "battlezone2.exe",
                ),
                "wb",
            ).close()

            result = discover_steam_game(game, [steam_root])
            self.assertIsNotNone(result)
            self.assertEqual(
                result.path,
                os.path.normpath(os.path.join(library_root, "steamapps", "common", "Battlezone Combat Commander")),
            )
            self.assertEqual(result.source, "steam")

    def test_windows_registry_root_drives_steam_discovery(self):
        game = {
            "name": "Battlezone 98 Redux",
            "appid": "301650",
            "exe": "battlezone98redux.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_root = os.path.join(temp_dir, "Steam")
            install_dir = os.path.join(steam_root, "steamapps", "common", "Battlezone 98 Redux")
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone98redux.exe"), "wb").close()
            with open(
                os.path.join(steam_root, "steamapps", "appmanifest_301650.acf"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write('"AppState"\n{\n"appid" "301650"\n"installdir" "Battlezone 98 Redux"\n}')

            fake_registry = FakeWinreg({
                ("HKCU", r"SOFTWARE\Valve\Steam"): {"SteamPath": steam_root},
            })
            result = discover_game_install(
                game,
                configured_path=os.path.join(temp_dir, "missing"),
                is_windows=True,
                winreg_module=fake_registry,
                env={"ProgramFiles": os.path.join(temp_dir, "PF")},
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "steam")
            self.assertEqual(result.path, os.path.normpath(install_dir))

    def test_configured_valid_path_wins(self):
        game = {"appid": "301650", "exe": "battlezone98redux.exe"}
        with tempfile.TemporaryDirectory() as temp_dir:
            open(os.path.join(temp_dir, "battlezone98redux.exe"), "wb").close()
            result = discover_game_install(game, configured_path=temp_dir)
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "configured")
            self.assertEqual(result.path, os.path.normpath(temp_dir))

    def test_windows_registry_roots_accepts_standard_valve_key(self):
        fake_registry = FakeWinreg({
            ("HKCU", r"SOFTWARE\Valve\Steam"): {"SteamPath": r"C:\Steam"},
        })
        roots = get_windows_steam_roots(fake_registry, env={"ProgramFiles": r"C:\Program Files"})
        self.assertIn(os.path.normpath(r"C:\Steam"), roots)


if __name__ == "__main__":
    unittest.main()
