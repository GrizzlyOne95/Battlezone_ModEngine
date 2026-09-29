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


def _backup_unreadable_config(path: str) -> None:
    """Keep a copy of a config that failed to parse so the next save can't erase it."""
    try:
        os.replace(path, path + ".corrupt")
    except OSError:
        pass


def load_config(config_path: str, legacy_config_path: str, base_dir: str, path_keys=None) -> dict:
    """Load the user config, falling back to the legacy file beside the app.

    Relative paths are only produced by older versions; they are resolved
    against ``base_dir`` for compatibility.
    """
    path_keys = path_keys or DEFAULT_PATH_KEYS
    for candidate in [config_path, legacy_config_path]:
        if not os.path.exists(candidate):
            continue

        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("config root is not an object")
        except (OSError, ValueError):
            _backup_unreadable_config(candidate)
            continue

        for key in path_keys:
            value = data.get(key)
            if value and isinstance(value, str) and not os.path.isabs(value):
                data[key] = os.path.normpath(os.path.join(base_dir, value))
        return data
    return {}


def build_storage_config(config: dict, base_dir: str) -> dict:
    """Store paths as absolute paths.

    The config lives in the per-user config folder and is shared by every copy
    of the app, so paths relative to one app folder would break as soon as a
    new release is extracted somewhere else.
    """
    storage_config = config.copy()
    for key, value in storage_config.items():
        if "path" in key and isinstance(value, str) and value:
            if not os.path.isabs(value):
                value = os.path.join(base_dir, value)
            storage_config[key] = os.path.normpath(value)
    return storage_config


def save_config(config_path: str, config_dir: str, base_dir: str, config: dict) -> None:
    storage_config = build_storage_config(config, base_dir)
    os.makedirs(config_dir, exist_ok=True)
    temp_path = config_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(storage_config, handle, indent=4)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, config_path)
