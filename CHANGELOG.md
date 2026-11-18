# Changelog

## v1.1.0

Cross-platform bug-fix release. It fixes wrong or wasted actions, stops mods being installed into the wrong place, and adds builds for more Linux distributions and Intel Macs.

### Downloads and platforms
- **Linux:** the release binary now runs on Ubuntu 20.04+, Debian 11+, Mint 20+ and SteamOS 3. Before, it needed a very recent glibc and failed to start on most LTS distributions.
- **macOS:** there are now separate downloads for Apple Silicon (`macos-arm64`) and Intel Macs (`macos-x86_64`). Before, only an Apple Silicon build existed.
- **SteamCMD** is now downloaded automatically on Linux and macOS, as it already was on Windows. On macOS the app also finds Homebrew and `~/steamcmd` installs.
- **macOS:** right-click and Control-click now open the Manage Mods menu. Before, Enable, Disable, Update and Delete could not be reached on a Mac.
- **Linux:** the packaged app now opens folders, the Workshop and `steam://` links with a clean library path, so browsers, file managers and Steam start reliably.
- **Linux:** Heroic install detection no longer parses Heroic's large store caches, which removes a startup delay.
- The game executable is now matched case-insensitively on Linux and macOS.

### Fixes
- **Steam-subscribed mods:** updating them no longer downloads a duplicate copy through SteamCMD. Steam keeps them up to date, and they are now shown as *Updated by Steam*.
- **Stale links:** a link that points at an old copy (a Steam copy, or a previous cache folder) is now replaced, so the game uses the files that were just downloaded. Before, the app reported success while the game kept the old files.
- **Game path checks:** mods are only installed, enabled or deleted once a valid game folder is selected. Before, Physical Copy mode with no game path wrote mods relative to the app's working folder.
- **BROWSE** now refuses a folder that doesn't contain the game, instead of accepting it and logging it as a success.
- **Physical Copy:**
  - It now has a checkbox, so it can be turned off again. Before, once it was switched on it stayed on permanently.
  - Copies are written to a staging folder first, so closing the app mid-copy no longer leaves a half-copied mod.
- **CLEAR cache:**
  - It now also removes the game's links into the cache. Before, it left links pointing at nothing.
  - CLEAR and DELETE are blocked while a download is running.
- **Broken links:** links whose files are gone now show as **BROKEN LINK** instead of ENABLED. Links to mods that are no longer in any source are listed too, so you can remove them.
- **Admin rights (Windows):**
  - The admin banner only appears when the game folder is write-protected, for example under Program Files. Linking doesn't need admin rights, and running elevated breaks drag-and-drop from the browser.
  - **Relaunch as Admin** no longer closes the app when you cancel the Windows admin (UAC) prompt.
- **STOP** during "Checking deps" now cancels the install.
- **Double-click** in Manage Mods now toggles a mod on or off, as the help text said.
- Links copied from the Steam client (`steam://url/CommunityFilePage/<id>`) are now accepted.
- **Workshop dates:** both the "23 Oct, 2016" and "Oct 23, 2016" formats are now understood, so update checks work whichever date format Steam shows.
- **Batch results:** a batch where nothing was deployed now reports FAILED instead of PARTIAL.
- **Error messages:** scan failures caused by the cache folder are now reported. Missing 32-bit SteamCMD libraries on Linux now come with install instructions.

### Wording and docs
- Startup messages are clearer. "Running in Virtual/Test mode" and "Downloads disabled" are gone.
- The README and the Linux/GOG guide now match the app. They cover Simple Mode, the one-step install, double-click and Control-click, the macOS Gatekeeper workaround, SteamCMD's 32-bit libraries, and Flatpak Steam.
