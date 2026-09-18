import os
import shutil
import subprocess


def normalize_path(path: str) -> str:
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def paths_match(left: str, right: str) -> bool:
    return bool(left and right and normalize_path(left) == normalize_path(right))


def build_game_context(games: dict, game_key: str, raw_game_path: str | None) -> dict:
    game = games[game_key]
    return {
        "key": game_key,
        "name": game["name"],
        "appid": game["appid"],
        "exe": game["exe"],
        "game_path": os.path.abspath(raw_game_path) if raw_game_path else "",
    }


def build_content_dir(cache_path: str, appid: str) -> str:
    return os.path.join(cache_path, "steamapps", "workshop", "content", appid)


def build_mod_cache_path(cache_path: str, appid: str, mid: str) -> str:
    return os.path.join(build_content_dir(cache_path, appid), mid)


def collect_workshop_mod_sources(
    primary_content_dir: str,
    external_content_dirs=None,
) -> dict[str, dict[str, str]]:
    """Merge managed cache content with read-only external Workshop sources.

    The Mod Engine cache always wins when the same Workshop item exists in more
    than one source. External directories are never modified by this helper.
    """
    sources: dict[str, dict[str, str]] = {}

    def add_directory(content_dir: str | None, source: str) -> None:
        if not content_dir or not os.path.isdir(content_dir):
            return
        try:
            entries = sorted(os.listdir(content_dir))
        except OSError:
            return

        for entry in entries:
            item_path = os.path.join(content_dir, entry)
            if not os.path.isdir(item_path):
                continue
            if entry not in sources:
                sources[entry] = {
                    "path": os.path.normpath(item_path),
                    "source": source,
                }

    add_directory(primary_content_dir, "cache")

    for content_dir in external_content_dirs or []:
        if paths_match(primary_content_dir, content_dir):
            continue
        add_directory(content_dir, "steam")

    return sources


def get_cache_marker_path(cache_path: str, marker_filename: str) -> str:
    return os.path.join(cache_path, marker_filename)


def ensure_cache_root(cache_path: str, marker_filename: str, marker_contents: str) -> str:
    if not cache_path:
        raise ValueError("Please select a Mod Cache path.")

    abs_path = os.path.abspath(cache_path)
    os.makedirs(abs_path, exist_ok=True)

    marker_path = get_cache_marker_path(abs_path, marker_filename)
    if not os.path.exists(marker_path):
        with open(marker_path, "w", encoding="utf-8") as handle:
            handle.write(marker_contents)

    return abs_path


def is_safe_cache_root(cache_path: str, marker_filename: str) -> bool:
    if not cache_path:
        return False

    abs_path = os.path.abspath(cache_path)
    if not os.path.isdir(abs_path):
        return False

    parent = os.path.dirname(abs_path.rstrip("\\/"))
    if not parent or parent == abs_path:
        return False

    return os.path.isfile(get_cache_marker_path(abs_path, marker_filename))


def clear_directory_contents(directory: str, remove_path, preserve_names=None) -> None:
    preserve_names = set(preserve_names or [])
    for entry in os.listdir(directory):
        if entry in preserve_names:
            continue
        remove_path(os.path.join(directory, entry))


def create_directory_link(src: str, dst: str, is_windows: bool) -> None:
    if is_windows:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", dst, src],
            timeout=10,
            capture_output=True,
            text=True,
            check=True,
        )
    else:
        os.symlink(src, dst, target_is_directory=True)


def deploy_mod(src: str, dst: str, use_physical: bool, remove_path, create_link) -> bool:
    if not os.path.exists(src):
        return False

    os.makedirs(os.path.dirname(dst), exist_ok=True)

    if use_physical:
        if os.path.lexists(dst):
            remove_path(dst)
        shutil.copytree(src, dst)
        return True

    if not os.path.lexists(dst):
        create_link(src, dst)

    return os.path.lexists(dst)
