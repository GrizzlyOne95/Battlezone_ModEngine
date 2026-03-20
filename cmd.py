import os
import sys
import re
import shutil
import zipfile
import subprocess
import threading
import urllib.request
import platform
from datetime import datetime
from io import BytesIO
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
from pathlib import Path

from config_utils import get_user_config_dir as util_get_user_config_dir, load_config as util_load_config, save_config as util_save_config
from deploy_utils import (
    build_content_dir as util_build_content_dir,
    build_game_context as util_build_game_context,
    build_mod_cache_path as util_build_mod_cache_path,
    clear_directory_contents as util_clear_directory_contents,
    create_directory_link as util_create_directory_link,
    deploy_mod as util_deploy_mod,
    ensure_cache_root as util_ensure_cache_root,
    get_cache_marker_path as util_get_cache_marker_path,
    is_safe_cache_root as util_is_safe_cache_root,
    normalize_path as util_normalize_path,
    paths_match as util_paths_match,
)
from platform_utils import (
    get_default_steamcmd_path as util_get_default_steamcmd_path,
    get_popen_output_kwargs as util_get_popen_output_kwargs,
    get_steamcmd_candidates as util_get_steamcmd_candidates,
    get_steamcmd_name as util_get_steamcmd_name,
    open_path as util_open_path,
)
from steamcmd_utils import (
    build_workshop_download_command,
    classify_workshop_items,
    ensure_console_language_file,
    parse_steamcmd_output_line,
    should_log_noisy_line,
)
from task_utils import TaskState, calculate_batch_progress
from workshop_parser import (
    extract_required_item_ids,
    is_remote_newer,
    parse_workshop_metadata,
)

# Platform-specific imports
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

if IS_WINDOWS:
    import winreg
    import ctypes
else:
    winreg = None
    ctypes = None

# --- EXTERNAL LIBRARIES ---
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    # Requires: pip install tkinterdnd2
    from tkinterdnd2 import DND_TEXT, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

# --- CONFIGURATION ---
STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
CONFIG_FILE = "bz_mod_config.json"
CACHE_MARKER_FILE = ".bz_mod_cache"
HTTP_TIMEOUT = 15

class ToolTip:
    def __init__(self, widget, text, bg="#1a1a1a", fg="#00ffff"):
        self.widget = widget
        self.text = text
        self.bg = bg
        self.fg = fg
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                       background=self.bg, foreground=self.fg, 
                       relief='solid', borderwidth=1, font=("Consolas", "9"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class BZModMaster:
    def __init__(self, root):
        self.root = root
        self.root.title("Battlezone Mod Engine")
        self.root.geometry("1150x850")
        
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
            self.resource_dir = sys._MEIPASS
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self.resource_dir = self.base_dir

        self.config_dir = self.get_user_config_dir()
        self.config_path = os.path.join(self.config_dir, CONFIG_FILE)
        self.legacy_config_path = os.path.join(self.base_dir, CONFIG_FILE)

        # --- GAME DEFINITIONS ---
        self.games = {
            "BZ98R": {
                "name": "Battlezone 98 Redux",
                "appid": "301650",
                "gog_ids": ["1454067812", "1459427445"],
                "exe": "battlezone98redux.exe",
                "font_file": "BZONE.ttf",
                "font_name": "BZONE",
                "icon_file": "bz98.png",
                "colors": {
                    "bg": "#0a0a0a", "fg": "#d4d4d4",
                    "highlight": "#00ff00", "dark_highlight": "#004400", "accent": "#00ffff"
                }
            },
            "BZCC": {
                "name": "Battlezone Combat Commander",
                "appid": "624970",
                "gog_ids": ["1193046833"],
                "exe": "battlezone2.exe",
                "font_file": "BGM.ttf",
                "font_name": "BankGothic",
                "icon_file": "bz2.png",
                "colors": {
                    "bg": "#0a0a0a", "fg": "#d4d4d4",
                    "highlight": "#00aaff", "dark_highlight": "#002244", "accent": "#88ccff"
                }
            }
        }

        self.load_custom_fonts()
        self.load_game_icons()

        icon_path = os.path.join(self.resource_dir, "modman.ico")
        if os.path.exists(icon_path):
            try: self.root.iconbitmap(icon_path)
            except: pass

        self.bin_dir = os.path.join(self.base_dir, "bin")
        self.config = self.load_config()
        
        # Determine active game
        self.current_game_key = self.config.get("last_game", "BZ98R")
        if self.current_game_key not in self.games: self.current_game_key = "BZ98R"
        
        self.apply_theme_vars()
        self.root.configure(bg=self.colors["bg"])

        self.use_physical_var = tk.BooleanVar(value=self.config.get("use_physical", False))
        self.advanced_mode_var = tk.BooleanVar(value=self.config.get("advanced_mode", False))
        
        # Load game-specific path or fallback to legacy global path
        saved_path = self.config.get(f"path_{self.current_game_key}", "")
        if not saved_path and self.current_game_key == "BZ98R":
            saved_path = self.config.get("game_path", "")
            
        self.path_var = tk.StringVar(value=saved_path)
        self.steamcmd_var = tk.StringVar(value=self.config.get("steamcmd_path", ""))
        self.cache_var = tk.StringVar(value=self.config.get("cache_path", os.path.join(self.base_dir, "workshop_cache")))
        
        self.mod_id_var = tk.StringVar()
        self.image_cache = {}
        self.is_valid_mod = False
        
        # Threading & Process Control
        self.stop_event = threading.Event()
        self.active_processes = []
        self.task_lock = threading.Lock()
        self.task_state = TaskState()

        try:
            self.ensure_cache_root(self.cache_var.get())
        except Exception:
            pass

        self.setup_ui()
        self.check_admin()
        
        if not self.path_var.get(): self.auto_detect_gog()
        if not self.steamcmd_var.get(): self.auto_detect_steamcmd()
        self.toggle_ui_mode()
        threading.Thread(target=self.initialize_engine, daemon=True).start()

    def load_custom_fonts(self):
        self.available_fonts = []
        if not IS_WINDOWS:
            return  # Font loading not needed on Linux
        for key, g in self.games.items():
            font_path = os.path.join(self.resource_dir, g["font_file"])
            if os.path.exists(font_path):
                try: 
                    # Check return value: > 0 means success
                    if ctypes.windll.gdi32.AddFontResourceExW(font_path, 0x10, 0) > 0:
                        self.available_fonts.append(g["font_name"])
                except: pass

    def load_game_icons(self):
        self.game_icons = {}
        if not HAS_PIL: return
        for key, g in self.games.items():
            try:
                p = os.path.join(self.resource_dir, g["icon_file"])
                if os.path.exists(p):
                    img = Image.open(p).resize((48, 48), Image.Resampling.LANCZOS)
                    self.game_icons[key] = ImageTk.PhotoImage(img)
            except: pass

    def apply_theme_vars(self):
        g = self.games[self.current_game_key]
        self.colors = g["colors"]
        # Fallback to Consolas if custom font didn't load
        self.current_font = g["font_name"] if g["font_name"] in self.available_fonts else "Consolas"

    def get_user_config_dir(self):
        return util_get_user_config_dir(IS_WINDOWS, IS_LINUX)

    def normalize_path(self, path):
        return util_normalize_path(path)

    def paths_match(self, left, right):
        return util_paths_match(left, right)

    def get_steamcmd_name(self):
        return util_get_steamcmd_name(IS_WINDOWS)

    def get_default_steamcmd_path(self):
        return util_get_default_steamcmd_path(self.bin_dir, IS_WINDOWS)

    def get_steamcmd_candidates(self):
        return util_get_steamcmd_candidates(self.bin_dir, IS_WINDOWS, IS_LINUX)

    def get_popen_output_kwargs(self):
        return util_get_popen_output_kwargs(IS_WINDOWS)

    def open_path(self, target):
        util_open_path(target, IS_WINDOWS, IS_LINUX)

    def build_game_context(self, game_key=None, game_path=None):
        resolved_key = game_key or self.current_game_key
        raw_game_path = game_path if game_path is not None else self.path_var.get()
        return util_build_game_context(self.games, resolved_key, raw_game_path)

    def build_content_dir(self, cache_path, appid):
        return util_build_content_dir(cache_path, appid)

    def build_mod_cache_path(self, cache_path, appid, mid):
        return util_build_mod_cache_path(cache_path, appid, mid)

    def get_cache_marker_path(self, cache_path):
        return util_get_cache_marker_path(cache_path, CACHE_MARKER_FILE)

    def ensure_cache_root(self, cache_path):
        return util_ensure_cache_root(cache_path, CACHE_MARKER_FILE, "Battlezone Mod Engine cache\n")

    def is_safe_cache_root(self, cache_path):
        return util_is_safe_cache_root(cache_path, CACHE_MARKER_FILE)

    def clear_directory_contents(self, directory, preserve_names=None):
        util_clear_directory_contents(directory, self.remove_existing_path, preserve_names=preserve_names)

    def fetch_url_text(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            return response.read().decode("utf-8", errors="replace")

    def fetch_url_bytes(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            return response.read()

    def create_directory_link(self, src, dst):
        util_create_directory_link(src, dst, IS_WINDOWS)

    def deploy_mod(self, mid, src, dst, use_physical):
        deployed = util_deploy_mod(src, dst, use_physical, self.remove_existing_path, self.create_directory_link)
        if not deployed and not os.path.exists(src):
            self.log(f"Mod source missing for {mid}: {src}", "error")
        return deployed

    def begin_download_batch(self):
        with self.task_lock:
            return self.task_state.begin_download_batch()

    def release_download_batch(self):
        with self.task_lock:
            self.task_state.release_download_batch()

    def load_config(self):
        return util_load_config(self.config_path, self.legacy_config_path, self.base_dir)

    def save_config(self, *args):
        # Update current game path in config before saving
        self.config[f"path_{self.current_game_key}"] = self.path_var.get()
        self.config["last_game"] = self.current_game_key
        self.config["steamcmd_path"] = self.steamcmd_var.get()
        self.config["cache_path"] = self.cache_var.get()
        self.config["use_physical"] = self.use_physical_var.get()
        self.config["advanced_mode"] = self.advanced_mode_var.get()

        util_save_config(self.config_path, self.config_dir, self.base_dir, self.config)

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('default')
        
        self.update_styles(style)

        # --- TABS MAIN STRUCTURE ---
        self.tabs = ttk.Notebook(self.root)
        self.dl_tab = ttk.Frame(self.tabs)
        self.manage_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.dl_tab, text=" DOWNLOADER ")
        self.tabs.add(self.manage_tab, text=" MANAGE MODS ")
        self.tabs.pack(fill="both", expand=True)
        self.tabs.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # ==========================================
        # TAB 1: DOWNLOADER
        # ==========================================
        
        # System Configuration
        cfg = ttk.LabelFrame(self.dl_tab, text=" SYSTEM CONFIGURATION ", padding=10)
        cfg.pack(fill="x", padx=10, pady=5)
        
        # Game Switcher Row
        game_row = ttk.Frame(cfg)
        game_row.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        self.target_game_label = ttk.Label(game_row, text="TARGET GAME:", font=(self.current_font, 12, "bold"))
        self.target_game_label.pack(side="left")
        
        game_names = [g["name"] for g in self.games.values()]
        self.game_selector = ttk.Combobox(game_row, values=game_names, state="readonly", width=40)
        
        target_name = self.games[self.current_game_key]["name"]
        if target_name in game_names:
            self.game_selector.current(game_names.index(target_name))
        else:
            self.game_selector.current(0)
            
        self.game_selector.pack(side="left", padx=10)
        self.game_selector.bind("<<ComboboxSelected>>", self.switch_game)

        ttk.Checkbutton(game_row, text="Advanced Mode", variable=self.advanced_mode_var, 
                       command=self.toggle_ui_mode).pack(side="right", padx=10)

        self.icon_label = tk.Label(game_row, bg=self.colors["bg"])
        self.icon_label.pack(side="left", padx=5)
        self.update_game_icon()

        # Path Rows
        paths = [
            ("Game Path:", self.path_var, self.browse_game, "path_entry", 
             "Where the game executable is installed."),
            ("SteamCMD:", self.steamcmd_var, self.browse_steamcmd, "steamcmd_entry", 
             "If you have SteamCMD installed, point to it here.\nIf you aren't sure you can leave it default or choose a new location."),
            ("Mod Cache:", self.cache_var, self.browse_cache, "cache_entry", 
             "Location where mods are downloaded locally before being linked to the game.")
        ]

        self.path_ui_elements = []
        for i, (txt, var, cmd, attr, tip) in enumerate(paths):
            row_idx = i + 1
            widgets = {'default_text': txt}
            
            l = ttk.Label(cfg, text=txt)
            l.grid(row=row_idx, column=0, sticky="w")
            widgets['label'] = l
            
            h_lbl = tk.Label(cfg, text="?", width=2, bg="#222", fg=self.colors['accent'], font=("Consolas", 8, "bold"), cursor="hand2")
            h_lbl.grid(row=row_idx, column=1, padx=(0, 5))
            ToolTip(h_lbl, tip, bg="#1a1a1a", fg=self.colors['accent'])
            widgets['help'] = h_lbl
            
            ent = ttk.Entry(cfg, textvariable=var)
            ent.grid(row=row_idx, column=2, sticky="ew", padx=5)
            setattr(self, attr, ent) 
            widgets['entry'] = ent
            
            b = ttk.Button(cfg, text="BROWSE", width=10, command=cmd)
            b.grid(row=row_idx, column=3, pady=2)
            widgets['browse'] = b
            
            extras = []
            if "Cache" in txt:
                extras.append(ttk.Button(cfg, text="OPEN", width=8, command=lambda v=var: self.open_generic_folder(v)))
                extras.append(ttk.Button(cfg, text="CLEAR", width=8, command=self.clear_cache))
            elif "Game" in txt:
                extras.append(ttk.Button(cfg, text="DETECT", width=8, command=lambda: self.auto_detect_gog(verbose=True)))
                extras.append(ttk.Button(cfg, text="OPEN", width=8, command=lambda v=var: self.open_generic_folder(v)))
            elif "Steam" in txt:
                extras.append(ttk.Button(cfg, text="DETECT", width=8, command=lambda: self.auto_detect_steamcmd(verbose=True)))
                extras.append(ttk.Button(cfg, text="OPEN", width=8, command=lambda v=var: self.open_generic_folder(v)))
            
            for idx, btn in enumerate(extras):
                btn.grid(row=row_idx, column=4 + idx, pady=2, padx=(0, 5))
            
            widgets['extras'] = extras
            self.path_ui_elements.append(widgets)
            
        cfg.columnconfigure(2, weight=1)

        # Mod Queue (Preview & Input)
        prev = ttk.LabelFrame(self.dl_tab, text=" MOD QUEUE ", padding=10)
        prev.pack(fill="x", padx=10, pady=5)
        
        thumb_container = tk.Frame(prev, bg="#050505", width=150, height=150, 
                                 highlightthickness=1, highlightbackground=self.colors['dark_highlight'])
        thumb_container.pack(side="left", padx=10)
        thumb_container.pack_propagate(False)
        self.thumb_container = thumb_container # Ref for theme update

        self.thumb_label = tk.Label(thumb_container, bg="#050505")
        self.thumb_label = tk.Label(thumb_container, bg="#050505", text="ADD MOD\nLINK OR ID", 
                                  fg=self.colors['accent'], font=(self.current_font, 10, "bold"), wraplength=140)
        self.thumb_label.pack(expand=True, fill="both")
        
        info_frame = ttk.Frame(prev)
        info_frame.pack(side="left", fill="both", expand=True)
        
        self.mod_name_label = ttk.Label(info_frame, text="READY FOR COMMAND", foreground=self.colors['accent'], font=(self.current_font, 11, "bold"))
        self.mod_name_label.pack(anchor="w", pady=(0, 5))
        
        self.mod_url_label = ttk.Label(info_frame, text="MOD URL OR ID:", font=(self.current_font, 8))
        self.mod_url_label.pack(anchor="w")
        self.mod_entry = ttk.Entry(info_frame, textvariable=self.mod_id_var)
        self.mod_entry.pack(fill="x", pady=5)
        
        if HAS_DND:
            self.mod_entry.drop_target_register(DND_TEXT)
            self.mod_entry.dnd_bind('<<Drop>>', lambda e: self.mod_id_var.set(e.data.strip("{}")))
            
            self.thumb_label.drop_target_register(DND_TEXT)
            self.thumb_label.dnd_bind('<<Drop>>', lambda e: self.mod_id_var.set(e.data.strip("{}")))
        self.mod_id_var.trace_add("write", self.on_input_change)

        # Context Menu for Inputs
        self.input_menu = tk.Menu(self.root, tearoff=0, bg="#1a1a1a", fg=self.colors['fg'])
        self.input_menu.add_command(label="PASTE FROM CLIPBOARD", command=self.paste_from_clipboard)
        self.thumb_label.bind("<Button-3>", self.show_input_menu)
        self.mod_entry.bind("<Button-3>", self.show_input_menu)

        btn_row = ttk.Frame(info_frame)
        btn_row.pack(fill="x", pady=5)
        self.dl_btn = ttk.Button(btn_row, text="INSTALL MOD", command=self.start_download, style="Success.TButton")
        self.dl_btn.pack(side="left", padx=(0, 5))
        self.launch_btn = ttk.Button(btn_row, text="LAUNCH GAME", command=self.launch_game)
        self.launch_btn.pack(side="left")
        self.workshop_btn = ttk.Button(btn_row, text="WORKSHOP", command=self.open_workshop)
        self.workshop_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(btn_row, text="STOP", command=self.stop_operation, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        # HUD Log
        log_header = ttk.Frame(self.dl_tab)
        log_header.pack(fill="x", padx=10, pady=(5, 0))
        
        self.hud_log_label = ttk.Label(log_header, text=" HUD LOG ", foreground=self.colors['highlight'], font=(self.current_font, 11, "bold"))
        self.hud_log_label.pack(side="left")
        ttk.Button(log_header, text="CLEAR", width=8, command=self.clear_hud_log).pack(side="right")
        
        self.log_box = tk.Text(self.dl_tab, state="disabled", font=("Consolas", 10), bg="#050505", fg=self.colors['fg'], height=12)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Log tags
        self.log_box.tag_config("timestamp", foreground="#444444")
        self.log_box.tag_config("success", foreground=self.colors['highlight'])
        self.log_box.tag_config("warning", foreground="#ffff44")
        self.log_box.tag_config("error", foreground="#ff4444")
        self.log_box.tag_config("info", foreground=self.colors['accent'])

        self.progress = ttk.Progressbar(self.dl_tab, style="BZ.Horizontal.TProgressbar", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=10)
        
        self.progress_label = tk.Label(self.dl_tab, text="IDLE", bg="#050505", fg="#666666", font=("Consolas", 8))
        self.progress_label.place(in_=self.progress, relx=0.5, rely=0.5, anchor="center")

        # ==========================================
        # TAB 2: MANAGE MODS
        # ==========================================
        
        self.tree = ttk.Treeview(self.manage_tab, columns=("Name", "ID", "Status", "Version", "Date"), show="tree headings")
        self.tree.column("#0", width=45, anchor="center", stretch=False)
        self.tree.heading("#0", text="")
        for col in ["Name", "ID", "Status", "Version", "Date"]: 
            self.tree.heading(col, text=col.upper(), command=lambda c=col: self.sort_tree(c, False))
            self.tree.column(col, anchor="center", width=100)
        self.tree.column("Name", width=250) 
        
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<Button-3>", self.show_mod_menu)
        self.tree.bind("<ButtonPress-1>", self.on_tree_press)
        self.tree.bind("<B1-Motion>", self.on_tree_motion)
        manage_ctrl = ttk.Frame(self.manage_tab)
        manage_ctrl.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(manage_ctrl, text="CHECK FOR UPDATES", command=self.refresh_list).pack(side="left")
        ttk.Button(manage_ctrl, text="SELECT ALL", command=self.select_all_mods).pack(side="left", padx=5)
        
        self.manage_help_lbl = tk.Label(manage_ctrl, text="?", width=2, bg="#222", fg=self.colors['accent'], font=("Consolas", 8, "bold"), cursor="hand2")
        self.manage_help_lbl.pack(side="left", padx=10)
        self.manage_help_tip = ToolTip(self.manage_help_lbl, "CONTROLS:\n• Double-Click: Toggle Enable/Disable\n• Right-Click: Context Menu\n• Drag/Shift+Click: Multi-Select", bg="#1a1a1a", fg=self.colors['accent'])

        ttk.Button(manage_ctrl, text="UPDATE ALL", command=self.update_all_mods).pack(side="right")

        # Context Menu
        self.mod_menu = tk.Menu(self.root, tearoff=0, bg="#1a1a1a", fg=self.colors['fg'])
        self.mod_menu.add_command(label="ENABLE (LINK)", command=self.enable_mod)
        self.mod_menu.add_command(label="DISABLE (UNLINK)", command=self.disable_mod)
        self.mod_menu.add_separator()
        self.mod_menu.add_command(label="UPDATE MOD", command=lambda: self.update_selected_mod(force=False))
        self.mod_menu.add_command(label="FORCE UPDATE", command=lambda: self.update_selected_mod(force=True))
        self.mod_menu.add_command(label="DELETE FROM DISK", command=self.delete_mod_physically)

        self.update_tree_tags()

    def toggle_ui_mode(self):
        advanced = self.advanced_mode_var.get()
        
        # 0: Game Path, 1: SteamCMD, 2: Cache
        self.set_row_visibility(0, show_row=advanced, simple=not advanced)
        self.set_row_visibility(1, show_row=advanced, simple=not advanced)
        self.set_row_visibility(2, show_row=True, simple=not advanced)
        
        # Update Cache Label
        cache_widgets = self.path_ui_elements[2]
        cache_widgets['label'].config(text="Download Folder:" if not advanced else cache_widgets['default_text'])

        # Update Simple Mode Texts
        if not advanced:
            self.thumb_label.config(text="DRAG MOD LINK HERE\nOR COPY/PASTE")
            self.mod_url_label.config(text="PASTE WORKSHOP LINK HERE:")
        else:
            self.thumb_label.config(text="ADD MOD\nLINK OR ID")
            self.mod_url_label.config(text="MOD URL OR ID:")

        # Buttons
        if not advanced:
            self.workshop_btn.pack_forget()
            self.launch_btn.pack_forget()
            self.stop_btn.pack_forget()
        else:
            # Repack to ensure order
            for btn in [self.dl_btn, self.launch_btn, self.workshop_btn, self.stop_btn]:
                btn.pack_forget()
            self.dl_btn.pack(side="left", padx=(0, 5))
            self.launch_btn.pack(side="left")
            self.workshop_btn.pack(side="left", padx=5)
            self.stop_btn.pack(side="left", padx=5)

    def set_row_visibility(self, index, show_row, simple):
        widgets = self.path_ui_elements[index]
        if show_row:
            widgets['label'].grid()
            widgets['entry'].grid()
            widgets['browse'].grid()
            
            if simple:
                widgets['help'].grid_remove()
                for w in widgets['extras']: w.grid_remove()
            else:
                widgets['help'].grid()
                for w in widgets['extras']: w.grid()
        else:
            widgets['label'].grid_remove()
            widgets['entry'].grid_remove()
            widgets['browse'].grid_remove()
            widgets['help'].grid_remove()
            for w in widgets['extras']: w.grid_remove()

    def update_styles(self, style):
        main_font = (self.current_font, 10)
        bold_font = (self.current_font, 11, "bold")
        c = self.colors

        # --- GLOBAL STYLES ---
        style.configure(".", background=c["bg"], foreground=c["fg"], font=main_font, bordercolor=c["dark_highlight"])
        style.configure("TFrame", background=c["bg"])
        style.configure("TNotebook", background=c["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a1a", foreground=c["fg"], padding=[10, 2])
        style.map("TNotebook.Tab", background=[("selected", c["dark_highlight"])], foreground=[("selected", c["highlight"])])
        style.configure("TLabelframe", background=c["bg"], bordercolor=c["highlight"])
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["highlight"], font=bold_font)
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("TEntry", fieldbackground="#1a1a1a", foreground=c["accent"], insertcolor=c["highlight"])
        style.configure("BZ.Horizontal.TProgressbar", thickness=15, background=c["highlight"], troughcolor="#050505")
        style.configure("TButton", background="#1a1a1a", foreground=c["fg"])
        style.map("TButton", background=[("active", c["dark_highlight"])], foreground=[("active", c["highlight"])])
        style.configure("Success.TButton", foreground=c["highlight"], font=bold_font)
        
        style.configure("Treeview", background="#0a0a0a", foreground=c["fg"], fieldbackground="#0a0a0a", rowheight=40)
        style.map("Treeview", background=[("selected", c["accent"])], foreground=[("selected", "#000000")])

    def update_game_icon(self):
        if not hasattr(self, 'icon_label'): return
        c = self.colors
        icon = self.game_icons.get(self.current_game_key)
        
        if icon:
            self.icon_label.config(image=icon, bg=c["bg"], highlightbackground=c["highlight"], highlightthickness=1, bd=0)
            self.icon_label.image = icon
        else:
            self.icon_label.config(image="", width=0, bd=0, highlightthickness=0)

    def update_tree_tags(self):
        c = self.colors
        self.tree.tag_configure('active', foreground=c['highlight'])
        self.tree.tag_configure('inactive', foreground="#666666")

    def switch_game(self, event=None):
        if self.task_state.has_active_tasks:
            self.game_selector.set(self.games[self.current_game_key]["name"])
            self.log("Wait for the current operation to finish before switching games.", "warning")
            return

        selected_name = self.game_selector.get()
        
        # Find key by name
        new_key = next((k for k, v in self.games.items() if v["name"] == selected_name), "BZ98R")
        
        if new_key == self.current_game_key: return
        
        # Save current state
        self.save_config()
        
        # Switch
        self.current_game_key = new_key
        self.apply_theme_vars()
        
        # Update Path Var
        saved_path = self.config.get(f"path_{self.current_game_key}", "")
        self.path_var.set(saved_path)
        
        # Update UI Styles
        style = ttk.Style()
        self.update_styles(style)
        
        # Update Manual Widgets
        c = self.colors
        self.root.configure(bg=c["bg"])
        self.log_box.configure(fg=c["fg"])
        self.log_box.tag_config("success", foreground=c['highlight'])
        self.log_box.tag_config("info", foreground=c['accent'])
        
        self.mod_name_label.configure(foreground=c['accent'], font=(self.current_font, 11, "bold"))
        self.hud_log_label.configure(foreground=c['highlight'], font=(self.current_font, 11, "bold"))
        self.thumb_label.configure(fg=c['accent'], font=(self.current_font, 10, "bold"))
        self.target_game_label.configure(font=(self.current_font, 12, "bold"))
        self.mod_url_label.configure(font=(self.current_font, 8))
        self.thumb_container.configure(highlightbackground=c['dark_highlight'])
        self.mod_menu.configure(fg=c['fg'])
        self.input_menu.configure(fg=c['fg'])
        
        if hasattr(self, 'manage_help_lbl'):
            self.manage_help_lbl.configure(fg=c['accent'])
            self.manage_help_tip.fg = c['accent']
        
        self.update_tree_tags()
        self.update_game_icon()
        
        self.log(f"Switched to {self.games[new_key]['name']}", "info")
        self.initialize_engine()
        self.refresh_list()
        self.save_config()
        
        if self.mod_id_var.get():
            self.is_valid_mod = False
            self.mod_name_label.config(text="VALIDATING...", foreground=c['fg'])
            self.on_input_change()

    def clear_hud_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def log(self, message, tag=None):
        self.root.after(0, lambda: self._log_impl(message, tag))

    def _log_impl(self, message, tag=None):
        # Simple Mode Filter: Only show tagged messages (Success, Warning, Error, Info)
        if not self.advanced_mode_var.get() and tag is None:
            return

        self.log_box.config(state="normal")
        ts = datetime.now().strftime("[%H:%M:%S] ")
        self.log_box.insert("end", ts, "timestamp")
        
        if tag:
            self.log_box.insert("end", f"{message}\n", tag)
        else:
            self.log_box.insert("end", f"{message}\n")
            
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def start_task(self):
        with self.task_lock:
            transition = self.task_state.start_task()
            if transition.entered_busy:
                self.stop_event.clear()
                self.root.after(0, lambda: self.stop_btn.config(state="normal"))
                self.root.after(0, lambda: self.game_selector.config(state="disabled"))

    def end_task(self, callback=None):
        with self.task_lock:
            transition = self.task_state.end_task()
            if transition.became_idle:
                self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
                self.root.after(0, lambda: self.game_selector.config(state="readonly"))
                self.root.after(0, self.reset_progress)
                if callback:
                    self.root.after(1000, callback)

    def stop_operation(self):
        self.stop_event.set()
        self.log("Stopping operations...", "warning")
        for p in list(self.active_processes):
            try: p.terminate()
            except: pass

    def get_dependencies(self, mid):
        """Scrapes the Steam Workshop page for required items."""
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mid}&l=english"
        try:
            html = self.fetch_url_text(url)
            return extract_required_item_ids(html)
        except Exception as e:
            self.log(f"Dependency Check Failed: {e}", "warning")
            pass
        return []

    def update_batch_progress(self, item_percent, completed_count, total_items):
        progress_state = calculate_batch_progress(item_percent, completed_count, total_items)
        self.progress.stop()
        self.progress.config(mode="determinate", value=progress_state["total_percent"])
        self.progress_label.config(text=progress_state["label_text"])
        if progress_state["button_text"]:
            self.dl_btn.config(text=progress_state["button_text"])

    def _abort_download_ui(self):
        self.release_download_batch()
        self.dl_btn.config(text="INSTALL MOD", state="normal")
        self.reset_progress()
        self.end_task()

    def _prompt_deps_and_start(self, queue, deps, sc_path, cache_path, game_context):
        try:
            if deps:
                if messagebox.askyesno("Dependencies Found", f"This mod requires {len(deps)} other items.\nDownload them as well?"):
                    queue.extend(deps)
        except Exception as e:
            self.log(f"Dependency prompt failed: {e}", "warning")

        use_physical = self.resolve_deploy_mode(game_context["game_path"], self.use_physical_var.get())
        if use_physical is None:
            self._abort_download_ui()
            return

        self.dl_btn.config(state="disabled", text="ENGINE ACTIVE")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.progress_label.config(text="INITIALIZING...", fg=self.colors['accent'])

        threading.Thread(
            target=self.download_logic,
            args=(queue, sc_path, cache_path, game_context, use_physical),
            daemon=True
        ).start()

    def start_download(self):
        mid = self.sanitize_id(self.mod_id_var.get())
        if not mid: 
            self.dl_btn.config(text="NO MOD ID")
            self.root.after(2000, lambda: self.dl_btn.config(text="INSTALL MOD", state="normal"))
            return
        
        # FINAL GATEKEEPER: Check validation flag
        if hasattr(self, 'is_valid_mod') and not self.is_valid_mod:
            current_game_name = self.games[self.current_game_key]["name"]
            messagebox.showerror("Validation Error", f"Target Mod ID does not belong to {current_game_name}.\nDownload Aborted.")
            return

        if not self.begin_download_batch():
            self.log("A download or update batch is already running.", "warning")
            return

        queue = [mid]
        game_context = self.build_game_context()
        sc_path = self.steamcmd_var.get()
        cache_path = self.cache_var.get()
        self.dl_btn.config(state="disabled", text="CHECKING DEPS...")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.progress_label.config(text="CHECKING DEPS...", fg=self.colors['accent'])
        self.start_task()

        def deps_worker():
            deps = []
            try:
                deps = self.get_dependencies(mid)
            except Exception as e:
                self.log(f"Dependency Check Failed: {e}", "warning")
            self.root.after(0, lambda: self._prompt_deps_and_start(queue, deps, sc_path, cache_path, game_context))

        threading.Thread(target=deps_worker, daemon=True).start()

    def download_logic(self, mod_ids, sc_path, cache_path, game_context, use_physical):
        if isinstance(mod_ids, str):
            mod_ids = [mod_ids]
        try:
            current_appid = game_context["appid"]
            game_path = game_context["game_path"]
            final_sc_path = self.ensure_steamcmd(sc_path)
            cache = self.ensure_cache_root(cache_path)
            
            ensure_console_language_file(final_sc_path)

            total_items = len(mod_ids)
            self.log(f"Batch processing {total_items} items...", "info")

            for mid, exists_locally in classify_workshop_items(cache, current_appid, mod_ids, self.build_mod_cache_path):
                if exists_locally:
                    self.log(f"Queueing update: {mid}", "warning")
                else:
                    self.log(f"Queueing download: {mid}", "info")

            cmd = build_workshop_download_command(final_sc_path, cache, current_appid, mod_ids)
            
            p = subprocess.Popen(cmd, **self.get_popen_output_kwargs())
            self.active_processes.append(p)
            
            completed_count = 0
            
            last_log_time = 0
            
            while True:
                if self.stop_event.is_set():
                    p.terminate()
                    break
                line = p.stdout.readline()
                if not line:
                    break
                
                event = parse_steamcmd_output_line(line)
                current_time = datetime.now().timestamp()

                if event["kind"] == "empty":
                    continue
                if event["kind"] == "success":
                    completed_count += 1
                    self.log(f"Success: {event['item']} ({completed_count}/{total_items})", "success")
                    self.root.after(0, lambda c=completed_count, t=total_items: self.update_batch_progress(0, c, t))
                elif event["kind"] == "error":
                    self.log(event["message"], "error")
                elif event["kind"] == "progress":
                    self.root.after(0, lambda v=event["value"], c=completed_count, t=total_items: self.update_batch_progress(v, c, t))
                elif event["kind"] == "verifying":
                    self.root.after(0, lambda c=completed_count, t=total_items: self.dl_btn.config(text=f"VERIFYING {c+1}/{t}..."))
                elif event["kind"] == "noisy":
                    if should_log_noisy_line(current_time, last_log_time):
                        self.log(event["message"])
                        last_log_time = current_time
                elif event["kind"] == "info":
                    self.log(event["message"])

            p.wait()
            if p in self.active_processes:
                self.active_processes.remove(p)
            if p.returncode not in (0, None) and not self.stop_event.is_set():
                self.log(f"SteamCMD exited with code {p.returncode}.", "warning")

            # Process Links for all items
            for mid in mod_ids:
                src = os.path.normpath(self.build_mod_cache_path(cache, current_appid, mid))
                dst = os.path.normpath(os.path.join(game_path, "mods", mid))
                
                if os.path.exists(src):
                    deployed_ok = False
                    try:
                        deployed_ok = self.deploy_mod(mid, src, dst, use_physical)
                    except subprocess.TimeoutExpired:
                        self.log(f"Link creation timed out for {mid}", "error")
                    except subprocess.CalledProcessError as e:
                        err = e.stderr.strip() if e.stderr else "Unknown error"
                        self.log(f"Link creation failed for {mid}: {err}", "error")
                    except Exception as e:
                        self.log(f"Link creation failed for {mid}: {e}", "error")
                    if deployed_ok:
                        self.log(f"Deployment complete: {mid}", "success")
                    else:
                        self.log(f"Deployment failed: {mid}", "error")
            
            self.root.after(0, lambda: self.dl_btn.config(text="DEPLOYED"))
            self.root.after(3000, lambda: self.dl_btn.config(text="INSTALL MOD", state="normal"))
            
        except Exception as e:
            self.log(f"CRITICAL: {e}", "error")
        finally:
            self.release_download_batch()
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def update_progress(self, value):
        self.progress.stop()
        self.progress.config(mode="determinate", value=value)
        self.progress_label.config(text=f"DOWNLOADING {int(value)}%")
        if value < 100: self.dl_btn.config(text=f"DOWNLOADING {int(value)}%")

    def reset_progress(self):
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.progress_label.config(text="IDLE", fg="#666666")

    def on_input_change(self, *args):
        mid = self.sanitize_id(self.mod_id_var.get())
        if mid and len(mid) >= 8:
            game_context = self.build_game_context()
            threading.Thread(target=self.fetch_preview, args=(mid, game_context), daemon=True).start()
    def open_workshop(self):
        appid = self.games[self.current_game_key]["appid"]
        webbrowser.open(f"https://steamcommunity.com/app/{appid}/workshop/")
    def fetch_preview(self, mid, game_context):
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mid}&l=english"
            html = self.fetch_url_text(url)
            metadata = parse_workshop_metadata(html)
            target_appid = game_context["appid"]
            current_app = metadata.appid

            if not self.is_active_preview_request(game_context["key"], mid):
                return

            if current_app and current_app != target_appid:
                self.is_valid_mod = False
                self.root.after(0, lambda: self.update_preview_title(game_context["key"], mid, "INVALID GAME DETECTED", "#ff0000"))
                return

            self.is_valid_mod = True
            title = metadata.title or f"ID: {mid}"

            self.root.after(0, lambda: self.update_preview_title(game_context["key"], mid, title, self.colors['accent']))
            if HAS_PIL and metadata.thumbnail_url:
                raw = self.fetch_url_bytes(metadata.thumbnail_url)
                img = Image.open(BytesIO(raw)).resize((150, 150), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.root.after(0, lambda p=photo: self.update_preview_image(game_context["key"], mid, p))
        except Exception as e:
            self.log(f"Metadata Fetch Error: {e}", "error")

    def is_active_preview_request(self, game_key, mid):
        return game_key == self.current_game_key and self.sanitize_id(self.mod_id_var.get()) == mid

    def update_preview_title(self, game_key, mid, title, color):
        if not self.is_active_preview_request(game_key, mid):
            return
        self.mod_name_label.config(text=title, foreground=color)

    def update_preview_image(self, game_key, mid, photo):
        if not self.is_active_preview_request(game_key, mid):
            return
        self.update_thumb(photo)

    def update_thumb(self, photo):
        self.thumb_label.config(image=photo)
        self.thumb_label.image = photo 

    def show_input_menu(self, event):
        self.input_menu.post(event.x_root, event.y_root)

    def paste_from_clipboard(self):
        try:
            self.mod_id_var.set(self.root.clipboard_get())
        except: pass

    def sanitize_id(self, input_str):
        match = re.search(r'id=(\d+)', input_str)
        return match.group(1) if match else (input_str.strip() if input_str.strip().isdigit() else None)

    def initialize_engine(self):
        game_name = self.games[self.current_game_key]["name"]
        self.log(f"{game_name} Engine Initializing...", "info")
        
        # Check Game Path - Logic adjusted for your test environment
        game_exe = os.path.join(self.path_var.get(), self.games[self.current_game_key]["exe"])
        if not os.path.exists(game_exe):
            self.log("NOTICE: Executable not found. Running in Virtual/Test mode.", "warning")
            self.path_entry.configure(foreground="#ffff44") # Yellow for "Mock Mode"
        else:
            self.log(f"System Link Established: {game_exe}", "success")
            self.path_entry.configure(foreground=self.colors['accent'])
        
        # Check SteamCMD
        if not os.path.exists(self.steamcmd_var.get()):
            self.log("WARNING: SteamCMD missing. Downloads disabled.", "warning")
            self.steamcmd_entry.configure(foreground="#ffff44")
        else:
            self.log("SteamCMD Binary: Verified.", "success")

        self.log("Ready for mod deployment.", "info")

    def ensure_steamcmd(self, target):
        if not target:
            target = self.get_default_steamcmd_path()
            self.root.after(0, lambda: self.steamcmd_var.set(target))
            
        if not os.path.exists(target):
            if not IS_WINDOWS:
                raise FileNotFoundError("SteamCMD was not found. Install steamcmd and point the app to the executable.")

            target_dir = os.path.dirname(target)
            self.log(f"SteamCMD missing. Downloading to {target_dir}...", "warning")
            os.makedirs(target_dir, exist_ok=True)
            zip_p = os.path.join(target_dir, "sc.zip")
            try:
                urllib.request.urlretrieve(STEAMCMD_URL, zip_p)
                with zipfile.ZipFile(zip_p, 'r') as z: z.extractall(target_dir)
                os.remove(zip_p)
                self.log("SteamCMD installed successfully.", "success")
            except Exception as e:
                self.log(f"SteamCMD Setup Error: {e}", "error")
                raise e
        return target

    def check_admin(self):
        if IS_WINDOWS and ctypes:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                self.log("NOTICE: Non-Admin mode detected.", "error")
                self.show_admin_warning()
        # Linux doesn't need admin for symlinks

    def show_admin_warning(self):
        self.admin_frame = tk.Frame(self.dl_tab, bg="#330000", pady=2)
        children = self.dl_tab.winfo_children()
        if children:
            self.admin_frame.pack(side="top", fill="x", padx=10, pady=(5,0), before=children[0])
        else:
            self.admin_frame.pack(side="top", fill="x", padx=10, pady=5)
            
        lbl = tk.Label(self.admin_frame, text="⚠ ADMIN OR NTFS REQUIRED FOR JUNCTIONS", 
                       bg="#330000", fg="#ff5555", font=("Consolas", 10, "bold"))
        lbl.pack(side="left", padx=10)
        
        btn = ttk.Button(self.admin_frame, text="RELAUNCH AS ADMIN", command=self.relaunch_admin)
        btn.pack(side="right", padx=5, pady=2)
        ToolTip(lbl, "Windows requires NTFS to create junctions.\nIf your game is on exFAT, use Physical Copy or move to NTFS.")

    def relaunch_admin(self):
        try:
            if getattr(sys, 'frozen', False):
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "", None, 1)
            else:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(sys.argv[0])}"', None, 1)
            self.root.destroy()
        except Exception as e:
            self.log(f"Relaunch failed: {e}", "error")

    def browse_game(self): 
        p = filedialog.askdirectory()
        if p:
            new_path = os.path.normpath(p)
            cache_path = self.cache_var.get()
            
            if self.paths_match(cache_path, new_path):
                messagebox.showerror("Path Conflict", "Game Path cannot be the same as Mod Cache Path.\nPlease select a different folder.")
                return

            self.path_var.set(new_path)
            self.path_entry.configure(foreground=self.colors['accent']) # Reset color
            self.save_config()
            self.log(f"Game path updated: {p}", "success")

    def browse_steamcmd(self): 
        if IS_WINDOWS:
            result = messagebox.askyesnocancel(
                "SteamCMD Setup",
                "Do you already have SteamCMD installed?\n\nYES: Browse for existing steamcmd.exe\nNO: Select a folder to download a new copy\nCANCEL: Abort"
            )
            if result is None:
                return
            if result:
                p = filedialog.askopenfilename(filetypes=[("Executable", "steamcmd.exe"), ("All Executables", "*.exe")])
                if p:
                    self.steamcmd_var.set(os.path.normpath(p))
                    self.steamcmd_entry.configure(foreground=self.colors['accent'])
                    self.save_config()
                    self.log(f"SteamCMD path updated: {p}", "success")
            else:
                p = filedialog.askdirectory(title="Select Install Location for SteamCMD")
                if p:
                    target = os.path.join(p, self.get_steamcmd_name())
                    self.steamcmd_var.set(os.path.normpath(target))
                    self.steamcmd_entry.configure(foreground=self.colors['accent'])
                    self.save_config()
                    self.log(f"SteamCMD will be installed to: {p}", "info")
            return

        p = filedialog.askopenfilename(
            title="Select SteamCMD executable",
            filetypes=[("SteamCMD", "steamcmd*"), ("All Files", "*.*")]
        )
        if p:
            self.steamcmd_var.set(os.path.normpath(p))
            self.steamcmd_entry.configure(foreground=self.colors['accent'])
            self.save_config()
            self.log(f"SteamCMD path updated: {p}", "success")

    def browse_cache(self): 
        p = filedialog.askdirectory()
        if p:
            new_path = os.path.normpath(p)
            game_path = self.path_var.get()
            
            if self.paths_match(game_path, new_path):
                messagebox.showerror("Path Conflict", "Mod Cache Path cannot be the same as Game Path.\nPlease select a different folder.")
                return

            self.ensure_cache_root(new_path)
            self.cache_var.set(new_path)
            self.save_config()
            
            # In Simple Mode, if Game Path is missing, prompt for it now
            if not self.advanced_mode_var.get():
                game_path = self.path_var.get()
                exe_name = self.games[self.current_game_key]["exe"]
                if not game_path or not os.path.exists(os.path.join(game_path, exe_name)):
                    messagebox.showinfo("Game Location Required", "Please select your Game Installation folder so mods can be installed.")
                    self.browse_game()

    def open_generic_folder(self, var):
        path = var.get()
        if not path: return
        target = path
        if os.path.isfile(target): target = os.path.dirname(target)
        if os.path.exists(target):
            self.open_path(target)
        else: messagebox.showinfo("Info", "Path does not exist.")

    def clear_cache(self):
        cache_path = self.cache_var.get()
        if not cache_path or not os.path.exists(cache_path):
            messagebox.showinfo("Cache Empty", "The cache folder does not exist.")
            return

        cache_root = self.ensure_cache_root(cache_path)
        if not self.is_safe_cache_root(cache_root):
            messagebox.showerror("Unsafe Cache Path", "Refusing to clear a cache path that is not marked as an app cache.")
            return

        if messagebox.askyesno("Clear Cache", f"Are you sure you want to delete all files in:\n{cache_path}\n\nThis will force re-download of all mods."):
            try:
                self.clear_directory_contents(cache_root, preserve_names={CACHE_MARKER_FILE})
                self.log("Cache cleared successfully.", "success")
                self.refresh_list()
            except Exception as e:
                self.log(f"Failed to clear cache: {e}", "error")



    def launch_game(self):
        exe = os.path.join(self.path_var.get(), self.games[self.current_game_key]["exe"])
        if os.path.exists(exe):
            self.launch_btn.config(text="LAUNCHING...")
            subprocess.Popen([exe], cwd=self.path_var.get())
            self.root.after(5000, lambda: self.launch_btn.config(text="LAUNCH GAME"))
        else:
            self.launch_btn.config(text="EXE MISSING")
            self.root.after(2000, lambda: self.launch_btn.config(text="LAUNCH GAME"))
    def auto_detect_gog(self, verbose=False):
        found_path = None
        
        if IS_WINDOWS and winreg:
            # Windows: Check registry
            gog_ids = self.games[self.current_game_key].get("gog_ids", [])
            for g_id in gog_ids:
                for arch in ["SOFTWARE\\WOW6432Node", "SOFTWARE"]:
                    try:
                        reg = f"{arch}\\GOG.com\\Games\\{g_id}"
                        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
                        path, _ = winreg.QueryValueEx(key, "path")
                        found_path = os.path.normpath(path)
                        break
                    except: pass
                if found_path: break
        elif IS_LINUX:
            # Linux: Check Heroic, Steam, and common GOG paths
            home = Path.home()
            game_exe = self.games[self.current_game_key]["exe"]
            
            candidates = [
                # Heroic GOG installations
                home / "Games" / "GOG" / "Battlezone 98 Redux",
                home / "Games" / "Heroic" / "Battlezone 98 Redux",
                # Steam installations
                home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Battlezone 98 Redux",
                home / ".steam" / "steam" / "steamapps" / "common" / "Battlezone 98 Redux",
                # Manual installations
                home / "games" / "battlezone98redux",
                home / ".wine" / "drive_c" / "GOG Games" / "Battlezone 98 Redux",
            ]
            
            for path in candidates:
                exe_path = path / game_exe
                if exe_path.exists():
                    found_path = str(path)
                    break
        
        if found_path:
            self.path_var.set(found_path)
            self.save_config()
            if verbose: messagebox.showinfo("Success", f"Game found at:\n{found_path}")
        elif verbose:
            messagebox.showwarning("Not Found", "Could not automatically locate GOG/Heroic installation.")

    def auto_detect_steamcmd(self, verbose=False):
        for p in self.get_steamcmd_candidates():
            if os.path.exists(p):
                self.steamcmd_var.set(os.path.normpath(p))
                self.save_config()
                if verbose: messagebox.showinfo("Success", f"SteamCMD found at:\n{p}")
                return
        if verbose:
            messagebox.showwarning("Not Found", "Could not locate SteamCMD.\nPlease browse manually.")
                
    def on_tab_change(self, event):
        """Auto-refreshes the list when the user clicks the Manage tab."""
        if self.tabs.index("current") == 1:
            self.refresh_list()

    def sort_tree(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try:
            l.sort(key=lambda t: int(t[0]) if t[0].isdigit() else t[0], reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))

    def on_tree_press(self, event):
        item = self.tree.identify_row(event.y)
        if item: self.selection_start = item

    def on_tree_motion(self, event):
        item = self.tree.identify_row(event.y)
        if item and hasattr(self, 'selection_start') and self.selection_start:
            if self.tree.identify_region(event.x, event.y) == "cell":
                children = self.tree.get_children()
                try:
                    start_idx = children.index(self.selection_start)
                    end_idx = children.index(item)
                    if start_idx > end_idx: start_idx, end_idx = end_idx, start_idx
                    self.tree.selection_set(children[start_idx : end_idx + 1])
                except ValueError: pass

    def show_mod_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self.mod_menu.post(event.x_root, event.y_root)

    def select_all_mods(self):
        self.tree.selection_set(self.tree.get_children())

    def refresh_list(self):
        """Scans SteamCMD cache and determines if mods are 'enabled' in the test folder."""
        self.progress_label.config(text="SCANNING...", fg=self.colors['accent'])
        self.image_cache.clear()
        self.progress.config(mode="indeterminate"); self.progress.start(10)
        
        # Offload file system scanning to a background thread
        cache_path = self.cache_var.get()
        game_context = self.build_game_context()
        
        self.start_task()
        threading.Thread(target=self._refresh_scan_logic, args=(cache_path, game_context), daemon=True).start()

    def _refresh_scan_logic(self, cache_path, game_context):
        try:
            base_cache = self.ensure_cache_root(cache_path)
            game_dir = game_context["game_path"]

            if not game_dir:
                self.log("SCAN FAILED: Game path is not configured.", "error")
                self.root.after(0, lambda: self._populate_tree([], game_context))
                return
            
            # Correct nested SteamCMD structure
            current_appid = game_context["appid"]
            content_dir = self.build_content_dir(base_cache, current_appid)
            game_mods_dir = os.path.join(game_dir, "mods")
            
            self.log("--- SCANNING FOR ASSETS ---", "info")

            # Ensure the test 'mods' folder exists
            if not os.path.exists(game_mods_dir):
                try: os.makedirs(game_mods_dir)
                except: pass

            if not os.path.exists(content_dir):
                self.log(f"SCAN FAILED: No cache at {content_dir}", "error")
                self.root.after(0, lambda: self._populate_tree([], game_context))
                return

            try:
                mod_ids = [d for d in os.listdir(content_dir) if os.path.isdir(os.path.join(content_dir, d))]
                self.log(f"Found {len(mod_ids)} assets in Steam cache.", "success")
            except:
                self.root.after(0, lambda: self._populate_tree([], game_context))
                return

            # Collect data to pass back to UI thread
            scan_data = []
            for mid in mod_ids:
                if self.stop_event.is_set(): return
                mod_path = os.path.join(content_dir, mid)
                link_path = os.path.join(game_mods_dir, mid)
                
                # Use lexists to see if the link is present in your test folder
                is_enabled = os.path.lexists(link_path)
                status = "ENABLED" if is_enabled else "DISABLED"
                
                try:
                    m_time = os.path.getmtime(mod_path)
                    dt = datetime.fromtimestamp(m_time).strftime('%Y-%m-%d')
                except:
                    m_time = 0
                    dt = "Unknown"
                
                scan_data.append((mid, status, is_enabled, m_time, dt))

            self.root.after(0, lambda: self._populate_tree(scan_data, game_context))
        finally:
            self.end_task()

    def _populate_tree(self, scan_data, game_context):
        if game_context["key"] != self.current_game_key:
            return

        self.tree.delete(*self.tree.get_children())
        
        for mid, status, is_enabled, m_time, dt in scan_data:
            display_status = f"{status} (Checking...)"
            
            item = self.tree.insert("", "end", values=("Fetching...", mid, display_status, "Checking...", dt))
            
            if is_enabled:
                self.tree.item(item, tags=('active',))
            else:
                self.tree.item(item, tags=('inactive',))

            threading.Thread(
                target=self.fetch_mod_info_for_tree,
                args=(item, mid, m_time, status, game_context),
                daemon=True
            ).start()

        self.root.after(0, self.update_tree_tags)

    def safe_tree_set(self, item, col, value):
        try:
            if self.tree.exists(item):
                self.tree.set(item, col, value)
        except tk.TclError:
            pass

    def add_tag(self, item, tag):
        if self.tree.exists(item):
            tags = list(self.tree.item(item, "tags"))
            if tag not in tags:
                tags.append(tag)
                self.tree.item(item, tags=tags)

    def safe_tree_set_for_game(self, game_key, item, col, value):
        if game_key != self.current_game_key:
            return
        self.safe_tree_set(item, col, value)

    def add_tree_tag_for_game(self, game_key, item, tag):
        if game_key != self.current_game_key:
            return
        self.add_tag(item, tag)

    def set_tree_image(self, item, raw_data, mid):
        if not self.tree.exists(item): return
        try:
            img = Image.open(BytesIO(raw_data))
            img.thumbnail((36, 36), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.image_cache[mid] = photo
            self.tree.item(item, image=photo)
        except Exception: pass

    def set_tree_image_for_game(self, game_key, item, raw_data, mid):
        if game_key != self.current_game_key:
            return
        self.set_tree_image(item, raw_data, mid)

    def fetch_mod_info_for_tree(self, item, mid, local_ts, base_status, game_context):
        """Fetches mod name and checks for updates."""
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mid}&l=english"
            html = self.fetch_url_text(url)
            metadata = parse_workshop_metadata(html)
            title = metadata.title or mid

            if HAS_PIL and metadata.thumbnail_url:
                try:
                    raw = self.fetch_url_bytes(metadata.thumbnail_url)
                    self.root.after(0, lambda: self.set_tree_image_for_game(game_context["key"], item, raw, mid))
                except Exception:
                    pass

            remote_date_str = metadata.remote_date_text or "Unknown"
            is_out_of_date = is_remote_newer(metadata.remote_date_text, local_ts)

            final_status = base_status
            if is_out_of_date:
                final_status = f"{base_status} (OUT OF DATE)"
                self.root.after(0, lambda: self.add_tree_tag_for_game(game_context["key"], item, "update_needed"))
                v_status = f"Remote: {remote_date_str}"
            else:
                v_status = "UP TO DATE"

            self.root.after(0, lambda: self.safe_tree_set_for_game(game_context["key"], item, "Name", title))
            self.root.after(0, lambda: self.safe_tree_set_for_game(game_context["key"], item, "Version", v_status))
            self.root.after(0, lambda: self.safe_tree_set_for_game(game_context["key"], item, "Status", final_status))
        except:
            self.root.after(0, lambda: self.safe_tree_set_for_game(game_context["key"], item, "Name", f"ID: {mid} (Fetch Error)"))
            self.root.after(0, lambda: self.safe_tree_set_for_game(game_context["key"], item, "Status", base_status))

    def enable_mod(self):
        """Creates a Junction link from the deep cache to the game folder for all selected mods."""
        selected = self.tree.selection()
        if not selected: return
        
        # Extract data on main thread
        mods_to_enable = [str(self.tree.item(item)['values'][1]) for item in selected]
        cache_path = self.cache_var.get()
        game_context = self.build_game_context()
        game_path = game_context["game_path"]
        use_physical = self.resolve_deploy_mode(game_path, self.use_physical_var.get())
        if use_physical is None:
            return

        self.start_task()
        threading.Thread(
            target=self._enable_mod_worker,
            args=(mods_to_enable, cache_path, game_context, use_physical),
            daemon=True
        ).start()

    def _enable_mod_worker(self, mods, cache_path, game_context, use_physical):
        try:
            cache_root = self.ensure_cache_root(cache_path)
            for mid in mods:
                if self.stop_event.is_set(): break
                current_appid = game_context["appid"]
                src = self.build_mod_cache_path(cache_root, current_appid, mid)
                dst = os.path.join(game_context["game_path"], "mods", mid)
                
                try:
                    deployed = self.deploy_mod(mid, src, dst, use_physical)
                    if deployed:
                        action = "Physical Copy" if use_physical else ("Junction created" if IS_WINDOWS else "Symlink created")
                        self.log(f"Mod {mid} enabled ({action}).", "success")
                except Exception as e:
                    self.log(f"Link Error for {mid}: {e}", "error")
        finally:
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def disable_mod(self):
        """Disables all selected mods by removing their Junction links."""
        selected = self.tree.selection()
        if not selected: return
        
        mods_to_disable = [str(self.tree.item(item)['values'][1]) for item in selected]
        game_path = self.path_var.get()
        self.start_task()
        threading.Thread(target=self._disable_mod_worker, args=(mods_to_disable, game_path), daemon=True).start()

    def _disable_mod_worker(self, mods, game_path):
        try:
            for mid in mods:
                if self.stop_event.is_set(): break
                dst = os.path.join(game_path, "mods", mid)
                
                try:
                    if os.path.lexists(dst):
                        if IS_WINDOWS:
                            # In Windows, 'os.rmdir' is the correct way to remove a Junction 
                            # without deleting the contents of the source folder.
                            if os.path.isdir(dst):
                                os.rmdir(dst) 
                            else:
                                os.remove(dst) # Handle file symlinks
                        else:
                            # Linux: Remove symlink
                            os.unlink(dst)
                        self.log(f"Mod {mid} decoupled from game engine.", "info")
                except Exception as e:
                    self.log(f"DECOUPLE ERROR for {mid}: {e}", "error")
        finally:
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def is_junction(self, path):
        """Helper to detect if a directory is a Windows Junction or Linux symlink."""
        if IS_WINDOWS and ctypes:
            return bool(os.path.isdir(path) and (ctypes.windll.kernel32.GetFileAttributesW(path) & 0x400))
        else:
            return os.path.islink(path)

    def get_fs_type(self, path):
        if not IS_WINDOWS or not ctypes or not path:
            return None
        try:
            drive = os.path.splitdrive(os.path.abspath(path))[0]
            if not drive:
                return None
            root = drive + "\\"
            fs_name_buf = ctypes.create_unicode_buffer(255)
            serial = ctypes.c_ulong()
            max_comp = ctypes.c_ulong()
            flags = ctypes.c_ulong()
            res = ctypes.windll.kernel32.GetVolumeInformationW(
                root,
                None,
                0,
                ctypes.byref(serial),
                ctypes.byref(max_comp),
                ctypes.byref(flags),
                fs_name_buf,
                ctypes.sizeof(fs_name_buf)
            )
            if res:
                return fs_name_buf.value
        except Exception:
            pass
        return None

    def junction_supported(self, path):
        if not IS_WINDOWS:
            return True, None
        fs = self.get_fs_type(path)
        if not fs:
            return True, None
        return (fs.upper() == "NTFS"), fs

    def resolve_deploy_mode(self, game_path, use_physical):
        if use_physical:
            return True
        if not game_path:
            messagebox.showerror("Game Path Required", "Please select your Game Installation folder so mods can be installed.")
            return None
        ok, fs = self.junction_supported(game_path)
        if ok:
            return False

        fs_name = fs if fs else "Unknown"
        msg = (
            "Your Game Path is on a filesystem that cannot create Junction links.\n\n"
            f"Detected: {fs_name}\n\n"
            "Solutions:\n"
            "• Use Physical Copy (recommended)\n"
            "• Move the game to an NTFS drive\n"
            "• Change the Mod Cache / Game Path to an NTFS drive\n\n"
            "Enable Physical Copy now?"
        )
        result = messagebox.askyesnocancel("Junctions Not Supported", msg)
        if result is None:
            self.log("Deployment cancelled by user.", "warning")
            return None
        if result:
            self.use_physical_var.set(True)
            self.save_config()
            self.log("Switched to Physical Copy mode due to non-NTFS game drive.", "warning")
            return True
        self.log("Deployment aborted: Junctions not supported on game drive.", "error")
        return None

    def remove_existing_path(self, path):
        try:
            if not os.path.lexists(path):
                return
            if IS_WINDOWS and self.is_junction(path):
                os.rmdir(path)
            elif os.path.islink(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as e:
            self.log(f"Failed to remove existing path: {path} ({e})", "warning")

    def update_all_mods(self):
        """Batch triggers SteamCMD for every out-of-date item currently in the list."""
        items = self.tree.get_children()
        if not items:
            self.log("No mods detected in cache for update.", "warning")
            return
        
        to_update = []
        for item in items:
            if "update_needed" in self.tree.item(item, "tags"):
                to_update.append(str(self.tree.item(item)['values'][1]))
        
        if not to_update:
            self.log("All mods are up to date.", "success")
            return

        game_context = self.build_game_context()
        use_physical = self.resolve_deploy_mode(game_context["game_path"], self.use_physical_var.get())
        if use_physical is None:
            return

        if not self.begin_download_batch():
            self.log("A download or update batch is already running.", "warning")
            return

        self.log(f"Initializing batch update for {len(to_update)} mods...", "info")
        self.dl_btn.config(state="disabled", text="ENGINE ACTIVE")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.progress_label.config(text="INITIALIZING...", fg=self.colors['accent'])
        self.start_task()
        threading.Thread(
            target=self.download_logic,
            args=(to_update, self.steamcmd_var.get(), self.cache_var.get(), game_context, use_physical),
            daemon=True
        ).start()

    def delete_mod_physically(self):
        """Wipes the selected mods from the SteamCMD cache and breaks any links."""
        selected = self.tree.selection()
        if not selected: return

        count = len(selected)
        if count == 1:
            mid = str(self.tree.item(selected[0])['values'][1])
            prompt_message = f"Permanently delete Mod ID {mid} from disk?"
        else:
            prompt_message = f"Permanently delete {count} selected mods from disk?"

        if messagebox.askyesno("TERMINATE ASSET(S)", prompt_message):
            mods_to_delete = [str(self.tree.item(item)['values'][1]) for item in selected]
            cache_path = self.cache_var.get()
            game_context = self.build_game_context()
            self.start_task()
            threading.Thread(
                target=self._delete_mod_worker,
                args=(mods_to_delete, cache_path, game_context),
                daemon=True
            ).start()

    def _delete_mod_worker(self, mods, cache_path, game_context):
        try:
            cache_root = self.ensure_cache_root(cache_path)
            if not self.is_safe_cache_root(cache_root):
                self.log("Refusing to delete from an unsafe cache path.", "error")
                return

            for mid in mods:
                if self.stop_event.is_set():
                    break

                link_path = os.path.join(game_context["game_path"], "mods", mid)
                if os.path.lexists(link_path):
                    try:
                        self.remove_existing_path(link_path)
                    except Exception as e:
                        self.log(f"Note: Could not remove link for {mid} during purge: {e}", "warning")

                mod_cache_path = self.build_mod_cache_path(cache_root, game_context["appid"], mid)
                try:
                    if os.path.exists(mod_cache_path):
                        self.remove_existing_path(mod_cache_path)
                        self.log(f"Asset {mid} purged from local storage.", "warning")
                except Exception as e:
                    self.log(f"Purge Error for {mid}: {e}", "error")
                
        finally:
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def update_selected_mod(self, force=False):
        """Triggers a single re-download batch via SteamCMD for the selected mods."""
        selected = self.tree.selection()
        if not selected:
            return

        game_context = self.build_game_context()
        use_physical = self.resolve_deploy_mode(game_context["game_path"], self.use_physical_var.get())
        if use_physical is None:
            return

        mod_ids = []
        for item in selected:
            mid = str(self.tree.item(item)['values'][1])
            
            if not force and "update_needed" not in self.tree.item(item, "tags"):
                self.log(f"Mod {mid} is up to date.", "info")
                continue

            mod_ids.append(mid)

        if not mod_ids:
            return

        if not self.begin_download_batch():
            self.log("A download or update batch is already running.", "warning")
            return

        self.log(f"Updating {len(mod_ids)} mod(s)...", "info")
        self.dl_btn.config(state="disabled", text="ENGINE ACTIVE")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.progress_label.config(text="INITIALIZING...", fg=self.colors['accent'])
        self.start_task()
        threading.Thread(
            target=self.download_logic,
            args=(mod_ids, self.steamcmd_var.get(), self.cache_var.get(), game_context, use_physical),
            daemon=True
        ).start()
if __name__ == "__main__":
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = BZModMaster(root)
    root.mainloop()
