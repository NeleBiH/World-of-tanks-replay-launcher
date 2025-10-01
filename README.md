# World of Tanks Replay Player (Linux, Wine)

A simple **PyQt6** desktop app for **playing World of Tanks `.wotreplay` files** on Linux using **Wine**.  
It auto-discovers your WoT installation(s), scans common folders for replays, lets you **search & filter**, and supports **drag & drop** to play a replay instantly.

## 📷 Screenshot 📷 ## 
<img width="1203" height="733" alt="Screenshot_20250826_222626" src="https://github.com/user-attachments/assets/cbdf1bab-5200-499f-ab5d-4ebf2d5a795a" />




---

## ✨ Features

- **Automatic discovery** of WoT installations (Steam/Proton prefixes are detected too, but replays still launch with Wine).
- **One‑click playback** of `.wotreplay` files with Wine.
- **Drag & drop** a replay onto the window to run it.
- **Replay search** box for quick filtering by name or metadata (player, tank, map—if present in header).
- **Persistent numbering** of replays shown in the list (e.g. `#001 | filename.wotreplay`).  
  Numbers are stored in a hidden JSON file in your home folder and survive app restarts.
- **Dark WoT‑inspired theme.**
- **Activity log** panel with all executed commands & hints.

---

## 🧩 Requirements

- **Python 3.9+**
- **PyQt6** (`pip install PyQt6`)
- **Wine** available on your `$PATH` (`wine --version` should work)

On Debian/Ubuntu-based distros you can get Wine via the distro repos or WineHQ. Example (minimal):  
```bash
UBUNTU
---
sudo apt update
sudo apt install wine 

or
ARCH
---
sudo pacman -S wine

FEDORA
---
sudo yum install wine

or

sudo dnf isntall wine
---

Then check wine version

wine --version
```

---

## 🚀 Installation & Run

1. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install PyQt6
   ```

2. **Run the app** (from the project folder):
   ```bash
   python3 World of tanks replay launcher.py
   ```

3. **Select or auto-detect WoT executable**:  
   - The left panel will try to **auto-detect** installs.  
   - Or click **“Choose WOT executable manually”** and pick `WorldOfTanks.exe` (or equivalent).

4. **Play a replay**:
   - **Drag & drop** a `.wotreplay` file anywhere on the app window, **or**
   - Double-click a replay in the list, **or**
   - Click **“Play Replay”** and choose a file manually.

> If Wine fails to start, the log will show a hint like: **“Check if Wine is installed: `wine --version`”**.

---

## 🗂️ Where the app looks for replays

- The game’s `replays/` folder near your WoT executable
- `~/Documents/World of Tanks/replays`
- `~/Downloads`
- Subfolders of those locations (recursive scan)

You can always load a replay from **anywhere** using the **“Play Replay”** button or drag & drop.

---

## 🔢 Persistent numbering (`~/.wotreplay_player_index.json`)

Each replay shown in the list gets a **stable numeric index** (e.g. `#001`, `#042`).  
These numbers are stored in a **hidden JSON** file in your home directory:

- Path: `~/.wotreplay_player_index.json`
- Purpose: keep consistent numbers between app runs (useful for referencing/sharing).
- The file maps **absolute replay paths** to **integers**.

**Example content:**
```json
{
  "/home/user/Documents/World of Tanks/replays/20250825_2206_usa...wotreplay": 1,
  "/home/user/Downloads/20250823_2109_...wotreplay": 2
}
```
---

## 🖱️ Drag & Drop

- Drag any `.wotreplay` file onto the app window.  
- The dropped file path is validated and immediately launched with Wine.

---

## 🧪 Troubleshooting

- **Wine not found / nothing happens**
  - Ensure Wine is installed and on PATH: `wine --version`  
  - Try launching Wine once to initialize the prefix: `wine notepad`

- **Replay doesn’t start**
  - Make sure your **WoT executable path** is correct (use the left panel to select it).
  - Some Proton/Steam installs keep files in a prefix (the app can still run the exe with Wine).

- **No replays found**
  - Use **Refresh replays**.
  - Manually open the file via **Play Replay** or drag & drop from anywhere.

- **Crashes on close / refresh**
  - The app uses safer thread shutdown; but if your system kills Wine/Steam, simply restart the app.

---

## 🛠️ Developer Notes

- **Tech stack**: Python, PyQt6, QThreads, JSON persistence, Wine subprocess calls.
- **Style**: Dark palette inspired by WoT colours.
- **Replay metadata**: The app reads header JSON (date, player, vehicle, map when present).  
  It **does not** try to derive victory/defeat since replay headers are inconsistent without an SDK.

### Ideas for extensions
- Context menu (open folder, copy path, delete file)
- More metadata parsing and tagging
- Export replay list to CSV/JSON
- Multi-select playback queue (sequential start)

---



## 📜 License

GNU GENERAL PUBLIC LICENSE Version 3


---



## ✅ Quick Checklist

- [x] Python 3.9+ installed
- [x] `pip install PyQt6`
- [x] Wine installed (`wine --version` works)
- [x] Run `python3 test.py`
- [x] Select or auto-detect WoT executable
- [x] Drag & drop or double‑click a `.wotreplay`

---

