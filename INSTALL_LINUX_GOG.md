# Installing Battlezone 98 Redux from GOG using Heroic on Linux

This guide provides reproducible steps to install Battlezone 98 Redux from GOG using Heroic Games Launcher on Linux, and set up the Battlezone Mod Engine.

## Prerequisites

- A GOG account with Battlezone 98 Redux purchased
- Arch-based Linux distribution (for other distros, adjust package manager commands)
- Internet connection

## Step 1: Install Heroic Games Launcher

### For Arch:
```bash
yay -S heroic-games-launcher-bin --noconfirm
```

### For other distributions:
```bash
# Flatpak (universal)
flatpak install flathub com.heroicgameslauncher.hgl

# Or download AppImage from:
# https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/releases
```

## Step 2: Install Required Dependencies

### Install Wine (for running Windows games):
```bash
sudo pacman -S wine --noconfirm
```

### Install innoextract (for extracting GOG installers):
```bash
sudo pacman -S innoextract --noconfirm
```

### For Debian/Ubuntu:
```bash
sudo apt update
sudo apt install wine innoextract -y
```

## Step 3: Configure Heroic

### Create game installation directory:
```bash
mkdir -p ~/Games/GOG
mkdir -p ~/Games/Prefixes
```

### Configure Heroic with Wine and install path:
```bash
# Update Heroic configuration
cat ~/.config/heroic/config.json | jq '.defaultInstallPath = "'$HOME'/Games/GOG" | .wineVersion = {bin: "/usr/bin/wine", name: "Wine - System", type: "wine"} | .winePrefix = "'$HOME'/Games/Prefixes/default"' > /tmp/heroic_config_new.json

mv /tmp/heroic_config_new.json ~/.config/heroic/config.json
```

## Step 4: Login to GOG in Heroic

### Launch Heroic:
```bash
heroic &
```

### In the Heroic GUI:
1. Click **"Stores"** in the left sidebar
2. Find **GOG** and click **"Login"**
3. Follow the browser authentication process
4. Authorize Heroic to access your GOG account

## Step 5: Install Battlezone 98 Redux

### Method 1: Using Heroic GUI (if game shows as installable)
1. Go to **Library** in Heroic
2. Find **Battlezone 98 Redux**
3. Click **Install**
4. Choose installation directory (default: `~/Games/GOG`)
5. Wait for download to complete

### Method 2: Manual Download using gogdl (if GUI shows "not installable")

This uses Heroic's built-in GOG downloader directly:

```bash
# Download and install the game
/opt/Heroic/resources/app.asar.unpacked/build/bin/x64/linux/gogdl \
  --auth-config-path ~/.config/heroic/gog_store/auth.json \
  download 1454067812 \
  --platform windows \
  --path ~/Games/GOG \
  --lang en-US
```

**Note:** This will download approximately 1.4 GB and install 2+ GB of game files. The process takes about 2-5 minutes depending on your connection.

### Verify Installation:
```bash
ls -lh ~/Games/GOG/
find ~/Games/GOG -name "battlezone98redux.exe"
```

You should see:
```
~/Games/GOG/Battlezone 98 Redux/battlezone98redux.exe
```











## Step 6: Install Battlezone Mod Engine

### Clone the repository:
```bash
cd ~/
git clone https://github.com/GrizzlyOne95/Battlezone_ModEngine.git
cd Battlezone_ModEngine
```

### Install Python dependencies:
```bash
# For Arch/Manjaro:
sudo pacman -S python python-pillow tk --noconfirm

# For Debian/Ubuntu:
sudo apt install python3 python3-pil python3-tk -y

# Optional: Install drag-and-drop support
pip install tkinterdnd2
```

### Launch the Mod Engine:
```bash
python bz_mod_engine.py &
```

## Step 7: Configure the Mod Engine

The application should auto-detect your installation. If not:

1. **Game Path**: Click "DETECT" or manually browse to:
   ```
   /home/YOUR_USERNAME/Games/GOG/Battlezone 98 Redux
   ```

2. **SteamCMD Path**: Click "DETECT" or set manually if needed

3. **Mod Cache**: Default is fine (`./workshop_cache`)

## Step 8: Download Mods from Steam Workshop

1. Go to [Steam Workshop for Battlezone 98 Redux](https://steamcommunity.com/app/301650/workshop/)
2. Copy the URL or ID of a mod (e.g., `https://steamcommunity.com/sharedfiles/filedetails/?id=123456789`)
3. Paste into the Mod Engine
4. Click **"Install Mod"**
5. Once downloaded, go to **"Manage Mods"** tab
6. Right-click the mod and select **"Enable"** to create a symlink

## Running the Game

### From Heroic:
```bash
heroic
# Then click on Battlezone 98 Redux and click Play
```

### Directly with Wine:
```bash
cd ~/Games/GOG/Battlezone\ 98\ Redux/
wine battlezone98redux.exe
```

### Using Proton (if you have Steam):
```bash
STEAM_COMPAT_DATA_PATH=~/Games/Prefixes/BZ98 \
~/.local/share/Steam/steamapps/common/Proton\ -\ Experimental/proton run \
~/Games/GOG/Battlezone\ 98\ Redux/battlezone98redux.exe
```

## Troubleshooting

### Game won't download from Heroic GUI:
- The game might show as "not installable" due to regional restrictions
- Use Method 2 (manual gogdl download) instead
- Ensure you're logged into GOG in Heroic

### Authentication errors:
```bash
# Re-authenticate with GOG
rm ~/.config/heroic/gog_store/auth.json
heroic
# Then login again through the GUI
```

### Wine/Proton issues:
```bash
# Install additional Wine dependencies
sudo pacman -S wine-gecko wine-mono lib32-gnutls

# For Debian/Ubuntu:
sudo apt install wine64 wine32 libwine
```

### Mod Engine won't launch:
```bash
# Ensure all dependencies are installed
python -c "import tkinter; import PIL; print('Dependencies OK')"

# If errors, reinstall:
sudo pacman -S python python-pillow tk
```

### Symlink permission issues:
On Linux, regular users can create symlinks, so no sudo/admin required. If you get permission errors:
```bash
# Check if the mod cache directory exists and is writable
ls -ld ./workshop_cache
chmod 755 ./workshop_cache
```

## Uninstallation

### Remove game:
```bash
rm -rf ~/Games/GOG/Battlezone\ 98\ Redux
```

### Remove Heroic:
```bash
yay -R heroic-games-launcher-bin
# Or for Flatpak:
flatpak uninstall com.heroicgameslauncher.hgl
```

### Remove configuration:
```bash
rm -rf ~/.config/heroic
rm -rf ~/Games/Prefixes
```

## Additional Notes

- **Game saves location**: `~/Games/GOG/Battlezone 98 Redux/Save/`
- **Mod location**: Symlinked to `~/Games/GOG/Battlezone 98 Redux/mods/`
- **Workshop cache**: `./workshop_cache/steamapps/workshop/content/301650/`
- **Performance**: Game runs well with Wine/Proton on most modern Linux systems
- **Multiplayer**: Online multiplayer should work through Wine with proper network configuration

## Quick Reference Commands

```bash
# Launch Heroic
heroic &

# Launch Mod Engine
cd ~/Battlezone_ModEngine
python bz_mod_engine.py &

# Run game directly
cd ~/Games/GOG/Battlezone\ 98\ Redux/
wine battlezone98redux.exe

# Check installed mods
ls -la ~/Games/GOG/Battlezone\ 98\ Redux/mods/

# Update Heroic config
jq . ~/.config/heroic/config.json
```

## Support

- **Mod Engine Issues**: https://github.com/GrizzlyOne95/Battlezone_ModEngine/issues
- **Heroic Issues**: https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/issues
- **GOG Support**: https://support.gog.com/
- **Wine/Proton**: https://www.protondb.com/ or https://appdb.winehq.org/

---

Last updated: January 31, 2026
Tested on: Arch Linux with Heroic 2.19.1
