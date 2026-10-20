# calc-php-converter 🧮🪙

> **A lightweight, open-source hobby utility for desktop currency conversion and on-screen calculations.**

A floating, transparent overlay widget built in Python with Tkinter. It was created as a personal productivity and hobby project to quickly convert Philippine Peso (PHP) to USDT / USD alongside quick math calculations while working or gaming.

---

### ✨ Features
- 🪟 **Floating & Frameless Overlay**: Stays neatly on top of your workspace or active windows.
- ⚡ **Instant PHP ⇄ USDT Calculations**: Real-time evaluation and bidirectional conversions.
- 🔍 **Google Lens OCR Snipping**: Quick region-snip tool to grab text or prices straight from the screen.
- ⌨️ **Global Hotkeys**:
  - `Ctrl + /` to quickly focus / summon.
  - `Ctrl + +` / `Ctrl + -` to adjust window opacity on the fly.
- 💾 **Session Memory**: Preserves window coordinates, sizing, and opacity preference in `window_config.json`.
- 🎨 **Minimal Dark Mode**: Clean modern aesthetic with zero clutter.

---

### 🚀 Getting Started

#### Requirements
- Python 3.8+
- Windows OS (uses Windows Win32 APIs for global hotkeys and DPI awareness)

#### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/MEhe132/Convert_php_to_usdt.git
   cd Convert_php_to_usdt
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python calc_overlay.py
   ```

---

### 🛠️ Tech Stack & Dependencies
- **GUI Framework**: Python `tkinter`
- **Imaging & Screen Capture**: `Pillow` (PIL)
- **OS Integration**: `ctypes` (Win32 User32 / Shcore APIs)

---

### 🤝 Contributing & Hobby Note
This is a small, personal hobby project shared with the community under the MIT License. Contributions, bug reports, and suggestions are warmly welcome! Feel free to open an issue or submit a pull request.

---

### 📄 License
Distributed under the [MIT License](LICENSE).
