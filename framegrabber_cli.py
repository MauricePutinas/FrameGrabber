# -*- coding: utf-8 -*-
"""
FrameGrabber CLI - jeden Frame eines Clips speichern, ohne GUI.

Beispiele:
  python framegrabber_cli.py clip.mp4
  python framegrabber_cli.py clip.mp4 -o out_ordner --format jpg
  python framegrabber_cli.py clip.mp4 --fps 12     (nur 12 Bilder/Sekunde)
  python framegrabber_cli.py clip.mp4 --alpha keep --sheet sprite   (Quell-Alpha erhalten)
  python framegrabber_cli.py greenscreen.mp4 --alpha chroma --key-color "#00FF00" --sheet contact
"""
import os
import sys
import shutil
import argparse
import subprocess

EXTS = {"png": ["-compression_level", "3"],
        "jpg": ["-q:v", "2"],
        "webp": ["-quality", "90"],
        "bmp": [], "tiff": []}


def find(name):
    return (shutil.which(name)
            or next((p for p in (rf"C:\ProgramData\chocolatey\bin\{name}.exe",
                                 rf"C:\ffmpeg\bin\{name}.exe") if os.path.isfile(p)), None))


def main():
    ap = argparse.ArgumentParser(description="Jeden Frame eines Clips als Bild speichern.")
    ap.add_argument("video", help="Pfad zum Video")
    ap.add_argument("-o", "--out", help="Ziel-Ordner (Standard: <video>_frames)")
    ap.add_argument("--format", default="png", choices=list(EXTS), help="Bildformat")
    ap.add_argument("--fps", type=float, default=None,
                    help="Nur N Bilder/Sek statt jeder Frame")
    ap.add_argument("--sheet", choices=["contact", "sprite"], default=None,
                    help="Zusätzlich ein Sheet bauen (contact=Kontaktbogen, sprite=Sprite-Sheet)")
    ap.add_argument("--cols", type=int, default=0, help="Spalten im Sheet (0 = automatisch)")
    ap.add_argument("--thumb", type=int, default=240,
                    help="Thumb-Breite im Sheet in px (0 = Originalgröße)")
    ap.add_argument("--only-sheet", action="store_true",
                    help="Einzel-Frames nach dem Sheet löschen")
    ap.add_argument("--alpha", choices=["off", "keep", "chroma"], default="off",
                    help="Transparenz: keep=Quell-Alpha erhalten, chroma=Farbe entfernen")
    ap.add_argument("--key-color", default="#00FF00",
                    help="Chroma-Key Farbe (Hex, z. B. #00FF00)")
    ap.add_argument("--key-sim", type=float, default=0.30,
                    help="Chroma-Key Toleranz 0..1 (Standard 0.30)")
    args = ap.parse_args()

    ffmpeg = find("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg nicht gefunden.")
    if not os.path.isfile(args.video):
        sys.exit("Video nicht gefunden: " + args.video)

    alpha_active = args.alpha in ("keep", "chroma")
    fmt = args.format
    if alpha_active and fmt not in ("png", "webp", "tiff"):
        print(f"Hinweis: Format '{fmt}' kann kein Alpha – nutze PNG.")
        fmt = "png"

    out = args.out or (os.path.splitext(args.video)[0] + "_frames")
    os.makedirs(out, exist_ok=True)
    pattern = os.path.join(out, "frame_%06d." + fmt)

    cmd = [ffmpeg, "-hide_banner", "-y", "-i", args.video]
    filters = []
    if args.fps:
        filters.append(f"fps={args.fps}")
    else:
        cmd += ["-fps_mode", "passthrough"]
    if args.alpha == "chroma":
        hexc = args.key_color.strip().lstrip("#")
        filters.append(f"colorkey=0x{hexc}:{args.key_sim}:0.10")
    if filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += EXTS[fmt]
    if alpha_active:
        cmd += ["-pix_fmt", "rgba"]
    cmd += ["-start_number", "1", pattern]

    print("Extrahiere Frames ->", out)
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        sys.exit("ffmpeg Fehler, Code " + str(rc))

    frames = sorted(os.path.join(out, f) for f in os.listdir(out)
                    if f.startswith("frame_") and f.endswith("." + fmt))
    print(f"Fertig: {len(frames)} Frames gespeichert.")

    if args.sheet:
        from framegrabber import build_sheet  # gemeinsame Sheet-Engine
        name = "sprite_sheet.png" if args.sheet == "sprite" else "kontaktbogen.png"
        sheet_path = os.path.join(out, name)
        build_sheet(frames, sheet_path, mode=args.sheet, columns=args.cols,
                    thumb_w=args.thumb, title=os.path.basename(args.video),
                    transparent_bg=alpha_active)
        print("Sheet gebaut ->", sheet_path)
        if args.only_sheet:
            for fp in frames:
                try:
                    os.remove(fp)
                except OSError:
                    pass
            print("Einzel-Frames gelöscht (nur Sheet behalten).")


if __name__ == "__main__":
    main()
