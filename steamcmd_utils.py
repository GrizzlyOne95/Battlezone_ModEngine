import os
import re


PROGRESS_RE = re.compile(r"progress:\s*(\d+\.\d+)")


def ensure_console_language_file(steamcmd_path: str, language: str = "english") -> str:
    steamcmd_dir = os.path.dirname(steamcmd_path)
    console_cfg = os.path.join(steamcmd_dir, "SteamConsole.txt")
    if not os.path.exists(console_cfg):
        with open(console_cfg, "w", encoding="utf-8") as handle:
            handle.write(f'@Language "{language}"\n')
    return console_cfg


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
        return {"kind": "success", "message": clean, "item": clean.split("item")[-1].strip()}
    if "Error" in clean or "Failed" in clean:
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
