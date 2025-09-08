#!/usr/bin/env python3
"""VMA Subtitle Tool - Windows GUI

Features:
- Select a video file
- Uses OpenAI speech-to-text (whisper-1) by default (requires OPENAI_API_KEY)
- Splits long videos into chunks to handle >30 minutes
- Translates English -> Traditional Chinese using googletrans
- Outputs bilingual SRT (English line, Chinese line)
- Designed to be packaged into a Windows .exe with PyInstaller
"""

import os
import sys
import time
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

# Optional dependencies (import at runtime so exe build bundles them)
try:
    import moviepy.editor as mpy
except Exception:
    mpy = None

try:
    from googletrans import Translator
except Exception:
    Translator = None

try:
    import openai
except Exception:
    openai = None

CHUNK_SECONDS = 5 * 60  # 5 minutes per chunk

def seconds_to_srt_timestamp(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def split_audio(video_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / "full_audio.wav"
    # use moviepy if available
    if mpy is not None:
        clip = mpy.VideoFileClip(str(video_path))
        clip.audio.write_audiofile(str(audio_path))
        duration = clip.duration
        clip.reader.close()
        clip.audio.reader.close_proc()
    else:
        # fallback: use ffmpeg to extract wav
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path)
        ]
        subprocess.check_call(cmd)
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
               "default=noprint_wrappers=1:nokey=1", str(audio_path)]
        duration = float(subprocess.check_output(cmd).decode().strip())

    chunks = []
    idx = 0
    start = 0.0
    while start < duration:
        end = min(duration, start + CHUNK_SECONDS)
        chunk_path = out_dir / f"chunk_{idx:03d}.wav"
        # re-encode chunk to ensure compatibility
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-ss", str(start), "-to", str(end),
            "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            str(chunk_path)
        ]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        chunks.append((float(start), float(end), str(chunk_path)))
        idx += 1
        start += CHUNK_SECONDS
    return chunks

def transcribe_chunk_openai(chunk_path, model="whisper-1", api_key=None):
    if openai is None:
        raise RuntimeError("openai library not installed")
    if api_key is None:
        raise RuntimeError("OpenAI API key not set")
    openai.api_key = api_key
    with open(chunk_path, "rb") as f:
        try:
            res = openai.Audio.transcribe(model, f)
            text = res.get("text") or ""
            segments = res.get("segments") or []
            return text, segments
        except Exception:
            # try alternate method if SDK version differs
            res = openai.Transcription.create(file=f, model=model)
            text = res.get("text") or ""
            segments = res.get("segments") or []
            return text, segments

def translate_text(text, translator):
    if translator is None:
        return text
    try:
        return translator.translate(text, src="en", dest="zh-tw").text
    except Exception:
        return text

def segments_to_srt(all_segments, srt_path):
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(all_segments, start=1):
            start_ts = seconds_to_srt_timestamp(seg["start"])
            end_ts = seconds_to_srt_timestamp(seg["end"])
            eng = seg["text"].strip()
            chi = seg.get("zh", "").strip()
            f.write(f"{i}\n{start_ts} --> {end_ts}\n{eng}\n{chi}\n\n")

def process_file(video_path, api_key, use_openai=True, output_dir=None, progress_callback=None):
    video_path = Path(video_path)
    output_dir = Path(output_dir or video_path.parent)
    work_dir = output_dir / (video_path.stem + "_work")
    work_dir.mkdir(parents=True, exist_ok=True)
    chunks = split_audio(video_path, work_dir)
    translator = Translator() if Translator is not None else None

    all_segments = []
    total_chunks = len(chunks)
    for idx, (start, end, chunk_path) in enumerate(chunks):
        if progress_callback:
            progress_callback(f"Transcribing chunk {idx+1}/{total_chunks}...")
        if use_openai:
            text, segments = transcribe_chunk_openai(chunk_path, api_key=api_key)
            if segments:
                for s in segments:
                    seg_start = start + s.get("start", 0.0)
                    seg_end = start + s.get("end", 0.0)
                    eng_text = s.get("text", "").strip()
                    chi_text = translate_text(eng_text, translator)
                    all_segments.append({"start": seg_start, "end": seg_end, "text": eng_text, "zh": chi_text})
            else:
                eng_text = text.strip()
                chi_text = translate_text(eng_text, translator)
                all_segments.append({"start": start, "end": end, "text": eng_text, "zh": chi_text})
        else:
            raise RuntimeError("Local transcription mode not implemented in this package.")
        if progress_callback:
            progress_callback(f"Finished chunk {idx+1}/{total_chunks}")
    all_segments.sort(key=lambda x: x["start"])
    srt_path = output_dir / (video_path.stem + ".srt")
    segments_to_srt(all_segments, srt_path)
    return srt_path

# Simple Tkinter GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VMA Subtitle Tool")
        self.geometry("520x300")
        self.resizable(False, False)

        self.video_path_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")

        tk.Label(self, text="Choose video file:").pack(anchor="w", padx=10, pady=(10,0))
        frame = tk.Frame(self)
        frame.pack(fill="x", padx=10)
        tk.Entry(frame, textvariable=self.video_path_var, width=60).pack(side="left", padx=(0,6))
        tk.Button(frame, text="Browse", command=self.browse).pack(side="left")

        tk.Label(self, text="OpenAI API Key (required for transcription):").pack(anchor="w", padx=10, pady=(10,0))
        tk.Entry(self, textvariable=self.api_key_var, width=60, show="*").pack(padx=10)

        tk.Button(self, text="Start → Generate SRT", command=self.start, width=30).pack(pady=12)

        tk.Label(self, textvariable=self.status_var, wraplength=480, justify="left").pack(padx=10, pady=6)

    def browse(self):
        p = filedialog.askopenfilename(title="Select video file", filetypes=[("Video files","*.mp4 *.mov *.mkv *.avi *.webm"), ("All files","*.*")])
        if p:
            self.video_path_var.set(p)

    def start(self):
        video = self.video_path_var.get().strip()
        api_key = self.api_key_var.get().strip()
        if not video:
            messagebox.showerror("Error", "Please choose a video file.")
            return
        if not api_key:
            messagebox.showerror("Error", "Please enter your OpenAI API key.")
            return
        self.status_var.set("Preparing...")
        threading.Thread(target=self._run_job, args=(video, api_key), daemon=True).start()

    def _run_job(self, video, api_key):
        try:
            def progress(msg):
                self.status_var.set(msg)
            srt = process_file(video, api_key, use_openai=True, output_dir=os.path.dirname(video), progress_callback=progress)
            self.status_var.set(f"Completed. SRT saved: {srt}")
            messagebox.showinfo("Done", f"SRT created:\n{srt}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_var.set(f"Error: {e}")

def main():
    app = App()
    app.mainloop()

if __name__ == '__main__':
    main()
