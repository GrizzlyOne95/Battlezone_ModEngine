import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GameInstall:
    path: str
    source: str


def is_valid_game_path(game: dict, path: str | None) -> bool:
    if not path:
        return False
    exe_name = game.get("exe", "")
    if not exe_name:
        return False
    return os.path.isfile(os.path.join(os.path.normpath(path), exe_name))


def _unique_paths(paths) -> list[str]:
    result = []
    seen = set()
    for path in paths:
        if not path:
            continue
        normalized = os.path.normpath(os.path.expandvars(os.path.expanduser(str(path))))
        key = os.path.normcase(normalized)
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _decode_vdf_string(value: str) -> str:
    return value.replace("\\\\", "\\").replace('\\"', '"')


def extract_steam_library_paths(vdf_text: str) -> list[str]:
    """Extract Steam library roots from both modern and legacy libraryfolders.vdf."""
    paths = []

    # Modern Steam format:
    # "0" { "path" "C:\\Program Files (x86)\\Steam" ... }
    for match in re.finditer(r'"path"\s*"((?:\\.|[^"])*)"', vdf_text, flags=re.IGNORECASE):
        paths.append(_decode_vdf_string(match.group(1)))

    # Legacy format:
    # "1" "D:\\SteamLibrary"
    for match in re.finditer(r'"\d+"\s*"((?:\\.|[^"])*)"', vdf_text):
        candidate = _decode_vdf_string(match.group(1))
        if "\\" in candidate or "/" in candidate:
            paths.append(candidate)

    return _unique_paths(paths)


def parse_appmanifest_install_dir(acf_text: str) -> str | None:
    match = re.search(r'"installdir"\s*"((?:\\.|[^"])*)"', acf_text, flags=re.IGNORECASE)
    if not match:
        return None
    value = _decode_vdf_string(match.group(1)).strip()
    return value or None


def get_steam_library_paths(steam_root: str) -> list[str]:
    libraries = [steam_root]
    library_file = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(library_file, "r", encoding="utf-8", errors="replace") as handle:
            libraries.extend(extract_steam_library_paths(handle.read()))
    except OSError:
        pass
    return _unique_paths(libraries)


def _registry_view_flags(winreg_module) -> list[int]:
    flags = [0]
    for flag_name in ("KEY_WOW64_32KEY", "KEY_WOW64_64KEY"):
        flag = getattr(winreg_module, flag_name, 0)
        if flag and flag not in flags:
            flags.append(flag)
    return flags


def _read_registry_value(winreg_module, hive, key_path: str, value_names) -> str | None:
    if winreg_module is None or hive is None:
        return None

    key_read = getattr(winreg_module, "KEY_READ", 0)
    for view_flag in _registry_view_flags(winreg_module):
        key = None
        try:
            key = winreg_module.OpenKey(hive, key_path, 0, key_read | view_flag)
            for value_name in value_names:
                try:
                    value, _ = winreg_module.QueryValueEx(key, value_name)
                except OSError:
                    continue
                if value:
                    return str(value)
        except OSError:
            continue
        finally:
            if key is not None:
                close_key = getattr(winreg_module, "CloseKey", None)
                if close_key:
                    try:
                        close_key(key)
                    except OSError:
                        pass

    return None


def get_windows_steam_roots(winreg_module, env=None) -> list[str]:
    """Locate Steam roots using Valve registry keys, then standard install folders."""
    if winreg_module is None:
        return []

    if env is None:
        env = os.environ
    roots = []

    locations = [
        (getattr(winreg_module, "HKEY_CURRENT_USER", None), r"SOFTWARE\Valve\Steam", ("SteamPath", "InstallPath")),
        (getattr(winreg_module, "HKEY_LOCAL_MACHINE", None), r"SOFTWARE\Valve\Steam", ("InstallPath",)),
    ]

    for hive, key_path, value_names in locations:
        value = _read_registry_value(winreg_module, hive, key_path, value_names)
        if value:
            roots.append(value)

    # Compatibility fallback for registry implementations that expose the redirected
    # 32-bit key by its physical WOW6432Node path instead of a WOW64 view flag.
    wow_path = r"SOFTWARE\WOW6432Node\Valve\Steam"
    value = _read_registry_value(
        winreg_module,
        getattr(winreg_module, "HKEY_LOCAL_MACHINE", None),
        wow_path,
        ("InstallPath",),
    )
    if value:
        roots.append(value)

    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        base = env.get(env_name)
        if base:
            roots.append(os.path.join(base, "Steam"))

    return _unique_paths(roots)


def discover_steam_game(game: dict, steam_roots) -> GameInstall | None:
    appid = str(game.get("appid", "")).strip()
    if not appid:
        return None

    for steam_root in _unique_paths(steam_roots):
        for library_root in get_steam_library_paths(steam_root):
            steamapps = os.path.join(library_root, "steamapps")
            manifest_path = os.path.join(steamapps, f"appmanifest_{appid}.acf")
            try:
                with open(manifest_path, "r", encoding="utf-8", errors="replace") as handle:
                    install_dir = parse_appmanifest_install_dir(handle.read())
            except OSError:
                continue

            if not install_dir:
                continue

            candidate = os.path.normpath(os.path.join(steamapps, "common", install_dir))
            if is_valid_game_path(game, candidate):
                return GameInstall(path=candidate, source="steam")

    return None


def get_windows_gog_paths(game: dict, winreg_module) -> list[str]:
    """Return GOG install paths registered for a supported game."""
    if winreg_module is None:
        return []

    gog_ids = [str(value).strip() for value in game.get("gog_ids", []) if str(value).strip()]
    if not gog_ids:
        return []

    hives = [
        getattr(winreg_module, "HKEY_LOCAL_MACHINE", None),
        getattr(winreg_module, "HKEY_CURRENT_USER", None),
    ]
    paths = []

    for gog_id in gog_ids:
        logical_key = rf"SOFTWARE\GOG.com\Games\{gog_id}"
        for hive in hives:
            value = _read_registry_value(winreg_module, hive, logical_key, ("path", "Path"))
            if value:
                paths.append(value)

        # Compatibility fallback matching the layout used by older GOG installers.
        redirected_key = rf"SOFTWARE\WOW6432Node\GOG.com\Games\{gog_id}"
        value = _read_registry_value(
            winreg_module,
            getattr(winreg_module, "HKEY_LOCAL_MACHINE", None),
            redirected_key,
            ("path", "Path"),
        )
        if value:
            paths.append(value)

    return _unique_paths(paths)


def discover_windows_gog_game(game: dict, winreg_module) -> GameInstall | None:
    for candidate in get_windows_gog_paths(game, winreg_module):
        if is_valid_game_path(game, candidate):
            return GameInstall(path=os.path.normpath(candidate), source="gog")
    return None


def _normalized_identifier(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _game_identifiers(game: dict) -> set[str]:
    values = [
        game.get("name", ""),
        game.get("appid", ""),
        *game.get("gog_ids", []),
        *game.get("aliases", []),
        *game.get("heroic_ids", []),
        *game.get("uninstall_names", []),
    ]
    return {_normalized_identifier(value) for value in values if str(value).strip()}


def _matches_game_identifier(game: dict, *values) -> bool:
    identifiers = _game_identifiers(game)
    for value in values:
        normalized = _normalized_identifier(value)
        if not normalized:
            continue
        for identifier in identifiers:
            if identifier and (identifier in normalized or normalized in identifier):
                return True
    return False


def _query_open_key_value(winreg_module, key, value_names) -> str | None:
    for value_name in value_names:
        try:
            value, _ = winreg_module.QueryValueEx(key, value_name)
        except OSError:
            continue
        if value:
            return str(value)
    return None


def _display_icon_directory(display_icon: str | None) -> str | None:
    if not display_icon:
        return None

    value = str(display_icon).strip()
    if not value:
        return None

    if value.startswith('"'):
        match = re.match(r'^"([^"]+)"', value)
        executable = match.group(1) if match else value.strip('"')
    else:
        executable = value.split(",", 1)[0].strip()

    if not executable:
        return None
    return os.path.dirname(os.path.normpath(os.path.expandvars(executable))) or None


def get_windows_uninstall_paths(game: dict, winreg_module) -> list[str]:
    """Locate matching installs from Windows Add/Remove Programs registry entries."""
    if winreg_module is None or not hasattr(winreg_module, "EnumKey"):
        return []

    hives = [
        getattr(winreg_module, "HKEY_LOCAL_MACHINE", None),
        getattr(winreg_module, "HKEY_CURRENT_USER", None),
    ]
    base_keys = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    key_read = getattr(winreg_module, "KEY_READ", 0)
    paths = []

    for hive in hives:
        if hive is None:
            continue
        for base_key in base_keys:
            for view_flag in _registry_view_flags(winreg_module):
                root = None
                try:
                    root = winreg_module.OpenKey(hive, base_key, 0, key_read | view_flag)
                    index = 0
                    while True:
                        try:
                            subkey_name = winreg_module.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1

                        child = None
                        try:
                            child_path = base_key + "\\" + subkey_name
                            child = winreg_module.OpenKey(hive, child_path, 0, key_read | view_flag)
                            display_name = _query_open_key_value(winreg_module, child, ("DisplayName",))
                            if not _matches_game_identifier(game, display_name or "", subkey_name):
                                continue

                            install_location = _query_open_key_value(
                                winreg_module,
                                child,
                                ("InstallLocation", "InstallPath"),
                            )
                            if install_location:
                                paths.append(install_location)

                            display_icon = _query_open_key_value(winreg_module, child, ("DisplayIcon",))
                            icon_dir = _display_icon_directory(display_icon)
                            if icon_dir:
                                paths.append(icon_dir)
                        except OSError:
                            continue
                        finally:
                            if child is not None:
                                close_key = getattr(winreg_module, "CloseKey", None)
                                if close_key:
                                    try:
                                        close_key(child)
                                    except OSError:
                                        pass
                except OSError:
                    continue
                finally:
                    if root is not None:
                        close_key = getattr(winreg_module, "CloseKey", None)
                        if close_key:
                            try:
                                close_key(root)
                            except OSError:
                                pass

    return _unique_paths(paths)


def discover_windows_uninstall_game(game: dict, winreg_module) -> GameInstall | None:
    for candidate in get_windows_uninstall_paths(game, winreg_module):
        if is_valid_game_path(game, candidate):
            return GameInstall(path=os.path.normpath(candidate), source="uninstall")
    return None


def get_linux_steam_roots(env=None, home: str | None = None) -> list[str]:
    if env is None:
        env = os.environ
    resolved_home = home or env.get("HOME") or os.path.expanduser("~")
    xdg_data = env.get("XDG_DATA_HOME") or os.path.join(resolved_home, ".local", "share")

    candidates = [
        env.get("STEAM_DIR"),
        env.get("STEAM_HOME"),
        os.path.join(xdg_data, "Steam"),
        os.path.join(resolved_home, ".steam", "steam"),
        os.path.join(resolved_home, ".steam", "root"),
        os.path.join(
            resolved_home,
            ".var",
            "app",
            "com.valvesoftware.Steam",
            ".local",
            "share",
            "Steam",
        ),
        os.path.join(
            resolved_home,
            ".var",
            "app",
            "com.valvesoftware.Steam",
            "data",
            "Steam",
        ),
    ]
    return _unique_paths(candidates)


def _heroic_config_roots(home: str) -> list[str]:
    return _unique_paths(
        [
            os.path.join(home, ".config", "heroic"),
            os.path.join(
                home,
                ".var",
                "app",
                "com.heroicgameslauncher.hgl",
                "config",
                "heroic",
            ),
            os.path.join(home, "snap", "heroic", "common", ".config", "heroic"),
        ]
    )


def _collect_heroic_paths(node, identifiers: set[str], inherited_match=False) -> list[str]:
    paths = []

    if isinstance(node, dict):
        identity_keys = {
            "appname",
            "app_name",
            "appid",
            "app_id",
            "gameid",
            "game_id",
            "id",
            "name",
            "title",
            "apptitle",
            "app_title",
        }
        path_keys = {
            "installpath",
            "install_path",
            "installlocation",
            "install_location",
            "path",
        }

        local_match = inherited_match
        for key, value in node.items():
            normalized_key = _normalized_identifier(key)
            if normalized_key in identifiers:
                local_match = True
            if str(key).lower() in identity_keys and not isinstance(value, (dict, list)):
                normalized_value = _normalized_identifier(value)
                if normalized_value in identifiers:
                    local_match = True
                elif any(identifier and identifier in normalized_value for identifier in identifiers):
                    local_match = True

        if local_match:
            for key, value in node.items():
                if str(key).lower() in path_keys and isinstance(value, str) and value.strip():
                    paths.append(value)

        for key, value in node.items():
            child_match = local_match or (_normalized_identifier(key) in identifiers)
            paths.extend(_collect_heroic_paths(value, identifiers, child_match))

    elif isinstance(node, list):
        for value in node:
            paths.extend(_collect_heroic_paths(value, identifiers, inherited_match))

    return paths


def get_linux_heroic_paths(game: dict, env=None, home: str | None = None) -> list[str]:
    """Read Heroic metadata where possible, then add conventional install locations."""
    if env is None:
        env = os.environ
    resolved_home = home or env.get("HOME") or os.path.expanduser("~")
    identifiers = _game_identifiers(game)
    paths = []

    try:
        import json
    except ImportError:
        json = None

    if json is not None:
        files_seen = 0
        for config_root in _heroic_config_roots(resolved_home):
            if not os.path.isdir(config_root):
                continue
            for root, _, files in os.walk(config_root):
                for filename in files:
                    if files_seen >= 200:
                        break
                    if not filename.lower().endswith(".json"):
                        continue
                    files_seen += 1
                    json_path = os.path.join(root, filename)
                    try:
                        if os.path.getsize(json_path) > 10 * 1024 * 1024:
                            continue
                        with open(json_path, "r", encoding="utf-8", errors="replace") as handle:
                            data = json.load(handle)
                    except (OSError, ValueError):
                        continue
                    paths.extend(_collect_heroic_paths(data, identifiers))
                if files_seen >= 200:
                    break
            if files_seen >= 200:
                break

    game_name = game.get("name", "")
    folder_names = [game_name, *game.get("aliases", [])]
    roots = [
        os.path.join(resolved_home, "Games"),
        os.path.join(resolved_home, "Games", "Heroic"),
        os.path.join(resolved_home, "Games", "GOG"),
    ]
    for root in roots:
        for folder_name in folder_names:
            if folder_name:
                paths.append(os.path.join(root, folder_name))

    return _unique_paths(paths)


def discover_linux_heroic_game(game: dict, env=None, home: str | None = None) -> GameInstall | None:
    for candidate in get_linux_heroic_paths(game, env=env, home=home):
        if is_valid_game_path(game, candidate):
            return GameInstall(path=os.path.normpath(candidate), source="heroic")
    return None


def discover_linux_game(game: dict, env=None, home: str | None = None) -> GameInstall | None:
    steam_result = discover_steam_game(game, get_linux_steam_roots(env=env, home=home))
    if steam_result:
        return steam_result

    heroic_result = discover_linux_heroic_game(game, env=env, home=home)
    if heroic_result:
        return heroic_result

    return None


def discover_game_install(
    game: dict,
    configured_path: str | None = None,
    *,
    is_windows: bool = False,
    is_linux: bool = False,
    winreg_module=None,
    env=None,
    home: str | None = None,
) -> GameInstall | None:
    """Resolve a configured install first, then supported storefront discovery."""
    if is_valid_game_path(game, configured_path):
        return GameInstall(path=os.path.normpath(configured_path), source="configured")

    if is_windows:
        steam_roots = get_windows_steam_roots(winreg_module, env=env)
        result = discover_steam_game(game, steam_roots)
        if result:
            return result

        result = discover_windows_gog_game(game, winreg_module)
        if result:
            return result

        result = discover_windows_uninstall_game(game, winreg_module)
        if result:
            return result

    if is_linux:
        result = discover_linux_game(game, env=env, home=home)
        if result:
            return result

    return None
