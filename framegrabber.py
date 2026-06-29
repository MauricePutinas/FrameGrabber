# -*- coding: utf-8 -*-
"""
FrameGrabber - Extract every frame of a clip and build alpha-transparent
animations (GIF / APNG / WebP) and contact / sprite sheets.

Dark-Glow-Glass GUI (Tkinter). Engines: ffmpeg (lossless frame extraction,
palette GIF) + Pillow (sheets, APNG/WebP).

MIT License.
"""

import os
import re
import sys
import glob
import math
import json
import queue
import shutil
import tempfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

APP_NAME = "FrameGrabber"
VERSION = "1.3"

# ---------- Theme (Dark Glow Glass) ----------
BG        = "#0b0e14"   # tiefes Nachtblau-schwarz
PANEL     = "#11161f"   # Panel
PANEL_2   = "#161d29"   # heller Panel
STROKE    = "#243042"   # Rahmenlinie
TXT       = "#e8eef7"   # Haupttext
TXT_DIM   = "#8aa0bd"   # gedimmter Text
ACCENT    = "#27e0c4"   # Neon-Tuerkis
ACCENT_2  = "#4d8dff"   # Neon-Blau
ACCENT_HV = "#5cf2dd"   # heller Akzent (Hover)
DANGER    = "#ff5d6c"
OK        = "#48e08a"

FONT      = "Segoe UI"

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv",
              ".flv", ".mpg", ".mpeg", ".ts", ".gif", ".3gp", ".mts")

FORMATS = {
    "PNG (verlustfrei)":  {"ext": "png",  "args": ["-compression_level", "3"]},
    "JPG (klein)":        {"ext": "jpg",  "args": ["-q:v", "2"]},
    "WebP":               {"ext": "webp", "args": ["-lossless", "0", "-quality", "90"]},
    "BMP (unkomprimiert)":{"ext": "bmp",  "args": []},
    "TIFF":               {"ext": "tiff", "args": []},
}


def resource_exe(name):
    """ffmpeg/ffprobe finden: PATH zuerst, dann typische Choco-Pfade."""
    found = shutil.which(name)
    if found:
        return found
    for cand in (
        rf"C:\ProgramData\chocolatey\bin\{name}.exe",
        rf"C:\ffmpeg\bin\{name}.exe",
    ):
        if os.path.isfile(cand):
            return cand
    return None


FFMPEG  = resource_exe("ffmpeg")
FFPROBE = resource_exe("ffprobe")

# subprocess: keine Konsolenfenster unter Windows
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def probe(path):
    """Video-Infos via ffprobe holen. Gibt dict zurueck."""
    info = {"fps": None, "frames": None, "duration": None, "w": None, "h": None}
    if not FFPROBE:
        return info
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=avg_frame_rate,r_frame_rate,nb_frames,width,height:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
        )
        data = json.loads(out.stdout or "{}")
        st = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        info["w"] = st.get("width")
        info["h"] = st.get("height")
        rate = st.get("avg_frame_rate") or st.get("r_frame_rate") or "0/0"
        num, _, den = rate.partition("/")
        try:
            den = float(den) if den else 0.0
            info["fps"] = (float(num) / den) if den else None
        except ValueError:
            info["fps"] = None
        try:
            info["duration"] = float(fmt.get("duration"))
        except (TypeError, ValueError):
            info["duration"] = None
        nb = st.get("nb_frames")
        if nb and str(nb).isdigit():
            info["frames"] = int(nb)
        elif info["fps"] and info["duration"]:
            info["frames"] = max(1, round(info["fps"] * info["duration"]))
    except Exception:
        pass
    return info


def _load_font(size):
    for path in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def build_sheet(frame_paths, out_path, mode="contact", columns=0,
                thumb_w=240, title="", transparent_bg=False, source_fps=None,
                progress_cb=None):
    """Baut aus allen Frame-Bildern ein einziges Sheet.

    mode="contact": Kontaktbogen (dunkler Hintergrund, Rand, Frame-Nummern)
    mode="sprite":  Sprite-Sheet (eng gepackt, transparent, ohne Beschriftung)
    columns=0 -> automatisch (etwa quadratisch). thumb_w=0 -> Originalgroesse.
    transparent_bg=True -> kompletter Canvas mit echtem Alpha (auch Kontaktbogen).
    """
    if not HAVE_PIL:
        raise RuntimeError("Pillow fehlt – bitte 'pip install Pillow' ausführen.")
    n = len(frame_paths)
    if n == 0:
        raise ValueError("Keine Frames zum Zusammenbauen gefunden.")
    Image.MAX_IMAGE_PIXELS = None  # grosse Sheets erlauben

    with Image.open(frame_paths[0]) as im0:
        ow, oh = im0.size
    aspect = oh / ow if ow else 0.5625

    cols = columns if columns and columns > 0 else max(1, round(math.sqrt(n * aspect)))
    cols = max(1, min(cols, n))
    rows = math.ceil(n / cols)

    sprite = (mode == "sprite")
    if sprite:
        tw = thumb_w if thumb_w and thumb_w > 0 else ow
        th = max(1, round(oh * tw / ow))
        margin = pad = label_h = header_h = 0
        bg = (0, 0, 0, 0)               # transparent
    else:
        tw = thumb_w if thumb_w and thumb_w > 0 else 240
        th = max(1, round(oh * tw / ow))
        margin, pad, label_h = 16, 8, 18
        header_h = 50 if title else 0
        bg = (11, 14, 20, 255)          # Dark-Glow Hintergrund

    if transparent_bg:
        bg = (0, 0, 0, 0)               # echtes Alpha statt Fuellfarbe

    cell_h = th + label_h
    sheet_w = margin * 2 + cols * tw + (cols - 1) * pad
    sheet_h = header_h + margin * 2 + rows * cell_h + (rows - 1) * pad

    if sheet_w * sheet_h > 240_000_000:
        raise ValueError(
            "Sheet würde zu groß (>240 MP). Kleinere Thumb-Breite oder mehr Spalten wählen.")

    sheet = Image.new("RGBA", (sheet_w, sheet_h), bg)
    draw = ImageDraw.Draw(sheet)

    if header_h:
        draw.text((margin, 12), title or "Kontaktbogen",
                  fill=(232, 238, 247, 255), font=_load_font(20))
        draw.text((margin, 36), f"{n} Frames  ·  {cols} × {rows}",
                  fill=(39, 224, 196, 255), font=_load_font(12))

    f_lbl = _load_font(11) if label_h else None
    for i, p in enumerate(frame_paths):
        r, c = divmod(i, cols)
        x = margin + c * (tw + pad)
        y = header_h + margin + r * (cell_h + pad)
        try:
            with Image.open(p) as im:
                im = im.convert("RGBA")
                if im.size != (tw, th):
                    im = im.resize((tw, th), Image.LANCZOS)
                if sprite or transparent_bg:
                    sheet.paste(im, (x, y))            # verlustfrei: exakte RGBA-Tiles
                else:
                    sheet.alpha_composite(im, (x, y))  # korrekt über deckenden Hintergrund
        except Exception:
            pass
        if f_lbl:
            draw.text((x + 3, y + th + 2), str(i + 1),
                      fill=(138, 160, 189, 255), font=f_lbl)
        if progress_cb and i % 8 == 0:
            progress_cb(i + 1, n)
    if progress_cb:
        progress_cb(n, n)

    ext = os.path.splitext(out_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        sheet.convert("RGB").save(out_path, quality=92)
    elif ext == ".png":
        # Raster + Quell-FPS als Metadaten einbetten -> Animations-Tab erkennt sie
        from PIL import PngImagePlugin
        meta = PngImagePlugin.PngInfo()
        meta.add_text("fg_kind", "sprite" if sprite else "contact")
        if sprite:
            meta.add_text("fg_cols", str(cols))
            meta.add_text("fg_rows", str(rows))
            meta.add_text("fg_frames", str(n))
        if source_fps:
            meta.add_text("fg_fps", f"{float(source_fps):.4f}")
        sheet.save(out_path, pnginfo=meta)
    else:
        sheet.save(out_path)
    return out_path


# =====================================================================
#  Animations-Engine  (Frame-Sequenz / Sprite-Sheet -> GIF / APNG / WebP)
#  GIF  = 1-Bit-Alpha (ffmpeg palettegen/paletteuse, auto-disposal=2)
#  APNG = echtes 8-Bit-Alpha (Pillow, disposal=1/blend=0 -> verifiziert)
#  WebP = echtes 8-Bit-Alpha (Pillow, lossless+exact -> verifiziert)
# =====================================================================

def collect_frame_paths(folder):
    """Nur die tool-eigenen frame_*.png einsammeln (nicht Sheets im selben Ordner!),
    korrekt sortiert (Null-gepaddte Namen sortieren lexikalisch richtig)."""
    return sorted(glob.glob(os.path.join(folder, "frame_*.png")))


def read_folder_meta(folder):
    """Liest die beim Extrahieren geschriebene _framegrabber.json (Quell-FPS etc.)."""
    try:
        with open(os.path.join(folder, "_framegrabber.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _grid_from_gaps(img):
    """Erkennt Spalten/Zeilen über voll-transparente Trennlinien (Sheets mit Abstand).
    Gibt (cols, rows) oder None (FrameGrabber-Sprite-Sheets sind lückenlos -> None)."""
    a = img.getchannel("A")
    W, H = img.size
    col_empty = [a.crop((x, 0, x + 1, H)).getbbox() is None for x in range(W)]
    row_empty = [a.crop((0, y, W, y + 1)).getbbox() is None for y in range(H)]

    def blocks(empty):
        n, prev_empty = 0, True
        for e in empty:
            if not e and prev_empty:
                n += 1
            prev_empty = e
        return n

    c, r = blocks(col_empty), blocks(row_empty)
    if c >= 1 and r >= 1 and (c > 1 or r > 1):
        return c, r
    return None


def detect_sheet_grid(sheet_path):
    """Erkennt {cols, rows, frames, fps} eines Sprite-Sheets:
    1) aus eingebetteten FrameGrabber-PNG-Metadaten   2) aus transparenten Lücken."""
    res = {"cols": None, "rows": None, "frames": None, "fps": None, "auto": False}
    if not HAVE_PIL:
        return res
    try:
        img = Image.open(sheet_path)
        txt = getattr(img, "text", {}) or {}
        if txt.get("fg_fps"):
            res["fps"] = float(txt["fg_fps"])
        if txt.get("fg_kind") == "sprite" and txt.get("fg_cols"):
            res["cols"] = int(txt["fg_cols"])
            res["rows"] = int(txt["fg_rows"])
            res["frames"] = int(txt.get("fg_frames", 0)) or None
            res["auto"] = True
            return res
        g = _grid_from_gaps(img.convert("RGBA"))
        if g:
            res["cols"], res["rows"] = g
            res["auto"] = True
    except Exception:
        pass
    return res


def slice_sprite_sheet(sheet_path, cols, rows):
    """Sprite-Sheet exakt in gleich große Zellen zerschneiden (row-major).
    Teilbarkeit ist zugleich der Gültigkeitstest: Kontaktbögen scheitern hier.
    Voll-transparente Zellen am ENDE (Raster-Auffüllung) werden verworfen."""
    if not HAVE_PIL:
        raise RuntimeError("Pillow fehlt – bitte 'pip install Pillow'.")
    if cols < 1 or rows < 1:
        raise ValueError("Spalten und Zeilen müssen ≥ 1 sein.")
    src = Image.open(sheet_path).convert("RGBA")
    W, H = src.size
    if W % cols != 0 or H % rows != 0:
        raise ValueError(
            f"{W}×{H} px ist nicht sauber durch {cols}×{rows} teilbar – das ist kein "
            "Sprite-Sheet. Kontaktbögen (mit Rand/Nummern) lassen sich nicht zerschneiden; "
            "nutze den Frame-Ordner oder ein Sprite-Sheet.")
    cw, ch = W // cols, H // rows
    cells = []
    for k in range(cols * rows):
        r, c = divmod(k, cols)
        cells.append(src.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
    while cells and cells[-1].getchannel("A").getbbox() is None:
        cells.pop()
    if not cells:
        raise ValueError("Im Sheet wurden keine sichtbaren Frames gefunden.")
    return cells


def _save_apng(frames, out_path, duration, loop):
    """APNG mit echtem 8-Bit-Alpha. disposal=1/blend=0 ist load-bearing:
    disposal=2 zerstört in Pillow 12 das Alpha (maxAlphaDiff=120, verifiziert)."""
    tmp = out_path + ".part"
    frames[0].save(tmp, format="PNG", save_all=True, append_images=frames[1:],
                   duration=duration, loop=loop, disposal=1, blend=0,
                   default_image=False)
    os.replace(tmp, out_path)


def _save_webp(frames, out_path, duration, loop):
    """Animiertes WebP, verlustfrei + exact (RGB unter Alpha erhalten) -> echtes Alpha,
    keine Geister. (ffmpeg libwebp produzierte im Test Schweife -> daher Pillow.)"""
    tmp = out_path + ".part"
    frames[0].save(tmp, format="WEBP", save_all=True, append_images=frames[1:],
                   duration=duration, loop=loop, lossless=True, exact=True,
                   minimize_size=True, allow_mixed=False)
    os.replace(tmp, out_path)


def _save_gif_pillow(frames, out_path, duration, loop, alpha_thresh):
    """GIF-Fallback ohne ffmpeg (1-Bit-Alpha). colors=255 ist load-bearing:
    lässt Index 255 für die reservierte Transparenz frei -> NICHT auf 256 erhöhen."""
    proc = []
    for f in frames:
        a = f.getchannel("A")
        p = f.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
        holes = a.point(lambda v: 255 if v < alpha_thresh else 0).convert("1")
        p.paste(255, holes)                      # Index 255 = transparent
        p.info["transparency"] = 255
        proc.append(p)
    tmp = out_path + ".part.gif"
    proc[0].save(tmp, save_all=True, append_images=proc[1:], duration=duration,
                 loop=loop, disposal=2, optimize=False, transparency=255)
    os.replace(tmp, out_path)


def _save_gif_ffmpeg(frames, out_path, gif_delay_ms, loop, alpha_thresh, matte):
    """GIF über ffmpeg: globale Palette (stats_mode=full) + reservierter Transparenz-
    Index + Bayer-Dither (motion-stabil). ffmpeg 8.1 emittiert automatisch disposal=2
    -> keine Geister-Schweife. matte!=None -> halbtransparente Kanten auf Farbe verrechnen
    (GIF wird dann quasi deckend). gif_delay_ms ist auf Zentisekunden gesnappt."""
    if not FFMPEG:
        _save_gif_pillow(frames, out_path, gif_delay_ms, loop, alpha_thresh)
        return
    tmp = tempfile.mkdtemp(prefix="fg_anim_")
    try:
        for i, f in enumerate(frames):
            im = f
            if matte is not None:
                bg = Image.new("RGBA", f.size, matte + (255,))
                im = Image.alpha_composite(bg, f)
            im.save(os.path.join(tmp, "frame_%06d.png" % i))
        pattern = os.path.join(tmp, "frame_%06d.png")
        if matte is None:
            fg = (f"split[a][b];[a]palettegen=reserve_transparent=1:stats_mode=full[p];"
                  f"[b][p]paletteuse=alpha_threshold={alpha_thresh}:dither=bayer:"
                  f"bayer_scale=3:diff_mode=rectangle:new=1")
        else:
            fg = ("split[a][b];[a]palettegen=stats_mode=full[p];"
                  "[b][p]paletteuse=dither=bayer:bayer_scale=3")
        out_tmp = out_path + ".part.gif"
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
               "-framerate", f"1000/{gif_delay_ms}", "-start_number", "0", "-i", pattern,
               "-filter_complex", fg, "-loop", str(loop), "-final_delay", "0", out_tmp]
        r = subprocess.run(cmd, creationflags=CREATE_NO_WINDOW,
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out_tmp):
            raise RuntimeError("ffmpeg-GIF fehlgeschlagen: " + (r.stderr or "")[:200])
        os.replace(out_tmp, out_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class FrameGrabber(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{VERSION}")
        self.configure(bg=BG)
        self.minsize(780, 720)
        self.geometry("840x800")

        self.video_path = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.fmt = tk.StringVar(value="PNG (verlustfrei)")
        self.every_frame = tk.BooleanVar(value=True)
        self.fps_value = tk.StringVar(value="12")
        self.alpha_mode = tk.StringVar(value="off")     # off | keep | chroma
        self.chroma_color = tk.StringVar(value="#00FF00")
        self.chroma_sim = tk.StringVar(value="0.30")
        self.build_sheet_var = tk.BooleanVar(value=False)
        self.sheet_type = tk.StringVar(value="contact")
        self.sheet_cols_auto = tk.BooleanVar(value=True)
        self.sheet_cols = tk.StringVar(value="10")
        self.sheet_thumb = tk.StringVar(value="240")
        self.sheet_delete = tk.BooleanVar(value=False)
        self._sheet_inputs = []
        # --- Animations-Tab ---
        self.anim_src = tk.StringVar(value="folder")     # folder | sheet
        self.anim_folder = tk.StringVar()
        self.anim_sheet = tk.StringVar()
        self.anim_cols = tk.StringVar(value="0")
        self.anim_rows = tk.StringVar(value="0")
        self.anim_timing = tk.StringVar(value="fps")     # fps | delay
        self.anim_fps = tk.StringVar(value="12")
        self.anim_delay = tk.StringVar(value="83")
        self.anim_loop = tk.StringVar(value="inf")       # inf | n
        self.anim_loop_n = tk.StringVar(value="3")
        self.anim_thresh = tk.StringVar(value="128")
        self.anim_matte_on = tk.BooleanVar(value=False)
        self.anim_matte_color = tk.StringVar(value="#0b0e14")
        self.fmt_gif = tk.BooleanVar(value=True)
        self.fmt_apng = tk.BooleanVar(value=True)
        self.fmt_webp = tk.BooleanVar(value=True)
        self.anim_scale_on = tk.BooleanVar(value=False)
        self.anim_scale = tk.StringVar(value="100")
        self.anim_dir = tk.StringVar(value="fwd")        # fwd | rev | boom
        self.anim_start = tk.StringVar(value="1")
        self.anim_end = tk.StringVar(value="")
        self.anim_basename = tk.StringVar(value="animation")
        self.info = {}
        self.proc = None
        self.worker = None
        self.anim_worker = None
        self.msgq = queue.Queue()
        self._cancel = threading.Event()
        self._anim_cancel = threading.Event()

        self._build_style()
        self._build_ui()
        self._poll_queue()

        if not FFMPEG or not FFPROBE:
            self.set_status("⚠ ffmpeg/ffprobe nicht gefunden!", DANGER)

    # ---------- Style ----------
    def _build_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TProgressbar", troughcolor=PANEL_2, background=ACCENT,
                    bordercolor=STROKE, lightcolor=ACCENT, darkcolor=ACCENT_2,
                    thickness=14)
        s.configure("Glow.Horizontal.TProgressbar", troughcolor=PANEL_2,
                    background=ACCENT, bordercolor=STROKE, thickness=16)
        # Notebook (Dark-Glow Tabs)
        s.configure("Dark.TNotebook", background=BG, borderwidth=0,
                    tabmargins=(6, 6, 6, 0))
        s.configure("Dark.TNotebook.Tab", background=PANEL, foreground=TXT_DIM,
                    bordercolor=STROKE, borderwidth=0, padding=(22, 9),
                    font=(FONT, 11, "bold"))
        s.map("Dark.TNotebook.Tab",
              background=[("selected", PANEL_2), ("active", PANEL_2)],
              foreground=[("selected", ACCENT), ("active", ACCENT_HV)])
        try:
            s.layout("Dark.TNotebook.Tab", [
                ("Notebook.tab", {"sticky": "nswe", "children": [
                    ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
                        ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
        except tk.TclError:
            pass

    # ---------- UI ----------
    def _card(self, parent, pady=(0, 14)):
        outer = tk.Frame(parent, bg=STROKE)
        outer.pack(fill="x", pady=pady)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="x", padx=1, pady=1)
        return inner

    def _build_ui(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=22, pady=18)

        # Header (geteilt)
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="◉ FRAME", font=(FONT, 22, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(head, text="GRABBER", font=(FONT, 22, "bold"),
                 fg=TXT, bg=BG).pack(side="left")
        tk.Label(head, text=f"  v{VERSION}", font=(FONT, 10),
                 fg=TXT_DIM, bg=BG).pack(side="left", pady=(10, 0))
        tk.Label(head, text="Frames · Sheets · Animation",
                 font=(FONT, 10), fg=TXT_DIM, bg=BG).pack(side="right", pady=(10, 0))

        # Footer (geteilt)
        tk.Label(outer, text="Engine: ffmpeg + Pillow   ·   Alpha: GIF = 1-Bit  |  "
                 "APNG / WebP = echtes 8-Bit-Alpha",
                 font=(FONT, 8), fg=STROKE, bg=BG).pack(side="bottom", pady=(6, 0))

        # Tabs
        self.nb = ttk.Notebook(outer, style="Dark.TNotebook")
        self.nb.pack(fill="both", expand=True, pady=(4, 0))
        page1 = tk.Frame(self.nb, bg=BG)
        page2 = tk.Frame(self.nb, bg=BG)
        self.nb.add(page1, text="  Frames & Sheet  ")
        self.nb.add(page2, text="  Animation  ")
        self._build_extract_tab(page1)
        self._build_animation_tab(page2)

        self._enable_dnd()

    def _build_extract_tab(self, parent):
        # --- Card 1: Drop / Datei ---
        c1 = self._card(parent)
        self.drop = tk.Frame(c1, bg=PANEL, height=120)
        self.drop.pack(fill="x", padx=18, pady=18)
        self.drop_lbl = tk.Label(
            self.drop,
            text="🎬  Video hier ablegen  oder  „Video wählen“ klicken",
            font=(FONT, 13), fg=TXT_DIM, bg=PANEL, pady=22)
        self.drop_lbl.pack(fill="x")
        self.file_lbl = tk.Label(self.drop, text="", font=(FONT, 11, "bold"),
                                 fg=ACCENT, bg=PANEL)
        self.file_lbl.pack()

        row = tk.Frame(c1, bg=PANEL)
        row.pack(fill="x", padx=18, pady=(0, 16))
        self._btn(row, "📂  Video wählen", self.pick_video, primary=True).pack(side="left")
        self.info_lbl = tk.Label(row, text="", font=(FONT, 10), fg=TXT_DIM, bg=PANEL)
        self.info_lbl.pack(side="left", padx=14)

        # --- Card 2: Optionen ---
        c2 = self._card(parent)
        opt = tk.Frame(c2, bg=PANEL)
        opt.pack(fill="x", padx=18, pady=16)

        tk.Label(opt, text="Format", font=(FONT, 10, "bold"),
                 fg=TXT, bg=PANEL).grid(row=0, column=0, sticky="w")
        fmt_box = ttk.Combobox(opt, textvariable=self.fmt, state="readonly",
                               values=list(FORMATS.keys()), width=22)
        fmt_box.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Frame-Modus
        modef = tk.Frame(opt, bg=PANEL)
        modef.grid(row=0, column=1, rowspan=2, sticky="w", padx=(34, 0))
        tk.Radiobutton(modef, text="Jeden Frame (alle)", variable=self.every_frame,
                       value=True, command=self._toggle_fps,
                       font=(FONT, 10), fg=TXT, bg=PANEL, selectcolor=PANEL_2,
                       activebackground=PANEL, activeforeground=ACCENT,
                       highlightthickness=0, bd=0).pack(anchor="w")
        fr = tk.Frame(modef, bg=PANEL)
        fr.pack(anchor="w")
        tk.Radiobutton(fr, text="Nur", variable=self.every_frame, value=False,
                       command=self._toggle_fps, font=(FONT, 10), fg=TXT, bg=PANEL,
                       selectcolor=PANEL_2, activebackground=PANEL,
                       activeforeground=ACCENT, highlightthickness=0, bd=0).pack(side="left")
        self.fps_entry = tk.Entry(fr, textvariable=self.fps_value, width=5,
                                  font=(FONT, 10), bg=PANEL_2, fg=TXT,
                                  insertbackground=ACCENT, relief="flat",
                                  disabledbackground=PANEL, disabledforeground=TXT_DIM)
        self.fps_entry.pack(side="left", padx=4)
        tk.Label(fr, text="Frames / Sekunde", font=(FONT, 10),
                 fg=TXT_DIM, bg=PANEL).pack(side="left")
        opt.columnconfigure(1, weight=1)
        self._toggle_fps()

        # Transparenz / Alpha
        trans = tk.Frame(c2, bg=PANEL)
        trans.pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(trans, text="Transparenz", font=(FONT, 10, "bold"),
                 fg=TXT, bg=PANEL).pack(anchor="w")
        trow = tk.Frame(trans, bg=PANEL)
        trow.pack(anchor="w", pady=(4, 0))
        for val, txt in (("off", "Aus"),
                         ("keep", "Alpha erhalten"),
                         ("chroma", "Farbe entfernen")):
            tk.Radiobutton(
                trow, text=txt, variable=self.alpha_mode, value=val,
                command=self._toggle_alpha, font=(FONT, 10), fg=TXT, bg=PANEL,
                selectcolor=PANEL_2, activebackground=PANEL, activeforeground=ACCENT,
                highlightthickness=0, bd=0).pack(side="left", padx=(0, 14))
        self.swatch = tk.Label(trow, text="  ", bg=self.chroma_color.get(),
                               width=3, relief="flat", cursor="hand2")
        self.swatch.pack(side="left", padx=(4, 6))
        self.swatch.bind("<Button-1>", lambda e: self._pick_color())
        self.chroma_entry = tk.Entry(
            trow, textvariable=self.chroma_color, width=9, font=(FONT, 10),
            bg=PANEL_2, fg=TXT, insertbackground=ACCENT, relief="flat",
            disabledbackground=PANEL, disabledforeground=TXT_DIM)
        self.chroma_entry.pack(side="left")
        self.chroma_entry.bind("<KeyRelease>", lambda e: self._sync_swatch())
        tk.Label(trow, text="  Toleranz", font=(FONT, 10),
                 fg=TXT_DIM, bg=PANEL).pack(side="left")
        self.sim_entry = tk.Entry(
            trow, textvariable=self.chroma_sim, width=5, font=(FONT, 10),
            bg=PANEL_2, fg=TXT, insertbackground=ACCENT, relief="flat",
            disabledbackground=PANEL, disabledforeground=TXT_DIM)
        self.sim_entry.pack(side="left", padx=(4, 0))
        self._toggle_alpha()

        # Ziel-Ordner
        tgt = tk.Frame(c2, bg=PANEL)
        tgt.pack(fill="x", padx=18, pady=(0, 16))
        tk.Label(tgt, text="Ziel-Ordner", font=(FONT, 10, "bold"),
                 fg=TXT, bg=PANEL).pack(anchor="w")
        tgt2 = tk.Frame(tgt, bg=PANEL)
        tgt2.pack(fill="x", pady=(4, 0))
        self.out_entry = tk.Entry(tgt2, textvariable=self.out_dir, font=(FONT, 10),
                                  bg=PANEL_2, fg=TXT, insertbackground=ACCENT,
                                  relief="flat")
        self.out_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self._btn(tgt2, "…", self.pick_outdir).pack(side="left")

        # --- Card 2b: Sheet / Kontaktbogen ---
        c2b = self._card(parent)
        sh = tk.Frame(c2b, bg=PANEL)
        sh.pack(fill="x", padx=18, pady=16)

        tk.Checkbutton(
            sh, text="  Zusätzlich ein Sheet bauen  (Kontaktbogen / Sprite-Sheet)",
            variable=self.build_sheet_var, command=self._toggle_sheet,
            font=(FONT, 10, "bold"), fg=TXT, bg=PANEL, selectcolor=PANEL_2,
            activebackground=PANEL, activeforeground=ACCENT, highlightthickness=0,
            bd=0).pack(anchor="w")

        self.sheet_box = tk.Frame(sh, bg=PANEL)
        self.sheet_box.pack(fill="x", padx=(24, 0), pady=(8, 0))

        trow = tk.Frame(self.sheet_box, bg=PANEL)
        trow.pack(anchor="w")
        for val, txt in (("contact", "Kontaktbogen  (Raster + Nummern, dunkel)"),
                         ("sprite",  "Sprite-Sheet  (eng gepackt, transparent)")):
            rb = tk.Radiobutton(
                trow, text=txt, variable=self.sheet_type, value=val,
                command=self._toggle_sheet, font=(FONT, 10), fg=TXT, bg=PANEL,
                selectcolor=PANEL_2, activebackground=PANEL, activeforeground=ACCENT,
                highlightthickness=0, bd=0)
            rb.pack(side="left", padx=(0, 16))
            self._sheet_inputs.append(rb)

        grow = tk.Frame(self.sheet_box, bg=PANEL)
        grow.pack(anchor="w", pady=(6, 0))
        self.cols_auto_cb = tk.Checkbutton(
            grow, text="Spalten automatisch", variable=self.sheet_cols_auto,
            command=self._toggle_sheet, font=(FONT, 10), fg=TXT, bg=PANEL,
            selectcolor=PANEL_2, activebackground=PANEL, activeforeground=ACCENT,
            highlightthickness=0, bd=0)
        self.cols_auto_cb.pack(side="left")
        self._sheet_inputs.append(self.cols_auto_cb)
        self.cols_entry = tk.Entry(
            grow, textvariable=self.sheet_cols, width=4, font=(FONT, 10),
            bg=PANEL_2, fg=TXT, insertbackground=ACCENT, relief="flat",
            disabledbackground=PANEL, disabledforeground=TXT_DIM)
        self.cols_entry.pack(side="left", padx=(8, 4))
        tk.Label(grow, text="Spalten", font=(FONT, 10),
                 fg=TXT_DIM, bg=PANEL).pack(side="left")
        tk.Label(grow, text="      Thumb-Breite", font=(FONT, 10),
                 fg=TXT_DIM, bg=PANEL).pack(side="left")
        self.thumb_entry = tk.Entry(
            grow, textvariable=self.sheet_thumb, width=5, font=(FONT, 10),
            bg=PANEL_2, fg=TXT, insertbackground=ACCENT, relief="flat",
            disabledbackground=PANEL, disabledforeground=TXT_DIM)
        self.thumb_entry.pack(side="left", padx=(8, 4))
        tk.Label(grow, text="px  (0 = Original)", font=(FONT, 10),
                 fg=TXT_DIM, bg=PANEL).pack(side="left")

        self.del_cb = tk.Checkbutton(
            self.sheet_box,
            text="Einzel-Frames nach dem Sheet löschen (nur Sheet behalten)",
            variable=self.sheet_delete, font=(FONT, 10), fg=TXT_DIM, bg=PANEL,
            selectcolor=PANEL_2, activebackground=PANEL, activeforeground=DANGER,
            highlightthickness=0, bd=0)
        self.del_cb.pack(anchor="w", pady=(6, 0))
        self._sheet_inputs.append(self.del_cb)
        self._toggle_sheet()

        # --- Card 3: Aktion + Fortschritt ---
        c3 = self._card(parent)
        act = tk.Frame(c3, bg=PANEL)
        act.pack(fill="x", padx=18, pady=16)

        self.go_btn = self._btn(act, "▶  FRAMES EXTRAHIEREN", self.start, primary=True, big=True)
        self.go_btn.pack(side="left")
        self.cancel_btn = self._btn(act, "✕  Abbrechen", self.cancel, danger=True)
        self.cancel_btn.pack(side="left", padx=10)
        self.open_btn = self._btn(act, "📁  Ordner öffnen", self.open_folder)
        self.open_btn.pack(side="right")
        self._set_enabled(self.cancel_btn, False)
        self._set_enabled(self.open_btn, False)

        self.pbar = ttk.Progressbar(c3, style="Glow.Horizontal.TProgressbar",
                                    mode="determinate", maximum=100)
        self.pbar.pack(fill="x", padx=18, pady=(0, 6))
        self.status = tk.Label(c3, text="Bereit.", font=(FONT, 10),
                               fg=TXT_DIM, bg=PANEL, anchor="w")
        self.status.pack(fill="x", padx=18, pady=(0, 16))

    # ---------- kleine Stil-Helfer ----------
    def _entry(self, parent, var, width=8):
        return tk.Entry(parent, textvariable=var, width=width, font=(FONT, 10),
                        bg=PANEL_2, fg=TXT, insertbackground=ACCENT, relief="flat",
                        disabledbackground=PANEL, disabledforeground=TXT_DIM)

    def _radio(self, parent, text, var, val, cmd=None):
        return tk.Radiobutton(parent, text=text, variable=var, value=val, command=cmd,
                              font=(FONT, 10), fg=TXT, bg=PANEL, selectcolor=PANEL_2,
                              activebackground=PANEL, activeforeground=ACCENT,
                              highlightthickness=0, bd=0)

    def _check(self, parent, text, var, cmd=None, fg=TXT):
        return tk.Checkbutton(parent, text=text, variable=var, command=cmd,
                              font=(FONT, 10), fg=fg, bg=PANEL, selectcolor=PANEL_2,
                              activebackground=PANEL, activeforeground=ACCENT,
                              highlightthickness=0, bd=0)

    # ---------- Animations-Tab ----------
    def _build_animation_tab(self, parent):
        # --- Card A: Quelle ---
        cA = self._card(parent)
        box = tk.Frame(cA, bg=PANEL)
        box.pack(fill="x", padx=18, pady=16)
        tk.Label(box, text="Quelle", font=(FONT, 10, "bold"),
                 fg=TXT, bg=PANEL).pack(anchor="w")
        srow = tk.Frame(box, bg=PANEL)
        srow.pack(anchor="w", pady=(4, 8))
        self._radio(srow, "Frame-Ordner (PNG-Sequenz)", self.anim_src, "folder",
                    self._toggle_anim_src).pack(side="left", padx=(0, 16))
        self._radio(srow, "Sprite-Sheet (eine PNG)", self.anim_src, "sheet",
                    self._toggle_anim_src).pack(side="left")

        # Sub-Panel: Ordner
        self.anim_folder_box = tk.Frame(box, bg=PANEL)
        self.anim_folder_box.pack(fill="x")
        fe = self._entry(self.anim_folder_box, self.anim_folder)
        fe.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self._btn(self.anim_folder_box, "📂  Ordner …", self.pick_anim_folder).pack(side="left")

        # Sub-Panel: Sheet
        self.anim_sheet_box = tk.Frame(box, bg=PANEL)
        sline = tk.Frame(self.anim_sheet_box, bg=PANEL)
        sline.pack(fill="x")
        se = self._entry(sline, self.anim_sheet)
        se.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self._btn(sline, "🖼  PNG …", self.pick_anim_sheet).pack(side="left")
        grid = tk.Frame(self.anim_sheet_box, bg=PANEL)
        grid.pack(anchor="w", pady=(8, 0))
        tk.Label(grid, text="Spalten", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")
        e = self._entry(grid, self.anim_cols, 4); e.pack(side="left", padx=(6, 14))
        e.bind("<KeyRelease>", lambda ev: self._refresh_anim_count())
        tk.Label(grid, text="Zeilen", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")
        e2 = self._entry(grid, self.anim_rows, 4); e2.pack(side="left", padx=(6, 0))
        e2.bind("<KeyRelease>", lambda ev: self._refresh_anim_count())

        self.anim_count_lbl = tk.Label(box, text="", font=(FONT, 9), fg=ACCENT, bg=PANEL)
        self.anim_count_lbl.pack(anchor="w", pady=(8, 0))

        # --- Card B: Timing + Loop ---
        cB = self._card(parent)
        tb = tk.Frame(cB, bg=PANEL)
        tb.pack(fill="x", padx=18, pady=16)
        tk.Label(tb, text="Tempo", font=(FONT, 10, "bold"), fg=TXT, bg=PANEL).grid(
            row=0, column=0, sticky="w", columnspan=4)
        self._radio(tb, "FPS", self.anim_timing, "fps", self._toggle_anim_timing).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        self.anim_fps_entry = self._entry(tb, self.anim_fps, 5)
        self.anim_fps_entry.grid(row=1, column=1, sticky="w", padx=(6, 18), pady=(4, 0))
        self._radio(tb, "Bild-Dauer (ms)", self.anim_timing, "delay",
                    self._toggle_anim_timing).grid(row=1, column=2, sticky="w", pady=(4, 0))
        self.anim_delay_entry = self._entry(tb, self.anim_delay, 6)
        self.anim_delay_entry.grid(row=1, column=3, sticky="w", padx=(6, 0), pady=(4, 0))

        lp = tk.Frame(cB, bg=PANEL)
        lp.pack(fill="x", padx=18, pady=(0, 16))
        tk.Label(lp, text="Schleife", font=(FONT, 10, "bold"), fg=TXT, bg=PANEL).pack(anchor="w")
        lrow = tk.Frame(lp, bg=PANEL)
        lrow.pack(anchor="w", pady=(4, 0))
        self._radio(lrow, "Endlos", self.anim_loop, "inf", self._toggle_anim_loop).pack(side="left", padx=(0, 14))
        self._radio(lrow, "Anzahl", self.anim_loop, "n", self._toggle_anim_loop).pack(side="left")
        self.anim_loop_entry = self._entry(lrow, self.anim_loop_n, 5)
        self.anim_loop_entry.pack(side="left", padx=(6, 4))
        tk.Label(lrow, text="× wiederholen", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")

        # --- Card C: Ausgabe-Formate + Alpha ---
        cC = self._card(parent)
        fb = tk.Frame(cC, bg=PANEL)
        fb.pack(fill="x", padx=18, pady=16)
        tk.Label(fb, text="Ausgabe", font=(FONT, 10, "bold"), fg=TXT, bg=PANEL).pack(anchor="w")
        frow = tk.Frame(fb, bg=PANEL)
        frow.pack(anchor="w", pady=(4, 0))
        self._check(frow, "GIF", self.fmt_gif).pack(side="left", padx=(0, 14))
        self._check(frow, "APNG (.png)", self.fmt_apng).pack(side="left", padx=(0, 14))
        self._check(frow, "WebP", self.fmt_webp).pack(side="left")
        tk.Label(fb, justify="left", font=(FONT, 8), fg=TXT_DIM, bg=PANEL,
                 text="GIF = läuft überall (auch Windows-Fotos), aber harte 1-Bit-Kanten\n"
                      "WebP = echtes weiches Alpha UND läuft in Windows-11-Fotos  ← Empfehlung\n"
                      "APNG (.png) = echtes Alpha, spielt aber nur im Browser/modernen "
                      "Viewer (Windows-Fotos zeigt nur das 1. Bild)").pack(anchor="w", pady=(4, 0))

        arow = tk.Frame(cC, bg=PANEL)
        arow.pack(fill="x", padx=18, pady=(0, 6))
        tk.Label(arow, text="Alpha-Schwelle (GIF)", font=(FONT, 10),
                 fg=TXT_DIM, bg=PANEL).pack(side="left")
        self._entry(arow, self.anim_thresh, 5).pack(side="left", padx=(8, 4))
        tk.Label(arow, text="0–255  (niedriger = weichere Silhouette)",
                 font=(FONT, 9), fg=TXT_DIM, bg=PANEL).pack(side="left")

        mrow = tk.Frame(cC, bg=PANEL)
        mrow.pack(fill="x", padx=18, pady=(0, 16))
        self._check(mrow, "Matte-Farbe (GIF):", self.anim_matte_on,
                    self._toggle_anim_matte, fg=TXT_DIM).pack(side="left")
        self.anim_matte_sw = tk.Label(mrow, text="  ", bg=self.anim_matte_color.get(),
                                      width=3, relief="flat", cursor="hand2")
        self.anim_matte_sw.pack(side="left", padx=(6, 6))
        self.anim_matte_sw.bind("<Button-1>", lambda e: self._pick_anim_matte())
        self.anim_matte_entry = self._entry(mrow, self.anim_matte_color, 9)
        self.anim_matte_entry.pack(side="left")
        self.anim_matte_entry.bind("<KeyRelease>", lambda e: self._sync_anim_matte())
        tk.Label(mrow, text=" verrechnet Halbtransparenz → GIF wird quasi deckend",
                 font=(FONT, 8), fg=TXT_DIM, bg=PANEL).pack(side="left")

        # --- Card D: Transform ---
        cD = self._card(parent)
        tr = tk.Frame(cD, bg=PANEL)
        tr.pack(fill="x", padx=18, pady=16)
        srow2 = tk.Frame(tr, bg=PANEL)
        srow2.pack(fill="x")
        self._check(srow2, "Skalieren", self.anim_scale_on,
                    self._toggle_anim_scale).pack(side="left")
        self.anim_scale_entry = self._entry(srow2, self.anim_scale, 5)
        self.anim_scale_entry.pack(side="left", padx=(8, 4))
        tk.Label(srow2, text="%", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")
        tk.Label(srow2, text="     Richtung", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")
        self._radio(srow2, "Vorwärts", self.anim_dir, "fwd").pack(side="left", padx=(8, 6))
        self._radio(srow2, "Rückwärts", self.anim_dir, "rev").pack(side="left", padx=(0, 6))
        self._radio(srow2, "Boomerang", self.anim_dir, "boom").pack(side="left")

        trow2 = tk.Frame(tr, bg=PANEL)
        trow2.pack(fill="x", pady=(8, 0))
        tk.Label(trow2, text="Start-Frame", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")
        self._entry(trow2, self.anim_start, 5).pack(side="left", padx=(8, 16))
        tk.Label(trow2, text="End-Frame", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")
        self._entry(trow2, self.anim_end, 5).pack(side="left", padx=(8, 4))
        tk.Label(trow2, text="(leer = bis Ende)", font=(FONT, 9), fg=TXT_DIM, bg=PANEL).pack(side="left")

        nrow = tk.Frame(cD, bg=PANEL)
        nrow.pack(fill="x", padx=18, pady=(0, 16))
        tk.Label(nrow, text="Dateiname", font=(FONT, 10), fg=TXT_DIM, bg=PANEL).pack(side="left")
        self._entry(nrow, self.anim_basename, 18).pack(side="left", padx=(8, 0), ipady=2)

        self._toggle_anim_src()
        self._toggle_anim_timing()
        self._toggle_anim_loop()
        self._toggle_anim_matte()
        self._toggle_anim_scale()

        # --- Card E: Aktion + Fortschritt ---
        cE = self._card(parent)
        act = tk.Frame(cE, bg=PANEL)
        act.pack(fill="x", padx=18, pady=16)
        self.anim_go_btn = self._btn(act, "▶  ANIMATION BAUEN", self.start_anim,
                                     primary=True, big=True)
        self.anim_go_btn.pack(side="left")
        self.anim_cancel_btn = self._btn(act, "✕  Abbrechen", self.cancel_anim, danger=True)
        self.anim_cancel_btn.pack(side="left", padx=10)
        self.anim_open_btn = self._btn(act, "📁  Ordner öffnen", self.open_anim_folder)
        self.anim_open_btn.pack(side="right")
        self._set_enabled(self.anim_cancel_btn, False)
        self._set_enabled(self.anim_open_btn, False)
        self.anim_pbar = ttk.Progressbar(cE, style="Glow.Horizontal.TProgressbar",
                                         mode="determinate", maximum=100)
        self.anim_pbar.pack(fill="x", padx=18, pady=(0, 6))
        self.anim_status = tk.Label(cE, text="Bereit." if HAVE_PIL else
                                    "Pillow fehlt – Animation deaktiviert.",
                                    font=(FONT, 10), fg=TXT_DIM if HAVE_PIL else DANGER,
                                    bg=PANEL, anchor="w")
        self.anim_status.pack(fill="x", padx=18, pady=(0, 16))

    def _btn(self, parent, text, cmd, primary=False, danger=False, big=False):
        if primary:
            bg, fg, hv = ACCENT, "#04110f", ACCENT_HV
        elif danger:
            bg, fg, hv = PANEL_2, DANGER, "#22171b"
        else:
            bg, fg, hv = PANEL_2, TXT, STROKE
        b = tk.Label(parent, text=text, font=(FONT, 11 if not big else 12,
                     "bold"), fg=fg, bg=bg, padx=18 if not big else 24,
                     pady=9 if not big else 12, cursor="hand2")
        b._bg, b._hv = bg, hv
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=b._hv) if b._enabled else None)
        b.bind("<Leave>", lambda e: b.configure(bg=b._bg) if b._enabled else None)
        b._enabled = True
        return b

    def _set_enabled(self, btn, enabled):
        btn._enabled = enabled
        if enabled:
            btn.configure(bg=btn._bg, cursor="hand2", fg=btn.cget("fg"))
        else:
            btn.configure(bg=PANEL, cursor="arrow", fg=STROKE)

    # ---------- Drag & Drop (optional via tkinterdnd2) ----------
    def _enable_dnd(self):
        try:
            import tkinterdnd2  # noqa
            self.tk.call("package", "require", "tkdnd")
            self.drop.drop_target_register("DND_Files")
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # ohne tkinterdnd2: nur Button-Auswahl

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        if os.path.isfile(path):
            self.load_video(path)

    # ---------- Logik ----------
    def _toggle_fps(self):
        if self.every_frame.get():
            self.fps_entry.configure(state="disabled")
        else:
            self.fps_entry.configure(state="normal")

    def _toggle_alpha(self):
        chroma = self.alpha_mode.get() == "chroma"
        st = "normal" if chroma else "disabled"
        self.chroma_entry.configure(state=st)
        self.sim_entry.configure(state=st)
        self.swatch.configure(cursor="hand2" if chroma else "arrow")
        self._sync_swatch()

    def _sync_swatch(self):
        if self.alpha_mode.get() == "chroma":
            try:
                self.swatch.configure(bg=self.chroma_color.get().strip())
            except tk.TclError:
                pass
        else:
            self.swatch.configure(bg=PANEL_2)

    def _pick_color(self):
        if self.alpha_mode.get() != "chroma":
            return
        try:
            _, hx = colorchooser.askcolor(self.chroma_color.get(),
                                          title="Hintergrundfarbe zum Entfernen")
        except tk.TclError:
            _, hx = colorchooser.askcolor(title="Hintergrundfarbe zum Entfernen")
        if hx:
            self.chroma_color.set(hx)
            self._sync_swatch()

    def _toggle_sheet(self):
        on = self.build_sheet_var.get()
        st = "normal" if on else "disabled"
        for w in self._sheet_inputs:
            w.configure(state=st)
        self.thumb_entry.configure(state=st)
        if on and not self.sheet_cols_auto.get():
            self.cols_entry.configure(state="normal")
        else:
            self.cols_entry.configure(state="disabled")

    def pick_video(self):
        path = filedialog.askopenfilename(
            title="Video wählen",
            filetypes=[("Video-Dateien", " ".join("*" + e for e in VIDEO_EXTS)),
                       ("Alle Dateien", "*.*")])
        if path:
            self.load_video(path)

    def load_video(self, path):
        if os.path.splitext(path)[1].lower() not in VIDEO_EXTS:
            if not messagebox.askyesno(APP_NAME, "Unbekanntes Format – trotzdem versuchen?"):
                return
        self.video_path.set(path)
        name = os.path.basename(path)
        self.drop_lbl.configure(text="✓  geladen")
        self.file_lbl.configure(text=name)
        base = os.path.splitext(path)[0]
        self.out_dir.set(base + "_frames")
        self.set_status("Lese Video-Infos …", TXT_DIM)
        self._set_enabled(self.open_btn, False)
        threading.Thread(target=self._probe_async, args=(path,), daemon=True).start()

    def _probe_async(self, path):
        info = probe(path)
        self.msgq.put(("info", info))

    def _show_info(self, info):
        self.info = info
        parts = []
        if info.get("w"):
            parts.append(f"{info['w']}×{info['h']}")
        if info.get("fps"):
            parts.append(f"{info['fps']:.2f} fps")
        if info.get("duration"):
            parts.append(f"{info['duration']:.2f} s")
        if info.get("frames"):
            parts.append(f"≈ {info['frames']} Frames")
        self.info_lbl.configure(text="   ·   ".join(parts) if parts else "keine Infos")
        self.set_status("Bereit zum Extrahieren.", OK)

    def pick_outdir(self):
        d = filedialog.askdirectory(title="Ziel-Ordner wählen")
        if d:
            self.out_dir.set(d)

    # ==================== Animations-Tab Logik ====================
    def _toggle_anim_src(self):
        if self.anim_src.get() == "folder":
            self.anim_sheet_box.pack_forget()
            self.anim_folder_box.pack(fill="x")
        else:
            self.anim_folder_box.pack_forget()
            self.anim_sheet_box.pack(fill="x")
        self._autofill_anim()

    def _toggle_anim_timing(self):
        fps = self.anim_timing.get() == "fps"
        self.anim_fps_entry.configure(state="normal" if fps else "disabled")
        self.anim_delay_entry.configure(state="disabled" if fps else "normal")

    def _toggle_anim_loop(self):
        self.anim_loop_entry.configure(
            state="normal" if self.anim_loop.get() == "n" else "disabled")

    def _toggle_anim_matte(self):
        on = self.anim_matte_on.get()
        self.anim_matte_entry.configure(state="normal" if on else "disabled")
        self.anim_matte_sw.configure(cursor="hand2" if on else "arrow")
        self._sync_anim_matte()

    def _toggle_anim_scale(self):
        self.anim_scale_entry.configure(
            state="normal" if self.anim_scale_on.get() else "disabled")

    def _sync_anim_matte(self):
        if self.anim_matte_on.get():
            try:
                self.anim_matte_sw.configure(bg=self.anim_matte_color.get().strip())
            except tk.TclError:
                pass
        else:
            self.anim_matte_sw.configure(bg=PANEL_2)

    def _pick_anim_matte(self):
        if not self.anim_matte_on.get():
            return
        try:
            _, hx = colorchooser.askcolor(self.anim_matte_color.get(), title="Matte-Farbe")
        except tk.TclError:
            _, hx = colorchooser.askcolor(title="Matte-Farbe")
        if hx:
            self.anim_matte_color.set(hx)
            self._sync_anim_matte()

    def pick_anim_folder(self):
        d = filedialog.askdirectory(title="Frame-Ordner wählen")
        if d:
            self.anim_folder.set(d)
            self._autofill_anim()

    def pick_anim_sheet(self):
        p = filedialog.askopenfilename(title="Sprite-Sheet (PNG) wählen",
                                       filetypes=[("PNG", "*.png"), ("Alle", "*.*")])
        if p:
            self.anim_sheet.set(p)
            self._autofill_anim()

    @staticmethod
    def _fmt_fps(v):
        v = float(v)
        return str(int(round(v))) if abs(v - round(v)) < 0.02 else f"{v:.2f}"

    def _autofill_anim(self):
        """Erkennt aus der Quelle automatisch: Spalten/Zeilen (Sheet) + Quell-FPS."""
        msg, color = "", TXT_DIM
        try:
            if self.anim_src.get() == "folder":
                d = self.anim_folder.get().strip()
                if not d or not os.path.isdir(d):
                    msg, color = "Frame-Ordner wählen …", TXT_DIM
                else:
                    n = len(collect_frame_paths(d))
                    meta = read_folder_meta(d)
                    if meta and meta.get("fps"):
                        self.anim_fps.set(self._fmt_fps(meta["fps"]))
                        self.anim_timing.set("fps"); self._toggle_anim_timing()
                    if n:
                        extra = (f" · {self._fmt_fps(meta['fps'])} fps (Quelle)"
                                 if meta and meta.get("fps") else "")
                        msg, color = f"✓ {n} Frames erkannt{extra}", ACCENT
                    else:
                        msg, color = "keine frame_*.png gefunden", DANGER
            else:
                p = self.anim_sheet.get().strip()
                if not p or not os.path.isfile(p):
                    msg, color = "Sprite-Sheet (PNG) wählen …", TXT_DIM
                else:
                    g = detect_sheet_grid(p)
                    if g.get("cols"):
                        self.anim_cols.set(str(g["cols"]))
                        self.anim_rows.set(str(g["rows"]))
                    if g.get("fps"):
                        self.anim_fps.set(self._fmt_fps(g["fps"]))
                        self.anim_timing.set("fps"); self._toggle_anim_timing()
                    if g.get("auto") and g.get("cols"):
                        fpart = f" · {self._fmt_fps(g['fps'])} fps" if g.get("fps") else ""
                        msg, color = (
                            f"✓ Raster {g['cols']}×{g['rows']} automatisch erkannt{fpart}",
                            ACCENT)
                    else:
                        msg, color = ("Raster nicht erkannt – bitte Spalten/Zeilen angeben "
                                      "(oder Sheet neu bauen)", TXT_DIM)
        except (ValueError, tk.TclError, OSError):
            pass
        if msg:
            self.anim_count_lbl.configure(text=msg, fg=color)

    def _refresh_anim_count(self):
        try:
            if self.anim_src.get() == "folder":
                d = self.anim_folder.get().strip()
                n = len(collect_frame_paths(d)) if d and os.path.isdir(d) else 0
                self.anim_count_lbl.configure(
                    text=(f"✓ {n} Frames erkannt" if n else "keine frame_*.png gefunden"),
                    fg=ACCENT if n else DANGER)
            else:
                p = self.anim_sheet.get().strip()
                cols = int(self.anim_cols.get() or 0)
                rows = int(self.anim_rows.get() or 0)
                if p and os.path.isfile(p) and cols > 0 and rows > 0:
                    self.anim_count_lbl.configure(
                        text=f"Raster {cols}×{rows} = bis zu {cols * rows} Frames", fg=ACCENT)
                else:
                    self.anim_count_lbl.configure(
                        text="Sheet + Spalten/Zeilen angeben", fg=TXT_DIM)
        except (ValueError, tk.TclError):
            self.anim_count_lbl.configure(text="", fg=TXT_DIM)

    def set_anim_status(self, text, color=TXT_DIM):
        self.anim_status.configure(text=text, fg=color)

    def _finish_anim(self):
        self._set_enabled(self.anim_go_btn, True)
        self._set_enabled(self.anim_cancel_btn, False)
        self._set_enabled(self.anim_open_btn, True)

    def _anim_out_dir(self):
        if self.anim_src.get() == "folder":
            return self.anim_folder.get().strip()
        return os.path.dirname(self.anim_sheet.get().strip())

    def open_anim_folder(self):
        if self.anim_open_btn._enabled:
            d = self._anim_out_dir()
            if os.path.isdir(d):
                os.startfile(d)

    def cancel_anim(self):
        if self.anim_cancel_btn._enabled:
            self._anim_cancel.set()
            self.set_anim_status("Wird abgebrochen …", DANGER)

    def start_anim(self):
        if not self.anim_go_btn._enabled:
            return
        if not HAVE_PIL:
            messagebox.showerror(APP_NAME, "Animationen brauchen Pillow:\n pip install Pillow")
            return
        if (self.worker and self.worker.is_alive()) or \
           (self.anim_worker and self.anim_worker.is_alive()):
            messagebox.showinfo(APP_NAME, "Es läuft bereits ein Vorgang.")
            return

        src = self.anim_src.get()
        if src == "folder":
            folder = self.anim_folder.get().strip()
            if not folder or not os.path.isdir(folder):
                messagebox.showwarning(APP_NAME, "Bitte einen Frame-Ordner wählen.")
                return
            if not collect_frame_paths(folder):
                messagebox.showwarning(
                    APP_NAME, "Keine frame_*.png im Ordner.\nEvtl. wurden die Frames nach "
                    "dem Sheet gelöscht – bitte neu extrahieren oder ein Sprite-Sheet nutzen.")
                return
            sheet_arg, out_dir = None, folder
        else:
            sheet = self.anim_sheet.get().strip()
            if not sheet or not os.path.isfile(sheet):
                messagebox.showwarning(APP_NAME, "Bitte ein Sprite-Sheet (PNG) wählen.")
                return
            try:
                cols = int(self.anim_cols.get()); rows = int(self.anim_rows.get())
                assert cols > 0 and rows > 0
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_NAME, "Spalten und Zeilen (>0) angeben.")
                return
            sheet_arg, out_dir = (sheet, cols, rows), os.path.dirname(sheet)

        if self.anim_timing.get() == "fps":
            try:
                fps = float(self.anim_fps.get().replace(",", ".")); assert fps > 0
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_NAME, "Ungültige FPS."); return
            delay_ms = 1000.0 / fps
        else:
            try:
                delay_ms = float(self.anim_delay.get().replace(",", ".")); assert delay_ms > 0
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_NAME, "Ungültige Bild-Dauer."); return

        if self.anim_loop.get() == "inf":
            loop = 0
        else:
            try:
                loop = int(self.anim_loop_n.get()); assert loop >= 1
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_NAME, "Schleifen-Anzahl ≥ 1 angeben."); return

        try:
            thr = int(self.anim_thresh.get()); assert 0 <= thr <= 255
        except (ValueError, AssertionError):
            messagebox.showwarning(APP_NAME, "Alpha-Schwelle 0–255 angeben."); return

        scale = None
        if self.anim_scale_on.get():
            try:
                scale = float(self.anim_scale.get().replace(",", ".")); assert scale > 0
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_NAME, "Ungültige Skalierung."); return

        try:
            start = int(self.anim_start.get() or 1)
            end = int(self.anim_end.get()) if self.anim_end.get().strip() else None
        except ValueError:
            messagebox.showwarning(APP_NAME, "Start/End-Frame müssen Zahlen sein."); return

        fmts = [f for f, on in (("gif", self.fmt_gif.get()),
                                ("png", self.fmt_apng.get()),
                                ("webp", self.fmt_webp.get())) if on]
        if not fmts:
            messagebox.showwarning(APP_NAME, "Mindestens ein Ausgabeformat wählen."); return

        base = os.path.splitext(os.path.basename(self.anim_basename.get().strip()))[0] or "animation"
        outputs = {f: os.path.join(out_dir, base + "." + f) for f in fmts}

        prot = set()
        if sheet_arg:
            prot.add(os.path.abspath(sheet_arg[0]))
        else:
            prot.update(os.path.abspath(p) for p in collect_frame_paths(out_dir))
        if any(os.path.abspath(p) in prot for p in outputs.values()):
            messagebox.showwarning(
                APP_NAME, "Der Dateiname würde eine Quelldatei überschreiben – bitte umbenennen.")
            return
        exist = [os.path.basename(p) for p in outputs.values() if os.path.exists(p)]
        if exist and not messagebox.askyesno(APP_NAME, "Überschreiben?\n" + ", ".join(exist)):
            return

        matte = None
        if self.anim_matte_on.get():
            hexc = self.anim_matte_color.get().strip().lstrip("#")
            if len(hexc) == 6:
                try:
                    matte = tuple(int(hexc[i:i + 2], 16) for i in (0, 2, 4))
                except ValueError:
                    matte = None

        opts = {
            "source": src, "folder": (folder if src == "folder" else None),
            "sheet": sheet_arg, "out_dir": out_dir, "outputs": outputs, "formats": fmts,
            "delay_ms": delay_ms, "loop": loop, "thresh": thr, "matte": matte,
            "scale": scale, "direction": self.anim_dir.get(), "start": start, "end": end,
        }
        self._anim_cancel.clear()
        self.anim_pbar.configure(value=0)
        self.set_anim_status("Lade Frames …", ACCENT)
        self._set_enabled(self.anim_go_btn, False)
        self._set_enabled(self.anim_cancel_btn, True)
        self._set_enabled(self.anim_open_btn, False)
        self.anim_worker = threading.Thread(target=self._run_anim, args=(opts,), daemon=True)
        self.anim_worker.start()

    def _run_anim(self, o):
        try:
            if o["source"] == "folder":
                paths = collect_frame_paths(o["folder"])
                if not paths:
                    raise ValueError("Keine frame_*.png gefunden.")
                frames = []
                for i, p in enumerate(paths):
                    if self._anim_cancel.is_set():
                        self.msgq.put(("animcancelled", o["out_dir"])); return
                    frames.append(Image.open(p).convert("RGBA").copy())
                    if i % 5 == 0:
                        self.msgq.put(("animprog", i * 35.0 / len(paths), i, len(paths)))
            else:
                self.msgq.put(("animstatus", "Zerschneide Sheet …"))
                sheet, cols, rows = o["sheet"]
                frames = slice_sprite_sheet(sheet, cols, rows)

            s = max(1, o["start"]); e = o["end"] or len(frames)
            frames = frames[s - 1:e]
            if not frames:
                raise ValueError("Trim ergibt 0 Frames.")

            if o["scale"] and abs(o["scale"] - 100) > 1e-6:
                nw = max(1, round(frames[0].width * o["scale"] / 100.0))
                nh = max(1, round(frames[0].height * o["scale"] / 100.0))
                frames = [f.resize((nw, nh), Image.LANCZOS) for f in frames]

            if o["direction"] == "rev":
                frames = frames[::-1]
            elif o["direction"] == "boom":
                if len(frames) >= 3:
                    frames = frames + frames[-2:0:-1]
                else:
                    self.msgq.put(("animstatus", "Boomerang braucht ≥3 Frames – vorwärts."))

            apng_webp_delay = max(1, int(round(o["delay_ms"])))
            gif_delay = max(10, int(round(o["delay_ms"] / 10.0) * 10))   # Zentisekunden

            made = []
            for idx, fmt in enumerate(o["formats"]):
                if self._anim_cancel.is_set():
                    self.msgq.put(("animcancelled", o["out_dir"])); return
                out = o["outputs"][fmt]
                self.msgq.put(("animstatus",
                               f"Schreibe {('APNG' if fmt == 'png' else fmt.upper())} …"))
                if fmt == "gif":
                    _save_gif_ffmpeg(frames, out, gif_delay, o["loop"], o["thresh"], o["matte"])
                elif fmt == "png":
                    _save_apng(frames, out, apng_webp_delay, o["loop"])
                elif fmt == "webp":
                    _save_webp(frames, out, apng_webp_delay, o["loop"])
                made.append(out)
                self.msgq.put(("animprog", 40 + (idx + 1) * 60.0 / len(o["formats"]),
                               idx + 1, len(o["formats"])))
            self.msgq.put(("animdone", o["out_dir"], made, len(frames)))
        except Exception as ex:
            self.msgq.put(("animerror", str(ex)))

    def start(self):
        if not self.go_btn._enabled:
            return
        if not FFMPEG:
            messagebox.showerror(APP_NAME, "ffmpeg wurde nicht gefunden.")
            return
        if (self.worker and self.worker.is_alive()) or \
           (self.anim_worker and self.anim_worker.is_alive()):
            messagebox.showinfo(APP_NAME, "Es läuft bereits ein Vorgang.")
            return
        path = self.video_path.get()
        if not path or not os.path.isfile(path):
            messagebox.showwarning(APP_NAME, "Bitte zuerst ein Video wählen.")
            return
        out = self.out_dir.get().strip()
        if not out:
            messagebox.showwarning(APP_NAME, "Bitte einen Ziel-Ordner angeben.")
            return
        os.makedirs(out, exist_ok=True)
        # Warnung wenn Ordner schon Bilder enthaelt
        existing = [f for f in os.listdir(out) if f.lower().startswith("frame_")]
        if existing:
            if not messagebox.askyesno(
                APP_NAME,
                f"Im Ziel-Ordner liegen schon {len(existing)} Frame-Bilder.\n"
                "Überschreiben / ergänzen?"):
                return

        alpha_mode = self.alpha_mode.get()
        alpha_active = alpha_mode in ("keep", "chroma")

        spec = FORMATS[self.fmt.get()]
        ext = spec["ext"]
        # Alpha braucht ein Format mit Transparenz -> ggf. auf PNG umstellen
        if alpha_active and ext not in ("png", "webp", "tiff"):
            self.fmt.set("PNG (verlustfrei)")
            spec = FORMATS["PNG (verlustfrei)"]
            ext = spec["ext"]
            self.set_status("Format für Alpha auf PNG umgestellt.", TXT_DIM)
        pattern = os.path.join(out, "frame_%06d." + ext)

        cmd = [FFMPEG, "-hide_banner", "-nostats", "-progress", "pipe:1",
               "-y", "-i", path]
        filters = []
        if self.every_frame.get():
            cmd += ["-fps_mode", "passthrough"]
            total = self.info.get("frames")
            play_fps = self.info.get("fps")          # natürliche Abspiel-FPS = Quell-FPS
        else:
            try:
                fps = float(self.fps_value.get().replace(",", "."))
                assert fps > 0
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_NAME, "Ungültiger FPS-Wert.")
                return
            filters.append(f"fps={fps}")
            dur = self.info.get("duration") or 0
            total = max(1, round(fps * dur)) if dur else None
            play_fps = fps
        if alpha_mode == "chroma":
            hexc = self.chroma_color.get().strip().lstrip("#")
            if len(hexc) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in hexc):
                messagebox.showwarning(APP_NAME, "Ungültige Farbe (Hex, z. B. #00FF00).")
                return
            try:
                sim = float(self.chroma_sim.get().replace(",", "."))
                assert 0 < sim <= 1
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_NAME, "Toleranz muss zwischen 0 und 1 liegen.")
                return
            filters.append(f"colorkey=0x{hexc}:{sim}:0.10")
        if filters:
            cmd += ["-vf", ",".join(filters)]
        cmd += spec["args"]
        if alpha_active:
            cmd += ["-pix_fmt", "rgba"]
        cmd += ["-start_number", "1", pattern]

        sheet_opts = None
        if self.build_sheet_var.get():
            if not HAVE_PIL:
                messagebox.showerror(APP_NAME, "Für Sheets wird Pillow benötigt:\n"
                                     "pip install Pillow")
                return
            try:
                cols = 0 if self.sheet_cols_auto.get() else int(self.sheet_cols.get())
            except ValueError:
                messagebox.showwarning(APP_NAME, "Ungültige Spalten-Zahl.")
                return
            try:
                thumb = int(self.sheet_thumb.get())
            except ValueError:
                messagebox.showwarning(APP_NAME, "Ungültige Thumb-Breite.")
                return
            sheet_opts = {
                "mode": self.sheet_type.get(),
                "columns": max(0, cols),
                "thumb_w": max(0, thumb),
                "delete_after": self.sheet_delete.get(),
                "title": os.path.basename(path),
                "transparent": alpha_active,
                "fps": play_fps,
            }

        self._cancel.clear()
        self.pbar.configure(value=0)
        self.set_status("Extrahiere …", ACCENT)
        self._set_enabled(self.go_btn, False)
        self._set_enabled(self.cancel_btn, True)
        self._set_enabled(self.open_btn, False)

        self.worker = threading.Thread(
            target=self._run_ffmpeg, args=(cmd, total, out, ext, sheet_opts, play_fps),
            daemon=True)
        self.worker.start()

    def _run_ffmpeg(self, cmd, total, out, ext, sheet_opts=None, play_fps=None):
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
            cur = 0
            for line in self.proc.stdout:
                if self._cancel.is_set():
                    self.proc.terminate()
                    break
                line = line.strip()
                if line.startswith("frame="):
                    try:
                        cur = int(line.split("=", 1)[1])
                    except ValueError:
                        pass
                    if total:
                        pct = min(100, cur * 100 / total)
                        self.msgq.put(("progress", pct, cur, total))
                    else:
                        self.msgq.put(("progress", None, cur, None))
                elif line == "progress=end":
                    break
            ret = self.proc.wait()
            if self._cancel.is_set():
                self.msgq.put(("cancelled", out))
                return
            if ret != 0:
                self.msgq.put(("error", f"ffmpeg Exit-Code {ret}"))
                return

            frames = sorted(
                os.path.join(out, f) for f in os.listdir(out)
                if f.lower().startswith("frame_") and f.lower().endswith("." + ext))
            count = len(frames)

            # Sidecar mit Quell-FPS -> Animations-Tab spielt in Original-Tempo ab
            try:
                with open(os.path.join(out, "_framegrabber.json"), "w",
                          encoding="utf-8") as jf:
                    json.dump({"fps": play_fps, "frames": count}, jf)
            except OSError:
                pass

            sheet_path = None
            if sheet_opts and count:
                sprite = sheet_opts["mode"] == "sprite"
                self.msgq.put(("status", "Baue %s aus %d Frames …"
                               % ("Sprite-Sheet" if sprite else "Kontaktbogen", count)))
                name = "sprite_sheet.png" if sprite else "kontaktbogen.png"
                sheet_path = os.path.join(out, name)
                build_sheet(
                    frames, sheet_path, mode=sheet_opts["mode"],
                    columns=sheet_opts["columns"], thumb_w=sheet_opts["thumb_w"],
                    title=sheet_opts["title"],
                    transparent_bg=sheet_opts.get("transparent", False),
                    source_fps=sheet_opts.get("fps"),
                    progress_cb=lambda i, t: self.msgq.put(
                        ("sheetprog", i * 100 / t, i, t)))
                if sheet_opts["delete_after"]:
                    for fp in frames:
                        try:
                            os.remove(fp)
                        except OSError:
                            pass
            self.msgq.put(("done", out, count, sheet_path))
        except Exception as e:
            self.msgq.put(("error", str(e)))
        finally:
            self.proc = None

    def cancel(self):
        if self.cancel_btn._enabled:
            self._cancel.set()
            self.set_status("Wird abgebrochen …", DANGER)

    def open_folder(self):
        if not self.open_btn._enabled:
            return
        d = self.out_dir.get()
        if os.path.isdir(d):
            os.startfile(d)

    # ---------- Queue / Status ----------
    def set_status(self, text, color=TXT_DIM):
        self.status.configure(text=text, fg=color)

    def _poll_queue(self):
        try:
            while True:
                msg = self.msgq.get_nowait()
                kind = msg[0]
                if kind == "info":
                    self._show_info(msg[1])
                elif kind == "progress":
                    pct, cur, total = msg[1], msg[2], msg[3]
                    if pct is not None:
                        self.pbar.configure(mode="determinate", value=pct)
                        self.set_status(f"Frame {cur} / {total}   ·   {pct:.0f} %", ACCENT)
                    else:
                        self.pbar.configure(mode="indeterminate")
                        self.pbar.step(4)
                        self.set_status(f"Frame {cur} …", ACCENT)
                elif kind == "status":
                    self.set_status(msg[1], ACCENT_2)
                elif kind == "sheetprog":
                    self.pbar.configure(mode="determinate", value=msg[1])
                    self.set_status(f"Baue Sheet …  {msg[2]} / {msg[3]}", ACCENT_2)
                elif kind == "done":
                    out, count, sheet_path = msg[1], msg[2], msg[3]
                    self.pbar.configure(mode="determinate", value=100)
                    if sheet_path:
                        self.set_status(
                            f"✓ Fertig – {count} Frames + Sheet gespeichert.", OK)
                    else:
                        self.set_status(f"✓ Fertig – {count} Frames gespeichert.", OK)
                    self._finish()
                    self.open_folder()
                elif kind == "cancelled":
                    self.set_status("Abgebrochen.", DANGER)
                    self.pbar.configure(value=0)
                    self._finish()
                elif kind == "error":
                    self.set_status("Fehler: " + msg[1], DANGER)
                    self._finish()
                    messagebox.showerror(APP_NAME, msg[1])
                # ---- Animations-Tab (eigene Nachrichten-Arten) ----
                elif kind == "animprog":
                    self.anim_pbar.configure(mode="determinate", value=msg[1])
                    self.set_anim_status(f"Lade Frame {msg[2]} / {msg[3]} …", ACCENT)
                elif kind == "animstatus":
                    self.set_anim_status(msg[1], ACCENT_2)
                elif kind == "animdone":
                    out, made, nframes = msg[1], msg[2], msg[3]
                    self.anim_pbar.configure(mode="determinate", value=100)
                    names = ", ".join(os.path.basename(p) for p in made)
                    self.set_anim_status(f"✓ Fertig – {nframes} Frames → {names}", OK)
                    self._finish_anim()
                    if os.path.isdir(out):
                        os.startfile(out)
                elif kind == "animcancelled":
                    self.set_anim_status("Abgebrochen.", DANGER)
                    self.anim_pbar.configure(value=0)
                    self._finish_anim()
                elif kind == "animerror":
                    self.set_anim_status("Fehler: " + msg[1], DANGER)
                    self._finish_anim()
                    messagebox.showerror(APP_NAME, msg[1])
        except queue.Empty:
            pass
        self.after(60, self._poll_queue)

    def _finish(self):
        self._set_enabled(self.go_btn, True)
        self._set_enabled(self.cancel_btn, False)
        self._set_enabled(self.open_btn, True)


if __name__ == "__main__":
    app = FrameGrabber()
    app.mainloop()
