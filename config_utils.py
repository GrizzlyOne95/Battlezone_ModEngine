import json
import os
from pathlib import Path


DEFAULT_PATH_KEYS = ["game_path", "steamcmd_path", "cache_path", "path_BZ98R", "path_BZCC"]


def get_user_config_dir(is_windows: bool, is_linux: bool, env=None, home: str | None = None) -> str:
    env = env or os.environ
    home_path = home or str(Path.home())
    if is_windows:
        base = env.get("APPDATA") or os.path.join(home_path, "AppData", "Roaming")
    elif is_linux:
        base = env.get("XDG_CONFIG_HOME") or os.path.join(home_path, ".config")
    else:
        base = os.path.join(home_path, ".config")
    return os.path.join(base, "BattlezoneModEngine")


def load_config(config_path: str, legacy_config_path: str, base_dir: str, path_keys=None) -> dict:
    path_keys = path_keys or DEFAULT_PATH_KEYS
    for candidate in [config_path, legacy_config_path]:
        if not os.path.exists(candidate):
            continue

        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            for key in path_keys:
                if key in data and data[key] and not os.path.isabs(data[key]):
                    data[key] = os.path.normpath(os.path.join(base_dir, data[key]))
            return data
        except Exception:
            return {}
    return {}


def make_rel_to_base(path: str, base_dir: str) -> str:
    if not path:
        return ""
    try:
        if os.path.splitdrive(path)[0].lower() == os.path.splitdrive(base_dir)[0].lower():
            return os.path.relpath(path, base_dir)
    except Exception:
        pass
    return path


def build_storage_config(config: dict, base_dir: str) -> dict:
    storage_config = config.copy()
    for key, value in storage_config.items():
        if "path" in key and isinstance(value, str):
            storage_config[key] = make_rel_to_base(value, base_dir)
    return storage_config


def save_config(config_path: str, config_dir: str, base_dir: str, config: dict) -> None:
    storage_config = build_storage_config(config, base_dir)
    os.makedirs(config_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(storage_config, handle, indent=4)
