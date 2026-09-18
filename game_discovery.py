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


def get_windows_steam_roots(winreg_module, env=None) -> list[str]:
    """Locate Steam roots using Valve registry keys, then standard install folders."""
    if winreg_module is None:
        return []

    if env is None:
        env = os.environ
    roots = []

    locations = [
        (getattr(winreg_module, "HKEY_CURRENT_USER", None), r"SOFTWARE\Valve\Steam", ("SteamPath", "InstallPath")),
        (getattr(winreg_module, "HKEY_LOCAL_MACHINE", None), r"SOFTWARE\WOW6432Node\Valve\Steam", ("InstallPath",)),
        (getattr(winreg_module, "HKEY_LOCAL_MACHINE", None), r"SOFTWARE\Valve\Steam", ("InstallPath",)),
    ]

    wow_flags = [0]
    for flag_name in ("KEY_WOW64_32KEY", "KEY_WOW64_64KEY"):
        flag = getattr(winreg_module, flag_name, 0)
        if flag and flag not in wow_flags:
            wow_flags.append(flag)

    key_read = getattr(winreg_module, "KEY_READ", 0)
    for hive, key_path, value_names in locations:
        if hive is None:
            continue
        for wow_flag in wow_flags:
            key = None
            found_in_key = False
            try:
                key = winreg_module.OpenKey(hive, key_path, 0, key_read | wow_flag)
                for value_name in value_names:
                    try:
                        value, _ = winreg_module.QueryValueEx(key, value_name)
                        if value:
                            roots.append(value)
                            found_in_key = True
                            break
                    except OSError:
                        continue
                if found_in_key:
                    # Do not keep opening the same logical key through alternate WOW views.
                    break
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


def discover_game_install(
    game: dict,
    configured_path: str | None = None,
    *,
    is_windows: bool = False,
    winreg_module=None,
    env=None,
) -> GameInstall | None:
    """Resolve a configured install first, then Windows Steam libraries."""
    if is_valid_game_path(game, configured_path):
        return GameInstall(path=os.path.normpath(configured_path), source="configured")

    if is_windows:
        steam_roots = get_windows_steam_roots(winreg_module, env=env)
        result = discover_steam_game(game, steam_roots)
        if result:
            return result

    return None
