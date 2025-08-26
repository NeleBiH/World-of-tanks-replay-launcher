#!/usr/bin/env python3
#
# World of Tanks Replay Player (Linux/Wine only)
#
# This script implements a PyQt6 graphical interface for discovering and
# playing World of Tanks replay files on Linux.  It searches your home
# directory and common installation paths for World of Tanks executables,
# enumerates `.wotreplay` files, and lets you filter and launch them using
# Wine.  Each replay file is assigned a unique numeric identifier that is
# persisted across sessions in a hidden JSON file in your home directory
# (``~/.wotreplay_player_index.json``).  This allows you to refer back to
# specific replays by number and ensures numbering remains stable.  The
# interface exposes a search field, sortable list of replays with
# separators and numbering, and a drop area where you can drag & drop a
# `.wotreplay` file to run it immediately.  Proton support has been
# removed; only Wine is used to start replays.
#
# To install and run this application you need:
#
#   * Python 3.x
#   * PyQt6 (install with ``pip install PyQt6``)
#   * Wine installed and available in your PATH (check with ``wine --version``)
#
# Save this script as ``test.py`` and run it with ``python test.py``.
# The window will open, automatically search for WOT installations,
# enumerate your replay files and allow you to launch them.
import sys
import os
import subprocess
import glob
import struct
import json
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFileDialog,
    QComboBox,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QSplitter,
    QScrollArea,
    QFrame,
    QPlainTextEdit,
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush

# -----------------------------------------------------------------------------
# Global application style
#
# We apply a dark, World of Tanks–inspired colour palette to the entire
# application to give it a cohesive look and feel.  Colours were taken from
# community palette references on colour-hex.com and translated into a CSS-like
# string that Qt understands.
# -----------------------------------------------------------------------------
APP_STYLE = """
/* Main window and general widget styling */
QMainWindow {
    background-color: #1e1e1e;
    color: #d0d0d0;
}
QWidget {
    color: #d0d0d0;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #45596f;
    border-radius: 5px;
    margin-top: 6px;
    padding: 6px;
}
QGroupBox::title {
    color: #95504d;
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 3px;
}
QLabel {
    color: #d0d0d0;
}
/* Buttons */
QPushButton {
    background-color: #45596f;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 6px 10px;
}
QPushButton:hover {
    background-color: #566f88;
}
QPushButton:pressed {
    background-color: #314562;
}
/* Input fields and combo boxes */
QLineEdit, QComboBox {
    background-color: #6f6f6f;
    color: #ffffff;
    border: 1px solid #45596f;
    border-radius: 3px;
    padding: 4px;
}
QComboBox::drop-down {
    border: none;
}
QListWidget {
    background-color: #363636;
    color: #d0d0d0;
    border: 1px solid #45596f;
    border-radius: 3px;
}
QScrollBar:vertical {
    background: #1e1e1e;
}
/* Add a subtle separation line and padding for each list item */
QListWidget::item {
    border-bottom: 1px solid #45596f;
    padding: 2px;
}
"""


class ReplayInfo:
    """Class for storing information about a replay file.

    Each instance of :class:`ReplayInfo` represents a single `.wotreplay` on disk
    and attempts to extract basic metadata from the file header.  Even if
    parsing fails, the object still keeps minimal file attributes like name
    and timestamps so that entries can be sorted and displayed.
    """

    def __init__(self, file_path):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        self.date_created = datetime.fromtimestamp(os.path.getctime(file_path)) if os.path.exists(file_path) else None
        self.date_modified = datetime.fromtimestamp(os.path.getmtime(file_path)) if os.path.exists(file_path) else None

        # Attempt to read metadata from the replay file header
        self.battle_time = None
        self.player_name = None
        self.tank_name = None
        self.map_name = None
        # We no longer parse or display the battle outcome (Victory/Defeat)
        # because reliably reading that information requires up‑to‑date
        # metadata keys which may change between game versions.  Keep the
        # attribute around for potential future use but default to ``None``.
        self.battle_result = None

        self._parse_replay_metadata()

    def _parse_replay_metadata(self):
        """Parse metadata out of a `.wotreplay` file.

        The World of Tanks replay format contains one or two JSON blocks at
        the beginning of the file.  The first 4 bytes indicate the length of
        the JSON that follows.  This method reads those blocks, decodes them
        as UTF-8 and extracts interesting keys such as date/time, player name,
        vehicle and map.  If any step fails, the object falls back to file
        attributes only.
        """
        try:
            with open(self.file_path, 'rb') as f:
                # WOT replay format: first 4 bytes indicate length of the JSON block
                json_length = struct.unpack('<I', f.read(4))[0]
                if 0 < json_length < 100000:  # Reasonable length guard
                    json_data = f.read(json_length).decode('utf-8', errors='ignore')
                    metadata = json.loads(json_data)

                    # Extract information from keys if present
                    if 'dateTime' in metadata:
                        self.battle_time = datetime.fromtimestamp(metadata['dateTime'])
                    if 'playerName' in metadata:
                        self.player_name = metadata['playerName']
                    if 'vehicleType' in metadata:
                        self.tank_name = metadata['vehicleType']
                    if 'mapName' in metadata:
                        self.map_name = metadata['mapName']
                    # Note: we deliberately do not parse or store the battle result here.
                    # Replay metadata often lacks enough information to reliably determine
                    # the outcome without an API/SDK, so self.battle_result remains None.

        except Exception:
            # If parsing fails, fall back to basic file info
            pass

    def get_display_text(self):
        """Return a human‑readable label for display in the list.

        The label includes the file name and selected metadata such as the
        battle date/time, player name, vehicle and map.  We deliberately
        omit any victory/defeat marker because replay files do not reliably
        encode that information without API support.
        """
        date_str = self.battle_time.strftime("%Y-%m-%d %H:%M") if self.battle_time else self.date_modified.strftime(
            "%Y-%m-%d %H:%M")

        info_parts = [f"📅 {date_str}"]

        if self.player_name:
            info_parts.append(f"👤 {self.player_name}")
        if self.tank_name:
            info_parts.append(f"🚗 {self.tank_name}")
        if self.map_name:
            info_parts.append(f"🗺️ {self.map_name}")

        # Do not append battle result; victory/defeat filtering is disabled.

        return f"{self.file_name}\n{' | '.join(info_parts)}"

    def get_sort_date(self):
        """Return the timestamp used for sorting (prefers battle time if available)."""
        return self.battle_time if self.battle_time else self.date_modified


class ReplaySearchThread(QThread):
    """Background thread that scans the file system for `.wotreplay` files."""
    replay_found = pyqtSignal(object)  # Emits a ReplayInfo object
    search_complete = pyqtSignal()
    progress_update = pyqtSignal(str)

    def __init__(self, wot_path):
        super().__init__()
        self.wot_path = wot_path
        self._stop_requested = False

    def stop(self):
        """Request that the search thread stop as soon as possible."""
        self._stop_requested = True

    def run(self):
        """Search for replay files within the WOT directory.

        The method iterates through a set of candidate directories and yields
        `ReplayInfo` objects for each `.wotreplay` it finds.  It emits
        progress signals along the way and finishes gracefully if the
        `_stop_requested` flag is set.
        """
        if not self.wot_path or self._stop_requested:
            self.search_complete.emit()
            return

        wot_dir = os.path.dirname(self.wot_path)
        replay_paths = []

        # Common directories to search for replay files
        replay_dirs = [
            os.path.join(wot_dir, "replays"),
            os.path.join(wot_dir, "replay"),
            os.path.join(wot_dir, "..", "replays"),
            os.path.join(wot_dir, "..", "replay"),
            wot_dir,
            os.path.expanduser("~/Documents/World of Tanks/replays"),
            os.path.expanduser("~/Downloads")
        ]

        self.progress_update.emit("Searching for replay files...")

        for replay_dir in replay_dirs:
            if self._stop_requested:
                return

            if os.path.exists(replay_dir):
                self.progress_update.emit(f"Searching: {replay_dir}")
                pattern = os.path.join(replay_dir, "*.wotreplay")
                found_files = glob.glob(pattern)

                # Recursively walk the directory tree to catch any nested replays
                for root, dirs, files in os.walk(replay_dir):
                    if self._stop_requested:
                        return

                    for file in files:
                        if self._stop_requested:
                            return

                        if file.lower().endswith('.wotreplay'):
                            full_path = os.path.join(root, file)
                            if full_path not in found_files:
                                found_files.append(full_path)

                replay_paths.extend(found_files)

        if self._stop_requested:
            return

        # Remove duplicates
        replay_paths = list(set(replay_paths))

        self.progress_update.emit(f"Found {len(replay_paths)} replay files, analysing...")

        for i, replay_path in enumerate(replay_paths):
            if self._stop_requested:
                return

            try:
                replay_info = ReplayInfo(replay_path)
                self.replay_found.emit(replay_info)

                if i % 10 == 0:  # Update progress every 10 files
                    self.progress_update.emit(f"Analysed {i + 1}/{len(replay_paths)} files...")

            except Exception as e:
                continue

        if not self._stop_requested:
            self.search_complete.emit()


class WOTSearchThread(QThread):
    """Background thread that searches for installed WOT game clients."""
    found_installation = pyqtSignal(str, str)  # path, region
    search_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._stop_requested = False

    def stop(self):
        """Request the thread to stop as soon as possible."""
        self._stop_requested = True

    def run(self):
        if self._stop_requested:
            return

        installations = self.find_wot_installations()
        for path, region in installations:
            if self._stop_requested:
                return
            self.found_installation.emit(path, region)

        if not self._stop_requested:
            self.search_complete.emit()

    def find_wot_installations(self):
        """Find all World of Tanks installations on the system.

        Searches a set of common directories as well as Steam Proton prefixes
        for possible game executables.  Returns a list of tuples of the form
        `(executable_path, region_description)`.
        """
        installations: list[tuple[str, str]] = []

        if self._stop_requested:
            return installations

        # Standard installation locations to probe
        common_paths = [
            "/home/games",
            os.path.expanduser("~/.local/share/Steam/steamapps/common/World of Tanks"),
            os.path.expanduser("~/.steam/steam/steamapps/common/World of Tanks"),
            os.path.expanduser("~/Games/World of Tanks"),
            "/opt/World of Tanks",
            "/usr/local/games/World of Tanks"
        ]

        # Steam Proton installation prefixes
        steam_proton_paths = [
            os.path.expanduser("~/.local/share/Steam/steamapps/compatdata/*/pfx/drive_c/Games/World_of_Tanks*"),
            os.path.expanduser("~/.steam/steam/steamapps/compatdata/*/pfx/drive_c/Games/World_of_Tanks*")
        ]

        # Search standard locations
        for base_path in common_paths:
            if self._stop_requested:
                return installations

            if os.path.exists(base_path):
                # Regional versions (EU/NA/Asia/RU)
                regions = {
                    'eu': ['eu', 'europe'],
                    'na': ['na', 'north_america', 'us'],
                    'asia': ['asia', 'sea'],
                    'ru': ['ru', 'russia', 'cis']
                }

                for region, variants in regions.items():
                    if self._stop_requested:
                        return installations

                    for variant in variants:
                        if self._stop_requested:
                            return installations

                        region_path = os.path.join(base_path, variant)
                        if os.path.exists(region_path):
                            wot_exe = self.find_executable(region_path)
                            if wot_exe:
                                installations.append((wot_exe, f"{region.upper()} ({variant})"))

                # Check directly in the base_path
                wot_exe = self.find_executable(base_path)
                if wot_exe:
                    # If no regional variant matched, classify as an unknown region
                    installations.append((wot_exe, "Unknown region"))

        # Search Steam Proton locations
        for pattern in steam_proton_paths:
            if self._stop_requested:
                return installations

            for path in glob.glob(pattern):
                if self._stop_requested:
                    return installations

                wot_exe = self.find_executable(path)
                if wot_exe:
                    # Note: paths found within Proton prefixes are still valid
                    # Windows executables.  Since Proton support is removed,
                    # these are labelled accordingly and will be run with Wine.
                    installations.append((wot_exe, "Proton prefix (run with Wine)"))

        return installations

    def find_executable(self, path):
        """Find the WOT executable within a given directory.

        Walks the directory tree looking for one of the well‑known executable
        names.  Returns the full path to the executable or ``None`` if not found.
        """
        if not os.path.exists(path):
            return None

        # Possible names of the game executable on Windows
        exe_names = [
            "WorldOfTanks.exe",
            "WorldOfTanksLauncher.exe",
            "wot.exe",
            "WoT.exe"
        ]

        for exe_name in exe_names:
            exe_path = os.path.join(path, exe_name)
            if os.path.exists(exe_path):
                return exe_path

        # Recursively search for executables lower in the tree
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower() in [name.lower() for name in exe_names]:
                    return os.path.join(root, file)

        return None


class MainWindow(QMainWindow):
    """Main application window.

    Handles all user interface components, thread management, drag‑and‑drop and
    replay playback.  UI strings are in English and the look & feel is
    customised via a dark palette defined at the top of this module.
    """

    def __init__(self) -> None:
        super().__init__()
        # Window title and geometry
        self.setWindowTitle("World of Tanks Replay Player - PyQt6 Extended")
        self.setGeometry(100, 100, 1200, 700)

        # Allow drag‑and‑drop of replay files onto the window
        self.setAcceptDrops(True)

        # Runtime state
        self.executable_path: str = ""
        # Proton support removed; always use Wine
        self.found_installations: list[tuple[str, str]] = []
        self.replay_list: list[ReplayInfo] = []
        self.filtered_replay_list: list[ReplayInfo] = []

        # Worker thread references
        self.search_thread: WOTSearchThread | None = None
        self.replay_search_thread: ReplaySearchThread | None = None

        # Mapping from absolute replay file paths to persistent numeric indices.
        # These indices are loaded from and saved to a hidden JSON file in
        # the user's home directory.  They allow replays to retain the same
        # number across application restarts.
        self.index_mapping: dict[str, int] = {}
        self.load_index_mapping()

        # Build UI and start auto discovery
        self.init_ui()
        self.start_auto_search()

    def closeEvent(self, event) -> None:
        """Cleanly stop worker threads when the window is closing."""
        self.log("Closing application...")

        # Gracefully stop and clean up the WOT installation search thread
        if self.search_thread:
            try:
                self.search_thread.stop()
                self.search_thread.quit()
                self.search_thread.wait(3000)
            except RuntimeError:
                # Thread might already be deleted; ignore
                pass
            self.search_thread = None

        # Gracefully stop and clean up the replay search thread
        if self.replay_search_thread:
            try:
                self.replay_search_thread.stop()
                self.replay_search_thread.quit()
                self.replay_search_thread.wait(3000)
            except RuntimeError:
                # Thread might already be deleted; ignore
                pass
            self.replay_search_thread = None

        event.accept()

    def init_ui(self) -> None:
        """Initialise all widgets and layouts for the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main splitter (left/right panes)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        central_widget_layout = QHBoxLayout()
        central_widget_layout.addWidget(main_splitter)
        central_widget.setLayout(central_widget_layout)

        # Left side – controls
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)

        # Group for automatic search of WOT installations
        auto_search_group = QGroupBox("Automatic search for WOT installations")
        auto_search_layout = QVBoxLayout()
        auto_search_group.setLayout(auto_search_layout)

        self.search_status = QLabel("Searching for WOT installations...")
        self.search_status.setStyleSheet("color: blue; font-weight: bold;")
        auto_search_layout.addWidget(self.search_status)

        self.installations_combo = QComboBox()
        self.installations_combo.addItem("No installation found")
        self.installations_combo.currentTextChanged.connect(self.on_installation_selected)
        auto_search_layout.addWidget(QLabel("Found installations:"))
        auto_search_layout.addWidget(self.installations_combo)

        left_layout.addWidget(auto_search_group)

        # Group for manual selection
        manual_group = QGroupBox("Manual executable selection")
        manual_layout = QVBoxLayout()
        manual_group.setLayout(manual_layout)

        self.select_executable_button = QPushButton("Choose WOT executable manually")
        self.select_executable_button.clicked.connect(self.select_executable)
        manual_layout.addWidget(self.select_executable_button)

        left_layout.addWidget(manual_group)

        # No launch options are exposed in the UI.  Replay playback always
        # uses Wine, so there is no need for an empty "Launch options" group.

        # Status and feedback
        self.feedback_label = QLabel("No executable selected.")
        self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
        self.feedback_label.setWordWrap(True)
        left_layout.addWidget(self.feedback_label)

        # Buttons for actions
        button_layout = QHBoxLayout()

        self.play_replay_button = QPushButton("Play Replay")
        self.play_replay_button.clicked.connect(self.play_selected_replay)
        self.play_replay_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3e8e41;
            }
        """)

        self.refresh_button = QPushButton("Refresh search")
        self.refresh_button.clicked.connect(self.start_auto_search)
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)

        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.play_replay_button)
        left_layout.addLayout(button_layout)

        # Log area: use QPlainTextEdit for efficiency and append-only logging
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        # Initialize with a startup message
        self.log_area.appendPlainText("Program started. Searching for WOT installations...")
        left_layout.addWidget(QLabel("Log:"))
        left_layout.addWidget(self.log_area)

        # Right side – replay list
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)

        # Drop area: visually indicate where users can drop a replay file.
        # Dropping on this label will trigger the global drop event handler on
        # the window, which launches the replay with Wine.  The dashed border
        # and colour hint come from the WoT palette defined above.
        self.drop_label = QLabel("⬇️  Drop replay file here to run")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet(
            "border: 2px dashed #95504d; color: #95504d; padding: 20px; margin: 5px;"
        )
        right_layout.addWidget(self.drop_label)

        # Group for replay files
        replay_group = QGroupBox("Replay files")
        replay_layout = QVBoxLayout()
        replay_group.setLayout(replay_layout)

        # Search field
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Search:"))
        self.replay_search = QLineEdit()
        self.replay_search.setPlaceholderText("Search replay files...")
        self.replay_search.textChanged.connect(self.filter_replays)
        search_layout.addWidget(self.replay_search)

        self.refresh_replays_button = QPushButton("Refresh replays")
        self.refresh_replays_button.clicked.connect(self.refresh_replay_list)
        self.refresh_replays_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        search_layout.addWidget(self.refresh_replays_button)
        replay_layout.addLayout(search_layout)

        # Replay status label
        self.replay_status = QLabel("Waiting for WOT installation...")
        self.replay_status.setStyleSheet("color: gray; font-style: italic;")
        replay_layout.addWidget(self.replay_status)

        # Replay list
        self.replay_list_widget = QListWidget()
        # Add a small spacing between items; combined with the CSS border this gives
        # each entry a clear separation line.
        self.replay_list_widget.setSpacing(2)
        self.replay_list_widget.itemDoubleClicked.connect(self.on_replay_double_click)
        self.replay_list_widget.itemClicked.connect(self.on_replay_click)
        replay_layout.addWidget(self.replay_list_widget)

        right_layout.addWidget(replay_group)

        # Add the left and right widgets to the splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)

        # Set initial sizes: left 40%, right 60%
        main_splitter.setSizes([480, 720])
        # Give the right panel a stretch factor so it expands more than the left
        main_splitter.setStretchFactor(1, 1)

    def start_auto_search(self):
        """Start automatic discovery of installed WOT executables."""
        # Stop any existing search thread cleanly.  Do not call isRunning() on a
        # potentially deleted object, just attempt to stop/quit/wait and ignore
        # RuntimeError if the underlying C++ object is already gone.
        if self.search_thread:
            try:
                self.search_thread.stop()
                self.search_thread.quit()
                self.search_thread.wait()
            except RuntimeError:
                # Thread may already have been deleted; ignore
                pass
            self.search_thread = None

        # Update UI status
        self.search_status.setText("Searching for WOT installations...")
        self.search_status.setStyleSheet("color: blue; font-weight: bold;")
        self.installations_combo.clear()
        self.installations_combo.addItem("Searching...")
        self.found_installations = []

        # Launch a new search thread
        thread = WOTSearchThread()
        thread.found_installation.connect(self.add_installation)
        thread.search_complete.connect(self.search_finished)
        # When the thread finishes, set our reference to None so we don't refer to deleted objects
        def on_finished():
            self.search_thread = None
        thread.finished.connect(on_finished)
        self.search_thread = thread
        thread.start()

    def add_installation(self, path, region):
        """Append a discovered installation to our internal list and log it."""
        self.found_installations.append((path, region))
        self.log(f"Discovered installation: {region} - {path}")

    def search_finished(self):
        """Called when WOT installation search completes; update the UI."""
        self.installations_combo.clear()

        if self.found_installations:
            count = len(self.found_installations)
            self.search_status.setText(f"Found {count} installation{'s' if count != 1 else ''}")
            self.search_status.setStyleSheet("color: green; font-weight: bold;")

            for path, region in self.found_installations:
                self.installations_combo.addItem(f"{region} - {path}")

            # Automatically select the first installation
            if self.found_installations:
                self.executable_path = self.found_installations[0][0]
                self.update_feedback()
                self.refresh_replay_list()
        else:
            self.search_status.setText("No WOT installation was found")
            self.search_status.setStyleSheet("color: red; font-weight: bold;")
            self.installations_combo.addItem("No installation found")
            self.log("No WOT installation was automatically found. Please use manual selection.")

    def on_installation_selected(self, text):
        """Called when the user selects an installation from the combo box."""
        if " - " in text and self.found_installations:
            for path, region in self.found_installations:
                if text == f"{region} - {path}":
                    self.executable_path = path
                    self.update_feedback()
                    self.refresh_replay_list()
                    break

    def select_executable(self):
        """Let the user choose a game executable manually."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose World of Tanks executable",
            os.path.expanduser("~"),
            "Executable files (*.exe);;All files (*)"
        )

        if file_path:
            self.executable_path = file_path
            self.update_feedback()
            self.refresh_replay_list()
            self.log(f"Manually selected executable: {file_path}")

    def refresh_replay_list(self):
        """Refresh the list of replay files based on the current executable."""
        if not self.executable_path:
            self.replay_status.setText("No WOT executable selected")
            return

        # Stop any existing replay search thread cleanly.  Avoid calling
        # isRunning() on a deleted thread object; attempt to stop/quit/wait
        # directly and handle any RuntimeError.
        if self.replay_search_thread:
            try:
                self.replay_search_thread.stop()
                self.replay_search_thread.quit()
                self.replay_search_thread.wait()
            except RuntimeError:
                pass
            self.replay_search_thread = None

        self.replay_status.setText("Searching replay files...")
        self.replay_list_widget.clear()
        self.replay_list = []

        thread = ReplaySearchThread(self.executable_path)
        thread.replay_found.connect(self.add_replay_to_list)
        thread.search_complete.connect(self.replay_search_finished)
        thread.progress_update.connect(self.update_replay_status)
        def on_finished():
            self.replay_search_thread = None
        thread.finished.connect(on_finished)
        self.replay_search_thread = thread
        thread.start()

    def add_replay_to_list(self, replay_info):
        """Append a found replay to the internal list."""
        self.replay_list.append(replay_info)

    def replay_search_finished(self):
        """Handle completion of replay file search."""
        # Sort by date descending (newest first)
        self.replay_list.sort(key=lambda x: x.get_sort_date(), reverse=True)

        # Assign persistent indices to each replay before filtering/display
        self.assign_indices()

        self.filtered_replay_list = self.replay_list.copy()
        self.update_replay_display()

        count = len(self.replay_list)
        self.replay_status.setText(f"Found {count} replay file{'s' if count != 1 else ''}")
        if count == 0:
            self.replay_status.setStyleSheet("color: orange;")
        else:
            self.replay_status.setStyleSheet("color: green;")

        self.log(f"Found {count} replay file{'s' if count != 1 else ''}")

    def update_replay_status(self, message):
        """Update the status label for the replay search process."""
        self.replay_status.setText(message)

    def update_replay_display(self):
        """Refresh the display of replay items in the list widget."""
        self.replay_list_widget.clear()

        for replay_info in self.filtered_replay_list:
            # Compose a label that starts with the persistent index in brackets.
            index_str = ''
            if hasattr(replay_info, 'index') and replay_info.index is not None:
                index_str = f"[{replay_info.index}] "
            label = index_str + replay_info.get_display_text()
            # Create the list item with display text and store the ReplayInfo object
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, replay_info)
            # Items are not coloured by outcome; we rely on separation lines to improve readability.
            self.replay_list_widget.addItem(item)

    def filter_replays(self):
        """Filter the replay list based on the search text."""
        search_text = self.replay_search.text().lower()

        if not search_text:
            self.filtered_replay_list = self.replay_list.copy()
        else:
            self.filtered_replay_list = []
            for replay_info in self.replay_list:
                # Search within file name, player name, tank name and map name
                if (search_text in replay_info.file_name.lower() or
                        (replay_info.player_name and search_text in replay_info.player_name.lower()) or
                        (replay_info.tank_name and search_text in replay_info.tank_name.lower()) or
                        (replay_info.map_name and search_text in replay_info.map_name.lower())):
                    self.filtered_replay_list.append(replay_info)

        self.update_replay_display()

    def on_replay_click(self, item):
        """Called when the user single‑clicks a replay in the list."""
        replay_info = item.data(Qt.ItemDataRole.UserRole)
        if replay_info:
            self.log(f"Selected replay: {replay_info.file_name}")

    def on_replay_double_click(self, item):
        """Called when the user double‑clicks a replay entry to play it."""
        replay_info = item.data(Qt.ItemDataRole.UserRole)
        if replay_info:
            self.play_replay_file(replay_info.file_path)

    def play_selected_replay(self):
        """Play the currently selected replay, or open a file dialog if none is selected."""
        current_item = self.replay_list_widget.currentItem()
        if current_item:
            replay_info = current_item.data(Qt.ItemDataRole.UserRole)
            if replay_info:
                self.play_replay_file(replay_info.file_path)
                return

        # If no replay is selected, open a file dialog to choose one
        self.play_replay()


    def update_feedback(self):
        """Update the feedback label with the current executable and mode."""
        if self.executable_path:
            # Always show Wine as the launch mode since Proton support is removed
            mode = "Wine"
            self.feedback_label.setText(
                f"✅ Selected executable: {self.executable_path}\n"
                f"🚀 Launch mode: {mode}"
            )
            self.feedback_label.setStyleSheet("color: green; font-weight: bold; padding: 10px;")
        else:
            self.feedback_label.setText("❌ No executable selected.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

    def play_replay(self):
        """Open a file dialog and play the selected replay."""
        if not self.executable_path:
            self.feedback_label.setText("❌ Please select an executable first.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            return

        # Let user choose a replay file
        replay_file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose replay file",
            os.path.expanduser("~/Downloads"),
            "WOT replay files (*.wotreplay);;All files (*)"
        )

        if replay_file_path:
            self.play_replay_file(replay_file_path)

    def play_replay_file(self, replay_file_path):
        """Launch a specific replay file using Wine.  Proton is no longer supported."""
        if not self.executable_path:
            self.feedback_label.setText("❌ Please select an executable first.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            return

        if not replay_file_path:
            self.log("No replay file selected.")
            return

        if not replay_file_path.lower().endswith(".wotreplay"):
            self.feedback_label.setText("❌ Please select a valid .wotreplay file.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            return

        self.log(f"Attempting to launch replay: {replay_file_path}")

        try:
            # Always use Wine to launch, since Proton support is removed
            success = self.run_with_wine(replay_file_path)

            if success:
                self.feedback_label.setText(f"✅ Launched replay: {os.path.basename(replay_file_path)}")
                self.feedback_label.setStyleSheet("color: green; font-weight: bold; padding: 10px;")
            else:
                self.feedback_label.setText("❌ Error launching replay.")
                self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

        except Exception as e:
            err_msg = str(e)
            self.log(f"Error: {err_msg}")
            self.feedback_label.setText(f"❌ Error: {err_msg}")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

    # run_with_proton has been removed because Proton support is no longer provided.

    def run_with_wine(self, replay_file):
        """Launch the replay using Wine."""
        self.log("Launching with Wine...")

        # Construct the Wine command
        cmd = ["wine", self.executable_path, replay_file]

        self.log(f"Executing: {' '.join(cmd)}")

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log("Replay started with Wine.")
            return True
        except Exception as e:
            err_msg = f"Error with Wine: {e}.\nCheck if Wine is installed: wine --version"
            self.log(err_msg)
            self.feedback_label.setText(f"❌ {err_msg}")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            return False

    # find_steam_path removed; Steam/Proton support is not needed when using Wine

    def log(self, message):
        """Append a message to the log area and scroll to the bottom."""
        # Append the new message and scroll to the bottom
        self.log_area.appendPlainText(message)
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ---------------------------------------------------------------------
    # Persistent replay index handling
    # ---------------------------------------------------------------------
    def load_index_mapping(self) -> None:
        """Load the replay index mapping from a hidden JSON file.

        The index mapping assigns a unique integer to each replay file path
        (absolute path).  It is stored in ``~/.wotreplay_player_index.json``
        so that numbering persists across application restarts.  If the file
        does not exist or cannot be parsed, ``index_mapping`` is left empty.
        """
        index_file = Path.home() / ".wotreplay_player_index.json"
        if index_file.exists():
            try:
                with index_file.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # ensure all values are ints
                        self.index_mapping = {str(k): int(v) for k, v in data.items()}
            except Exception as exc:
                # On any error, leave index_mapping empty but log a warning
                self.index_mapping = {}
                self.log(f"Warning: could not read index file: {exc}")

    def save_index_mapping(self) -> None:
        """Write the current index mapping back to the hidden JSON file."""
        index_file = Path.home() / ".wotreplay_player_index.json"
        try:
            with index_file.open('w', encoding='utf-8') as f:
                json.dump(self.index_mapping, f, indent=4)
        except Exception as exc:
            # If saving fails, write a warning to the log but do not stop the app
            self.log(f"Warning: could not save index file: {exc}")

    def assign_indices(self) -> None:
        """Assign persistent indices to all replays in ``self.replay_list``.

        For each replay, if its absolute path already exists in the
        ``index_mapping``, re‑use the stored index.  Otherwise assign a new
        index equal to the current maximum plus one and update the
        mapping.  After assignment, the updated mapping is saved to disk.
        Each ``ReplayInfo`` object will receive an ``index`` attribute.
        """
        # Determine the highest existing index
        max_index = max(self.index_mapping.values(), default=0)
        updated = False
        for replay_info in self.replay_list:
            abs_path = os.path.abspath(replay_info.file_path)
            idx = self.index_mapping.get(abs_path)
            if idx is None:
                max_index += 1
                idx = max_index
                self.index_mapping[abs_path] = idx
                updated = True
            # Attach the index to the object for display
            setattr(replay_info, 'index', idx)
        if updated:
            self.save_index_mapping()

    # -------------------------------------------------------------------------
    # Drag & drop handlers
    # -------------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        """Accept drag events for .wotreplay files only."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local = url.toLocalFile()
                if local.lower().endswith(".wotreplay"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:
        """Handle drop by launching the first .wotreplay file."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local = url.toLocalFile()
                if local.lower().endswith(".wotreplay"):
                    self.play_replay_file(local)
                    break
            event.acceptProposedAction()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)

    # Apply the Fusion style for a consistent look across platforms
    app.setStyle('Fusion')
    # Apply our custom dark colour palette defined at the top of this module
    app.setStyleSheet(APP_STYLE)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
