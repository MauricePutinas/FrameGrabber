@echo off
title FrameGrabber
cd /d "%~dp0"
echo Starte FrameGrabber ...
start "" pythonw "%~dp0framegrabber.py"
exit
