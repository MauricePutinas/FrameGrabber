# -*- coding: utf-8 -*-
"""
FrameGrabber Animator CLI – aus Frames/Sprite-Sheet alpha-transparente
Animationen (GIF / APNG / WebP) bauen, ohne GUI.

Beispiele:
  python frameanim_cli.py mein_video_frames --gif --apng
  python frameanim_cli.py sheet.png --cols 8 --rows 4 --webp --fps 15
  python frameanim_cli.py frames --boom --scale 50 -o loop
"""
import os
import sys
import argparse

# Engine + Helfer aus dem Hauptmodul wiederverwenden
import framegrabber as fg
from PIL import Image


def main():
    ap = argparse.ArgumentParser(
        description="Frames/Sprite-Sheet -> alpha-transparente Animation (GIF/APNG/WebP).")
    ap.add_argument("src", help="Frame-Ordner ODER eine Sprite-Sheet-PNG")
    ap.add_argument("--cols", type=int, default=0, help="Sheet: Spalten")
    ap.add_argument("--rows", type=int, default=0, help="Sheet: Zeilen")
    ap.add_argument("--fps", type=float, default=12.0, help="Bilder/Sekunde (Standard 12)")
    ap.add_argument("--loop", type=int, default=0, help="0 = endlos, N = Wiederholungen")
    ap.add_argument("--gif", action="store_true")
    ap.add_argument("--apng", action="store_true")
    ap.add_argument("--webp", action="store_true")
    ap.add_argument("--thresh", type=int, default=128, help="GIF Alpha-Schwelle 0–255")
    ap.add_argument("--matte", default=None, help="GIF: Hintergrundfarbe (#rrggbb) verrechnen")
    ap.add_argument("--scale", type=float, default=100.0, help="Skalierung in %%")
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--boom", action="store_true", help="Boomerang (ping-pong)")
    ap.add_argument("--start", type=int, default=1, help="Start-Frame (1-basiert)")
    ap.add_argument("--end", type=int, default=None, help="End-Frame (inklusive)")
    ap.add_argument("-o", "--name", default="animation", help="Ausgabe-Basisname")
    args = ap.parse_args()

    if not fg.HAVE_PIL:
        sys.exit("Pillow fehlt – bitte 'pip install Pillow'.")

    # --- Frames laden ---
    if os.path.isdir(args.src):
        paths = fg.collect_frame_paths(args.src)
        if not paths:
            sys.exit("Keine frame_*.png im Ordner.")
        frames = [Image.open(p).convert("RGBA").copy() for p in paths]
        out_dir = args.src
    elif os.path.isfile(args.src):
        if args.cols < 1 or args.rows < 1:
            sys.exit("Sprite-Sheet braucht --cols und --rows.")
        frames = fg.slice_sprite_sheet(args.src, args.cols, args.rows)
        out_dir = os.path.dirname(args.src) or "."
    else:
        sys.exit("Quelle nicht gefunden: " + args.src)

    # --- Trim / Scale / Richtung ---
    s = max(1, args.start); e = args.end or len(frames)
    frames = frames[s - 1:e]
    if not frames:
        sys.exit("Trim ergibt 0 Frames.")
    if abs(args.scale - 100) > 1e-6:
        nw = max(1, round(frames[0].width * args.scale / 100.0))
        nh = max(1, round(frames[0].height * args.scale / 100.0))
        frames = [f.resize((nw, nh), Image.LANCZOS) for f in frames]
    if args.reverse:
        frames = frames[::-1]
    elif args.boom:
        if len(frames) >= 3:
            frames = frames + frames[-2:0:-1]
        else:
            print("Hinweis: Boomerang braucht >= 3 Frames – nutze vorwärts.")

    # --- Formate (Default: gif + apng) ---
    fmts = [f for f, on in (("gif", args.gif), ("png", args.apng), ("webp", args.webp)) if on]
    if not fmts:
        fmts = ["gif", "png"]

    matte = None
    if args.matte:
        h = args.matte.strip().lstrip("#")
        if len(h) == 6:
            matte = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    delay_ms = 1000.0 / args.fps
    apng_webp_delay = max(1, int(round(delay_ms)))
    gif_delay = max(10, int(round(delay_ms / 10.0) * 10))

    for fmt in fmts:
        out = os.path.join(out_dir, args.name + "." + fmt)
        print(f"Schreibe {('APNG' if fmt == 'png' else fmt.upper())} -> {out}")
        if fmt == "gif":
            fg._save_gif_ffmpeg(frames, out, gif_delay, args.loop, args.thresh, matte)
        elif fmt == "png":
            fg._save_apng(frames, out, apng_webp_delay, args.loop)
        elif fmt == "webp":
            fg._save_webp(frames, out, apng_webp_delay, args.loop)
    print(f"Fertig: {len(frames)} Frames, {len(fmts)} Datei(en).")


if __name__ == "__main__":
    main()
