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


def discover_game_install(
    game: dict,
    configured_path: str | None = None,
    *,
    is_windows: bool = False,
    winreg_module=None,
    env=None,
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

    return None
