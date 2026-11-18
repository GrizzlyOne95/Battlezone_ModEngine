# Battlezone Mod Engine

A cross-platform tool to download and manage Steam Workshop mods for Battlezone 98 Redux and Battlezone Combat Commander. It is mainly for copies that cannot subscribe to the Workshop themselves (GOG, Heroic), and it also lists and links Workshop items a Steam copy has already downloaded.

## Release Builds

Download the latest platform archive from the GitHub Releases page. Packaged application names are intentionally stable and versionless:

- Windows launcher: `BZModEngine.exe`
- Linux launcher: `BZModEngine`
- macOS launcher: `BZModEngine` (separate downloads for Apple Silicon and Intel Macs)

Release archives carry the version and platform, for example:

- `Battlezone_ModEngine-v1.0.12-windows.zip`
- `Battlezone_ModEngine-v1.0.12-linux.tar.gz`
- `Battlezone_ModEngine-v1.0.12-macos-arm64.tar.gz` (Apple Silicon: M1 and newer)
- `Battlezone_ModEngine-v1.0.12-macos-x86_64.tar.gz` (Intel Macs)

Official Windows builds use the shared **Battlezone Modding Tools** product identity:

```text
FileDescription: Battlezone Mod Engine
ProductName: Battlezone Modding Tools
CompanyName: GrizzlyOne95
OriginalFilename: BZModEngine.exe
```

`FileVersion` and `ProductVersion` are derived from the canonical repository version.

<img width="1727" height="1323" alt="image" src="https://github.com/user-attachments/assets/3aeebf39-91f9-4ae7-9fc9-6dcdfd7ac581" />

<img width="1727" height="1323" alt="image" src="https://github.com/user-attachments/assets/8eed08c4-f078-4f96-aa69-b0173857f1cd" />

<img width="1727" height="1323" alt="image" src="https://github.com/user-attachments/assets/e9e4b5a1-f72f-468a-882c-060898b340a9" />

## Features
*   **Steam Workshop Integration**: Downloads mods using SteamCMD. No credentials or login are needed. SteamCMD is downloaded automatically on first use (Windows, Linux and macOS).
*   **Multi-Game Support**: Supports both **Battlezone 98 Redux** and **Battlezone Combat Commander**.
*   **Mod Management**: Enable, disable, update, or delete mods via a GUI.
*   **Smart Linking**: Uses Windows Junctions or Linux symlinks to link mods to the game folder without duplicating files.
*   **Physical Copy Option**: A **Physical Copy** checkbox copies mods into the game folder instead of linking them. The app offers to turn it on when the game drive cannot hold junctions (exFAT/FAT32); you can turn it off again at any time.
*   **Auto-Detection**: Locates GOG, Heroic, and Steam installations automatically on both Windows and Linux.
*   **Cross-Platform**: Works on Windows, Linux, and macOS.

## Requirements
*   **Windows**: Windows 10/11
*   **Linux**: The release build runs on distributions with glibc 2.31 or newer (Ubuntu 20.04+, Debian 11+, Mint 20+, SteamOS 3). From source: Python 3.10+ with tkinter. SteamCMD needs 32-bit libraries (Debian/Ubuntu: `sudo apt install lib32gcc-s1`; Arch: `sudo pacman -S lib32-gcc-libs`).
*   **macOS**: A modern macOS release on Apple Silicon or Intel. The games themselves are Windows builds, so you run them through CrossOver, Whisky or Wine.
*   Battlezone 98 Redux or Battlezone Combat Commander (GOG, Heroic, or Steam version)

## Installation

### Linux
```bash
# Install dependencies
sudo pacman -S python python-pillow tk  # Arch/Manjaro
# OR
sudo apt install python3 python3-pil python3-tk  # Debian/Ubuntu

# Optional: Install tkinterdnd2 for drag-and-drop support
pip install tkinterdnd2

# Run the application
python bz_mod_engine.py
```

### Windows
*   **From Source**: Install dependencies (`pip install Pillow tkinterdnd2`) and run `bz_mod_engine.py`.
*   **Junctions require NTFS**. If your game is on exFAT or FAT32, the app will offer a Physical Copy fallback.

### macOS
```bash
python3 -m pip install -r requirements.txt
python3 bz_mod_engine.py
```

Official releases also provide a standalone `BZModEngine` executable for macOS.

## Publishing a Release
Bump the version in `VERSION`, add a `## v<VERSION>` section to `CHANGELOG.md`, and merge the change into `main` (any merge method). CI builds every platform (Windows, Linux, macOS Apple Silicon and Intel) and publishes `v<VERSION>` with its archives, attestations, that changelog section and generated release notes. A version that already has a tag is never re-released, so later pushes to `main` only build. To re-run a missed release, start the **Build and Release** workflow manually on `main`, or push a `v<VERSION>` tag.

## Release Integrity (Attestations)
Official releases include build attestations to maximize user trust. You can verify attestations on the GitHub Releases page for each version, or build from source using `bz_mod_engine.py` and the instructions above.

## Usage
1.  Run the application as a normal user on Windows, Linux and macOS. On Windows, admin rights are only needed when the game is installed in a protected folder such as `C:\Program Files`; the app shows a **Relaunch as Admin** banner in that case.
2.  **Downloader Tab**:
    *   Check that **Install Status** shows the game as detected. If it doesn't, click **DETECT** or **BROWSE** to pick the game folder. Tick **Advanced Mode** to see and change the Game Path, SteamCMD and Mod Cache folders.
    *   Paste a Steam Workshop URL or ID. You can also drag a link from your browser or the Steam client into the box.
    *   Click **INSTALL MOD**. The mod is downloaded and enabled in one step.
3.  **Manage Mods Tab**:
    *   Double-click a mod to enable or disable it, or right-click it (Control-click on macOS) for more options.
    *   **CHECK FOR UPDATES** compares your downloads with the Workshop; **UPDATE ALL** downloads the newer ones. Items marked *Updated by Steam* are Steam subscriptions, which Steam keeps up to date itself.
    *   A **BROKEN LINK** status means the mod's files are gone (for example after clearing the cache). Disable it, or use **FORCE UPDATE** to download it again.

## Troubleshooting
*   **Windows SmartScreen**: If Windows blocks the app, click **More info** → **Run anyway**. This occurs because the executable is not digitally signed.
*   **macOS "cannot be opened because the developer cannot be verified"**: The binary is not notarized. Right-click (or Control-click) `BZModEngine` in Finder and choose **Open**, then confirm. Alternatively run `xattr -d com.apple.quarantine BZModEngine` in Terminal from the folder you extracted it to.
*   **SteamCMD fails to start on Linux** (exit code 127): install the 32-bit libraries listed under Requirements.
*   **Flatpak or Snap Steam on Linux**: Sandboxed Steam may not be able to follow links to a Mod Cache outside its sandbox. If enabled mods don't show up in game, turn on **Physical Copy**.
*   **Linux**: Symlinks need no special permissions; the game folder just has to be writable by your user.
*   **Heroic Games Launcher**: Install games through Heroic, and the tool will auto-detect the installation path.
*   **External Drives (Windows)**: Junctions only work on NTFS. If your game is on exFAT, choose the Physical Copy fallback or move the game to an NTFS drive.
