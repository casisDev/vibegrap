#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VibeGrap - interface gráfica moderna para o yt-dlp.

Recursos: análise do link com miniatura, escolha de qualidade, faixa(s) de áudio,
legendas, playlist (escolher itens), trecho do vídeo, fila de downloads com
progresso total (itens, bytes, velocidade, tempo restante), cookies do navegador,
limite de velocidade, proxy, tema claro/escuro e gerenciador de ferramentas
(ffmpeg, Deno e atualização do yt-dlp).

Executar como script:  python ytdlp_gui.py
Instalador (Windows):  veja o README.md
"""

import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
import zipfile
from tkinter import filedialog, messagebox

APP_NAME = "VibeGrap"
IS_WIN = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)

# Em modo "janela" (sem console) o PyInstaller deixa stdout/stderr como None.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

try:
    import customtkinter as ctk
except ImportError:
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("Componente ausente", 'Instale com:\n\npip install customtkinter pillow "yt-dlp[default]"')
    raise SystemExit(1)

try:
    from PIL import Image, ImageOps
except ImportError:  # miniaturas e logo são opcionais
    Image = ImageOps = None


# ---------------------------------------------------------------- pastas
def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _read_asset(name, default=""):
    try:
        with open(resource_path(os.path.join("assets", name)), encoding="utf-8") as f:
            return f.read().strip() or default
    except OSError:
        return default


# Gravados pelo GitHub Actions na hora de montar o instalador (veja .github/workflows/build.yml).
# Em execução a partir do código-fonte, os arquivos não existem e a atualização automática fica desligada.
APP_VERSION = _read_asset("version.txt", "2.0.0")
UPDATE_REPO = _read_asset("update_repo.txt")  # "dono/repositorio"
UPDATE_API = "https://api.github.com"
INSTALLER_ARGS = ["/SILENT", "/CLOSEAPPLICATIONS"]
# "Impressão digital" das bibliotecas embutidas (Python, Pillow, customtkinter...). Só quando ela é igual à da
# versão nova dá para atualizar apenas o VibeGrap.exe + assets (pacote leve); senão baixa o instalador completo.
APP_BASE = _read_asset("base_id.txt")
PATCH_FILES = ("VibeGrap.exe", "LICENSE", "THIRD_PARTY_NOTICES.md")  # o que o pacote leve pode trazer...
PATCH_DIR = "_internal/assets/"                                      # ...mais tudo desta pasta
PATCH_MAX_BYTES = 150 * 1024 * 1024


def _data_dir():
    if IS_WIN:
        base = os.environ.get("APPDATA")
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
    base = base or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "VibeGrap")
    os.makedirs(os.path.join(path, "bin"), exist_ok=True)
    return path


DATA_DIR = _data_dir()
BIN_DIR = os.path.join(DATA_DIR, "bin")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
# Cópia atualizada do yt-dlp (arquivo "zipapp" oficial). Se existir, tem prioridade
# sobre a versão embutida no programa - assim dá para atualizar sem reinstalar.
UPDATE_ZIPAPP = os.path.join(DATA_DIR, "yt-dlp")


def _apply_pending_ytdlp():
    """Uma atualização baixada fica em 'yt-dlp.new' e só entra no lugar na abertura seguinte.
    (Trocar o arquivo com o programa rodando poderia misturar versões.)"""
    new = UPDATE_ZIPAPP + ".new"
    if not os.path.isfile(new):
        return
    try:
        if zipfile.is_zipfile(new):
            os.replace(new, UPDATE_ZIPAPP)
        else:
            os.remove(new)
    except OSError:
        pass


def _import_ytdlp():
    import importlib

    _apply_pending_ytdlp()
    if os.path.isfile(UPDATE_ZIPAPP) and zipfile.is_zipfile(UPDATE_ZIPAPP):
        sys.path.insert(0, UPDATE_ZIPAPP)
        try:
            mod = importlib.import_module("yt_dlp")
            importlib.import_module("yt_dlp.version")
            return mod
        except Exception:
            try:
                sys.path.remove(UPDATE_ZIPAPP)
            except ValueError:
                pass
            for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
                del sys.modules[name]
    mod = importlib.import_module("yt_dlp")
    importlib.import_module("yt_dlp.version")
    return mod


try:
    yt_dlp = _import_ytdlp()
except ImportError:
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("yt-dlp não encontrado", 'Instale com:\n\npip install -U "yt-dlp[default]"')
    raise SystemExit(1)

YTDLP_VERSION = yt_dlp.version.__version__


# ---------------------------------------------------------------- constantes
TEMPLATES = {
    "Título": "%(title)s.%(ext)s",
    "Título [id]": "%(title)s [%(id)s].%(ext)s",
    "Canal - Título": "%(uploader)s - %(title)s.%(ext)s",
    "Nº - Título (playlists)": "%(playlist_index&{} - |)s%(title)s.%(ext)s",
}
BROWSERS = ["Nenhum", "chrome", "firefox", "edge", "brave", "opera", "vivaldi", "chromium", "safari"]
CONTAINERS = ["mp4", "mkv", "webm"]
AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav", "original"]
AUDIO_BITRATES = ["128", "192", "256", "320"]
GENERIC_QUALITIES = ["Melhor disponível", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]
BEST = GENERIC_QUALITIES[0]
MODE_LABELS = {"Vídeo + áudio": "video", "Só áudio": "audio"}
THEMES = {"Sistema": "system", "Claro": "light", "Escuro": "dark"}
FINAL_STATES = ("Concluído", "Concluído com avisos", "Erro", "Cancelado")

ABOUT_TEXT = (
    "Desenvolvido por casisDev. Interface para o yt-dlp: o trabalho pesado é feito por yt-dlp, FFmpeg, Deno, "
    "customtkinter e outros projetos livres.\n"
    "É um programa de “vibe coding”: criado com assistência de IA (Claude, da Anthropic), com testes automáticos mas "
    "sem auditoria profissional, e oferecido sem garantias.\n"
    "Baixe apenas conteúdo que você tem o direito de baixar e respeite os termos de serviço dos sites. "
    "Não é afiliado ao projeto yt-dlp, ao YouTube nem a nenhum outro citado."
)

FFMPEG_URLS = [
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
]
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
YTDLP_ZIPAPP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
YTDLP_SUMS_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
YTDLP_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
HISTORY_MAX = 500

DEFAULT_CFG = {
    "folder": os.path.join(os.path.expanduser("~"), "Downloads"),
    "mode": "video",
    "container": "mp4",
    "audio_fmt": "mp3",
    "audio_q": "192",
    "template": "Título",
    "playlist_folder": True,
    "browser": "Nenhum",
    "cookiefile": "",
    "proxy": "",
    "limit": "",
    "meta": True,
    "thumb": False,
    "overwrite": False,
    "theme": "Sistema",
    "auto_update": True,
    "auto_ytdlp": True,
    "notify": True,
}

# ---------------------------------------------------------------- paleta (claro, escuro)
# Vermelho, branco e preto (as cores do próprio yt-dlp). Para mudar o visual, mexa só aqui.
BG = ("#f4f4f5", "#0f0f10")
SIDEBAR = ("#ffffff", "#151516")
CARD = ("#ffffff", "#1b1b1d")
BORDER = ("#e4e4e7", "#2c2c30")
FIELD = ("#f4f4f5", "#0f0f10")
TXT = ("#0f0f10", "#f5f5f5")
MUTED = ("#6b6b72", "#a1a1aa")
ACCENT = ("#d62828", "#ef4444")      # vermelho principal
ACCENT_H = ("#b91c1c", "#dc2626")    # vermelho ao passar o mouse
SOFT = ("#f0f0f2", "#27272b")        # botões secundários
SOFT_H = ("#e4e4e8", "#34343a")
SEL = ("#fbd3d3", "#5c1a1a")         # item selecionado (abas, botões segmentados)
SEL_H = ("#f7bcbc", "#712020")
DONE = TXT                           # item concluído: texto normal (preto/branco), sem verde, para manter a paleta
RED = ("#b91c1c", "#f87171")         # texto de erro


# ---------------------------------------------------------------- utilidades
def load_settings():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULT_CFG})
    except Exception:
        pass
    return cfg


def save_settings(cfg):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fmt_dur(seconds):
    if not seconds and seconds != 0:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(n):
    """Bytes -> texto legível em português (ex.: 1,2 GB)."""
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return "—"


def short(text, limit=95):
    text = (text or "").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_time(text):
    """'90', '1:30', '01:02:03.5' -> segundos (float). Vazio -> None."""
    text = (text or "").strip()
    if not text:
        return None
    parts = text.replace(",", ".").split(":")
    if len(parts) > 3:
        raise ValueError(text)
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    if total < 0:
        raise ValueError(text)
    return total


def exe_dir():
    if FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_tool(name):
    exe = name + (".exe" if IS_WIN else "")
    for folder in (exe_dir(), BIN_DIR):
        path = os.path.join(folder, exe)
        if os.path.isfile(path):
            return path
    return shutil.which(name)


def ffmpeg_location():
    path = find_tool("ffmpeg")
    return os.path.dirname(path) if path else None


def detect_js_runtime():
    for name in ("deno", "node", "bun", "quickjs"):
        path = find_tool(name)
        if path:
            return name, path
    return None


def build_format(mode, height, exact_langs, lang_prefix, can_merge=True):
    """Monta a string de formato do yt-dlp. Retorna (formato, várias_faixas_de_áudio)."""
    h = f"[height<={height}]" if height else ""
    if exact_langs:
        audio = [f"ba[language={lang}]" for lang in exact_langs]
    elif lang_prefix:
        audio = [f"ba[language^={lang_prefix}]"]
    else:
        audio = []

    if mode == "audio":
        if audio:
            return f"{audio[0]}/ba/b", False
        return "ba/b", False

    if not can_merge:  # sem ffmpeg: só formatos que já vêm com vídeo+áudio
        return f"b{h}/b", False

    v = f"bv*{h}"
    if audio:
        joined = "+".join(audio)
        return f"{v}+{joined}/{v}+ba/b{h}/b", len(audio) > 1
    return f"{v}+ba/b{h}/b", False


class _Silent:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def estimate_size(info, fmt, multi, duration_factor=1.0):
    """Tamanho estimado (bytes) do formato escolhido, ou None se não der para saber."""
    try:
        formats = [dict(f) for f in (info.get("formats") or [])]
        if not formats:
            return None
        ydl = yt_dlp.YoutubeDL(
            {"quiet": True, "no_warnings": True, "logger": _Silent(), "format": fmt, "allow_multiple_audio_streams": multi}
        )
        selector = ydl.build_format_selector(fmt)
        incomplete = all(f.get("vcodec") != "none" and f.get("acodec") == "none" for f in formats) or all(
            f.get("vcodec") == "none" and f.get("acodec") != "none" for f in formats
        )
        chosen = next(iter(selector({"formats": formats, "incomplete_formats": incomplete})), None)
        if not chosen:
            return None
        total = 0.0
        for part in chosen.get("requested_formats") or [chosen]:
            size = part.get("filesize") or part.get("filesize_approx")
            if not size and part.get("tbr") and info.get("duration"):
                size = part["tbr"] * 1000 / 8 * info["duration"]
            if not size:
                return None
            total += size
        return int(total * duration_factor)
    except Exception:
        return None


def download_file(url, dest, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "VibeGrap"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(got / total * 100)


def parse_version(text):
    """'v2.1.0' -> (2, 1, 0). Ignora sufixos como '-beta'."""
    nums = re.findall(r"\d+", str(text).split("-")[0].split("+")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(latest, current):
    a, b = list(parse_version(latest)), list(parse_version(current))
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a > b


REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def fetch_latest_release(repo, api=None, timeout=15, base=None):
    """Consulta a última Release do repositório no GitHub."""
    base = APP_BASE if base is None else base
    if not REPO_RE.match(repo or ""):
        raise ValueError("Repositório inválido: " + repr(repo))
    api = api or UPDATE_API
    req = urllib.request.Request(
        f"{api}/repos/{repo}/releases/latest",
        headers={"User-Agent": "vibegrap-updater", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = data.get("tag_name") or ""
    assets = data.get("assets") or []
    asset = next((a for a in assets if str(a.get("name", "")).lower().endswith("setup.exe")), None)
    by_name = {str(a.get("name", "")): a for a in assets}
    patch_name = f"VibeGrap-App-{base}.zip" if re.fullmatch(r"[0-9a-f]{6,64}", base or "") else None
    patch = by_name.get(patch_name) if patch_name else None
    patch_sha = by_name.get(patch_name + ".sha256") if patch else None
    has_patch = bool(patch and patch_sha)
    return {
        "patch_url": patch.get("browser_download_url") if has_patch else None,
        "patch_size": patch.get("size") if has_patch else None,
        "patch_sha_url": patch_sha.get("browser_download_url") if has_patch else None,
        "tag": tag,
        "version": tag.lstrip("vV"),
        "notes": (data.get("body") or "").strip(),
        "page": data.get("html_url") or f"https://github.com/{repo}/releases",
        "asset_url": asset.get("browser_download_url") if asset else None,
        "asset_size": asset.get("size") if asset else None,
        "repo": repo,
    }


def asset_url_ok(url, repo, api=None):
    """Só aceita baixar o instalador do próprio repositório (ou da API do GitHub)."""
    api = api or UPDATE_API
    return bool(url) and (url.startswith(f"https://github.com/{repo}/releases/download/") or url.startswith(api + "/"))


def download_update(info, dest, progress=None):
    if not asset_url_ok(info.get("asset_url"), info.get("repo", UPDATE_REPO)):
        raise RuntimeError("Endereço do instalador não é confiável.")
    download_file(info["asset_url"], dest, progress)
    size = info.get("asset_size")
    if size and os.path.getsize(dest) != size:
        os.remove(dest)
        raise RuntimeError("O instalador baixado está incompleto. Tente de novo.")
    return dest


# ---------------------------------------------------------------- atualização leve (só o VibeGrap.exe + assets)
def can_write_dir(folder):
    try:
        with tempfile.NamedTemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def pick_update_mode(info, frozen=None, win=None, app_dir=None):
    """'patch' (pacote leve), 'installer' (instalador completo) ou 'page' (abrir o navegador)."""
    frozen = FROZEN if frozen is None else frozen
    win = IS_WIN if win is None else win
    if not (frozen and win):
        return "page"
    if info.get("patch_url") and info.get("patch_sha_url") and can_write_dir(app_dir or exe_dir()):
        return "patch"
    return "installer" if info.get("asset_url") else "page"


def download_patch(info, dest, progress=None):
    """Baixa o pacote leve e confere o tamanho e o SHA-256 publicado junto na Release."""
    repo = info.get("repo", UPDATE_REPO)
    if not (asset_url_ok(info.get("patch_url"), repo) and asset_url_ok(info.get("patch_sha_url"), repo)):
        raise RuntimeError("Endereço da atualização não é confiável.")
    req = urllib.request.Request(info["patch_sha_url"], headers={"User-Agent": "VibeGrap"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read(512).decode("ascii", "replace")
    m = re.match(r"\s*([0-9a-fA-F]{64})", text)
    if not m:
        raise RuntimeError("Hash da atualização ausente ou inválido.")
    download_file(info["patch_url"], dest, progress)
    size = info.get("patch_size")
    if (size and os.path.getsize(dest) != size) or sha256_file(dest) != m.group(1).lower():
        os.remove(dest)
        raise RuntimeError("A atualização baixada não confere (tamanho ou hash). Nada foi instalado.")
    return dest


def extract_patch(zip_path, stage_dir):
    """Extrai o pacote leve numa pasta temporária, aceitando só os arquivos esperados."""
    if os.path.isdir(stage_dir):
        shutil.rmtree(stage_dir)
    os.makedirs(stage_dir)
    with zipfile.ZipFile(zip_path) as z:
        members, total = [], 0
        for i in z.infolist():
            if i.is_dir():
                continue
            name = i.filename.replace("\\", "/")
            parts = name.split("/")
            if name.startswith("/") or ".." in parts or ":" in name or not (name in PATCH_FILES or name.startswith(PATCH_DIR)):
                raise RuntimeError("Arquivo inesperado no pacote de atualização: " + name)
            total += i.file_size
            members.append((i, name))
        if total > PATCH_MAX_BYTES or not any(n == PATCH_FILES[0] for _, n in members):
            raise RuntimeError("Pacote de atualização inválido.")
        for i, name in members:
            dest = os.path.join(stage_dir, *name.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(i) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    with open(os.path.join(stage_dir, PATCH_FILES[0]), "rb") as f:
        if f.read(2) != b"MZ":
            raise RuntimeError("O VibeGrap.exe do pacote não é um executável válido.")
    return stage_dir


def apply_patch(stage, app_dir, exe_name="VibeGrap.exe"):
    """Troca o .exe e os assets. O Windows deixa RENOMEAR um .exe em uso (mas não apagar): o antigo vira
    .old e é apagado na próxima abertura. Qualquer falha desfaz tudo e devolve o programa como estava."""
    exe = os.path.join(app_dir, exe_name)
    old = exe + ".old"
    assets_dst = os.path.join(app_dir, *PATCH_DIR.strip("/").split("/"))
    backup = stage.rstrip("/\\") + "_rollback"
    if os.path.exists(old):
        os.remove(old)
    if os.path.isdir(backup):
        shutil.rmtree(backup)
    if os.path.isdir(assets_dst):
        shutil.copytree(assets_dst, backup)
    os.replace(exe, old)
    try:
        shutil.copy2(os.path.join(stage, PATCH_FILES[0]), exe)
        assets_src = os.path.join(stage, *PATCH_DIR.strip("/").split("/"))
        if os.path.isdir(assets_src):
            shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)
        for extra in PATCH_FILES[1:]:
            if os.path.isfile(os.path.join(stage, extra)):
                try:
                    shutil.copy2(os.path.join(stage, extra), os.path.join(app_dir, extra))
                except OSError:
                    pass  # licença não é crítica
    except Exception:
        try:
            if os.path.exists(exe):
                os.remove(exe)
        except OSError:
            pass
        os.replace(old, exe)
        if os.path.isdir(backup):
            shutil.copytree(backup, assets_dst, dirs_exist_ok=True)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    return exe


def cleanup_after_patch():
    """Apaga restos de uma atualização leve anterior (o .exe antigo e a pasta temporária)."""
    try:
        if FROZEN:
            old = sys.executable + ".old"
            if os.path.exists(old):
                os.remove(old)
        shutil.rmtree(os.path.join(tempfile.gettempdir(), "vibegrap-update"), ignore_errors=True)
    except OSError:
        pass


def relaunch_app(exe, app_dir):
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # o novo processo não herda o estado do antigo
    flags = (0x00000008 | 0x00000200) if IS_WIN else 0  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe], cwd=app_dir, env=env, creationflags=flags, close_fds=True)


def parse_item_ranges(text, total):
    """Lê '1-10, 15, 20-' e devolve (itens ordenados, problemas). Aceita 1-10, 1:10, 5- (até o fim) e -3 (do início)."""
    text = re.sub(r"\s*([-:–])\s*", r"\1", (text or "").strip())
    picked, problems = set(), []
    for tok in filter(None, re.split(r"[,;\s]+", text)):
        m = re.fullmatch(r"(\d*)[-:–](\d*)", tok)
        if m and (m.group(1) or m.group(2)):
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else total
        elif tok.isdigit():
            a = b = int(tok)
        else:
            problems.append(f"“{tok}” não é um item nem um intervalo")
            continue
        if a > b:
            a, b = b, a
        if a < 1 or a > total:
            problems.append(f"“{tok}” está fora da playlist (1 a {total})")
            continue
        picked.update(range(a, min(b, total) + 1))
    return sorted(picked), problems


def compress_items(nums):
    """[1,2,3,5,7,8] -> '1-3,5,7-8' (formato do --playlist-items do yt-dlp)."""
    out, nums = [], sorted(set(nums))
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ",".join(out)


def trimmed_logo(path):
    """Abre o logo e corta a margem vazia, para ele aparecer grande e sem distorção."""
    img = Image.open(path).convert("RGBA")
    box = img.convert("L").point(lambda v: 255 if v > 40 else 0).getbbox()
    return img.crop(box) if box else img


def extract_from_zip(zip_path, wanted, require_bin_dir=False):
    """Extrai arquivos pelo nome base (evita 'zip slip'). Retorna os nomes extraídos."""
    found = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            base = os.path.basename(name).lower()
            norm = name.replace("\\", "/")
            if base in wanted and (not require_bin_dir or "/bin/" in norm):
                with z.open(name) as src, open(os.path.join(BIN_DIR, base), "wb") as dst:
                    shutil.copyfileobj(src, dst)
                found.append(base)
    return found


# ---------------------------------------------------------------- erros em português
# (padrão no texto do erro, mensagem para o usuário). A primeira regra que combinar vence.
ERROR_RULES = [
    (r"not a bot|confirm you.re not a bot",
     "O YouTube pediu uma verificação anti-robô. Em Configurações, escolha o navegador em “Cookies do navegador” "
     "(onde você está logado) e atualize o yt-dlp em Ferramentas."),
    (r"confirm your age|age[- ]restricted|inappropriate for some users",
     "Vídeo com restrição de idade. Em Configurações, escolha o navegador onde você está logado em “Cookies do navegador”."),
    (r"private video|this video is private",
     "Este vídeo é privado. Se ele é seu, escolha o navegador logado em Configurações → Cookies do navegador."),
    (r"members[- ]only|join this channel|available to this channel.s members",
     "Vídeo exclusivo para membros do canal. Use os cookies do navegador onde você é membro (Configurações)."),
    (r"copyright",
     "O vídeo foi bloqueado por direitos autorais e não pode ser baixado."),
    (r"not available in your country|blocked it in your country|geo[- ]?restrict|not made this video available in your country",
     "Este vídeo não está disponível na sua região. Um proxy/VPN (Configurações → Proxy) pode ajudar."),
    (r"premieres? in|will begin in|live event will begin|this live event",
     "A transmissão/estreia ainda não começou. Tente de novo mais tarde."),
    (r"video unavailable|this video is (not available|unavailable)|has been removed|no longer available|account.*terminated|does not exist",
     "O vídeo está indisponível ou foi removido."),
    (r"sign in|log ?in required|login required|requires authentication|rate-limit reached",
     "O site exige login para este conteúdo. Escolha o navegador logado em Configurações → Cookies do navegador."),
    (r"unsupported url",
     "Esse link não é suportado. Confira se é o endereço completo de um vídeo."),
    (r"requested format is not available",
     "A qualidade escolhida não existe para este vídeo. Experimente “Melhor disponível”."),
    (r"http error 429|too many requests",
     "O site limitou as requisições (muitos pedidos seguidos). Espere alguns minutos e tente de novo."),
    (r"http error 403|forbidden",
     "O site recusou o acesso (403). Atualize o yt-dlp em Ferramentas ou use os cookies do navegador."),
    (r"http error 404|404 not found",
     "O endereço não foi encontrado (404). Confira o link."),
    (r"no space left|not enough space|errno 28|disk full",
     "O disco está cheio. Libere espaço ou escolha outra pasta."),
    (r"permission denied|errno 13|access is denied",
     "Sem permissão para gravar nessa pasta. Escolha outra pasta de destino."),
    (r"ffmpeg|ffprobe",
     "O ffmpeg não foi encontrado ou falhou. Abra Ferramentas e use “Baixar / atualizar ffmpeg”."),
    (r"js runtime|javascript runtime|n challenge|signature solving|no video formats found",
     "O YouTube exige um runtime JavaScript. Abra Ferramentas e baixe o Deno; depois atualize o yt-dlp."),
    (r"getaddrinfo|name or service not known|temporary failure in name resolution|network is unreachable|"
     r"timed out|timeout|connection (reset|refused|aborted)|remote end closed|urlopen error|unable to download webpage|"
     r"unable to connect|failed to resolve|ssl",
     "Sem conexão com o site. Verifique sua internet (ou o proxy) e tente de novo."),
]


def clean_error(text):
    """Remove cores do terminal e prefixos técnicos ('ERROR: ', '[youtube] abc:')."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(text or "")).strip()
    text = re.sub(r"^(ERROR:\s*)+", "", text)
    text = re.sub(r"^(?:\[[A-Za-z][\w:.-]*\]\s*(?:[\w-]+:\s+)?)+", "", text).strip()
    return text


def friendly_error(text):
    """Traduz erros comuns do yt-dlp para uma frase clara em português."""
    raw = clean_error(text)
    for pattern, message in ERROR_RULES:
        if re.search(pattern, raw, re.I):
            return message
    return short(raw, 220) if raw else "Falhou por um motivo desconhecido. Veja o Registro."


# ---------------------------------------------------------------- histórico
def load_history(path=None):
    try:
        with open(path or HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [e for e in data if isinstance(e, dict) and e.get("url")] if isinstance(data, list) else []
    except Exception:
        return []


def save_history(entries, path=None):
    try:
        with open(path or HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries[:HISTORY_MAX], f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def filter_history(entries, text):
    t = (text or "").strip().lower()
    if not t:
        return list(entries)
    return [e for e in entries if t in (e.get("title", "") + " " + e.get("url", "")).lower()]


# ---------------------------------------------------------------- atualização do yt-dlp
def ytdlp_latest_version(url=None, timeout=15):
    req = urllib.request.Request(url or YTDLP_LATEST_API, headers={"User-Agent": "VibeGrap", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = str(data.get("tag_name") or "").lstrip("vV")
    if not tag:
        raise RuntimeError("Resposta sem número de versão.")
    return tag


def expected_sha256(sums_url=None, name="yt-dlp", timeout=20):
    """Lê o arquivo SHA2-256SUMS oficial e devolve o hash esperado do arquivo 'name'."""
    req = urllib.request.Request(sums_url or YTDLP_SUMS_URL, headers={"User-Agent": "VibeGrap"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", "replace")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise RuntimeError("Não achei o hash oficial do yt-dlp.")


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_ytdlp_update(progress=None, url=None, sums_url=None, dest=None):
    """Baixa o yt-dlp novo, confere o hash oficial e deixa em 'yt-dlp.new' (entra em uso na próxima abertura)."""
    dest = dest or UPDATE_ZIPAPP + ".new"
    tmp = dest + ".part"
    try:
        want = expected_sha256(sums_url)  # sem o hash oficial, não instala
        download_file(url or YTDLP_ZIPAPP_URL, tmp, progress)
        if sha256_file(tmp) != want:
            raise RuntimeError("O arquivo baixado não confere com o hash oficial. Nada foi instalado.")
        if not zipfile.is_zipfile(tmp) or "yt_dlp/__init__.py" not in zipfile.ZipFile(tmp).namelist():
            raise RuntimeError("Arquivo de atualização inválido.")
        os.replace(tmp, dest)
        return dest
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def open_folder(path):
    if not os.path.isdir(path):
        return
    try:
        if IS_WIN:
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:  # noqa: BLE001
        messagebox.showerror("Erro", str(exc))


class Cancelado(Exception):
    pass


class QLogger:
    """Envia as mensagens do yt-dlp para a página de registro."""

    def __init__(self, q):
        self.q = q

    def debug(self, msg):
        if not msg.startswith("[debug]"):
            self.q.put(("log", msg))

    def info(self, msg):
        self.q.put(("log", msg))

    def warning(self, msg):
        self.q.put(("log", "Aviso: " + msg))

    def error(self, msg):
        self.q.put(("log", "Erro: " + msg))


# ---------------------------------------------------------------- widgets próprios
def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER, **kw)


def lbl(parent, text="", muted=False, size=13, bold=False, **kw):
    return ctk.CTkLabel(
        parent,
        text=text,
        text_color=MUTED if muted else TXT,
        font=ctk.CTkFont(size=size, weight="bold" if bold else "normal"),
        **kw,
    )


def btn(parent, text, command, kind="primary", width=None, **kw):
    styles = {
        "primary": dict(fg_color=ACCENT, hover_color=ACCENT_H, text_color="white"),
        "soft": dict(fg_color=SOFT, hover_color=SOFT_H, text_color=TXT),
        "danger": dict(fg_color=("#fde8e8", "#3a2227"), hover_color=("#fbd5d5", "#4a2a30"), text_color=RED),
        "ghost": dict(fg_color="transparent", hover_color=SOFT_H, text_color=MUTED),
    }[kw.pop("style", kind)]
    extra = {"width": width} if width else {}
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=9, height=kw.pop("height", 36), **styles, **extra, **kw)


def menu(parent, variable, values, width=150, command=None):
    return ctk.CTkOptionMenu(
        parent,
        variable=variable,
        values=list(values),
        width=width,
        height=34,
        corner_radius=9,
        fg_color=FIELD,
        button_color=SOFT,
        button_hover_color=SOFT_H,
        text_color=TXT,
        dropdown_fg_color=CARD,
        dropdown_text_color=TXT,
        dropdown_hover_color=SOFT,
        command=command,
        dynamic_resizing=False,
    )


def entry(parent, variable=None, width=None, **kw):
    return ctk.CTkEntry(
        parent,
        textvariable=variable,
        height=36,
        corner_radius=9,
        fg_color=FIELD,
        border_color=BORDER,
        text_color=TXT,
        **({"width": width} if width else {}),
        **kw,
    )


def switch(parent, text, variable, command=None):
    return ctk.CTkSwitch(
        parent,
        text=text,
        variable=variable,
        onvalue=True,
        offvalue=False,
        progress_color=ACCENT,
        text_color=TXT,
        command=command,
    )


class PickList(ctk.CTkFrame):
    """Lista de seleção múltipla por clique (rápida mesmo com centenas de itens)."""

    def __init__(self, master, height=6, on_change=None):
        super().__init__(master, fg_color=FIELD, corner_radius=10, border_width=1, border_color=BORDER)
        font = ("Segoe UI", 10) if IS_WIN else None
        self.lb = tk.Listbox(
            self,
            height=height,
            selectmode="multiple",
            exportselection=False,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            **({"font": font} if font else {}),
        )
        self.sb = ctk.CTkScrollbar(self, command=self.lb.yview, width=12)
        self.lb.configure(yscrollcommand=self.sb.set)
        self.lb.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=8)
        self.sb.pack(side="right", fill="y", padx=3, pady=6)
        if on_change:
            self.lb.bind("<<ListboxSelect>>", lambda _e: on_change())
        self.restyle()

    def restyle(self):
        dark = ctk.get_appearance_mode() == "Dark"
        self.lb.configure(
            bg="#0f0f10" if dark else "#f4f4f5",
            fg="#f5f5f5" if dark else "#0f0f10",
            selectbackground="#ef4444" if dark else "#d62828",
            selectforeground="#ffffff",
        )

    def set(self, items):
        self.lb.delete(0, "end")
        for it in items:
            self.lb.insert("end", it)

    def clear(self):
        self.lb.delete(0, "end")

    def selected(self):
        return list(self.lb.curselection())

    def size(self):
        return self.lb.size()

    def select_all(self):
        self.lb.select_set(0, "end")
        self.lb.event_generate("<<ListboxSelect>>")

    def select_none(self):
        self.lb.select_clear(0, "end")
        self.lb.event_generate("<<ListboxSelect>>")

    def set_selected(self, indexes):
        self.lb.select_clear(0, "end")
        for i in indexes:
            self.lb.select_set(i)
        if indexes:
            self.lb.see(min(indexes))
        self.lb.event_generate("<<ListboxSelect>>")

    def get_all(self):
        return self.lb.get(0, "end")


class QueueRow(ctk.CTkFrame):
    """Um cartão da fila de downloads."""

    def __init__(self, master, title, desc, on_remove):
        super().__init__(master, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        self.columnconfigure(0, weight=1)
        self.lbl_title = lbl(self, short(title), bold=True, size=14, anchor="w", justify="left")
        self.lbl_title.grid(row=0, column=0, sticky="ew", padx=(14, 6), pady=(10, 0))
        self.lbl_state = lbl(self, "Aguardando", muted=True, anchor="e")
        self.lbl_state.grid(row=0, column=1, sticky="e", padx=6, pady=(10, 0))
        self.btn_x = ctk.CTkButton(
            self, text="✕", width=28, height=28, corner_radius=8, fg_color="transparent",
            hover_color=SOFT_H, text_color=MUTED, command=on_remove,
        )
        self.btn_x.grid(row=0, column=2, rowspan=2, padx=(0, 10))
        self.lbl_desc = lbl(self, short(desc, 80), muted=True, size=12, anchor="w")
        self.lbl_desc.grid(row=1, column=0, sticky="ew", padx=(14, 6))
        self.lbl_size = lbl(self, "", muted=True, size=12, anchor="e")
        self.lbl_size.grid(row=1, column=1, sticky="e", padx=6)
        self.bar = ctk.CTkProgressBar(self, height=6, corner_radius=3, progress_color=ACCENT, fg_color=FIELD)
        self.bar.set(0)
        self.bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(8, 12))

    def set_title(self, text):
        self.lbl_title.configure(text=short(text))

    def set_state(self, text, color=None):
        self.lbl_state.configure(text=text, text_color=color or MUTED)

    def set_progress(self, frac):
        frac = max(0.0, min(1.0, frac))
        empty = frac <= 0.001
        if empty != getattr(self, "_empty", None):  # evita a "pontinha" azul da barra vazia
            self._empty = empty
            self.bar.configure(progress_color=FIELD if empty else ACCENT)
        self.bar.set(frac)

    def set_size(self, text):
        self.lbl_size.configure(text=text)

    def set_error(self, text):
        self.lbl_desc.configure(text=short(text, 110), text_color=RED)


# ---------------------------------------------------------------- aplicação
class App(ctk.CTk):
    def __init__(self):
        self.cfg = load_settings()
        ctk.set_appearance_mode(THEMES.get(self.cfg["theme"], "system"))
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=BG)
        self.title(f"{APP_NAME}")
        w = min(1200, max(900, self.winfo_screenwidth() - 60))
        h = min(820, max(600, self.winfo_screenheight() - 100))
        self.geometry(f"{w}x{h}")
        self.minsize(900, 600)
        self._set_icon()

        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.worker = None
        self.items = {}
        self.order = []
        self.seq = 0
        self.info = None
        self.analyzed_url = None
        self.audio_langs = []
        self.sub_items = []
        self.pl_index = []
        self.warned_ffmpeg = False
        self.thumb_img = None
        self.lists = []
        self.run_ids = set()
        self.running = False
        self.cur_speed = 0
        self.last_summary = None
        self.pages = {}
        self.nav = {}
        self.update_info = None
        self.upd_win = None
        self.toast_win = None
        self.history = load_history()
        self.hist_dirty = True       # a lista só é redesenhada quando a aba Histórico está aberta
        self.current_page = "download"

        self._make_vars()
        self._build()
        self._show("download")
        self._on_mode()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._pump)
        self.after(500, self._startup_check)
        self.after(3000, self._startup_update_check)
        self.after(7000, self._startup_ytdlp_check)
        self.after(5000, cleanup_after_patch)

    # ------------------------------------------------------------ ícone
    def _set_icon(self):
        ico, png = resource_path("assets/VibeGrap_icon.ico"), resource_path("assets/VibeGrap_logo.png")
        try:
            if IS_WIN and os.path.isfile(ico):
                # o customtkinter redefine o ícone logo após abrir a janela; reaplicamos depois
                self.after(250, lambda: self.iconbitmap(ico))
            elif Image is not None and os.path.isfile(ico):
                from PIL import ImageTk
                im = Image.open(ico)
                im.size = max(im.info.get("sizes") or [im.size])
                self._icon_photo = ImageTk.PhotoImage(im.convert("RGBA"))
                self.iconphoto(True, self._icon_photo)
            elif os.path.isfile(png):
                self.iconphoto(True, tk.PhotoImage(file=png))
        except Exception:
            pass

    # ------------------------------------------------------------ variáveis
    def _make_vars(self):
        c = self.cfg
        self.v_folder = tk.StringVar(value=c["folder"])
        self.v_mode = tk.StringVar(value=c["mode"])
        self.v_plaudio = tk.BooleanVar(value=c["mode"] == "audio")  # atalho "só áudio" da aba Playlist
        self.v_plrange = tk.StringVar(value="")
        self.v_quality = tk.StringVar(value=BEST)
        self.v_container = tk.StringVar(value=c["container"])
        self.v_afmt = tk.StringVar(value=c["audio_fmt"])
        self.v_aq = tk.StringVar(value=c["audio_q"])
        self.v_lang = tk.StringVar()
        self.v_subtxt = tk.StringVar()
        self.v_sub_embed = tk.BooleanVar(value=False)
        self.v_sub_keep = tk.BooleanVar(value=True)
        self.v_playlist = tk.BooleanVar(value=False)
        self.v_start = tk.StringVar()
        self.v_end = tk.StringVar()
        self.v_precise = tk.BooleanVar(value=False)
        self.v_template = tk.StringVar(value=c["template"] if c["template"] in TEMPLATES else "Título")
        self.v_plfolder = tk.BooleanVar(value=c["playlist_folder"])
        self.v_limit = tk.StringVar(value=c["limit"])
        self.v_proxy = tk.StringVar(value=c["proxy"])
        self.v_browser = tk.StringVar(value=c["browser"] if c["browser"] in BROWSERS else "Nenhum")
        self.v_cookiefile = tk.StringVar(value=c["cookiefile"])
        self.v_meta = tk.BooleanVar(value=c["meta"])
        self.v_thumb = tk.BooleanVar(value=c["thumb"])
        self.v_overwrite = tk.BooleanVar(value=c["overwrite"])
        self.v_theme = tk.StringVar(value=c["theme"] if c["theme"] in THEMES else "Sistema")
        self.v_autoupdate = tk.BooleanVar(value=c["auto_update"])
        self.v_auto_ytdlp = tk.BooleanVar(value=c["auto_ytdlp"])
        self.v_notify = tk.BooleanVar(value=c["notify"])
        self.v_hsearch = tk.StringVar()
        self.v_status = tk.StringVar(value="Pronto.")
        self.v_audio_hint = tk.StringVar(value="Analise um link para listar as faixas de áudio disponíveis.")
        self.v_tools = tk.StringVar()
        self.v_tools_msg = tk.StringVar()

    # ------------------------------------------------------------ estrutura geral
    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_sidebar()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        stack = ctk.CTkFrame(content, fg_color="transparent")
        stack.grid(row=0, column=0, sticky="nsew")
        stack.columnconfigure(0, weight=1)
        stack.rowconfigure(0, weight=1)
        self.pages["download"] = self._page_download(stack)
        self.pages["queue"] = self._page_queue(stack)
        self.pages["history"] = self._page_history(stack)
        self.pages["settings"] = self._page_settings(stack)
        self.pages["tools"] = self._page_tools(stack)
        self.pages["log"] = self._page_log(stack)
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self._build_total(content)

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0, width=230, border_width=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.rowconfigure(10, weight=1)

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 18))
        logo = resource_path("assets/VibeGrap_logo.png")
        logo_ok = False
        if Image is not None and os.path.isfile(logo):
            try:  # o logo é opcional: se algo falhar com imagens, o app abre mesmo assim
                img = trimmed_logo(logo)
                w = 172  # largura útil da barra lateral; a altura segue a proporção do logo (sem distorcer)
                self.logo_img = ctk.CTkImage(img, size=(w, max(1, round(w * img.height / img.width))))
                card = ctk.CTkFrame(head, fg_color="#000000", corner_radius=14)  # faixa preta: o logo é branco/vermelho
                card.pack(fill="x")
                ctk.CTkLabel(card, image=self.logo_img, text="").pack(padx=10, pady=10)
                logo_ok = True
            except Exception:
                pass
        if not logo_ok:
            lbl(head, "VibeGrap", bold=True, size=17).pack(anchor="w")
            lbl(head, "Downloader", muted=True, size=12).pack(anchor="w")

        items = [
            ("download", "Novo download"),
            ("queue", "Fila"),
            ("history", "Histórico"),
            ("settings", "Configurações"),
            ("tools", "Ferramentas"),
            ("log", "Registro"),
        ]
        for i, (key, text) in enumerate(items, start=1):
            b = ctk.CTkButton(
                side, text=text, anchor="w", height=40, corner_radius=10,
                fg_color="transparent", hover_color=SOFT_H, text_color=TXT,
                font=ctk.CTkFont(size=14), command=lambda k=key: self._show(k),
            )
            b.grid(row=i, column=0, sticky="ew", padx=14, pady=2)
            self.nav[key] = b

        self.btn_update = ctk.CTkButton(
            side, text="Verificar atualização", height=36, corner_radius=10, fg_color=SOFT,
            hover_color=SOFT_H, text_color=TXT, command=self._on_update_click,
        )
        self.btn_update.grid(row=11, column=0, sticky="ew", padx=16, pady=(0, 8))
        lbl(side, f"v{APP_VERSION}  ·  yt-dlp {YTDLP_VERSION}", muted=True, size=11).grid(
            row=12, column=0, sticky="w", padx=20, pady=(0, 16)
        )

    def _show(self, name):
        self.pages[name].tkraise()
        self.current_page = name
        if name == "history" and self.hist_dirty:
            self._render_history()
        for key, b in self.nav.items():
            active = key == name
            b.configure(fg_color=SOFT if active else "transparent")

    def _header(self, parent, title, subtitle):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", padx=4, pady=(0, 10))
        lbl(box, title, bold=True, size=24).pack(anchor="w")
        lbl(box, subtitle, muted=True, size=13).pack(anchor="w", pady=(2, 0))
        return box

    # ------------------------------------------------------------ painel de progresso total
    def _build_total(self, parent):
        tc = card(parent)
        tc.grid(row=1, column=0, sticky="ew", padx=28, pady=(4, 22))
        tc.columnconfigure(0, weight=1)

        head = ctk.CTkFrame(tc, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        head.columnconfigure(1, weight=1)
        lbl(head, "Progresso total", bold=True, size=14).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, textvariable=self.v_status, text_color=MUTED, anchor="w", font=ctk.CTkFont(size=12)).grid(
            row=0, column=1, sticky="ew", padx=14
        )
        self.lbl_pct = lbl(head, "0%", bold=True, size=14)
        self.lbl_pct.grid(row=0, column=2, sticky="e")

        self.bar_total = ctk.CTkProgressBar(tc, height=12, corner_radius=6, progress_color=ACCENT, fg_color=FIELD)
        self.bar_total.set(0)
        self.bar_total.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        stats = ctk.CTkFrame(tc, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))
        self.stat = {}
        for i, (key, caption) in enumerate(
            (("items", "Itens"), ("bytes", "Baixado / Total"), ("speed", "Velocidade"), ("eta", "Tempo restante"))
        ):
            stats.columnconfigure(i, weight=1, uniform="stat")
            lbl(stats, caption, muted=True, size=11).grid(row=0, column=i, sticky="w")
            value = lbl(stats, "—", bold=True, size=14)
            value.grid(row=1, column=i, sticky="w")
            self.stat[key] = value

    # ------------------------------------------------------------ página: novo download
    def _page_download(self, parent):
        # a página é um quadro comum (para o tkraise funcionar); a rolagem fica dentro dele
        page = ctk.CTkFrame(parent, fg_color="transparent")

        # --- destino e ações: barra fixa no rodapé (sempre visível, sem precisar rolar)
        c = card(page)
        c.pack(side="bottom", fill="x", padx=28, pady=(6, 10))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=14)
        row.columnconfigure(1, weight=1)
        lbl(row, "Salvar em", muted=True).grid(row=0, column=0, sticky="w", padx=(0, 10))
        entry(row, self.v_folder).grid(row=0, column=1, sticky="ew")
        btn(row, "Escolher…", self._choose_folder, "soft", width=92).grid(row=0, column=2, padx=(8, 0))
        btn(row, "Abrir", lambda: open_folder(self.v_folder.get()), "ghost", width=56).grid(row=0, column=3, padx=(2, 12))
        btn(row, "Adicionar à fila", self._add_clicked, "soft", width=140).grid(row=0, column=4, padx=(0, 8))
        btn(row, "Baixar agora", self._download_now, "primary", width=130).grid(row=0, column=5)

        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True)
        wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=14, pady=(18, 0))
        self._header(wrap, "Novo download", "Cole um link, analise e escolha formato, faixa de áudio e legendas.")

        # --- link
        c = card(wrap)
        c.pack(fill="x", pady=6)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(16, 8))
        row.columnconfigure(0, weight=1)
        self.ent_url = ctk.CTkEntry(
            row, height=42, corner_radius=10, fg_color=FIELD, border_color=BORDER, text_color=TXT,
            placeholder_text="Cole aqui o link do vídeo ou da playlist",
        )
        self.ent_url.grid(row=0, column=0, sticky="ew")
        self.ent_url.bind("<Return>", lambda _e: self._analyze())
        btn(row, "Colar", self._paste, "soft", width=80, height=42).grid(row=0, column=1, padx=(8, 0))
        self.btn_analyze = btn(row, "Analisar", self._analyze, "primary", width=110, height=42)
        self.btn_analyze.grid(row=0, column=2, padx=(8, 0))
        row2 = ctk.CTkFrame(c, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 14))
        switch(row2, "É um link de playlist (ou vídeo dentro de uma)", self.v_playlist).pack(side="left")
        btn(row2, "Vários links…", self._batch_dialog, "ghost", width=120, height=30).pack(side="right")

        # --- informações do vídeo
        c = card(wrap)
        c.pack(fill="x", pady=6)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        self.lbl_thumb = ctk.CTkLabel(
            inner, text="Sem\nminiatura", width=176, height=99, corner_radius=10,
            fg_color=FIELD, text_color=MUTED, font=ctk.CTkFont(size=12),
        )
        self.lbl_thumb.pack(side="left")
        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self.lbl_title = lbl(txt, "Nenhum link analisado ainda", bold=True, size=16, anchor="w", justify="left", wraplength=640)
        self.lbl_title.pack(anchor="w", fill="x")
        self.lbl_meta = lbl(txt, "O título, a duração e o tamanho estimado aparecem aqui.", muted=True, anchor="w", justify="left", wraplength=640)
        self.lbl_meta.pack(anchor="w", fill="x", pady=(4, 0))
        self.lbl_stats = lbl(txt, "", muted=True, size=12, anchor="w", justify="left", wraplength=640)
        self.lbl_stats.pack(anchor="w", fill="x", pady=(4, 0))

        # --- opções
        c = card(wrap)
        c.pack(fill="x", pady=6)
        self.tabs = ctk.CTkTabview(
            c, height=356, corner_radius=12, fg_color="transparent",
            segmented_button_selected_color=SEL, segmented_button_selected_hover_color=SEL_H,
            segmented_button_unselected_color=SOFT, segmented_button_unselected_hover_color=SOFT_H,
            text_color=TXT,
        )
        self.tabs.pack(fill="x", padx=12, pady=(8, 10))
        self._tab_format(self.tabs.add("Formato e áudio"))
        self._tab_subs(self.tabs.add("Legendas"))
        self._tab_playlist(self.tabs.add("Playlist e trecho"))
        ctk.CTkFrame(wrap, fg_color="transparent", height=12).pack()
        return page

    def _tab_format(self, tab):
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))
        self.seg_mode = ctk.CTkSegmentedButton(
            top, values=list(MODE_LABELS), command=self._on_seg, height=34,
            selected_color=SEL, selected_hover_color=SEL_H,
            unselected_color=SOFT, unselected_hover_color=SOFT_H, text_color=TXT,
        )
        self.seg_mode.pack(side="left")
        self.seg_mode.set("Só áudio" if self.v_mode.get() == "audio" else "Vídeo + áudio")

        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 8))
        specs = (
            ("Qualidade máxima", "om_quality", self.v_quality, GENERIC_QUALITIES, 170, self._update_estimate),
            ("Contêiner", "om_container", self.v_container, CONTAINERS, 110, None),
            ("Formato do áudio", "om_afmt", self.v_afmt, AUDIO_FORMATS, 130, None),
            ("Qualidade (kbps)", "om_aq", self.v_aq, AUDIO_BITRATES, 110, None),
        )
        for i, (caption, attr, var, values, width, cmd) in enumerate(specs):
            col = ctk.CTkFrame(grid, fg_color="transparent")
            col.grid(row=0, column=i, padx=(0, 14), sticky="w")
            lbl(col, caption, muted=True, size=12).pack(anchor="w")
            om = menu(col, var, values, width=width, command=(lambda _v, c=cmd: c() if c else None))
            om.pack(anchor="w", pady=(2, 0))
            setattr(self, attr, om)

        lbl(tab, "Faixas de áudio (idiomas / dublagens)", bold=True).pack(anchor="w", pady=(6, 2))
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        self.pl_audio = PickList(row, height=4, on_change=self._update_estimate)
        self.lists.append(self.pl_audio)
        self.pl_audio.grid(row=0, column=0, sticky="ew")
        side = ctk.CTkFrame(row, fg_color="transparent")
        side.grid(row=0, column=1, sticky="n", padx=(14, 0))
        ctk.CTkLabel(side, textvariable=self.v_audio_hint, text_color=MUTED, wraplength=320, justify="left", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(anchor="w")
        lbl(side, "Ou digite o idioma preferido (ex.: pt, en, ja)", size=12, muted=True).pack(anchor="w", pady=(8, 2))
        entry(side, self.v_lang, width=140).pack(anchor="w")

    def _tab_subs(self, tab):
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="both", expand=True, pady=6)
        row.columnconfigure(0, weight=1)
        self.pl_subs = PickList(row, height=8)
        self.lists.append(self.pl_subs)
        self.pl_subs.grid(row=0, column=0, sticky="nsew")
        side = ctk.CTkFrame(row, fg_color="transparent")
        side.grid(row=0, column=1, sticky="n", padx=(14, 0))
        lbl(side, "Clique nos idiomas desejados na lista\nou digite os códigos (ex.: pt,en):", muted=True, size=12, justify="left", anchor="w").pack(anchor="w")
        entry(side, self.v_subtxt, width=240).pack(anchor="w", pady=(6, 10))
        switch(side, "Embutir legendas no vídeo", self.v_sub_embed).pack(anchor="w", pady=3)
        switch(side, "Manter também o arquivo .srt", self.v_sub_keep).pack(anchor="w", pady=3)

    def _tab_playlist(self, tab):
        rng = ctk.CTkFrame(tab, fg_color="transparent")
        rng.pack(fill="x", pady=(6, 0))
        lbl(rng, "Itens", muted=True).pack(side="left")
        self.ent_plrange = entry(rng, self.v_plrange, width=230, placeholder_text="ex.: 1-10, 15, 20-25")
        self.ent_plrange.pack(side="left", padx=(8, 8))
        self.ent_plrange.bind("<Return>", lambda _e: self._pl_apply())
        btn(rng, "Aplicar", self._pl_apply, "soft", width=90).pack(side="left")
        self.lbl_plcount = lbl(rng, "", muted=True, size=12)
        self.lbl_plcount.pack(side="left", padx=12)

        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", pady=(6, 8))
        row.columnconfigure(0, weight=1)
        self.pl_items = PickList(row, height=4, on_change=self._pl_count)
        self.lists.append(self.pl_items)
        self.pl_items.grid(row=0, column=0, sticky="ew")
        side = ctk.CTkFrame(row, fg_color="transparent")
        side.grid(row=0, column=1, sticky="n", padx=(14, 0))
        btn(side, "Selecionar tudo", self.pl_items.select_all, "soft", width=150).pack(pady=(0, 6))
        btn(side, "Limpar seleção", self.pl_items.select_none, "soft", width=150).pack()

        sw = ctk.CTkFrame(tab, fg_color="transparent")
        sw.pack(fill="x", pady=(0, 10))
        switch(sw, "Extrair só o áudio de todos os itens", self.v_plaudio, self._on_pl_audio).pack(side="left")
        lbl(sw, "usa o formato e a qualidade da aba “Formato e áudio”", muted=True, size=12).pack(side="left", padx=12)

        lbl(tab, "Baixar só um trecho (vídeo único)", bold=True).pack(anchor="w", pady=(4, 2))
        cut = ctk.CTkFrame(tab, fg_color="transparent")
        cut.pack(fill="x")
        lbl(cut, "Início", muted=True).pack(side="left")
        entry(cut, self.v_start, width=100).pack(side="left", padx=(6, 14))
        lbl(cut, "Fim", muted=True).pack(side="left")
        entry(cut, self.v_end, width=100).pack(side="left", padx=(6, 14))
        lbl(cut, "ex.: 1:30  ou  01:02:03", muted=True, size=12).pack(side="left")
        switch(cut, "Corte preciso (mais lento)", self.v_precise).pack(side="left", padx=18)

    # ------------------------------------------------------------ página: fila
    def _page_queue(self, parent):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        wrap = ctk.CTkFrame(page, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=28, pady=(18, 0))
        self._header(wrap, "Fila de downloads", "Acompanhe cada item. Os que falharem podem ser tentados de novo.")
        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        self.btn_start = btn(bar, "Iniciar fila", self._start_queue, "primary", width=130)
        self.btn_start.pack(side="left")
        self.btn_cancel = btn(bar, "Cancelar", self._cancel, "danger", width=110)
        self.btn_cancel.pack(side="left", padx=8)
        self.btn_cancel.configure(state="disabled")
        btn(bar, "Limpar concluídos", self._clear_done, "soft", width=150).pack(side="left")
        self.lbl_empty = lbl(wrap, "A fila está vazia. Adicione um link em “Novo download”.", muted=True)
        self.lbl_empty.pack(pady=(10, 0))
        self.qframe = ctk.CTkScrollableFrame(wrap, fg_color="transparent", corner_radius=0)
        self.qframe.pack(fill="both", expand=True)
        return page

    # ------------------------------------------------------------ página: histórico
    def _page_history(self, parent):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        wrap = ctk.CTkFrame(page, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=28, pady=(18, 0))
        self._header(wrap, "Histórico", "O que você já baixou. Fica salvo mesmo depois de fechar o programa.")
        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        self.ent_hsearch = entry(bar, self.v_hsearch, placeholder_text="Buscar por título ou link…")
        self.ent_hsearch.pack(side="left", fill="x", expand=True)
        btn(bar, "Limpar histórico", self._clear_history, "soft", width=150).pack(side="left", padx=(8, 0))
        self.v_hsearch.trace_add("write", lambda *_: self._render_history())
        self.lbl_hempty = lbl(wrap, "", muted=True)
        self.lbl_hempty.pack(pady=(10, 0))
        self.hframe = ctk.CTkScrollableFrame(wrap, fg_color="transparent", corner_radius=0)
        self.hframe.pack(fill="both", expand=True)
        self._render_history()
        return page

    def _render_history(self):
        self.hist_dirty = False
        for w in self.hframe.winfo_children():
            w.destroy()
        rows = filter_history(self.history, self.v_hsearch.get())
        self.nav["history"].configure(text="Histórico")
        if not rows:
            self.lbl_hempty.configure(
                text="Nada encontrado." if self.history else "Ainda não há downloads no histórico."
            )
            return
        self.lbl_hempty.configure(text="")
        for e in rows[:100]:
            r = ctk.CTkFrame(self.hframe, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
            r.pack(fill="x", pady=5, padx=2)
            r.columnconfigure(0, weight=1)
            lbl(r, short(e.get("title") or e["url"]), bold=True, size=14, anchor="w", justify="left").grid(
                row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
            ok = e.get("status") != "Erro"
            info = " · ".join(x for x in (e.get("date", ""), fmt_size(e["size"]) if e.get("size") else "", e.get("status", "")) if x)
            l2 = lbl(r, info, muted=True, size=12, anchor="w")
            if not ok:
                l2.configure(text_color=RED)
            l2.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
            acts = ctk.CTkFrame(r, fg_color="transparent")
            acts.grid(row=0, column=1, rowspan=2, padx=10)
            btn(acts, "Abrir pasta", lambda f=e.get("folder", ""): open_folder(f), "soft", width=100).pack(side="left", padx=3)
            btn(acts, "Copiar link", lambda u=e["url"]: self._copy_text(u), "soft", width=100).pack(side="left", padx=3)
            btn(acts, "Usar de novo", lambda u=e["url"]: self._reuse_url(u), "soft", width=110).pack(side="left", padx=3)
        if len(rows) > 100:
            lbl(self.hframe, f"Mostrando 100 de {len(rows)}. Use a busca para achar os outros.", muted=True, size=12).pack(pady=8)

    def _copy_text(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.v_status.set("Link copiado.")

    def _reuse_url(self, url):
        self.ent_url.delete(0, "end")
        self.ent_url.insert(0, url)
        self._show("download")

    def _clear_history(self):
        if self.history and messagebox.askyesno("Limpar histórico", "Apagar todo o histórico? Os arquivos baixados não são apagados."):
            self.history = []
            save_history([])
            self._render_history()

    def _record_history(self, it, status):
        size = it.get("done") or 0
        entry = {
            "title": re.sub(r"^\[Playlist\]\s*", "", it.get("title") or ""),
            "url": it["url"],
            "folder": (it.get("opts", {}).get("paths") or {}).get("home", ""),
            "size": int(size),
            "status": status,
            "date": time.strftime("%d/%m/%Y %H:%M"),
        }
        self.history.insert(0, entry)
        del self.history[HISTORY_MAX:]
        save_history(self.history)
        self.hist_dirty = True
        if self.current_page == "history":
            self._render_history()

    # ------------------------------------------------------------ aviso ao terminar
    def _should_notify(self):
        try:
            return self.state() == "iconic" or self.focus_displayof() is None
        except Exception:  # noqa: BLE001
            return False

    def _toast(self, title, text, ms=8000):
        """Pequeno aviso no canto da tela (funciona em qualquer sistema, sem depender de nada extra)."""
        try:
            if self.toast_win is not None and self.toast_win.winfo_exists():
                self.toast_win.destroy()
            t = self.toast_win = ctk.CTkToplevel(self, fg_color=BG)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            box = ctk.CTkFrame(t, fg_color=CARD, border_width=2, border_color=ACCENT, corner_radius=12)
            box.pack(fill="both", expand=True)
            lbl(box, title, bold=True, size=14).pack(anchor="w", padx=16, pady=(12, 0))
            ctk.CTkLabel(box, text=text, text_color=MUTED, justify="left", anchor="w", wraplength=300,
                         font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(2, 12))
            t.update_idletasks()
            w, h = max(t.winfo_reqwidth(), 340), t.winfo_reqheight()
            t.geometry(f"{w}x{h}+{self.winfo_screenwidth() - w - 24}+{self.winfo_screenheight() - h - 72}")

            def open_app(_e=None):
                t.destroy()
                self.deiconify()
                self.lift()
                self.focus_force()

            for widget in (t, box, *box.winfo_children()):
                widget.bind("<Button-1>", open_app)
            t.after(ms, lambda: t.winfo_exists() and t.destroy())
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ atualização automática do yt-dlp
    def _startup_ytdlp_check(self):
        if self.v_auto_ytdlp.get() and FROZEN:
            threading.Thread(target=self._ytdlp_auto_worker, daemon=True).start()

    def _ytdlp_auto_worker(self):
        try:
            latest = ytdlp_latest_version()
            if not is_newer(latest, YTDLP_VERSION):
                self.q.put(("ytdlp", "uptodate", latest))
                return
            if os.path.isfile(UPDATE_ZIPAPP + ".new"):
                return  # já há uma atualização esperando a próxima abertura
            stage_ytdlp_update()
            self.q.put(("ytdlp", "staged", latest))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("ytdlp", "error", str(exc)))

    def _on_ytdlp_msg(self, msg):
        kind, val = msg[1], msg[2]
        if kind == "staged":
            self._log(f"yt-dlp {val} baixado e verificado. Entra em uso na próxima vez que abrir o programa.")
            self.v_status.set(f"yt-dlp {val} pronto: será usado na próxima abertura.")
        elif kind == "uptodate":
            self._log(f"yt-dlp está em dia ({YTDLP_VERSION}).")
        else:
            self._log(f"Não consegui verificar/atualizar o yt-dlp agora: {val}")

    # ------------------------------------------------------------ página: configurações
    def _page_settings(self, parent):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True)
        wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=14, pady=(18, 0))
        self._header(wrap, "Configurações", "Preferências gerais. Tudo é salvo automaticamente.")

        c = card(wrap)
        c.pack(fill="x", pady=6)
        g = ctk.CTkFrame(c, fg_color="transparent")
        g.pack(fill="x", padx=18, pady=16)
        g.columnconfigure(1, weight=1)

        def row(r, caption, widget_factory, hint=""):
            lbl(g, caption).grid(row=r, column=0, sticky="w", pady=7, padx=(0, 16))
            w = widget_factory(g)
            w.grid(row=r, column=1, sticky="ew", pady=7)
            if hint:
                lbl(g, hint, muted=True, size=12).grid(row=r, column=2, sticky="w", padx=(12, 0))

        row(0, "Aparência", lambda p: menu(p, self.v_theme, list(THEMES), width=160, command=self._set_theme))
        row(1, "Nome do arquivo", lambda p: menu(p, self.v_template, list(TEMPLATES), width=240))
        row(2, "Limite de velocidade", lambda p: entry(p, self.v_limit, width=160), "ex.: 500K, 2M")
        row(3, "Proxy", lambda p: entry(p, self.v_proxy), "ex.: http://127.0.0.1:8080")
        row(4, "Cookies do navegador", lambda p: menu(p, self.v_browser, BROWSERS, width=160), "para vídeos com login ou restrição de idade")

        def cookie_row(p):
            f = ctk.CTkFrame(p, fg_color="transparent")
            f.columnconfigure(0, weight=1)
            entry(f, self.v_cookiefile).grid(row=0, column=0, sticky="ew")
            btn(f, "Escolher…", self._choose_cookies, "soft", width=96).grid(row=0, column=1, padx=(8, 0))
            return f

        row(5, "ou arquivo cookies.txt", cookie_row)

        c = card(wrap)
        c.pack(fill="x", pady=6)
        s = ctk.CTkFrame(c, fg_color="transparent")
        s.pack(fill="x", padx=18, pady=16)
        switch(s, "Pasta própria para playlists", self.v_plfolder).pack(anchor="w", pady=5)
        switch(s, "Gravar metadados e capítulos no arquivo", self.v_meta).pack(anchor="w", pady=5)
        switch(s, "Embutir miniatura (capa) no arquivo", self.v_thumb).pack(anchor="w", pady=5)
        switch(s, "Sobrescrever arquivos já existentes", self.v_overwrite).pack(anchor="w", pady=5)
        switch(s, "Verificar se há versão nova do programa ao abrir", self.v_autoupdate).pack(anchor="w", pady=5)
        switch(s, "Manter o yt-dlp atualizado sozinho (confere o hash oficial)", self.v_auto_ytdlp).pack(anchor="w", pady=5)
        switch(s, "Avisar quando os downloads terminarem (com o programa em segundo plano)", self.v_notify).pack(anchor="w", pady=5)
        return page

    # ------------------------------------------------------------ página: ferramentas
    def _page_tools(self, parent):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        wrap = ctk.CTkFrame(page, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=28, pady=(18, 0))
        self._header(wrap, "Ferramentas", "Componentes usados pelo yt-dlp para funcionar bem.")
        c = card(wrap)
        c.pack(fill="x", pady=6)
        ctk.CTkLabel(c, textvariable=self.v_tools, justify="left", anchor="w", text_color=TXT,
                     font=ctk.CTkFont(family="Consolas" if IS_WIN else "monospace", size=12)).pack(fill="x", padx=18, pady=16)
        c2 = card(wrap)
        c2.pack(fill="x", pady=6)
        inner = ctk.CTkFrame(c2, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)
        self.pb_tools = ctk.CTkProgressBar(inner, height=10, corner_radius=5, progress_color=ACCENT, fg_color=FIELD)
        self.pb_tools.set(0)
        self.pb_tools.pack(fill="x")
        ctk.CTkLabel(inner, textvariable=self.v_tools_msg, text_color=MUTED, anchor="w").pack(fill="x", pady=(6, 10))
        self.tool_buttons = [
            btn(inner, "Baixar / atualizar ffmpeg", lambda: self._run_tool("ffmpeg"), "soft"),
            btn(inner, "Baixar Deno (necessário para o YouTube)", lambda: self._run_tool("deno"), "soft"),
            btn(inner, "Atualizar o yt-dlp (reinicie o programa depois)", lambda: self._run_tool("ytdlp"), "soft"),
        ]
        for b in self.tool_buttons:
            b.pack(fill="x", pady=4)
        btn(inner, "Abrir pasta das ferramentas", lambda: open_folder(BIN_DIR), "ghost").pack(fill="x", pady=4)

        c3 = card(wrap)
        c3.pack(fill="x", pady=6)
        about = ctk.CTkFrame(c3, fg_color="transparent")
        about.pack(fill="x", padx=18, pady=16)
        lbl(about, f"{APP_NAME} v{APP_VERSION}  ·  software livre (licença MIT)", bold=True).pack(anchor="w")
        ctk.CTkLabel(about, text=ABOUT_TEXT, justify="left", anchor="w", text_color=MUTED, wraplength=760,
                     font=ctk.CTkFont(size=12)).pack(fill="x", pady=(6, 10))
        btn(about, "Licenças e créditos", self._about_dialog, "soft", width=190).pack(anchor="w")
        self._refresh_tools()
        return page

    def _about_dialog(self):
        """Mostra a licença do programa e os créditos/licenças de terceiros."""
        parts = []
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            for folder in (exe_dir(), resource_path(".")):
                path = os.path.join(folder, name)
                if os.path.isfile(path):
                    try:
                        with open(path, encoding="utf-8") as f:
                            parts.append(f.read().strip())
                    except OSError:
                        pass
                    break
        text = ("\n\n" + "─" * 60 + "\n\n").join(parts) or (
            "Os arquivos de licença não foram encontrados nesta instalação.\n"
            "Eles acompanham o código-fonte: LICENSE e THIRD_PARTY_NOTICES.md."
        )
        win = getattr(self, "about_win", None)
        if win is not None and win.winfo_exists():
            win.focus()
            return
        win = self.about_win = ctk.CTkToplevel(self, fg_color=BG)
        win.title("Licenças e créditos")
        win.geometry("820x600")
        win.transient(self)
        self.about_text = ctk.CTkTextbox(
            win, corner_radius=12, fg_color=CARD, border_width=1, border_color=BORDER, text_color=TXT, wrap="word",
            font=ctk.CTkFont(size=12),
        )
        self.about_text.pack(fill="both", expand=True, padx=18, pady=(18, 8))
        self.about_text.insert("1.0", text)
        self.about_text.configure(state="disabled")
        btn(win, "Fechar", win.destroy, "soft", width=110).pack(anchor="e", padx=18, pady=(0, 16))
        win.after(150, win.focus)

    # ------------------------------------------------------------ página: registro
    def _page_log(self, parent):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        wrap = ctk.CTkFrame(page, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=28, pady=(18, 22))
        self._header(wrap, "Registro", "Mensagens detalhadas do yt-dlp. Útil para entender erros.")
        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        btn(bar, "Limpar registro", self._clear_log, "soft", width=140).pack(side="left")
        self.txt_log = ctk.CTkTextbox(
            wrap, corner_radius=12, fg_color=CARD, border_width=1, border_color=BORDER, text_color=TXT,
            font=ctk.CTkFont(family="Consolas" if IS_WIN else "monospace", size=12), wrap="word",
        )
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.configure(state="disabled")
        return page

    # ------------------------------------------------------------ pequenos handlers
    def _url(self):
        return self.ent_url.get().strip()

    def _on_seg(self, label):
        self.v_mode.set(MODE_LABELS[label])
        self.v_plaudio.set(self.v_mode.get() == "audio")
        self.seg_mode.set(label)
        self._on_mode()
        self._update_estimate()

    def _on_pl_audio(self):
        label = "Só áudio" if self.v_plaudio.get() else "Vídeo + áudio"
        self.seg_mode.set(label)
        self._on_seg(label)

    def _pl_count(self):
        total = len(self.pl_index)
        if total:
            self.lbl_plcount.configure(text=f"{len(self.pl_items.selected())} de {total} selecionados", text_color=MUTED)
        else:
            self.lbl_plcount.configure(text="", text_color=MUTED)

    def _pl_apply(self):
        """Marca na lista os itens digitados (1-10, 15, 20-)."""
        if not self.pl_index:
            self.lbl_plcount.configure(text="Analise uma playlist primeiro.", text_color=RED)
            return
        text = self.v_plrange.get().strip()
        if not text:
            self.pl_items.select_all()
            self._pl_count()
            return
        nums, problems = parse_item_ranges(text, max(self.pl_index))
        where = {pos: i for i, pos in enumerate(self.pl_index)}
        self.pl_items.set_selected([where[n] for n in nums if n in where])
        self._pl_count()
        if problems:
            self.lbl_plcount.configure(text="; ".join(problems[:2]), text_color=RED)
        elif not nums:
            self.lbl_plcount.configure(text="Nenhum item encontrado nesse intervalo.", text_color=RED)

    def _on_mode(self):
        audio = self.v_mode.get() == "audio"
        self.om_quality.configure(state="disabled" if audio else "normal")
        self.om_container.configure(state="disabled" if audio else "normal")
        self.om_afmt.configure(state="normal" if audio else "disabled")
        self.om_aq.configure(state="normal" if audio else "disabled")

    def _set_theme(self, label):
        ctk.set_appearance_mode(THEMES.get(label, "system"))
        for pl in self.lists:
            pl.restyle()
        self._save_cfg()

    def _paste(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        self.ent_url.delete(0, "end")
        self.ent_url.insert(0, text)

    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.v_folder.get() or None)
        if folder:
            self.v_folder.set(folder)

    def _choose_cookies(self):
        path = filedialog.askopenfilename(filetypes=[("cookies.txt", "*.txt"), ("Todos", "*.*")])
        if path:
            self.v_cookiefile.set(path)

    def _log(self, msg):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", str(msg).rstrip() + "\n")
        lines = int(self.txt_log.index("end-1c").split(".")[0])
        if lines > 1000:
            self.txt_log.delete("1.0", f"{lines - 800}.0")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _clear_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    def _startup_check(self):
        if not ffmpeg_location():
            self._log("Aviso: ffmpeg não encontrado. Abra Ferramentas para instalar (necessário para juntar vídeo+áudio e converter).")
            if IS_WIN and messagebox.askyesno(
                "Componente necessário",
                "O ffmpeg não foi encontrado. Ele é necessário para juntar vídeo e áudio, converter para MP3 etc.\n\n"
                "Abrir as Ferramentas para baixá-lo agora?",
            ):
                self._show("tools")
        if not detect_js_runtime():
            self._log("Dica: para o YouTube funcionar é preciso um runtime JavaScript (Deno ou Node). Veja Ferramentas.")

    def _save_cfg(self):
        self.cfg.update(
            folder=self.v_folder.get(), mode=self.v_mode.get(), container=self.v_container.get(),
            audio_fmt=self.v_afmt.get(), audio_q=self.v_aq.get(), template=self.v_template.get(),
            playlist_folder=self.v_plfolder.get(), browser=self.v_browser.get(), cookiefile=self.v_cookiefile.get(),
            proxy=self.v_proxy.get(), limit=self.v_limit.get(), meta=self.v_meta.get(), thumb=self.v_thumb.get(),
            overwrite=self.v_overwrite.get(), theme=self.v_theme.get(), auto_update=self.v_autoupdate.get(),
            auto_ytdlp=self.v_auto_ytdlp.get(), notify=self.v_notify.get(),
        )
        save_settings(self.cfg)

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Sair", "Há downloads em andamento. Cancelar e sair?"):
                return
            self.cancel.set()
        self._save_cfg()
        self.destroy()

    # ------------------------------------------------------------ opções comuns
    def _base_opts(self):
        opts = {
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "logger": QLogger(self.q),
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 30,
        }
        loc = ffmpeg_location()
        if loc:
            opts["ffmpeg_location"] = loc
        js = detect_js_runtime()
        if js:
            opts["js_runtimes"] = {js[0]: {"path": js[1]}}
        proxy = self.v_proxy.get().strip()
        if proxy:
            opts["proxy"] = proxy
        cookiefile = self.v_cookiefile.get().strip()
        browser = self.v_browser.get()
        if cookiefile and os.path.isfile(cookiefile):
            opts["cookiefile"] = cookiefile
        elif browser and browser != "Nenhum":
            opts["cookiesfrombrowser"] = (browser,)
        return opts

    # ------------------------------------------------------------ análise
    def _analyze(self):
        url = self._url()
        if not url:
            messagebox.showwarning("Atenção", "Cole um link primeiro.")
            return
        self.btn_analyze.configure(state="disabled", text="Analisando…")
        self.lbl_title.configure(text="Analisando o link…")
        self.lbl_meta.configure(text="Pode levar alguns segundos.")
        self.lbl_stats.configure(text="")
        opts = self._base_opts()
        opts.update({"skip_download": True, "extract_flat": "in_playlist", "noplaylist": not self.v_playlist.get()})
        threading.Thread(target=self._analyze_worker, args=(url, opts), daemon=True).start()

    def _analyze_worker(self, url, opts):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                info = ydl.sanitize_info(info)
            self.q.put(("info", url, info))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("info_error", url, str(exc)))

    def _fetch_thumb(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read(5_000_000)
            self.q.put(("thumb", url, data))
        except Exception:
            pass

    def _set_thumb(self, data):
        if Image is None:
            return
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img = ImageOps.fit(img, (352, 198), Image.LANCZOS)
            self.thumb_img = ctk.CTkImage(light_image=img, dark_image=img, size=(176, 99))
            self.lbl_thumb.configure(image=self.thumb_img, text="")
        except Exception:
            pass

    def _on_info(self, url, info):
        self.btn_analyze.configure(state="normal", text="Analisar")
        if not info:
            self.lbl_title.configure(text="Não foi possível obter informações desse link.")
            return
        self.info = info
        self.analyzed_url = url
        self.pl_audio.clear()
        self.pl_subs.clear()
        self.pl_items.clear()
        self.audio_langs, self.sub_items, self.pl_index = [], [], []
        self._pl_count()
        self.lbl_thumb.configure(image=None, text="Sem\nminiatura")
        self.thumb_img = None
        thumb = info.get("thumbnail")
        if thumb and Image is not None:
            threading.Thread(target=self._fetch_thumb, args=(thumb,), daemon=True).start()

        if info.get("_type") == "playlist":
            self._fill_playlist(info)
        else:
            self._fill_single(info)

    def _fill_single(self, info):
        formats = info.get("formats") or []
        heights = sorted({f["height"] for f in formats if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
        self.om_quality.configure(values=[BEST] + [f"{h}p" for h in heights])
        self.v_quality.set(BEST)

        tracks = {}
        for f in formats:
            if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none") and f.get("language"):
                lang = f["language"]
                abr = f.get("abr") or 0
                if lang not in tracks or abr > tracks[lang][0]:
                    tracks[lang] = (abr, f.get("format_note") or "")
        labels = []
        for lang in sorted(tracks):
            note = re.sub(r",\s*(ultralow|low|medium|high)\s*$", "", tracks[lang][1])
            self.audio_langs.append(lang)
            labels.append(f"{lang}  —  {note}" if note else lang)
        self.pl_audio.set(labels)
        if len(tracks) >= 2:
            self.v_audio_hint.set(
                f"{len(tracks)} faixas de áudio encontradas. Clique nas que quiser (várias é possível). "
                "Nada selecionado = faixa padrão."
            )
        elif len(tracks) == 1:
            self.v_audio_hint.set("Esta fonte tem apenas uma faixa de áudio com idioma identificado.")
        else:
            self.v_audio_hint.set("Esta fonte não separa faixas de áudio por idioma (será usada a padrão).")

        subs = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        sub_labels = []
        for lang in sorted(subs):
            if lang == "live_chat":
                continue
            name = (subs[lang][0].get("name") if subs[lang] else "") or ""
            self.sub_items.append((lang, False))
            sub_labels.append(f"{lang}  —  {name}" if name else lang)
        for lang in sorted(auto):
            name = (auto[lang][0].get("name") if auto[lang] else "") or ""
            self.sub_items.append((lang, True))
            sub_labels.append(f"{lang}  —  {name} (automática)" if name else f"{lang}  (automática)")
        self.pl_subs.set(sub_labels)

        self.lbl_title.configure(text=short(info.get("title") or "(sem título)", 140))
        bits = [info.get("uploader") or info.get("channel") or "", fmt_dur(info.get("duration")) if info.get("duration") else ""]
        if info.get("is_live"):
            bits.append("AO VIVO")
        self.lbl_meta.configure(text="  ·  ".join(b for b in bits if b) or " ")
        self._stats_base = f"{len(heights)} qualidades  ·  {len(tracks)} faixas de áudio  ·  {len(sub_labels)} legendas"
        self._update_estimate()

    def _fill_playlist(self, info):
        self.om_quality.configure(values=GENERIC_QUALITIES)
        self.v_quality.set(BEST)
        labels = []
        for pos, entry_ in enumerate(info.get("entries") or [], 1):
            if not entry_:
                continue
            title = entry_.get("title") or entry_.get("url") or entry_.get("id") or "(sem título)"
            self.pl_index.append(pos)
            labels.append(f"{pos:>3}. {title}")
        self.pl_items.set(labels)
        self.v_plrange.set("")
        self.pl_items.select_all()
        self._pl_count()
        self.v_audio_hint.set("Playlist: use o campo de idioma preferido abaixo (vale para todos os vídeos).")
        self.lbl_title.configure(text=short("Playlist: " + (info.get("title") or "(sem título)"), 140))
        self.lbl_meta.configure(text=f"{len(self.pl_index)} itens  ·  escolha quais baixar na aba “Playlist e trecho”")
        self.lbl_stats.configure(text="")
        self._stats_base = ""
        self.tabs.set("Playlist e trecho")

    def _update_estimate(self):
        """Atualiza o tamanho estimado mostrado no cartão do vídeo."""
        info = self.info
        if not info or info.get("_type") == "playlist" or self._url() != self.analyzed_url:
            return
        _mode, _h, _exact, _prefix, fmt, multi = self._format_choice(info, bool(ffmpeg_location()))
        size = estimate_size(info, fmt, multi)
        base = getattr(self, "_stats_base", "")
        extra = f"Tamanho estimado: ~{fmt_size(size)}" if size else "Tamanho estimado: indisponível para este link"
        self.lbl_stats.configure(text=f"{base}\n{extra}" if base else extra)

    # ------------------------------------------------------------ montar um item da fila
    def _format_choice(self, info, have_ff):
        mode = self.v_mode.get()
        m = re.match(r"(\d+)p", self.v_quality.get())
        height = int(m.group(1)) if m else None
        exact = [self.audio_langs[i] for i in self.pl_audio.selected() if i < len(self.audio_langs)] if info else []
        prefix = self.v_lang.get().strip()
        fmt, multi = build_format(mode, height, exact, prefix, can_merge=have_ff)
        return mode, height, exact, prefix, fmt, multi

    def _build_item(self, url):
        """Lê as opções da tela e devolve um item da fila (ou None se algo estiver inválido)."""
        info = self.info if (self.info and url == self.analyzed_url) else None
        is_playlist = bool(info and info.get("_type") == "playlist")
        have_ff = bool(ffmpeg_location())

        if not have_ff and not self.warned_ffmpeg:
            self.warned_ffmpeg = True
            if IS_WIN and messagebox.askyesno(
                "ffmpeg não encontrado",
                "Sem o ffmpeg não é possível juntar vídeo+áudio, converter áudio, embutir legendas/capa.\n"
                "Abrir as Ferramentas para baixá-lo agora?",
            ):
                self._show("tools")
                return None

        mode, height, exact, prefix, fmt, multi = self._format_choice(info, have_ff)
        qtxt = self.v_quality.get()

        opts = self._base_opts()
        opts["format"] = fmt
        folder = self.v_folder.get().strip()
        if not folder:
            messagebox.showwarning("Atenção", "Escolha a pasta de destino.")
            return None
        opts["paths"] = {"home": folder}
        tpl = TEMPLATES[self.v_template.get()]
        if self.v_plfolder.get():
            tpl = "%(playlist_title&{}/|)s" + tpl
        opts["outtmpl"] = tpl
        opts["noplaylist"] = not self.v_playlist.get() and not is_playlist
        opts["windowsfilenames"] = IS_WIN
        opts["trim_file_name"] = 150
        opts["overwrites"] = True if self.v_overwrite.get() else None
        if is_playlist:
            opts["ignoreerrors"] = True
            if self.pl_index:
                sel = [self.pl_index[i] for i in self.pl_items.selected() if i < len(self.pl_index)]
                if not sel:
                    messagebox.showwarning("Atenção", "Selecione pelo menos um item da playlist.")
                    return None
                if len(sel) < len(self.pl_index):
                    opts["playlist_items"] = compress_items(sel)

        pps = []
        notes = []

        # --- áudio / vídeo
        if mode == "audio":
            codec = self.v_afmt.get()
            codec = "best" if codec == "original" else codec
            if have_ff:
                pp = {"key": "FFmpegExtractAudio", "preferredcodec": codec}
                if codec in ("mp3", "m4a", "opus"):
                    pp["preferredquality"] = self.v_aq.get()
                pps.append(pp)
            else:
                self._log("Aviso: sem ffmpeg, o áudio será salvo no formato original (sem conversão).")
            notes.append("Áudio " + (codec.upper() if codec != "best" else "original"))
        else:
            container = self.v_container.get()
            if multi and container != "mkv":
                container = "mkv"
                self._log("Várias faixas de áudio: contêiner alterado para MKV.")
            opts["merge_output_format"] = container
            notes.append(f"{qtxt if height else 'Melhor'} {container.upper()}")
        if multi:
            opts["allow_multiple_audio_streams"] = True
        if exact:
            notes.append("áudio: " + ",".join(exact))
        elif prefix:
            notes.append(f"áudio: {prefix}*")

        # --- legendas
        sub_langs, want_manual, want_auto = [], False, False
        if info and not is_playlist:
            for i in self.pl_subs.selected():
                if i >= len(self.sub_items):
                    continue
                lang, is_auto = self.sub_items[i]
                sub_langs.append(lang)
                want_auto = want_auto or is_auto
                want_manual = want_manual or not is_auto
        typed = [s.strip() for s in self.v_subtxt.get().split(",") if s.strip()]
        for s in typed:
            if s not in sub_langs:
                sub_langs.append(s)
        if typed:
            want_manual = want_auto = True
        if sub_langs:
            opts["subtitleslangs"] = sub_langs
            opts["writesubtitles"] = want_manual
            opts["writeautomaticsub"] = want_auto
            opts["subtitlesformat"] = "srt/best"
            notes.append("legendas: " + ",".join(sub_langs[:3]) + ("…" if len(sub_langs) > 3 else ""))
            if have_ff:
                pps.append({"key": "FFmpegSubtitlesConvertor", "format": "srt", "when": "before_dl"})
                if self.v_sub_embed.get() and mode == "video":
                    pps.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": bool(self.v_sub_keep.get())})

        # --- trecho
        factor = 1.0
        try:
            start, end = parse_time(self.v_start.get()), parse_time(self.v_end.get())
        except ValueError:
            messagebox.showwarning("Atenção", "Tempo inválido. Use formatos como 90, 1:30 ou 01:02:03.")
            return None
        if (start is not None or end is not None) and not is_playlist:
            if end is not None and start is not None and end <= start:
                messagebox.showwarning("Atenção", "O fim do trecho deve ser maior que o início.")
                return None
            opts["download_ranges"] = yt_dlp.utils.download_range_func(
                None, [(start or 0.0, end if end is not None else float("inf"))]
            )
            opts["force_keyframes_at_cuts"] = bool(self.v_precise.get())
            notes.append(f"trecho {fmt_dur(start or 0)}–{fmt_dur(end) if end else 'fim'}")
            dur = (info or {}).get("duration")
            if dur:
                span = (min(end, dur) if end is not None else dur) - (start or 0.0)
                factor = max(span, 0) / dur

        # --- limite de velocidade
        limit = self.v_limit.get().strip()
        if limit:
            rate = yt_dlp.utils.parse_bytes(limit)
            if not rate:
                messagebox.showwarning("Atenção", "Limite de velocidade inválido. Use, por exemplo, 500K ou 2M.")
                return None
            opts["ratelimit"] = rate

        # --- metadados / miniatura (dependem do ffmpeg)
        if have_ff:
            if self.v_meta.get():
                pps.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})
            if self.v_thumb.get():
                opts["writethumbnail"] = True
                pps.append({"key": "EmbedThumbnail"})
        opts["postprocessors"] = pps

        est = None
        if info and not is_playlist:
            est = estimate_size(info, fmt, multi, factor)
        title = info.get("title") if info else None
        title = title or url
        if is_playlist:
            title = f"[Playlist] {title}"
        return {"url": url, "title": title, "desc": " · ".join(notes), "opts": opts, "playlist": is_playlist, "est": est}

    # ------------------------------------------------------------ fila
    def _reset_progress(self, item):
        item.update(files={}, entries={}, frac=0.0, done=0, total=item.get("est") or 0, approx=bool(item.get("est")), n_entries=0)

    def _add_item(self, item):
        with self.lock:
            self.seq += 1
            iid = str(self.seq)
            item["status"] = "Aguardando"
            self._reset_progress(item)
            row = QueueRow(self.qframe, item["title"], item["desc"], on_remove=lambda i=iid: self._remove_item(i))
            row.pack(fill="x", pady=5, padx=2)
            if item.get("est"):
                row.set_size(f"~{fmt_size(item['est'])}")
            item["row"] = row
            self.items[iid] = item
            self.order.append(iid)
            if self.running:
                self.run_ids.add(iid)
        self._update_queue_nav()
        return iid

    def _update_queue_nav(self):
        n = len(self.order)
        self.nav["queue"].configure(text=f"Fila  ({n})" if n else "Fila")
        self.lbl_empty.configure(text="" if n else "A fila está vazia. Adicione um link em “Novo download”.")

    def _add_clicked(self):
        url = self._url()
        if not url:
            messagebox.showwarning("Atenção", "Cole um link primeiro.")
            return None
        item = self._build_item(url)
        if item:
            self._save_cfg()
            iid = self._add_item(item)
            self.v_status.set("Item adicionado à fila.")
            return iid
        return None

    def _download_now(self):
        if self._add_clicked():
            self._show("queue")
            self._start_queue()

    def _remove_item(self, iid):
        with self.lock:
            item = self.items.get(iid)
            if not item or item["status"] == "Baixando":
                return
            self.items.pop(iid, None)
            if iid in self.order:
                self.order.remove(iid)
            self.run_ids.discard(iid)
        item["row"].destroy()
        self._update_queue_nav()

    def _clear_done(self):
        for iid in [i for i in self.order if self.items[i]["status"] in ("Concluído", "Concluído com avisos")]:
            self._remove_item(iid)

    def _start_queue(self):
        if self.worker and self.worker.is_alive():
            return
        with self.lock:
            for iid in self.order:
                if self.items[iid]["status"] in ("Erro", "Cancelado"):
                    self.items[iid]["status"] = "Aguardando"
                    self._reset_progress(self.items[iid])
                    self._row_reset(iid)
            waiting = [i for i in self.order if self.items[i]["status"] == "Aguardando"]
            if not waiting:
                self.v_status.set("A fila está vazia — adicione um link.")
                return
            self.run_ids = set(waiting)
        self.cancel.clear()
        self.running = True
        self.cur_speed = 0
        self.last_summary = None
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.bar_total.set(0)
        self.v_status.set("Baixando…")
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    def _row_reset(self, iid):
        row = self.items[iid]["row"]
        row.set_state("Aguardando")
        row.set_progress(0)
        row.lbl_desc.configure(text=short(self.items[iid]["desc"], 80), text_color=MUTED)
        est = self.items[iid].get("est")
        row.set_size(f"~{fmt_size(est)}" if est else "")

    def _cancel(self):
        self.cancel.set()
        self.v_status.set("Cancelando…")

    # ------------------------------------------------------------ download (thread)
    def _worker(self):
        ok = failed = 0
        while not self.cancel.is_set():
            with self.lock:
                iid = next((i for i in self.order if self.items[i]["status"] == "Aguardando"), None)
                if iid is None:
                    break
                self.items[iid]["status"] = "Baixando"
            item = self.items[iid]
            self.q.put(("state", iid, "Baixando", None))
            opts = dict(item["opts"])
            opts["logger"] = QLogger(self.q)
            opts["progress_hooks"] = [self._make_hook(iid)]
            opts["postprocessor_hooks"] = [self._make_pp_hook(iid)]
            self.q.put(("log", f"\n=== {item['title']}"))
            error = ""
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    code = ydl.download([item["url"]])
                if code:
                    item["status"] = "Concluído com avisos" if item.get("playlist") else "Erro"
                    error = "O yt-dlp terminou com erro. Veja o Registro para os detalhes."
                else:
                    item["status"] = "Concluído"
                if item["status"] == "Erro":
                    failed += 1
                else:
                    ok += 1
            except Cancelado:
                item["status"] = "Cancelado"
            except Exception as exc:  # noqa: BLE001
                if self.cancel.is_set():
                    item["status"] = "Cancelado"
                else:
                    item["status"] = "Erro"
                    failed += 1
                    raw = clean_error(exc)
                    error = friendly_error(raw)
                    self.q.put(("log", f"Falhou: {raw}"))
            self.q.put(("state", iid, item["status"], error))
        self.q.put(("fim", ok, failed))

    def _make_hook(self, iid):
        def hook(d):
            if self.cancel.is_set():
                raise Cancelado()
            status = d.get("status")
            info = d.get("info_dict") or {}
            key = d.get("filename") or d.get("tmpfilename") or info.get("id") or "?"
            done = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if status == "finished":
                total = d.get("total_bytes") or done
                done = total
            self.q.put((
                "dl", iid,
                {
                    "key": key, "done": done, "total": total, "finished": status == "finished",
                    "estimated": not d.get("total_bytes") and bool(d.get("total_bytes_estimate")),
                    "speed": d.get("speed") or 0, "eta": d.get("eta"),
                    "idx": info.get("playlist_index"), "n": info.get("n_entries") or info.get("playlist_count"),
                    "title": info.get("title"),
                },
            ))

        return hook

    def _make_pp_hook(self, iid):
        def hook(d):
            if self.cancel.is_set() and d.get("status") == "started":
                raise Cancelado()
            if d.get("status") == "started":
                self.q.put(("pp", iid, str(d.get("postprocessor"))))

        return hook

    # ------------------------------------------------------------ modelo de progresso (thread da interface)
    def _on_dl(self, iid, d):
        it = self.items.get(iid)
        if not it:
            return
        self.cur_speed = d["speed"] if not d["finished"] else self.cur_speed
        idx, n = d.get("idx"), d.get("n")
        if it["playlist"] and idx and n:
            it["n_entries"] = n
            ent = it["entries"].setdefault(idx, {})
            ent[d["key"]] = (d["done"], d["total"])
            files = [v for e in it["entries"].values() for v in e.values()]
        else:
            it["files"][d["key"]] = (d["done"], d["total"])
            files = list(it["files"].values())
        done = sum(v[0] for v in files)
        known = sum(max(v[1], v[0]) for v in files)

        if it["playlist"] and idx and n:
            ent = it["entries"][idx]
            e_done = sum(v[0] for v in ent.values())
            e_tot = sum(max(v[1], v[0]) for v in ent.values())
            e_frac = e_done / e_tot if e_tot else 0
            frac = ((idx - 1) + min(e_frac, 1.0)) / n
            total = known / max(len(it["entries"]), 1) * n
            approx = True
        else:
            denom = max(known, it.get("est") or 0)
            frac = done / denom if denom else 0
            total = denom
            approx = denom > known or d["estimated"]

        it["frac"] = max(it["frac"], min(frac, 0.99))
        it["done"] = done
        it["total"] = max(total, done)
        it["approx"] = approx
        parts = [f"{it['frac'] * 100:.0f}%"]
        if d["speed"]:
            parts.append(f"{fmt_size(d['speed'])}/s")
        if d["eta"] is not None:
            parts.append(f"falta {fmt_dur(d['eta'])}")
        it["live"] = "  ·  ".join(parts)
        if d.get("title") and it["title"] == it["url"]:
            it["title"] = d["title"]
            it["row"].set_title(d["title"])

    def _refresh_row(self, iid):
        it = self.items.get(iid)
        if not it:
            return
        row = it["row"]
        row.set_progress(it["frac"])
        if it["total"]:
            row.set_size(f"{fmt_size(it['done'])} / {'~' if it['approx'] else ''}{fmt_size(it['total'])}")
        elif it["done"]:
            row.set_size(fmt_size(it["done"]))
        if it["status"] == "Baixando" and it.get("live"):
            row.set_state(it["live"], ACCENT)

    def _on_state(self, iid, status, extra):
        it = self.items.get(iid)
        if not it:
            return
        it["status"] = status
        row = it["row"]
        if status == "Baixando":
            row.set_state("Baixando…", ACCENT)
        elif status in ("Concluído", "Concluído com avisos"):
            it["frac"] = 1.0
            it["total"] = max(it["total"], it["done"])
            it["approx"] = False
            row.set_state(status, DONE)
            row.set_progress(1.0)
            if it["done"]:
                row.set_size(fmt_size(it["done"]))
            self._record_history(it, status)
        elif status == "Erro":
            row.set_state("Erro", RED)
            row.set_error(extra or "Falhou. Veja o Registro.")
            self._record_history(it, status)
        elif status == "Cancelado":
            row.set_state("Cancelado")
        row.btn_x.configure(state="disabled" if status == "Baixando" else "normal")

    def _refresh_total(self):
        ids = [i for i in self.run_ids if i in self.items]
        n = len(ids)
        if not n:
            return
        frac_sum = done_b = total_b = 0
        finished = 0
        unknown = False
        for iid in ids:
            it = self.items[iid]
            if it["status"] in FINAL_STATES:
                finished += 1
                frac_sum += 1.0 if it["status"] in ("Concluído", "Concluído com avisos") else it["frac"]
            else:
                frac_sum += it["frac"]
            done_b += it["done"]
            t = it["total"] or it.get("est") or 0
            total_b += t
            if not t or it["approx"]:
                unknown = unknown or not t
        pct = frac_sum / n
        self.bar_total.set(min(pct, 1.0))
        self.lbl_pct.configure(text=f"{pct * 100:.0f}%")
        self.stat["items"].configure(text=f"{finished} de {n}")
        if total_b and not unknown:
            self.stat["bytes"].configure(text=f"{fmt_size(done_b)} / ~{fmt_size(max(total_b, done_b))}")
        else:
            self.stat["bytes"].configure(text=f"{fmt_size(done_b)} baixados")
        if self.running and self.cur_speed:
            self.stat["speed"].configure(text=f"{fmt_size(self.cur_speed)}/s")
            if total_b and not unknown and total_b > done_b:
                self.stat["eta"].configure(text=fmt_dur((total_b - done_b) / self.cur_speed))
            else:
                self.stat["eta"].configure(text="calculando…")
        elif not self.running:
            self.stat["speed"].configure(text="—")
            self.stat["eta"].configure(text="—")

    # ------------------------------------------------------------ fila de mensagens (threads -> interface)
    def _pump(self):
        dirty = False
        rows = set()
        try:
            while True:
                msg = self.q.get_nowait()
                try:
                    kind = msg[0]
                    if kind == "log":
                        self._log(msg[1])
                    elif kind == "dl":
                        self._on_dl(msg[1], msg[2])
                        rows.add(msg[1])
                        dirty = True
                    elif kind == "pp":
                        it = self.items.get(msg[1])
                        if it:
                            it["row"].set_state("Processando…", ACCENT)
                    elif kind == "state":
                        self._on_state(msg[1], msg[2], msg[3])
                        rows.add(msg[1])
                        dirty = True
                    elif kind == "info":
                        self._on_info(msg[1], msg[2])
                    elif kind == "info_error":
                        self.btn_analyze.configure(state="normal", text="Analisar")
                        self.lbl_title.configure(text="Falha ao analisar o link.")
                        self.lbl_meta.configure(text=short(msg[2], 160))
                        self._log("Erro ao analisar: " + msg[2])
                        hint = ""
                        if "youtu" in msg[1] and not detect_js_runtime():
                            hint = "\n\nDica: o YouTube exige um runtime JavaScript (Deno). Abra Ferramentas e instale."
                        messagebox.showerror(
                            "Não foi possível analisar",
                            friendly_error(msg[2]) + hint + "\n\nDetalhe técnico:\n" + clean_error(msg[2])[:300],
                        )
                    elif kind == "thumb":
                        if self.info and self.info.get("thumbnail") == msg[1]:
                            self._set_thumb(msg[2])
                    elif kind == "fim":
                        self._on_fim(msg[1], msg[2])
                        dirty = True
                    elif kind == "tool":
                        self._on_tool_msg(msg)
                    elif kind == "update":
                        self._on_update_result(msg[1], msg[2], msg[3])
                    elif kind == "upd":
                        self._on_upd_msg(msg)
                    elif kind == "ytdlp":
                        self._on_ytdlp_msg(msg)
                except Exception as exc:  # noqa: BLE001
                    self._log(f"(erro interno na interface: {exc})")
        except queue.Empty:
            pass
        for iid in rows:
            self._refresh_row(iid)
        if dirty or self.running:
            self._refresh_total()
        self.after(80, self._pump)

    def _on_fim(self, ok, failed):
        self.running = False
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self._refresh_total()
        done_b = sum(self.items[i]["done"] for i in self.run_ids if i in self.items)
        if self.cancel.is_set():
            self.v_status.set("Cancelado.")
        else:
            self.v_status.set(f"Concluído: {ok} com sucesso, {failed} com erro  ·  {fmt_size(done_b)} baixados")
            if ok or failed:
                self.bell()
                if self.v_notify.get() and self._should_notify():
                    self._toast(
                        "Downloads terminados" if not failed else "Downloads terminaram com erros",
                        f"{ok} com sucesso, {failed} com erro  ·  {fmt_size(done_b)} baixados",
                    )
        self.stat["speed"].configure(text="—")
        self.stat["eta"].configure(text="—")

    # ------------------------------------------------------------ atualização do próprio programa
    def _startup_update_check(self):
        if self.v_autoupdate.get() and UPDATE_REPO:
            self._check_update(manual=False)

    def _on_update_click(self):
        if self.update_info:
            self._ask_update()
        else:
            self._check_update(manual=True)

    def _check_update(self, manual):
        if not REPO_RE.match(UPDATE_REPO or ""):
            if manual:
                messagebox.showinfo(
                    "Atualização",
                    "Esta cópia do programa não está ligada a um repositório do GitHub, então não consegue "
                    "verificar atualizações sozinha.\n\nBaixe a versão mais recente na página Releases do projeto.",
                )
            return
        self.btn_update.configure(state="disabled", text="Verificando…")
        threading.Thread(target=self._update_worker, args=(manual,), daemon=True).start()

    def _update_worker(self, manual):
        try:
            self.q.put(("update", fetch_latest_release(UPDATE_REPO), manual, None))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("update", None, manual, str(exc)))

    def _set_update_button(self, info):
        if info:
            self.btn_update.configure(
                state="normal", text=f"Atualizar para v{info['version']}",
                fg_color=ACCENT, hover_color=ACCENT_H, text_color="white",
            )
        else:
            self.btn_update.configure(
                state="normal", text="Verificar atualização", fg_color=SOFT, hover_color=SOFT_H, text_color=TXT,
            )

    def _on_update_result(self, info, manual, error):
        if error or not info:
            self.update_info = None
            self._set_update_button(None)
            if manual:
                messagebox.showerror(
                    "Atualização",
                    "Não foi possível verificar agora (sem internet ou limite do GitHub). Tente mais tarde.\n\n"
                    + short(error or "", 200),
                )
            return
        if is_newer(info["version"], APP_VERSION):
            self.update_info = info
            self._set_update_button(info)
            self.v_status.set(f"Nova versão disponível: v{info['version']}")
            if manual:
                self._ask_update()
        else:
            self.update_info = None
            self._set_update_button(None)
            if manual:
                messagebox.showinfo("Atualização", f"Você já está na versão mais recente (v{APP_VERSION}).")

    def _ask_update(self):
        info = self.update_info
        if not info:
            return
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Atualização", "Há downloads em andamento. Termine ou cancele antes de atualizar.")
            return
        notes = short(info["notes"], 500) if info["notes"] else "(sem notas)"
        head = f"Versão instalada: v{APP_VERSION}\nNova versão: v{info['version']}\n\nNovidades:\n{notes}\n\n"
        mode = pick_update_mode(info)
        if mode == "patch":
            size = f" (~{fmt_size(info['patch_size'])})" if info.get("patch_size") else ""
            if messagebox.askyesno(
                f"Nova versão v{info['version']}",
                head + f"Baixar só o que mudou{size} e atualizar agora? O programa fecha e abre de novo sozinho.",
            ):
                self._do_update(info)
        elif mode == "installer":
            if messagebox.askyesno(
                f"Nova versão v{info['version']}",
                head + "Baixar e instalar agora? O programa fecha e abre de novo sozinho.",
            ):
                self._do_update(info)
        elif messagebox.askyesno(f"Nova versão v{info['version']}", head + "Abrir a página de download no navegador?"):
            webbrowser.open(info["page"])

    def _do_update(self, info):
        win = self.upd_win = ctk.CTkToplevel(self, fg_color=BG)
        win.title("Atualizando…")
        win.geometry("460x150")
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", lambda: None)  # não fechar durante o download
        lbl(win, f"Baixando a versão v{info['version']}…", bold=True).pack(anchor="w", padx=20, pady=(20, 8))
        self.upd_bar = ctk.CTkProgressBar(win, height=10, corner_radius=5, progress_color=ACCENT, fg_color=FIELD)
        self.upd_bar.set(0)
        self.upd_bar.pack(fill="x", padx=20)
        self.upd_msg = lbl(win, "", muted=True, size=12)
        self.upd_msg.pack(anchor="w", padx=20, pady=8)
        threading.Thread(target=self._update_download_worker, args=(info,), daemon=True).start()

    def _update_download_worker(self, info):
        try:
            folder = os.path.join(tempfile.gettempdir(), "vibegrap-update")
            os.makedirs(folder, exist_ok=True)
            if pick_update_mode(info) == "patch":
                try:  # atualização leve; se qualquer etapa falhar, cai no instalador completo
                    zp = os.path.join(folder, "VibeGrap-App.zip")
                    download_patch(info, zp, lambda pct: self.q.put(("upd", "pct", pct)))
                    stage = extract_patch(zp, os.path.join(folder, "patch"))
                    exe = apply_patch(stage, exe_dir(), os.path.basename(sys.executable))
                    self.q.put(("upd", "done", exe, None, "patch"))
                    return
                except Exception as exc:  # noqa: BLE001
                    if not info.get("asset_url"):
                        raise
                    self.q.put(("upd", "txt", "A atualização leve não deu certo. Baixando o instalador completo…"))
            dest = os.path.join(folder, "VibeGrap-Setup.exe")
            download_update(info, dest, lambda pct: self.q.put(("upd", "pct", pct)))
            self.q.put(("upd", "done", dest, None))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("upd", "done", None, str(exc)))

    def _on_upd_msg(self, msg):
        if msg[1] == "txt":
            if self.upd_win is not None and self.upd_win.winfo_exists():
                self.upd_msg.configure(text=msg[2])
            return
        if msg[1] == "pct":
            if self.upd_win is not None and self.upd_win.winfo_exists():
                self.upd_bar.set(msg[2] / 100)
                self.upd_msg.configure(text=f"{msg[2]:.0f}%")
            return
        path, error = msg[2], msg[3]
        if error or not path:
            if self.upd_win is not None and self.upd_win.winfo_exists():
                self.upd_win.destroy()
            if messagebox.askyesno(
                "Atualização",
                "Não foi possível baixar a atualização:\n" + short(error or "", 200) + "\n\nAbrir a página de download no navegador?",
            ) and self.update_info:
                webbrowser.open(self.update_info["page"])
            return
        if len(msg) > 4 and msg[4] == "patch":
            self.upd_msg.configure(text="Pronto! Reiniciando o programa…")
            relaunch_app(path, exe_dir())
            self.after(500, self._quit_for_update)
            return
        self.upd_msg.configure(text="Abrindo o instalador… o programa vai fechar e abrir de novo.")
        self._launch_installer(path)
        self.after(500, self._quit_for_update)

    def _launch_installer(self, path):
        cmd = [path] + INSTALLER_ARGS
        flags = (0x00000008 | 0x00000200) if IS_WIN else 0  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)
        return cmd

    def _quit_for_update(self):
        self._save_cfg()
        self.destroy()
        os._exit(0)

    # ------------------------------------------------------------ vários links
    def _batch_dialog(self):
        win = ctk.CTkToplevel(self, fg_color=BG)
        win.title("Adicionar vários links")
        win.geometry("640x420")
        win.transient(self)
        lbl(win, "Um link por linha (usam as opções atuais da tela):", bold=True).pack(anchor="w", padx=18, pady=(18, 6))
        txt = ctk.CTkTextbox(win, corner_radius=10, fg_color=CARD, border_width=1, border_color=BORDER, text_color=TXT)
        txt.pack(fill="both", expand=True, padx=18)
        try:
            clip = self.clipboard_get()
            if "http" in clip:
                txt.insert("1.0", clip.strip() + "\n")
        except tk.TclError:
            pass

        def add():
            urls = [u.strip() for u in txt.get("1.0", "end").splitlines() if u.strip()]
            n = 0
            for u in urls:
                item = self._build_item(u)
                if item:
                    self._add_item(item)
                    n += 1
            self._save_cfg()
            self.v_status.set(f"{n} link(s) adicionados à fila.")
            win.destroy()
            if n:
                self._show("queue")

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=14)
        btn(row, "Adicionar à fila", add, "primary", width=160).pack(side="left")
        btn(row, "Fechar", win.destroy, "soft", width=100).pack(side="left", padx=8)
        win.after(150, win.focus)

    # ------------------------------------------------------------ ferramentas
    def _refresh_tools(self):
        ff, fp, js = find_tool("ffmpeg"), find_tool("ffprobe"), detect_js_runtime()
        upd = "cópia atualizada ativa" if UPDATE_ZIPAPP in sys.path else "versão embutida"
        self.v_tools.set(
            f"yt-dlp      {YTDLP_VERSION}   ({upd})\n"
            f"ffmpeg      {ff or 'NÃO ENCONTRADO'}\n"
            f"ffprobe     {fp or 'NÃO ENCONTRADO'}\n"
            f"JavaScript  {js[0] + '  (' + js[1] + ')' if js else 'NÃO ENCONTRADO (Deno/Node/Bun)'}"
        )

    def _run_tool(self, which):
        if which in ("ffmpeg", "deno") and not IS_WIN:
            messagebox.showinfo(
                "Instalação manual",
                "Neste sistema, instale pelo gerenciador de pacotes (ex.: sudo apt install ffmpeg; Deno: https://deno.com).",
            )
            return
        for b in self.tool_buttons:
            b.configure(state="disabled")
        self.pb_tools.set(0)
        self.v_tools_msg.set("Baixando…")
        threading.Thread(target=self._tool_worker, args=(which,), daemon=True).start()

    def _tool_worker(self, which):
        def progress(pct):
            self.q.put(("tool", "pct", pct))

        try:
            tmp = os.path.join(DATA_DIR, "download.tmp")
            if which == "ffmpeg":
                last = None
                for url in FFMPEG_URLS:
                    try:
                        download_file(url, tmp, progress)
                        last = None
                        break
                    except Exception as exc:  # noqa: BLE001
                        last = exc
                if last:
                    raise last
                self.q.put(("tool", "msg", "Extraindo ffmpeg…"))
                names = extract_from_zip(tmp, {"ffmpeg.exe", "ffprobe.exe"}, require_bin_dir=True)
                if "ffmpeg.exe" not in names:
                    raise RuntimeError("ffmpeg.exe não encontrado no arquivo baixado.")
            elif which == "deno":
                download_file(DENO_URL, tmp, progress)
                names = extract_from_zip(tmp, {"deno.exe"})
                if not names:
                    raise RuntimeError("deno.exe não encontrado no arquivo baixado.")
            else:
                stage_ytdlp_update(progress)
            if os.path.exists(tmp):
                os.remove(tmp)
            self.q.put(("tool", "done", "Concluído!" + (" Reinicie o programa para usar a nova versão do yt-dlp." if which == "ytdlp" else "")))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("tool", "done", f"Falhou: {exc}"))

    def _on_tool_msg(self, msg):
        if msg[1] == "pct":
            self.pb_tools.set(msg[2] / 100)
        elif msg[1] == "msg":
            self.v_tools_msg.set(msg[2])
        elif msg[1] == "done":
            self.v_tools_msg.set(msg[2])
            self.pb_tools.set(1)
            for b in self.tool_buttons:
                b.configure(state="normal")
            self._refresh_tools()


if __name__ == "__main__":
    App().mainloop()
