# VMA Subtitle Tool (Windows EXE build)

This tool converts videos into bilingual SRT subtitles (English + Traditional Chinese).

## Usage
1. Install Python 3.10+ and ffmpeg on Windows (ensure ffmpeg is in PATH).
2. Install requirements: `pip install -r requirements.txt`
3. Run: `python main.py`
4. GUI will open, select video, enter OpenAI API Key, click Start.
5. SRT file will be created next to video.

## Build EXE
Use PyInstaller:
```
pyinstaller --noconfirm --onefile main.py
```
The EXE will appear under `dist\main.exe`.

## GitHub Actions Build
A workflow file is included under `.github/workflows/build-windows.yml` to automatically build the EXE on push.
