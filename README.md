<div align="center">

# 🎬 FrameGrabber

### Turn any clip into individual frames — and into clean, **alpha‑transparent animations** (GIF · APNG · WebP).
### Mach aus jedem Clip Einzelbilder — und saubere, **alpha‑transparente Animationen** (GIF · APNG · WebP).

<img src="assets/demo_checker.gif" width="460" alt="Transparent animation loop on a checkerboard">

![License](https://img.shields.io/badge/license-MIT-27e0c4)
![Python](https://img.shields.io/badge/Python-3.11+-4d8dff)
![Engine](https://img.shields.io/badge/engine-ffmpeg%20%2B%20Pillow-8aa0bd)
![Platform](https://img.shields.io/badge/platform-Windows-555)
![No subscription](https://img.shields.io/badge/cost-%E2%82%AC0%20offline-48e08a)

**🇬🇧 [English](#-english)  ·  🇩🇪 [Deutsch](#-deutsch)**

</div>

---

## 💥 The one‑click WOW / Der Aha‑Moment

**You own a green‑screen `.mp4`? Get a clean, transparent animated GIF / WebP out of it — free, offline, no subscription.**
**Du hast ein Greenscreen‑`.mp4`? Hol dir ein sauberes, transparentes animiertes GIF / WebP heraus — kostenlos, offline, ohne Abo.**

<img src="assets/demo_chroma_before_after.png" width="820" alt="Green screen mp4 turned into a transparent cut-out">

---

## 🖥️ The app / Die App

| Tab 1 — Frames & Sheet | Tab 2 — Animation |
|:--:|:--:|
| <img src="assets/ui_frames.png" width="400"> | <img src="assets/ui_animation.png" width="400"> |
| Extract **every frame** + build contact / sprite sheets | Frames or sprite sheet → **GIF / APNG / WebP** |
| Jeden Frame extrahieren + Kontaktbogen / Sprite‑Sheet | Frames oder Sprite‑Sheet → **GIF / APNG / WebP** |

---

## 🎨 What it makes / Was dabei rauskommt

| Transparent loop · Transparenter Loop | Transparency proof · Transparenz‑Beweis |
|:--:|:--:|
| <img src="assets/demo_loop.gif" width="360"> | <img src="assets/demo_checker.gif" width="360"> |
| **Sprite sheet** (tight, transparent) | **Contact sheet** (numbered preview) |
| <img src="assets/demo_sprite_sheet.png" width="360"> | <img src="assets/demo_contact_sheet.png" width="360"> |

---

<a name="-english"></a>
## 🇬🇧 English

FrameGrabber is a small, fast desktop tool (Dark‑Glow‑Glass Tkinter GUI + CLI) that does two things brilliantly:

### ✨ Features

**Tab 1 — Frames & Sheet**
- 🎞️ **Extract every single frame** of a clip — losslessly. Pick *every frame* (`fps_mode passthrough`, nothing dropped) or *N frames/second*.
- 🖼️ Output as **PNG** (lossless) · JPG · WebP · BMP · TIFF.
- 🪄 **Transparency**:
  - **Keep alpha** — preserves existing transparency (APNG, transparent MOV/WebM) as RGBA frames.
  - **Chroma‑key** — punch out a background colour (green screen) → **real alpha**, with a colour picker + tolerance.
- 🧩 **Sheets** built from all frames:
  - **Contact sheet** — a numbered grid preview (dark‑glow look).
  - **Sprite sheet** — tightly packed, transparent, ready for game engines / animation.

**Tab 2 — Animation**
- 🔁 Turn a **frame folder** *or* a **sprite sheet** into a finished, looping animation.
- 🟢 **GIF** — plays everywhere (incl. Windows Photos), 1‑bit transparency.
- 🟣 **APNG** & 🔵 **WebP** — **true 8‑bit soft alpha** (smooth edges).
- 🎛️ FPS / frame‑delay · infinite or N loops · alpha threshold · matte colour · scale · forward / reverse / **boomerang** · start/end trim.
- 🧠 **Auto‑detect**: columns/rows of a sprite sheet **and** the source FPS are read automatically — so the animation plays at the **original speed**, no manual setup.

### 🧱 Perfect registration, for free
Every frame is the full canvas, so all frames already line up pixel‑perfect — no jitter, no alignment step. Sprite sheets are sliced exactly on the grid (verified byte‑identical round‑trip).

### 🚀 Install
```bash
# Requirements: Python 3.11+, ffmpeg on PATH, Pillow
pip install pillow
# optional drag & drop into the window:
pip install tkinterdnd2
```
ffmpeg: install from https://ffmpeg.org or `choco install ffmpeg`.

### ▶️ Use it
**GUI:** double‑click `FrameGrabber starten.bat` (or `pythonw framegrabber.py`).

**CLI — frames:**
```bash
python framegrabber_cli.py clip.mp4                       # every frame -> PNG
python framegrabber_cli.py clip.mp4 --fps 12 --format jpg
python framegrabber_cli.py greenscreen.mp4 --alpha chroma --key-color "#00FF00" --sheet sprite
```
**CLI — animations:**
```bash
python frameanim_cli.py clip_frames --gif --apng --webp   # folder -> animations
python frameanim_cli.py sheet.png --cols 8 --rows 5 --webp --fps 24
python frameanim_cli.py frames --boom --scale 50 -o loop  # boomerang, half size
```

### 🎯 Which format?
| Format | Plays on double‑click (Windows) | Soft (8‑bit) alpha |
|---|:--:|:--:|
| **GIF** | ✅ everywhere | ❌ 1‑bit only (hard edges) |
| **WebP** | ✅ Windows 11 Photos | ✅ **yes** *(recommended)* |
| **APNG** (`.png`) | ❌ shows 1st frame only | ✅ yes — animates **in a browser** |

> APNG **is** animated — Windows Photos just doesn't play it. Drag the `.png` into Chrome/Edge and it moves.

### ⚙️ How it works
- Frame extraction & palette GIF: **ffmpeg** (`fps_mode passthrough`; `palettegen reserve_transparent` + `paletteuse alpha_threshold` + Bayer dither; auto `disposal=2` → no ghost trails; GIF delay snapped to centiseconds).
- Sheets, APNG, WebP: **Pillow** (APNG `disposal=1/blend=0`, WebP `lossless+exact` → bit‑exact alpha, no trails).
- Output is written atomically (`os.replace`); source FPS + sprite grid are embedded as metadata for auto‑detection.

---

<a name="-deutsch"></a>
## 🇩🇪 Deutsch

FrameGrabber ist ein kleines, schnelles Desktop‑Tool (Dark‑Glow‑Glass Tkinter‑GUI + CLI), das zwei Dinge richtig gut kann:

### ✨ Funktionen

**Tab 1 — Frames & Sheet**
- 🎞️ **Jeden einzelnen Frame** eines Clips extrahieren — verlustfrei. Wahlweise *jeder Frame* (`fps_mode passthrough`, nichts geht verloren) oder *N Bilder/Sekunde*.
- 🖼️ Ausgabe als **PNG** (verlustfrei) · JPG · WebP · BMP · TIFF.
- 🪄 **Transparenz**:
  - **Alpha erhalten** — behält vorhandene Transparenz (APNG, transparentes MOV/WebM) als RGBA‑Frames.
  - **Farbe entfernen (Chroma‑Key)** — stanzt eine Hintergrundfarbe (Greenscreen) aus → **echtes Alpha**, mit Farbwähler + Toleranz.
- 🧩 **Sheets** aus allen Frames:
  - **Kontaktbogen** — nummeriertes Raster zur Übersicht (Dark‑Glow‑Look).
  - **Sprite‑Sheet** — eng gepackt, transparent, perfekt für Game‑Engines / Animation.

**Tab 2 — Animation**
- 🔁 Aus einem **Frame‑Ordner** *oder* einem **Sprite‑Sheet** eine fertige, loopende Animation bauen.
- 🟢 **GIF** — läuft überall (auch Windows‑Fotos), 1‑Bit‑Transparenz.
- 🟣 **APNG** & 🔵 **WebP** — **echtes weiches 8‑Bit‑Alpha** (saubere Kanten).
- 🎛️ FPS / Bild‑Dauer · endlos oder N‑mal · Alpha‑Schwelle · Matte‑Farbe · Skalieren · Vorwärts / Rückwärts / **Boomerang** · Start/End‑Trim.
- 🧠 **Auto‑Erkennung**: Spalten/Zeilen eines Sprite‑Sheets **und** die Quell‑FPS werden automatisch gelesen — die Animation läuft in **Original‑Geschwindigkeit**, ohne manuelles Einstellen.

### 🧱 Perfekt deckungsgleich — gratis
Jeder Frame ist die volle Bildfläche, also liegen alle Frames automatisch pixelgenau übereinander — kein Zittern, kein Ausrichten. Sprite‑Sheets werden exakt am Raster zerschnitten (byte‑identischer Round‑Trip verifiziert).

### 🚀 Installation
```bash
# Voraussetzungen: Python 3.11+, ffmpeg im PATH, Pillow
pip install pillow
# optional Drag & Drop ins Fenster:
pip install tkinterdnd2
```
ffmpeg: von https://ffmpeg.org oder `choco install ffmpeg`.

### ▶️ Benutzen
**GUI:** Doppelklick auf `FrameGrabber starten.bat` (oder `pythonw framegrabber.py`).

**CLI — Frames:**
```bash
python framegrabber_cli.py clip.mp4                       # jeder Frame -> PNG
python framegrabber_cli.py clip.mp4 --fps 12 --format jpg
python framegrabber_cli.py greenscreen.mp4 --alpha chroma --key-color "#00FF00" --sheet sprite
```
**CLI — Animationen:**
```bash
python frameanim_cli.py clip_frames --gif --apng --webp   # Ordner -> Animationen
python frameanim_cli.py sheet.png --cols 8 --rows 5 --webp --fps 24
python frameanim_cli.py frames --boom --scale 50 -o loop  # Boomerang, halbe Größe
```

### 🎯 Welches Format?
| Format | Spielt per Doppelklick (Windows) | Weiches (8‑Bit) Alpha |
|---|:--:|:--:|
| **GIF** | ✅ überall | ❌ nur 1‑Bit (harte Kanten) |
| **WebP** | ✅ Windows‑11‑Fotos | ✅ **ja** *(Empfehlung)* |
| **APNG** (`.png`) | ❌ zeigt nur 1. Bild | ✅ ja — animiert **im Browser** |

> APNG **ist** animiert — Windows‑Fotos spielt es nur nicht ab. Zieh die `.png` in Chrome/Edge, dann bewegt sie sich.

### ⚙️ Wie es funktioniert
- Frame‑Extraktion & Paletten‑GIF: **ffmpeg** (`fps_mode passthrough`; `palettegen reserve_transparent` + `paletteuse alpha_threshold` + Bayer‑Dither; automatisch `disposal=2` → keine Geister‑Schweife; GIF‑Delay auf Zentisekunden gesnappt).
- Sheets, APNG, WebP: **Pillow** (APNG `disposal=1/blend=0`, WebP `lossless+exact` → bit‑genaues Alpha, keine Schweife).
- Ausgabe wird atomar geschrieben (`os.replace`); Quell‑FPS + Sprite‑Raster werden als Metadaten für die Auto‑Erkennung eingebettet.

---

<div align="center">

**MIT License** · made with ffmpeg + Pillow · the demo mascot says hi 👋

</div>
