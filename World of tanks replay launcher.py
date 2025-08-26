#!/usr/bin/env python3
import sys
import os
import subprocess
import glob
import struct
import json
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel,
                             QVBoxLayout, QHBoxLayout, QWidget, QFileDialog,
                             QComboBox, QCheckBox, QTextEdit, QGroupBox,
                             QListWidget, QListWidgetItem, QLineEdit, QSplitter,
                             QScrollArea, QFrame)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFont


class ReplayInfo:
    """Klasa za čuvanje informacija o replay fajlu"""

    def __init__(self, file_path):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        self.date_created = datetime.fromtimestamp(os.path.getctime(file_path)) if os.path.exists(file_path) else None
        self.date_modified = datetime.fromtimestamp(os.path.getmtime(file_path)) if os.path.exists(file_path) else None

        # Pokušaj čitanje metapodataka iz replay fajla
        self.battle_time = None
        self.player_name = None
        self.tank_name = None
        self.map_name = None
        self.battle_result = None

        self._parse_replay_metadata()

    def _parse_replay_metadata(self):
        """Parsira metapodatke iz .wotreplay fajla"""
        try:
            with open(self.file_path, 'rb') as f:
                # WOT replay format: 4 bytes za dužinu JSON bloka, zatim JSON
                json_length = struct.unpack('<I', f.read(4))[0]
                if json_length > 0 and json_length < 100000:  # Razumna granica
                    json_data = f.read(json_length).decode('utf-8', errors='ignore')
                    metadata = json.loads(json_data)

                    # Izvuci informacije
                    if 'dateTime' in metadata:
                        self.battle_time = datetime.fromtimestamp(metadata['dateTime'])
                    if 'playerName' in metadata:
                        self.player_name = metadata['playerName']
                    if 'vehicleType' in metadata:
                        self.tank_name = metadata['vehicleType']
                    if 'mapName' in metadata:
                        self.map_name = metadata['mapName']
                    if 'winnerTeam' in metadata and 'playerTeam' in metadata:
                        self.battle_result = "Pobeda" if metadata['winnerTeam'] == metadata['playerTeam'] else "Poraz"

        except Exception as e:
            # Ako ne možemo da parsiramo, koristićemo osnovne file info
            pass

    def get_display_text(self):
        """Vraća tekst za prikaz u listi"""
        date_str = self.battle_time.strftime("%Y-%m-%d %H:%M") if self.battle_time else self.date_modified.strftime(
            "%Y-%m-%d %H:%M")

        info_parts = [f"📅 {date_str}"]

        if self.player_name:
            info_parts.append(f"👤 {self.player_name}")
        if self.tank_name:
            info_parts.append(f"🚗 {self.tank_name}")
        if self.map_name:
            info_parts.append(f"🗺️ {self.map_name}")
        if self.battle_result:
            result_icon = "🏆" if self.battle_result == "Pobeda" else "💀"
            info_parts.append(f"{result_icon} {self.battle_result}")

        return f"{self.file_name}\n{' | '.join(info_parts)}"

    def get_sort_date(self):
        """Vraća datum za sortiranje"""
        return self.battle_time if self.battle_time else self.date_modified


class ReplaySearchThread(QThread):
    """Thread za pretragu replay fajlova"""
    replay_found = pyqtSignal(object)  # ReplayInfo objekat
    search_complete = pyqtSignal()
    progress_update = pyqtSignal(str)

    def __init__(self, wot_path):
        super().__init__()
        self.wot_path = wot_path
        self._stop_requested = False

    def stop(self):
        """Zahteva zaustavljanje thread-a"""
        self._stop_requested = True

    def run(self):
        """Pretražuje replay fajlove u WOT direktorijumu"""
        if not self.wot_path or self._stop_requested:
            self.search_complete.emit()
            return

        wot_dir = os.path.dirname(self.wot_path)
        replay_paths = []

        # Česti direktorijumi za replay fajlove
        replay_dirs = [
            os.path.join(wot_dir, "replays"),
            os.path.join(wot_dir, "replay"),
            os.path.join(wot_dir, "..", "replays"),
            os.path.join(wot_dir, "..", "replay"),
            wot_dir,
            os.path.expanduser("~/Documents/World of Tanks/replays"),
            os.path.expanduser("~/Downloads")
        ]

        self.progress_update.emit("Pretražujem replay fajlove...")

        for replay_dir in replay_dirs:
            if self._stop_requested:
                return

            if os.path.exists(replay_dir):
                self.progress_update.emit(f"Pretražujem: {replay_dir}")
                pattern = os.path.join(replay_dir, "*.wotreplay")
                found_files = glob.glob(pattern)

                # Rekurzivna pretraga
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

        # Ukloni duplikate
        replay_paths = list(set(replay_paths))

        self.progress_update.emit(f"Pronađeno {len(replay_paths)} replay fajlova, analiziram...")

        for i, replay_path in enumerate(replay_paths):
            if self._stop_requested:
                return

            try:
                replay_info = ReplayInfo(replay_path)
                self.replay_found.emit(replay_info)

                if i % 10 == 0:  # Update progress svakih 10 fajlova
                    self.progress_update.emit(f"Analizirano {i + 1}/{len(replay_paths)} fajlova...")

            except Exception as e:
                continue

        if not self._stop_requested:
            self.search_complete.emit()


class WOTSearchThread(QThread):
    """Thread za pretraživanje WOT instalacija u pozadini"""
    found_installation = pyqtSignal(str, str)  # path, region
    search_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._stop_requested = False

    def stop(self):
        """Zahteva zaustavljanje thread-a"""
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
        """Pronalazi sve WOT instalacije na sistemu"""
        installations = []

        if self._stop_requested:
            return installations

        # Standardne lokacije
        common_paths = [
            "/home/games",
            os.path.expanduser("~/.local/share/Steam/steamapps/common/World of Tanks"),
            os.path.expanduser("~/.steam/steam/steamapps/common/World of Tanks"),
            os.path.expanduser("~/Games/World of Tanks"),
            "/opt/World of Tanks",
            "/usr/local/games/World of Tanks"
        ]

        # Steam Proton lokacije
        steam_proton_paths = [
            os.path.expanduser("~/.local/share/Steam/steamapps/compatdata/*/pfx/drive_c/Games/World_of_Tanks*"),
            os.path.expanduser("~/.steam/steam/steamapps/compatdata/*/pfx/drive_c/Games/World_of_Tanks*")
        ]

        # Pretraga standardnih lokacija
        for base_path in common_paths:
            if self._stop_requested:
                return installations

            if os.path.exists(base_path):
                # Regionalne verzije
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

                # Direktno u base_path
                wot_exe = self.find_executable(base_path)
                if wot_exe:
                    installations.append((wot_exe, "Nepoznata regija"))

        # Pretraga Steam Proton lokacija
        for pattern in steam_proton_paths:
            if self._stop_requested:
                return installations

            for path in glob.glob(pattern):
                if self._stop_requested:
                    return installations

                wot_exe = self.find_executable(path)
                if wot_exe:
                    installations.append((wot_exe, "Steam Proton"))

        return installations

    def find_executable(self, path):
        """Pronalazi WorldOfTanks.exe u datom direktorijumu"""
        if not os.path.exists(path):
            return None

        # Moguća imena executable fajlova
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

        # Rekurzivna pretraga
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower() in [name.lower() for name in exe_names]:
                    return os.path.join(root, file)

        return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("World of Tanks Replay Player - PyQt6 Extended")
        self.setGeometry(100, 100, 1200, 700)

        self.executable_path = ""
        self.use_proton = False
        self.found_installations = []
        self.replay_list = []
        self.filtered_replay_list = []

        # Thread objekti
        self.search_thread = None
        self.replay_search_thread = None

        self.init_ui()
        self.start_auto_search()

    def closeEvent(self, event):
        """Pravilno zatvaranje thread-ova kada se prozor zatvara"""
        self.log("Zatvaranje aplikacije...")

        # Zaustavi i sačekaj da se završe thread-ovi
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.stop()
            self.search_thread.quit()
            self.search_thread.wait(3000)  # Sačekaj maksimalno 3 sekunde
            if self.search_thread.isRunning():
                self.search_thread.terminate()

        if self.replay_search_thread and self.replay_search_thread.isRunning():
            self.replay_search_thread.stop()
            self.replay_search_thread.quit()
            self.replay_search_thread.wait(3000)  # Sačekaj maksimalno 3 sekunde
            if self.replay_search_thread.isRunning():
                self.replay_search_thread.terminate()

        event.accept()

    def init_ui(self):
        """Inicijalizuje korisničku površinu"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Glavni splitter (levo/desno)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        central_widget_layout = QHBoxLayout()
        central_widget_layout.addWidget(main_splitter)
        central_widget.setLayout(central_widget_layout)

        # Leva strana - kontrole
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)

        # Grupa za auto pretragu
        auto_search_group = QGroupBox("Automatska pretraga WOT instalacija")
        auto_search_layout = QVBoxLayout()
        auto_search_group.setLayout(auto_search_layout)

        self.search_status = QLabel("Pretražujem WOT instalacije...")
        self.search_status.setStyleSheet("color: blue; font-weight: bold;")
        auto_search_layout.addWidget(self.search_status)

        self.installations_combo = QComboBox()
        self.installations_combo.addItem("Nijedna instalacija pronađena")
        self.installations_combo.currentTextChanged.connect(self.on_installation_selected)
        auto_search_layout.addWidget(QLabel("Pronađene instalacije:"))
        auto_search_layout.addWidget(self.installations_combo)

        left_layout.addWidget(auto_search_group)

        # Grupa za ručni izbor
        manual_group = QGroupBox("Ručni izbor executable")
        manual_layout = QVBoxLayout()
        manual_group.setLayout(manual_layout)

        self.select_executable_button = QPushButton("Izaberi WOT Executable ručno")
        self.select_executable_button.clicked.connect(self.select_executable)
        manual_layout.addWidget(self.select_executable_button)

        left_layout.addWidget(manual_group)

        # Opcije za pokretanje
        options_group = QGroupBox("Opcije pokretanja")
        options_layout = QVBoxLayout()
        options_group.setLayout(options_layout)

        self.proton_checkbox = QCheckBox("Koristi Steam Proton umesto Wine")
        self.proton_checkbox.toggled.connect(self.toggle_proton)
        options_layout.addWidget(self.proton_checkbox)

        left_layout.addWidget(options_group)

        # Status i kontrole
        self.feedback_label = QLabel("Nijedan executable nije izabran.")
        self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
        self.feedback_label.setWordWrap(True)
        left_layout.addWidget(self.feedback_label)

        # Dugmad
        button_layout = QHBoxLayout()

        self.play_replay_button = QPushButton("Pokreni Replay")
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

        self.refresh_button = QPushButton("Osveži pretragu")
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

        # Log oblast
        self.log_area = QTextEdit()
        self.log_area.setMaximumHeight(150)
        self.log_area.setPlainText("Program pokrenut. Pretražujem WOT instalacije...")
        left_layout.addWidget(QLabel("Log:"))
        left_layout.addWidget(self.log_area)

        # Desna strana - replay lista
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)

        # Replay grupa
        replay_group = QGroupBox("Replay Fajlovi")
        replay_layout = QVBoxLayout()
        replay_group.setLayout(replay_layout)

        # Search polje
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Pretraga:"))
        self.replay_search = QLineEdit()
        self.replay_search.setPlaceholderText("Pretraži replay fajlove...")
        self.replay_search.textChanged.connect(self.filter_replays)
        search_layout.addWidget(self.replay_search)

        self.refresh_replays_button = QPushButton("Osveži Replay")
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

        # Replay status
        self.replay_status = QLabel("Čekam WOT instalaciju...")
        self.replay_status.setStyleSheet("color: gray; font-style: italic;")
        replay_layout.addWidget(self.replay_status)

        # Replay lista
        self.replay_list_widget = QListWidget()
        self.replay_list_widget.itemDoubleClicked.connect(self.on_replay_double_click)
        self.replay_list_widget.itemClicked.connect(self.on_replay_click)
        replay_layout.addWidget(self.replay_list_widget)

        right_layout.addWidget(replay_group)

        # Dodaj widgete u splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)

        # Podesi veličine splitter-a (levo 40%, desno 60%)
        main_splitter.setSizes([480, 720])

    def start_auto_search(self):
        """Pokreće automatsku pretragu WOT instalacija"""
        # Zaustavi postojeći thread ako radi
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.quit()
            self.search_thread.wait()

        self.search_status.setText("Pretražujem WOT instalacije...")
        self.search_status.setStyleSheet("color: blue; font-weight: bold;")
        self.installations_combo.clear()
        self.installations_combo.addItem("Pretraga u toku...")
        self.found_installations = []

        self.search_thread = WOTSearchThread()
        self.search_thread.found_installation.connect(self.add_installation)
        self.search_thread.search_complete.connect(self.search_finished)
        self.search_thread.finished.connect(self.search_thread.deleteLater)  # Automatsko brisanje
        self.search_thread.start()

    def add_installation(self, path, region):
        """Dodaje pronađenu instalaciju u listu"""
        self.found_installations.append((path, region))
        self.log(f"Pronađena instalacija: {region} - {path}")

    def search_finished(self):
        """Završava pretragu i ažurira UI"""
        self.installations_combo.clear()

        if self.found_installations:
            self.search_status.setText(f"Pronađeno {len(self.found_installations)} instalacija")
            self.search_status.setStyleSheet("color: green; font-weight: bold;")

            for path, region in self.found_installations:
                self.installations_combo.addItem(f"{region} - {path}")

            # Automatski izaberi prvu instalaciju
            if self.found_installations:
                self.executable_path = self.found_installations[0][0]
                self.update_feedback()
                self.refresh_replay_list()
        else:
            self.search_status.setText("Nijedna WOT instalacija nije pronađena")
            self.search_status.setStyleSheet("color: red; font-weight: bold;")
            self.installations_combo.addItem("Nijedna instalacija pronađena")
            self.log("Nijedna WOT instalacija nije automatski pronađena. Koristite ručni izbor.")

    def on_installation_selected(self, text):
        """Poziva se kada korisnik izabere instalaciju iz combo box-a"""
        if " - " in text and self.found_installations:
            for path, region in self.found_installations:
                if text == f"{region} - {path}":
                    self.executable_path = path
                    self.update_feedback()
                    self.refresh_replay_list()
                    break

    def select_executable(self):
        """Ručni izbor executable fajla"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Izaberi World of Tanks Executable",
            os.path.expanduser("~"),
            "Executable Files (*.exe);;All Files (*)"
        )

        if file_path:
            self.executable_path = file_path
            self.update_feedback()
            self.refresh_replay_list()
            self.log(f"Ručno izabran executable: {file_path}")

    def refresh_replay_list(self):
        """Osvežava listu replay fajlova"""
        if not self.executable_path:
            self.replay_status.setText("Nema izabranog WOT executable-a")
            return

        # Zaustavi postojeći thread ako radi
        if self.replay_search_thread and self.replay_search_thread.isRunning():
            self.replay_search_thread.quit()
            self.replay_search_thread.wait()

        self.replay_status.setText("Pretražujem replay fajlove...")
        self.replay_list_widget.clear()
        self.replay_list = []

        self.replay_search_thread = ReplaySearchThread(self.executable_path)
        self.replay_search_thread.replay_found.connect(self.add_replay_to_list)
        self.replay_search_thread.search_complete.connect(self.replay_search_finished)
        self.replay_search_thread.progress_update.connect(self.update_replay_status)
        self.replay_search_thread.finished.connect(self.replay_search_thread.deleteLater)  # Automatsko brisanje
        self.replay_search_thread.start()

    def add_replay_to_list(self, replay_info):
        """Dodaje replay u listu"""
        self.replay_list.append(replay_info)

    def replay_search_finished(self):
        """Završava pretragu replay fajlova"""
        # Sortuj po datumu (najnoviji prvi)
        self.replay_list.sort(key=lambda x: x.get_sort_date(), reverse=True)

        self.filtered_replay_list = self.replay_list.copy()
        self.update_replay_display()

        count = len(self.replay_list)
        self.replay_status.setText(f"Pronađeno {count} replay fajlova")
        if count == 0:
            self.replay_status.setStyleSheet("color: orange;")
        else:
            self.replay_status.setStyleSheet("color: green;")

        self.log(f"Pronađeno {count} replay fajlova")

    def update_replay_status(self, message):
        """Ažurira status pretrage replay fajlova"""
        self.replay_status.setText(message)

    def update_replay_display(self):
        """Ažurira prikaz replay liste"""
        self.replay_list_widget.clear()

        for replay_info in self.filtered_replay_list:
            item = QListWidgetItem()
            item.setText(replay_info.get_display_text())
            item.setData(Qt.ItemDataRole.UserRole, replay_info)

            # Dodeli boju na osnovu rezultata bitke
            if replay_info.battle_result == "Pobeda":
                item.setBackground(Qt.GlobalColor.green)
                item.setForeground(Qt.GlobalColor.white)
            elif replay_info.battle_result == "Poraz":
                item.setBackground(Qt.GlobalColor.red)
                item.setForeground(Qt.GlobalColor.white)

            self.replay_list_widget.addItem(item)

    def filter_replays(self):
        """Filtrira replay listu na osnovu search teksta"""
        search_text = self.replay_search.text().lower()

        if not search_text:
            self.filtered_replay_list = self.replay_list.copy()
        else:
            self.filtered_replay_list = []
            for replay_info in self.replay_list:
                # Pretraži u file name, player name, tank name, map name
                if (search_text in replay_info.file_name.lower() or
                        (replay_info.player_name and search_text in replay_info.player_name.lower()) or
                        (replay_info.tank_name and search_text in replay_info.tank_name.lower()) or
                        (replay_info.map_name and search_text in replay_info.map_name.lower())):
                    self.filtered_replay_list.append(replay_info)

        self.update_replay_display()

    def on_replay_click(self, item):
        """Poziva se kada korisnik klikne na replay"""
        replay_info = item.data(Qt.ItemDataRole.UserRole)
        if replay_info:
            self.log(f"Izabran replay: {replay_info.file_name}")

    def on_replay_double_click(self, item):
        """Poziva se kada korisnik dvaput klikne na replay"""
        replay_info = item.data(Qt.ItemDataRole.UserRole)
        if replay_info:
            self.play_replay_file(replay_info.file_path)

    def play_selected_replay(self):
        """Pokreće izabrani replay ili otvara file dialog"""
        current_item = self.replay_list_widget.currentItem()
        if current_item:
            replay_info = current_item.data(Qt.ItemDataRole.UserRole)
            if replay_info:
                self.play_replay_file(replay_info.file_path)
                return

        # Ako nijedan replay nije izabran, otvori file dialog
        self.play_replay()

    def toggle_proton(self, checked):
        """Prebacuje između Proton i Wine načina"""
        self.use_proton = checked
        mode = "Steam Proton" if checked else "Wine"
        self.log(f"Način pokretanja promenjen na: {mode}")
        self.update_feedback()

    def update_feedback(self):
        """Ažurira feedback poruku"""
        if self.executable_path:
            mode = "Steam Proton" if self.use_proton else "Wine"
            self.feedback_label.setText(
                f"✅ Izabran executable: {self.executable_path}\n"
                f"🚀 Način pokretanja: {mode}"
            )
            self.feedback_label.setStyleSheet("color: green; font-weight: bold; padding: 10px;")
        else:
            self.feedback_label.setText("❌ Nijedan executable nije izabran.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

    def play_replay(self):
        """Pokreće WOT replay (file dialog verzija)"""
        if not self.executable_path:
            self.feedback_label.setText("❌ Molimo izaberite executable prvo.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            return

        # Izaberi replay fajl
        replay_file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Izaberi Replay File",
            os.path.expanduser("~/Downloads"),
            "WOT Replay Files (*.wotreplay);;All Files (*)"
        )

        if replay_file_path:
            self.play_replay_file(replay_file_path)

    def play_replay_file(self, replay_file_path):
        """Pokreće specifični replay fajl"""
        if not self.executable_path:
            self.feedback_label.setText("❌ Molimo izaberite executable prvo.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            return

        if not replay_file_path:
            self.log("Nijedan replay fajl nije izabran.")
            return

        if not replay_file_path.lower().endswith(".wotreplay"):
            self.feedback_label.setText("❌ Molimo izaberite valjan .wotreplay fajl.")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            return

        self.log(f"Pokušavam pokretanje replay-a: {replay_file_path}")

        try:
            if self.use_proton:
                success = self.run_with_proton(replay_file_path)
            else:
                success = self.run_with_wine(replay_file_path)

            if success:
                self.feedback_label.setText(f"✅ Pokretanje replay-a: {os.path.basename(replay_file_path)}")
                self.feedback_label.setStyleSheet("color: green; font-weight: bold; padding: 10px;")
            else:
                self.feedback_label.setText("❌ Greška pri pokretanju replay-a.")
                self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

        except Exception as e:
            self.log(f"Greška: {str(e)}")
            self.feedback_label.setText(f"❌ Greška: {str(e)}")
            self.feedback_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

    def run_with_proton(self, replay_file):
        """Pokreće replay koristeći Steam Proton"""
        self.log("Pokretanje sa Steam Proton...")

        # Pronađi Steam i Proton
        steam_path = self.find_steam_path()
        if not steam_path:
            self.log("Steam nije pronađen!")
            return False

        # Komanda za Steam Proton
        cmd = [
            steam_path,
            "-applaunch", "1407200",  # WOT App ID na Steam-u
            replay_file
        ]

        self.log(f"Izvršavam: {' '.join(cmd)}")

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log("Replay pokrenut sa Steam Proton.")
            return True
        except Exception as e:
            self.log(f"Greška sa Proton: {e}")
            # Fallback na wine
            self.log("Pokušavam sa Wine kao fallback...")
            return self.run_with_wine(replay_file)

    def run_with_wine(self, replay_file):
        """Pokreće replay koristeći Wine"""
        self.log("Pokretanje sa Wine...")

        # Komanda za Wine
        cmd = ["wine", self.executable_path, replay_file]

        self.log(f"Izvršavam: {' '.join(cmd)}")

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log("Replay pokrenut sa Wine.")
            return True
        except Exception as e:
            self.log(f"Greška sa Wine: {e}")
            return False

    def find_steam_path(self):
        """Pronalazi Steam executable"""
        steam_paths = [
            "/usr/bin/steam",
            "/usr/local/bin/steam",
            "/opt/steam/steam",
            os.path.expanduser("~/.steam/steam.sh"),
            os.path.expanduser("~/.local/share/Steam/steam.sh")
        ]

        for path in steam_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path

        # Pokušaj sa which
        try:
            result = subprocess.run(["which", "steam"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

        return None

    def log(self, message):
        """Dodaje poruku u log"""
        current_text = self.log_area.toPlainText()
        new_text = f"{current_text}\n{message}"
        self.log_area.setPlainText(new_text)

        # Scroll na dno
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def main():
    app = QApplication(sys.argv)

    # Postavi font i stil
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
