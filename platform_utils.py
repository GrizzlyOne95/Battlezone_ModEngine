import os
import subprocess


def get_steamcmd_name(is_windows: bool) -> str:
    return "steamcmd.exe" if is_windows else "steamcmd.sh"


def get_default_steamcmd_path(bin_dir: str, is_windows: bool) -> str:
    return os.path.join(bin_dir, get_steamcmd_name(is_windows))


def get_steamcmd_candidates(bin_dir: str, is_windows: bool, is_linux: bool, cwd: str | None = None, env=None, home: str | None = None) -> list[str]:
    env = env or os.environ
    cwd = cwd or os.getcwd()

    if is_windows:
        return [
            get_default_steamcmd_path(bin_dir, True),
            r"C:\steamcmd\steamcmd.exe",
            os.path.expandvars(r"%ProgramFiles(x86)%\SteamCMD\steamcmd.exe"),
            os.path.expandvars(r"%ProgramFiles%\SteamCMD\steamcmd.exe"),
            os.path.join(cwd, "steamcmd.exe"),
        ]

    resolved_home = home or env.get("HOME") or os.path.expanduser("~")
    if is_linux:
        return [
            get_default_steamcmd_path(bin_dir, False),
            os.path.join(resolved_home, "steamcmd", "steamcmd.sh"),
            os.path.join(resolved_home, ".steam", "steamcmd", "steamcmd.sh"),
            "/usr/games/steamcmd",
            "/usr/bin/steamcmd",
        ]

    return [get_default_steamcmd_path(bin_dir, False)]


def get_popen_output_kwargs(is_windows: bool, subprocess_module=subprocess) -> dict:
    kwargs = {
        "stdout": subprocess_module.PIPE,
        "stderr": subprocess_module.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if is_windows and hasattr(subprocess_module, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess_module.CREATE_NO_WINDOW
    return kwargs


def open_path(target: str, is_windows: bool, is_linux: bool, os_module=os, subprocess_module=subprocess) -> None:
    if is_windows:
        os_module.startfile(target)
        return

    opener = "xdg-open" if is_linux else "open"
    subprocess_module.Popen(
        [opener, target],
        stdout=subprocess_module.DEVNULL,
        stderr=subprocess_module.DEVNULL,
    )
