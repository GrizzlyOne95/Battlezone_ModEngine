# Battlezone Mod Engine

A cross-platform tool to download and manage Steam Workshop mods for non-Steam versions of Battlezone 98 Redux or Battlezone Combat Commander.

<img width="1727" height="1323" alt="image" src="https://github.com/user-attachments/assets/3aeebf39-91f9-4ae7-9fc9-6dcdfd7ac581" />

<img width="1727" height="1323" alt="image" src="https://github.com/user-attachments/assets/8eed08c4-f078-4f96-aa69-b0173857f1cd" />


<img width="1727" height="1323" alt="image" src="https://github.com/user-attachments/assets/e9e4b5a1-f72f-468a-882c-060898b340a9" />


## Features
*   **Steam Workshop Integration**: Downloads mods using SteamCMD. No credentials or login are needed.
*   **Multi-Game Support**: Supports both **Battlezone 98 Redux** and **Battlezone Combat Commander**.
*   **Mod Management**: Enable, disable, update, or delete mods via a GUI.
*   **Smart Linking**: Uses Windows Junctions or Linux symlinks to link mods to the game folder without duplicating files.
*   **Physical Copy Fallback**: Automatically switches to Physical Copy when junctions are not supported.
*   **Auto-Detection**: Locates GOG, Heroic, and Steam installations automatically on both Windows and Linux.
*   **Cross-Platform**: Works on Windows 10/11 and Linux (tested with Arch).

## Requirements
*   **Windows**: Windows 10/11
*   **Linux**: Any modern distribution with Python 3 and tkinter
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
python cmd.py
```

### Windows
*   **From Source**: Install dependencies (`pip install Pillow tkinterdnd2`) and run `cmd.py`.
*   **Junctions require NTFS**. If your game is on exFAT or FAT32, the app will offer a Physical Copy fallback.

## Release Integrity (Attestations)
Official releases include build attestations to maximize user trust. You can verify attestations on the GitHub Releases page for each version, or build from source using `cmd.py` and the instructions above.

## Usage
1.  Run the application (normal user is fine on Windows and Linux).
2.  **Downloader Tab**:
    *   Ensure Game Path and SteamCMD paths are correct.
    *   Paste a Steam Workshop URL or ID. You can also drag a link from Steam right into the box!
    *   Click "Install Mod".
3.  **Manage Mods Tab**:
    *   Right-click mods to Enable (Link) or Disable (Unlink).
    *   Check for updates to keep mods synchronized with the Workshop.

## Troubleshooting
*   **Windows SmartScreen**: If Windows blocks the app, click **More info** → **Run anyway**. This occurs because the executable is not digitally signed.
*   **Linux**: Make sure your user has permission to create symlinks (usually enabled by default).
*   **Heroic Games Launcher**: Install games through Heroic, and the tool will auto-detect the installation path.
*   **External Drives (Windows)**: Junctions only work on NTFS. If your game is on exFAT, choose the Physical Copy fallback or move the game to an NTFS drive.
