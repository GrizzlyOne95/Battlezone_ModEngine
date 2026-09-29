import os
import shutil


def normalize_path(path: str) -> str:
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def paths_match(left: str, right: str) -> bool:
    return bool(left and right and normalize_path(left) == normalize_path(right))


def is_same_or_nested_path(parent: str, child: str) -> bool:
    """Return True when ``child`` is ``parent`` or lives somewhere beneath it."""
    if not parent or not child:
        return False
    norm_parent = normalize_path(parent)
    norm_child = normalize_path(child)
    try:
        return os.path.commonpath([norm_parent, norm_child]) == norm_parent
    except ValueError:
        # Different drives on Windows.
        return False


def paths_overlap(left: str, right: str) -> bool:
    """Return True when either path is the same as, or contains, the other."""
    return is_same_or_nested_path(left, right) or is_same_or_nested_path(right, left)


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


# Entries SteamCMD itself creates inside a ``+force_install_dir`` folder. A
# folder holding nothing else is safe to adopt as a Mod Engine cache.
STEAMCMD_CACHE_ENTRIES = frozenset({"steamapps"})


def list_unexpected_cache_entries(abs_path: str, marker_filename: str) -> list[str] | None:
    """Entries in a cache folder that SteamCMD/the Mod Engine did not create.

    Returns None when the folder cannot be listed.
    """
    try:
        entries = set(os.listdir(abs_path))
    except OSError:
        return None
    entries.discard(marker_filename)
    return sorted(entries - STEAMCMD_CACHE_ENTRIES)


def can_adopt_cache_dir(abs_path: str, marker_filename: str) -> bool:
    """A folder may be marked as a cache only if it is empty or SteamCMD-only."""
    return list_unexpected_cache_entries(abs_path, marker_filename) == []


def ensure_cache_root(cache_path: str, marker_filename: str, marker_contents: str) -> str:
    """Create the cache folder and mark it as app-owned when that is provably safe.

    The marker is what authorises destructive operations (Clear Cache, purge),
    so it is never written into a folder that already holds unrelated files.
    Such a folder can still be used for downloads; it just cannot be cleared.
    """
    if not cache_path:
        raise ValueError("Please select a Mod Cache path.")

    abs_path = os.path.abspath(cache_path)
    os.makedirs(abs_path, exist_ok=True)

    marker_path = get_cache_marker_path(abs_path, marker_filename)
    if not os.path.exists(marker_path) and can_adopt_cache_dir(abs_path, marker_filename):
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


def create_directory_link(src: str, dst: str, is_windows: bool, winapi_module=None) -> None:
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)
    if is_windows:
        # Create the junction directly instead of going through ``cmd /c mklink``,
        # which re-parses the command line and treats characters such as ``&``
        # in a path as command separators.
        if winapi_module is None:
            import _winapi as winapi_module
        winapi_module.CreateJunction(src, dst)
    else:
        os.symlink(src, dst, target_is_directory=True)


def is_link_or_junction(path: str, is_windows: bool, get_file_attributes=None) -> bool:
    """Detect a symlink, or on Windows any reparse point such as a junction."""
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None and isjunction(path):
        return True
    if is_windows and get_file_attributes is not None and os.path.lexists(path):
        # GetFileAttributesW does not follow reparse points, so this also detects
        # dangling junctions. ctypes returns a signed int by default, so
        # INVALID_FILE_ATTRIBUTES arrives as -1; normalise before comparing.
        attributes = get_file_attributes(path) & 0xFFFFFFFF
        invalid_attributes = 0xFFFFFFFF
        return attributes != invalid_attributes and bool(attributes & 0x400)
    return False


def remove_path(path: str, is_link) -> None:
    """Remove a link, junction, file, or directory tree. Errors propagate.

    Links and junctions are removed without touching the folder they point to.
    """
    if not os.path.lexists(path):
        return
    if is_link(path):
        try:
            os.unlink(path)
        except (IsADirectoryError, PermissionError):
            # Windows junctions and directory symlinks are removed with rmdir.
            os.rmdir(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def deploy_mod(src: str, dst: str, use_physical: bool, remove_path, create_link, is_link=None) -> bool:
    if not os.path.exists(src):
        return False

    is_link = is_link or os.path.islink
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    if use_physical:
        if os.path.lexists(dst):
            remove_path(dst)
        shutil.copytree(src, dst)
        return True

    if os.path.lexists(dst):
        dangling_link = is_link(dst) and not os.path.exists(dst)
        physical_copy = not is_link(dst)
        # A stale physical copy (from Physical Copy mode) or a broken link would
        # otherwise keep the game on old content while reporting success.
        if dangling_link or physical_copy:
            remove_path(dst)

    if not os.path.lexists(dst):
        create_link(src, dst)

    return os.path.lexists(dst)


def get_latest_mtime(path: str) -> float:
    """Newest modification time of a folder or anything inside it.

    A directory's own mtime does not change when files inside it are replaced,
    so it cannot be used alone to tell when a Workshop item was last updated.
    """
    latest = os.path.getmtime(path)
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                latest = max(latest, os.lstat(os.path.join(root, name)).st_mtime)
            except OSError:
                continue
    return latest
