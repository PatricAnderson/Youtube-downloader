# -*- coding: utf-8 -*-

# Requisitos: pip install customtkinter yt-dlp Pillow requests

import customtkinter as ctk
from tkinter import filedialog, messagebox
import yt_dlp
from threading import Thread, Lock
from PIL import Image
from io import BytesIO
import os
import requests
import zipfile
import stat
import sys
import webbrowser
import time
from queue import Queue
import subprocess
import shutil
import json

# --- Configurações da Janela ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        # PyInstaller cria uma pasta temporária e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class AdvancedDesktopDownloader(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader Pro")
        
        try:
            icon_path = resource_path("icon.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"Erro ao definir o ícone: {e}")

        self.geometry("900x750") 
        self.resizable(True, True)
        self.minsize(800, 750)

        # --- Variáveis de Estado ---
        self.video_info = None
        self.downloader_folder = self.get_app_data_folder()
        self.config_path = os.path.join(self.downloader_folder, "config.json")
        self.ffmpeg_path = os.path.join(self.downloader_folder, "ffmpeg", "bin", "ffmpeg.exe")
        self.save_path = self.load_settings().get("save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
        self.is_downloading = Lock()
        self.download_queue = Queue()

        # --- Estrutura da UI ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.top_frame = ctk.CTkFrame(self, corner_radius=10)
        self.top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.top_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.top_frame, text="URL:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=(10, 5), pady=10)
        self.url_entry = ctk.CTkEntry(self.top_frame, placeholder_text="Cole a URL do vídeo ou playlist do YouTube aqui...")
        self.url_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        self.paste_button = ctk.CTkButton(self.top_frame, text="Colar", width=60, command=self.paste_from_clipboard)
        self.paste_button.grid(row=0, column=2, padx=5, pady=10)
        
        self.fetch_button = ctk.CTkButton(self.top_frame, text="Buscar Detalhes", command=self.start_fetch_thread)
        self.fetch_button.grid(row=0, column=3, padx=(5, 10), pady=10)

        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.options_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.options_frame.grid_columnconfigure(0, weight=1)
        
        self.queue_frame = ctk.CTkFrame(self, corner_radius=10)
        self.queue_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        self.queue_frame.grid_columnconfigure(0, weight=1)
        self.queue_frame.grid_rowconfigure(1, weight=1)
        
        queue_title_frame = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
        queue_title_frame.grid(row=0, column=0, padx=10, pady=(10,5), sticky="ew")
        queue_title_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(queue_title_frame, text="Fila de Downloads", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(queue_title_frame, text="Limpar Concluídos", width=140, command=self.clear_completed).grid(row=0, column=1, sticky="e")

        self.scrollable_queue = ctk.CTkScrollableFrame(self.queue_frame, label_text="")
        self.scrollable_queue.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.scrollable_queue.grid_columnconfigure(0, weight=1)

        self.bottom_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.bottom_frame.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.bottom_frame, text="Pronto para começar.")
        self.status_label.grid(row=0, column=0, sticky="w")
        
        self.ffmpeg_progress_bar = ctk.CTkProgressBar(self.bottom_frame, height=10)
        self.ffmpeg_progress_bar.set(0)
        self.ffmpeg_progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.ffmpeg_progress_bar.grid_remove() 

        self.theme_switch = ctk.CTkSwitch(self.bottom_frame, text="Modo Claro", command=self.toggle_theme)
        self.theme_switch.grid(row=0, column=1, sticky="e")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.check_and_prepare_ffmpeg()
        Thread(target=self.process_queue, daemon=True).start()

    def on_closing(self):
        self.save_settings()
        self.destroy()

    def load_settings(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return json.load(f)
        except: return {}

    def save_settings(self):
        settings = {"save_path": self.save_path}
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e: print(f"Erro ao guardar configurações: {e}")

    def process_queue(self):
        while True:
            queue_item, download_task = self.download_queue.get()
            if self.is_downloading.acquire(blocking=False):
                try: self.run_download(queue_item, download_task)
                finally: self.is_downloading.release()
            self.download_queue.task_done()

    def run_download(self, queue_item, task):
        try:
            self.after(0, lambda: queue_item.status_label.configure(text="A preparar..."))
            final_path_info = {}
            
            def progress_hook(d):
                if d['status'] == 'downloading':
                    total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    percentage = downloaded_bytes / total_bytes
                    speed = d.get('speed', 0)
                    speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else ""
                    eta = d.get('eta', 0)
                    eta_str = f"ETA: {int(eta // 60)}m {int(eta % 60)}s" if eta else ""
                    downloaded_mb = downloaded_bytes / 1024 / 1024
                    total_mb = total_bytes / 1024 / 1024
                    size_str = f"{downloaded_mb:.1f}/{total_mb:.1f} MB"
                    status_text = f"Baixando... {size_str} ({int(percentage * 100)}%) | {speed_str} | {eta_str}"
                    self.after(0, lambda: queue_item.update_progress(percentage, status_text))
                elif d['status'] == 'finished':
                    if d.get('info_dict', {}).get('filepath'):
                        final_path_info['path'] = d['info_dict']['filepath']

            ydl_opts = {
                'progress_hooks': [progress_hook],
                'ffmpeg_location': os.path.dirname(self.ffmpeg_path),
                'outtmpl': os.path.join(self.save_path, os.path.splitext(task['filename'])[0])
            }
            if task['download_type'] == 'audio':
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': task['format'], 'preferredquality': '192'}]
            else:
                if task['resolution'] and task['resolution'] != "N/A":
                    ydl_opts['format'] = f"bv*[ext={task['format']}][height<={task['resolution'][:-1]}]+ba[ext=m4a]/b[ext={task['format']}]/b"
                else: 
                    ydl_opts['format'] = f"bv*[ext={task['format']}]+ba[ext=m4a]/b[ext={task['format']}]/b"
                ydl_opts['merge_output_format'] = task['format']
                
            if task['subtitles']:
                ydl_opts['writesubtitles'] = True
                ydl_opts['subtitleslangs'] = ['all']
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([task['url']])
            final_path = final_path_info.get('path')
            if not final_path:
                expected_path = os.path.join(self.save_path, task['filename'])
                if os.path.exists(expected_path): final_path = expected_path
                else: raise Exception("Não foi possível determinar o caminho final.")
            self.on_complete(queue_item, final_path)
        except Exception as e:
            self.after(0, lambda err=e: queue_item.status_label.configure(text=f"Erro: {str(err)[:50]}...", text_color="red"))
            print(f"Erro no download: {e}")
            
    def start_fetch_thread(self):
        url = self.url_entry.get()
        if not url: return messagebox.showerror("Erro", "Por favor, insira uma URL válida.")
        self.fetch_button.configure(state="disabled", text="Buscando...")
        self.info_frame.grid_forget()
        self.options_frame.grid_forget()
        Thread(target=self.fetch_video_details, args=(url,), daemon=True).start()

    def fetch_video_details(self, url):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': 'in_playlist'}) as ydl:
                info = ydl.extract_info(url, download=False)
            if 'entries' in info and info.get('_type') == 'playlist':
                self.after(0, lambda: self.open_playlist_window(info))
            else:
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl_full:
                    full_info = ydl_full.extract_info(info['url'], download=False)
                self.after(0, lambda: self.display_info_and_options(full_info))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Erro", f"Não foi possível obter detalhes.\n{e}"))
        finally:
            self.after(0, lambda: self.fetch_button.configure(state="normal", text="Buscar Detalhes"))

    def open_playlist_window(self, playlist_info):
        if hasattr(self, 'playlist_win') and self.playlist_win.winfo_exists():
            self.playlist_win.focus()
        else:
            self.playlist_win = PlaylistWindow(self, playlist_info)
            
    def add_to_queue(self, single_video_info, download_options):
        safe_title = "".join(c for c in single_video_info['title'] if c.isalnum() or c in " ()-_").rstrip()
        base_filename = f"{safe_title}"
        selected_format = download_options['format']
        final_filename = f"{base_filename}.{selected_format}"
        task = {
            "url": single_video_info.get('webpage_url') or single_video_info.get('url'),
            "title": single_video_info['title'], "filename": final_filename,
            "download_type": download_options['type'], "format": selected_format, 
            "resolution": download_options['resolution'], "subtitles": download_options['subtitles']
        }
        item_frame = QueueItem(self.scrollable_queue, task)
        item_frame.pack(fill="x", expand=True, padx=5, pady=5)
        self.download_queue.put((item_frame, task))
        
    def on_complete(self, queue_item, file_path):
        self.after(0, lambda: queue_item.mark_as_complete(file_path))

    def display_info_and_options(self, full_video_info):
        self.video_info = full_video_info
        for widget in self.info_frame.winfo_children(): widget.destroy()
        for widget in self.options_frame.winfo_children(): widget.destroy()
        self.info_frame.configure(fg_color=["gray90", "gray13"])
        self.info_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.info_frame.grid_columnconfigure(1, weight=1)
        try:
            thumbnail_url = full_video_info.get('thumbnail')
            response = requests.get(thumbnail_url, stream=True)
            img_data = Image.open(BytesIO(response.content))
            thumbnail_image = ctk.CTkImage(light_image=img_data, dark_image=img_data, size=(160, 90))
            ctk.CTkLabel(self.info_frame, image=thumbnail_image, text="").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        except:
            ctk.CTkFrame(self.info_frame, width=160, height=90, fg_color="gray20").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        title_label = ctk.CTkLabel(self.info_frame, text=full_video_info['title'], font=ctk.CTkFont(size=14, weight="bold"), wraplength=550, justify="left")
        title_label.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        self.options_frame.grid(row=2, column=0, padx=10, pady=0, sticky="ew")
        
        self.single_video_options = OptionsWidget(self.options_frame, full_video_info)
        self.single_video_options.pack(fill="x", expand=True)
        add_button = ctk.CTkButton(self.options_frame, text="Adicionar à Fila de Downloads", command=self.add_single_item_to_queue)
        add_button.pack(pady=10, fill="x", expand=True)
    
    def add_single_item_to_queue(self):
        download_options = self.single_video_options.get_options()
        self.add_to_queue(self.video_info, download_options)
        self.status_label.configure(text=f"'{self.video_info['title'][:40]}...' adicionado à fila.")
        self.after(3000, lambda: self.status_label.configure(text="Pronto."))
            
    def paste_from_clipboard(self):
        try: self.url_entry.delete(0, "end"); self.url_entry.insert(0, self.clipboard_get())
        except: messagebox.showwarning("Aviso", "Nenhum texto encontrado na área de transferência.")
            
    def toggle_theme(self):
        ctk.set_appearance_mode("light" if self.theme_switch.get() == 1 else "dark")
        
    def get_app_data_folder(self):
        path = os.getenv('APPDATA') or os.path.dirname(os.path.abspath(__file__))
        return os.path.join(path, "YouTubeDownloaderPro")

    def check_and_prepare_ffmpeg(self):
        if os.path.exists(self.ffmpeg_path): return
        if messagebox.askyesno("FFmpeg Necessário", "O FFmpeg é essencial. Deseja baixa-lo agora (cerca de 50MB)?"):
            self.fetch_button.configure(state="disabled")
            self.ffmpeg_progress_bar.grid() 
            Thread(target=self.download_ffmpeg, daemon=True).start()

    def download_ffmpeg(self):
        try:
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            zip_path = os.path.join(self.downloader_folder, "ffmpeg.zip")
            os.makedirs(self.downloader_folder, exist_ok=True)
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            with open(zip_path, "wb") as f:
                bytes_dl = 0
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_dl += len(chunk)
                    if total_size > 0: self.after(0, self.update_ffmpeg_progress, bytes_dl / total_size)
            self.after(0, lambda: self.status_label.configure(text="Extraindo o FFmpeg..."))
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                temp_path = os.path.join(self.downloader_folder, "temp_ffmpeg")
                zip_ref.extractall(temp_path)
                inner_folder = os.path.join(temp_path, os.listdir(temp_path)[0])
                shutil.move(inner_folder, os.path.join(self.downloader_folder, "ffmpeg"))
                shutil.rmtree(temp_path)
            os.remove(zip_path)
            self.after(0, lambda: messagebox.showinfo("Sucesso", f"FFmpeg instalado em:\n{self.downloader_folder}"))
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha ao instalar o FFmpeg: {err}"))
        finally:
            self.after(0, self.hide_ffmpeg_progress)

    def update_ffmpeg_progress(self, percentage):
        self.ffmpeg_progress_bar.set(percentage)
        self.status_label.configure(text=f"Baixando o FFmpeg... {int(percentage * 100)}%")

    def hide_ffmpeg_progress(self):
        self.ffmpeg_progress_bar.grid_remove()
        self.status_label.configure(text="Pronto.")
        self.fetch_button.configure(state="normal")
    
    def clear_completed(self):
        for widget in list(self.scrollable_queue.winfo_children()):
            if isinstance(widget, QueueItem) and widget.completed: widget.destroy()

class OptionsWidget(ctk.CTkFrame):
    def __init__(self, master, video_info):
        super().__init__(master, fg_color="transparent")
        
        format_frame = ctk.CTkFrame(self)
        format_frame.pack(fill="x", expand=True, pady=5)
        self.video_radio = ctk.StringVar(value="video")
        ctk.CTkRadioButton(format_frame, text="Vídeo", variable=self.video_radio, value="video", command=self.toggle_format_options).pack(side="left", padx=10)
        ctk.CTkRadioButton(format_frame, text="Apenas Áudio", variable=self.video_radio, value="audio", command=self.toggle_format_options).pack(side="left", padx=10)
        
        self.video_options_frame = ctk.CTkFrame(format_frame, fg_color="transparent")
        self.video_options_frame.pack(side="left", padx=20)
        ctk.CTkLabel(self.video_options_frame, text="Formato:").pack(side="left")
        self.video_format_menu = ctk.CTkOptionMenu(self.video_options_frame, values=["MP4", "MKV", "WEBM"], width=100)
        self.video_format_menu.pack(side="left", padx=5)
        ctk.CTkLabel(self.video_options_frame, text="Resolução:").pack(side="left")
        
        resolutions = sorted(list(set(f['height'] for f in video_info['formats'] if f.get('height'))), reverse=True)
        self.resolution_menu = ctk.CTkOptionMenu(self.video_options_frame, values=[f"{r}p" for r in resolutions if r] or ["N/A"], width=100)
        self.resolution_menu.pack(side="left", padx=5)
        
        self.audio_options_frame = ctk.CTkFrame(format_frame, fg_color="transparent")
        ctk.CTkLabel(self.audio_options_frame, text="Formato:").pack(side="left")
        self.audio_format_menu = ctk.CTkOptionMenu(self.audio_options_frame, values=["MP3", "M4A", "WAV", "OGG"], width=100)
        self.audio_format_menu.pack(side="left", padx=5)
        
        extra_frame = ctk.CTkFrame(self)
        extra_frame.pack(fill="x", expand=True, pady=5)
        self.subtitles_check = ctk.CTkCheckBox(extra_frame, text="Baixar Legendas (se disponível)")
        self.subtitles_check.pack(side="left", padx=10)

        self.toggle_format_options()

    def toggle_format_options(self):
        is_video = self.video_radio.get() == "video"
        self.audio_options_frame.pack_forget() if is_video else self.audio_options_frame.pack(side="left", padx=20)
        self.video_options_frame.pack(side="left", padx=20) if is_video else self.video_options_frame.pack_forget()

    def get_options(self):
        return {
            "type": self.video_radio.get(),
            "format": self.video_format_menu.get().lower() if self.video_radio.get() == "video" else self.audio_format_menu.get().lower(),
            "resolution": self.resolution_menu.get() if self.video_radio.get() == "video" else None,
            "subtitles": self.subtitles_check.get() == 1
        }

class PlaylistWindow(ctk.CTkToplevel):
    def __init__(self, master, playlist_info):
        super().__init__(master)
        self.master_app = master
        
        self.title(f"Playlist: {playlist_info['title']}")
        self.geometry("800x600")
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(top_frame, text="Selecionar Todos", command=self.select_all).pack(side="left", padx=5)
        ctk.CTkButton(top_frame, text="Desselecionar Todos", command=self.deselect_all).pack(side="left", padx=5)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Vídeos na Playlist")
        self.scroll_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        self.video_entries = []
        for video in playlist_info['entries']:
            if not video: continue
            var = ctk.StringVar(value="on")
            cb = ctk.CTkCheckBox(self.scroll_frame, text=video.get('title', 'Título desconhecido'), variable=var, onvalue="on", offvalue="off")
            cb.pack(fill="x", padx=5, pady=2, expand=True)
            self.video_entries.append({'checkbox': cb, 'info': video})

        options_container = ctk.CTkFrame(self)
        options_container.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        
        first_video_info = playlist_info['entries'][0] if playlist_info['entries'] else {}
        self.options_widget = OptionsWidget(options_container, first_video_info)
        self.options_widget.pack(fill="x", expand=True)
        
        add_button = ctk.CTkButton(options_container, text="Adicionar Selecionados à Fila", command=self.add_selected_to_queue)
        add_button.pack(pady=10, fill="x", expand=True)

    def select_all(self):
        for entry in self.video_entries: entry['checkbox'].select()
    def deselect_all(self):
        for entry in self.video_entries: entry['checkbox'].deselect()

    def add_selected_to_queue(self):
        count = 0
        download_options = self.options_widget.get_options()
        for entry in self.video_entries:
            if entry['checkbox'].get() == "on":
                self.master_app.add_to_queue(entry['info'], download_options)
                count += 1
        
        self.master_app.status_label.configure(text=f"{count} vídeos adicionados à fila.")
        self.after(3000, lambda: self.master_app.status_label.configure(text="Pronto."))
        self.destroy()

class QueueItem(ctk.CTkFrame):
    def __init__(self, master, task):
        super().__init__(master, corner_radius=5)
        self.task = task
        self.file_path = ""
        self.completed = False 
        self.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(self, text=task['title'], wraplength=400, justify="left")
        self.title_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.status_label = ctk.CTkLabel(self, text="Aguardando na fila...", text_color="gray")
        self.status_label.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="w")
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=5, sticky="e")
        self.open_folder_button = ctk.CTkButton(self.action_frame, text="Abrir Pasta", width=100, state="disabled", command=self.open_folder)
        self.open_folder_button.pack(pady=2)
        self.play_button = ctk.CTkButton(self.action_frame, text="Reproduzir", width=100, state="disabled", command=self.play_file)
        self.play_button.pack(pady=2)

    def update_progress(self, percentage, text):
        self.progress_bar.set(percentage)
        self.status_label.configure(text=text, text_color="white")
        if percentage < 0.7:
            self.progress_bar.configure(progress_color="#3B8ED0")
        elif percentage < 0.95:
            self.progress_bar.configure(progress_color="#F1C40F")
        else:
            self.progress_bar.configure(progress_color="#27AE60")
        
    def mark_as_complete(self, file_path):
        self.file_path = file_path
        self.completed = True
        self.progress_bar.set(1)
        self.progress_bar.configure(progress_color="#2ECC71")
        self.status_label.configure(text="Concluído!", text_color="green")
        self.open_folder_button.configure(state="normal")
        self.play_button.configure(state="normal")
        
    def open_folder(self):
        if not self.file_path: return
        folder_path = os.path.dirname(self.file_path)
        try:
            if sys.platform == "win32": os.startfile(folder_path)
            elif sys.platform == "darwin": subprocess.Popen(["open", folder_path])
            else: subprocess.Popen(["xdg-open", folder_path])
        except Exception as e: messagebox.showerror("Erro", f"Não foi possível abrir a pasta: {e}")

    def play_file(self):
        if self.file_path and os.path.exists(self.file_path):
            try: os.startfile(self.file_path)
            except Exception as e: messagebox.showerror("Erro", f"Não foi possível abrir o arquivo: {e}")
        else:
            messagebox.showwarning("Aviso", "O arquivo não foi encontrado.")

if __name__ == "__main__":
    app = AdvancedDesktopDownloader()
    app.mainloop()
