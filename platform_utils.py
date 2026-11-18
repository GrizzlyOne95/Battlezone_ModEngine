import os
import signal
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

    # macOS: Valve's tarball, or the Homebrew cask wrapper.
    return [
        get_default_steamcmd_path(bin_dir, False),
        os.path.join(resolved_home, "steamcmd", "steamcmd.sh"),
        os.path.join(resolved_home, "Library", "Application Support", "SteamCMD", "steamcmd.sh"),
        "/opt/homebrew/bin/steamcmd",
        "/usr/local/bin/steamcmd",
    ]


def get_subprocess_env(is_linux: bool, frozen: bool, env=None) -> dict | None:
    """Environment for external programs started from a packaged build.

    PyInstaller's Linux bootloader points LD_LIBRARY_PATH at the libraries
    bundled inside the app. Browsers, file managers, Steam and SteamCMD must
    not inherit that, or they can fail to start. The original value is kept
    in LD_LIBRARY_PATH_ORIG. Returns None when no change is needed.
    """
    if not (is_linux and frozen):
        return None
    env = dict(os.environ if env is None else env)
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def get_popen_output_kwargs(is_windows: bool, subprocess_module=subprocess) -> dict:
    kwargs = {
        "stdout": subprocess_module.PIPE,
        "stderr": subprocess_module.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if is_windows and hasattr(subprocess_module, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess_module.CREATE_NO_WINDOW
    if not is_windows:
        # steamcmd.sh launches the real SteamCMD binary as a child process. A new
        # session lets Stop signal the whole group instead of only the wrapper.
        kwargs["start_new_session"] = True
    return kwargs


def terminate_process_tree(process, is_windows: bool, os_module=os, subprocess_module=subprocess) -> None:
    """Stop a process and any children it started (e.g. steamcmd.sh -> steamcmd)."""
    if process.poll() is not None:
        return
    try:
        if is_windows:
            subprocess_module.run(
                ["taskkill", "/F", "/T", "/PID", str(int(process.pid))],
                stdout=subprocess_module.DEVNULL,
                stderr=subprocess_module.DEVNULL,
                creationflags=getattr(subprocess_module, "CREATE_NO_WINDOW", 0),
                timeout=10,
            )
        else:
            os_module.killpg(os_module.getpgid(process.pid), signal.SIGTERM)
    except (OSError, subprocess_module.SubprocessError):
        pass
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass


def open_path(
    target: str,
    is_windows: bool,
    is_linux: bool,
    os_module=os,
    subprocess_module=subprocess,
    env=None,
) -> None:
    """Open a folder, file or URL (https://, steam://) with the system handler."""
    if is_windows:
        os_module.startfile(target)
        return

    opener = "xdg-open" if is_linux else "open"
    subprocess_module.Popen(
        [opener, target],
        stdout=subprocess_module.DEVNULL,
        stderr=subprocess_module.DEVNULL,
        env=env,
    )
