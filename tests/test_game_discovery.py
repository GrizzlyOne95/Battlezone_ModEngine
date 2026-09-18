import os
import tempfile
import unittest

from game_discovery import (
    discover_game_install,
    discover_linux_game,
    discover_linux_heroic_game,
    discover_steam_game,
    discover_windows_gog_game,
    discover_windows_uninstall_game,
    extract_steam_library_paths,
    get_linux_heroic_paths,
    get_linux_steam_roots,
    get_windows_gog_paths,
    get_windows_steam_roots,
    get_windows_uninstall_paths,
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

    def EnumKey(self, key, index):
        hive, path = key
        prefix = path + "\\"
        children = []
        for candidate_hive, candidate_path in self.values:
            if candidate_hive != hive or not candidate_path.startswith(prefix):
                continue
            remainder = candidate_path[len(prefix):]
            if "\\" not in remainder and remainder not in children:
                children.append(remainder)
        children.sort()
        if index >= len(children):
            raise OSError("no more keys")
        return children[index]

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

    def test_windows_gog_registry_paths_support_game_ids(self):
        game = {
            "gog_ids": ["1454067812", "1459427445"],
            "exe": "battlezone98redux.exe",
        }
        fake_registry = FakeWinreg({
            ("HKLM", r"SOFTWARE\GOG.com\Games\1459427445"): {"path": r"D:\GOG\Battlezone 98 Redux"},
        })
        paths = get_windows_gog_paths(game, fake_registry)
        self.assertIn(os.path.normpath(r"D:\GOG\Battlezone 98 Redux"), paths)

    def test_windows_gog_legacy_wow6432node_path_is_supported(self):
        game = {
            "gog_ids": ["1193046833"],
            "exe": "battlezone2.exe",
        }
        fake_registry = FakeWinreg({
            ("HKLM", r"SOFTWARE\WOW6432Node\GOG.com\Games\1193046833"): {
                "path": r"E:\GOG\Battlezone Combat Commander"
            },
        })
        paths = get_windows_gog_paths(game, fake_registry)
        self.assertIn(os.path.normpath(r"E:\GOG\Battlezone Combat Commander"), paths)

    def test_discovers_valid_gog_install_and_reports_source(self):
        game = {
            "name": "Battlezone 98 Redux",
            "appid": "301650",
            "gog_ids": ["1454067812"],
            "exe": "battlezone98redux.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "GOG", "Battlezone 98 Redux")
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone98redux.exe"), "wb").close()

            fake_registry = FakeWinreg({
                ("HKLM", r"SOFTWARE\GOG.com\Games\1454067812"): {"path": install_dir},
            })
            result = discover_windows_gog_game(game, fake_registry)
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "gog")
            self.assertEqual(result.path, os.path.normpath(install_dir))

    def test_invalid_gog_registry_path_is_ignored(self):
        game = {
            "gog_ids": ["1454067812"],
            "exe": "battlezone98redux.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_registry = FakeWinreg({
                ("HKLM", r"SOFTWARE\GOG.com\Games\1454067812"): {"path": temp_dir},
            })
            self.assertIsNone(discover_windows_gog_game(game, fake_registry))

    def test_unified_windows_discovery_falls_back_to_gog_after_steam(self):
        game = {
            "name": "Battlezone Combat Commander",
            "appid": "624970",
            "gog_ids": ["1193046833"],
            "exe": "battlezone2.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "GOG", "Battlezone Combat Commander")
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone2.exe"), "wb").close()

            fake_registry = FakeWinreg({
                ("HKLM", r"SOFTWARE\GOG.com\Games\1193046833"): {"path": install_dir},
            })
            result = discover_game_install(
                game,
                configured_path=os.path.join(temp_dir, "missing"),
                is_windows=True,
                winreg_module=fake_registry,
                env={},
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "gog")
            self.assertEqual(result.path, os.path.normpath(install_dir))


    def test_windows_uninstall_registry_fallback(self):
        game = {
            "name": "Battlezone Combat Commander",
            "appid": "624970",
            "gog_ids": ["1193046833"],
            "exe": "battlezone2.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "Battlezone Combat Commander")
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone2.exe"), "wb").close()

            base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            entry = base + r"\Battlezone Combat Commander"
            fake_registry = FakeWinreg({
                ("HKLM", base): {},
                ("HKLM", entry): {
                    "DisplayName": "Battlezone Combat Commander",
                    "InstallLocation": install_dir,
                },
            })

            paths = get_windows_uninstall_paths(game, fake_registry)
            self.assertIn(os.path.normpath(install_dir), paths)

            result = discover_windows_uninstall_game(game, fake_registry)
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "uninstall")
            self.assertEqual(result.path, os.path.normpath(install_dir))

    def test_windows_uninstall_uses_display_icon_directory(self):
        game = {
            "name": "Battlezone 98 Redux",
            "appid": "301650",
            "exe": "battlezone98redux.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "Battlezone 98 Redux")
            os.makedirs(install_dir)
            exe_path = os.path.join(install_dir, "battlezone98redux.exe")
            open(exe_path, "wb").close()

            base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            entry = base + r"\BZ98R"
            fake_registry = FakeWinreg({
                ("HKLM", base): {},
                ("HKLM", entry): {
                    "DisplayName": "Battlezone 98 Redux",
                    "DisplayIcon": f'"{exe_path}",0',
                },
            })

            result = discover_windows_uninstall_game(game, fake_registry)
            self.assertIsNotNone(result)
            self.assertEqual(result.path, os.path.normpath(install_dir))

    def test_unified_windows_discovery_reaches_uninstall_registry(self):
        game = {
            "name": "Battlezone Combat Commander",
            "appid": "624970",
            "gog_ids": ["1193046833"],
            "exe": "battlezone2.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "BZCC")
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone2.exe"), "wb").close()

            base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            entry = base + r"\BZCC"
            fake_registry = FakeWinreg({
                ("HKLM", base): {},
                ("HKLM", entry): {
                    "DisplayName": "Battlezone Combat Commander",
                    "InstallLocation": install_dir,
                },
            })

            result = discover_game_install(
                game,
                configured_path=os.path.join(temp_dir, "missing"),
                is_windows=True,
                winreg_module=fake_registry,
                env={},
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "uninstall")

    def test_linux_steam_roots_include_standard_and_flatpak_locations(self):
        roots = get_linux_steam_roots(
            env={"HOME": "/home/test", "XDG_DATA_HOME": "/home/test/.local/share"},
            home="/home/test",
        )
        self.assertIn(os.path.normpath("/home/test/.local/share/Steam"), roots)
        self.assertIn(
            os.path.normpath("/home/test/.var/app/com.valvesoftware.Steam/.local/share/Steam"),
            roots,
        )

    def test_unified_linux_discovery_finds_steam_install(self):
        game = {
            "name": "Battlezone 98 Redux",
            "appid": "301650",
            "exe": "battlezone98redux.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_root = os.path.join(temp_dir, ".local", "share", "Steam")
            install_dir = os.path.join(
                steam_root,
                "steamapps",
                "common",
                "Battlezone 98 Redux",
            )
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone98redux.exe"), "wb").close()
            with open(
                os.path.join(steam_root, "steamapps", "appmanifest_301650.acf"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    '"AppState"\n{\n"appid" "301650"\n'
                    '"installdir" "Battlezone 98 Redux"\n}'
                )

            result = discover_game_install(
                game,
                is_linux=True,
                env={"HOME": temp_dir, "XDG_DATA_HOME": os.path.join(temp_dir, ".local", "share")},
                home=temp_dir,
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "steam")
            self.assertEqual(result.path, os.path.normpath(install_dir))

    def test_linux_heroic_metadata_discovers_install(self):
        game = {
            "name": "Battlezone 98 Redux",
            "appid": "301650",
            "gog_ids": ["1454067812"],
            "exe": "battlezone98redux.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "Games", "Custom BZ98R")
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone98redux.exe"), "wb").close()

            config_dir = os.path.join(
                temp_dir,
                ".config",
                "heroic",
                "legendaryConfig",
                "legendary",
            )
            os.makedirs(config_dir)
            with open(
                os.path.join(config_dir, "installed.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    '{"1454067812": {"title": "Battlezone 98 Redux", '
                    f'"install_path": {install_dir!r}}}'
                )

            paths = get_linux_heroic_paths(
                game,
                env={"HOME": temp_dir},
                home=temp_dir,
            )
            self.assertIn(os.path.normpath(install_dir), paths)

            result = discover_linux_heroic_game(
                game,
                env={"HOME": temp_dir},
                home=temp_dir,
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "heroic")
            self.assertEqual(result.path, os.path.normpath(install_dir))

    def test_unified_linux_discovery_falls_back_to_heroic(self):
        game = {
            "name": "Battlezone Combat Commander",
            "appid": "624970",
            "gog_ids": ["1193046833"],
            "exe": "battlezone2.exe",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "Games", "Heroic", "Battlezone Combat Commander")
            os.makedirs(install_dir)
            open(os.path.join(install_dir, "battlezone2.exe"), "wb").close()

            result = discover_linux_game(
                game,
                env={"HOME": temp_dir},
                home=temp_dir,
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.source, "heroic")
            self.assertEqual(result.path, os.path.normpath(install_dir))



if __name__ == "__main__":
    unittest.main()
