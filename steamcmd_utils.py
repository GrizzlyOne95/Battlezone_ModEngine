import os
import re


PROGRESS_RE = re.compile(r"progress:\s*(\d+\.\d+)")
SUCCESS_ITEM_RE = re.compile(r"Downloaded item\s+(\d+)", re.IGNORECASE)
ERROR_RE = re.compile(r"\b(error|failed|failure|timeout)\b", re.IGNORECASE)
# Harmless start-up noise SteamCMD prints on most systems.
BENIGN_FAILURE_RE = re.compile(r"ILocalize::|\bSDL\b", re.IGNORECASE)


def ensure_console_language_file(steamcmd_path: str, language: str = "english") -> str | None:
    """Best-effort: pin SteamCMD's console language so its output can be parsed.

    Returns the file path, or None when the SteamCMD folder is not writable
    (for example a distro package in /usr/games). That is not fatal.
    """
    steamcmd_dir = os.path.dirname(steamcmd_path)
    console_cfg = os.path.join(steamcmd_dir, "SteamConsole.txt")
    if not os.path.exists(console_cfg):
        try:
            with open(console_cfg, "w", encoding="utf-8") as handle:
                handle.write(f'@Language "{language}"\n')
        except OSError:
            return None
    return console_cfg


def safe_extract_zip(zip_file, target_dir: str) -> None:
    """Extract a zip archive, refusing members that would escape ``target_dir``."""
    root = os.path.realpath(target_dir)
    for member in zip_file.namelist():
        destination = os.path.realpath(os.path.join(root, member))
        if os.path.commonpath([root, destination]) != root:
            raise ValueError(f"Unsafe path in archive: {member}")
    zip_file.extractall(root)


def build_workshop_download_command(steamcmd_path: str, cache_path: str, appid: str, mod_ids: list[str]) -> list[str]:
    cmd = [steamcmd_path, "+force_install_dir", cache_path, "+login", "anonymous"]
    for mid in mod_ids:
        cmd.extend(["+workshop_download_item", appid, mid])
    cmd.append("+quit")
    return cmd


def classify_workshop_items(cache_path: str, appid: str, mod_ids: list[str], build_mod_cache_path) -> list[tuple[str, bool]]:
    return [(mid, os.path.exists(build_mod_cache_path(cache_path, appid, mid))) for mid in mod_ids]


def parse_steamcmd_output_line(line: str) -> dict:
    clean = line.strip()
    if not clean:
        return {"kind": "empty", "message": ""}

    progress_match = PROGRESS_RE.search(clean)
    if "Success. Downloaded item" in clean:
        item_match = SUCCESS_ITEM_RE.search(clean)
        item = item_match.group(1) if item_match else clean.split("item", 1)[-1].strip()
        return {"kind": "success", "message": clean, "item": item}
    # SteamCMD reports failures as e.g. "ERROR! Download item 123 failed (Failure)."
    # or "ERROR! Timeout downloading item 123", so match case-insensitively.
    if ERROR_RE.search(clean) and not BENIGN_FAILURE_RE.search(clean):
        return {"kind": "error", "message": clean}
    if progress_match:
        return {"kind": "progress", "message": clean, "value": float(progress_match.group(1))}
    if "Verifying" in clean:
        return {"kind": "verifying", "message": clean}
    if "Update state" in clean:
        return {"kind": "ignore", "message": clean}
    if "Downloading" in clean or "Extracting" in clean:
        return {"kind": "noisy", "message": clean}
    return {"kind": "info", "message": clean}


def should_log_noisy_line(current_time: float, last_log_time: float, min_interval_seconds: float = 1.0) -> bool:
    return (current_time - last_log_time) > min_interval_seconds


def summarize_download_batch(mod_ids: list[str], succeeded, exists_locally) -> dict:
    """Classify each requested item after a SteamCMD run.

    ``succeeded`` holds item IDs SteamCMD reported as downloaded;
    ``exists_locally(mid)`` says whether the item folder is on disk.
    """
    succeeded = set(succeeded)
    downloaded, stale, missing = [], [], []
    for mid in mod_ids:
        if mid in succeeded and exists_locally(mid):
            downloaded.append(mid)
        elif exists_locally(mid):
            # An older copy is still usable, but this update did not land.
            stale.append(mid)
        else:
            missing.append(mid)

    if not stale and not missing:
        status = "DEPLOYED"
    elif downloaded or stale:
        status = "PARTIAL"
    else:
        status = "FAILED"
    return {"downloaded": downloaded, "stale": stale, "missing": missing, "status": status}
