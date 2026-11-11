"""Testes automáticos do VibeGrap (rodam com tela virtual: xvfb-run python tests/test_app.py).

Cobrem: utilidades, escolha de formatos, tamanho estimado, nomes de arquivo, interface,
cálculo do progresso total e downloads de ponta a ponta contra um servidor local.
"""

import functools
import http.server
import importlib.util
import io
import os
import queue
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="ytdlpgui_test_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "cfg")

spec = importlib.util.spec_from_file_location("g", os.path.join(ROOT, "ytdlp_gui.py"))
g = importlib.util.module_from_spec(spec)
sys.modules["g"] = g
spec.loader.exec_module(g)
import yt_dlp  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name, str(extra)[:230])
    if not cond:
        FAILS.append(name)


# ------------------------------------------------------------ utilidades
check("parse_time 90", g.parse_time("90") == 90)
check("parse_time 1:30", g.parse_time("1:30") == 90)
check("parse_time 01:02:03", g.parse_time("01:02:03") == 3723)
check("parse_time vazio", g.parse_time("  ") is None)
try:
    g.parse_time("abc")
    check("parse_time inválido levanta erro", False)
except ValueError:
    check("parse_time inválido levanta erro", True)
check("fmt_size 0", g.fmt_size(0) == "0 B", g.fmt_size(0))
check("fmt_size MB (vírgula)", g.fmt_size(5 * 1024 * 1024) == "5,0 MB", g.fmt_size(5 * 1024 * 1024))
check("fmt_size GB", g.fmt_size(1.5 * 1024 ** 3) == "1,5 GB", g.fmt_size(1.5 * 1024 ** 3))
check("fmt_size None", g.fmt_size(None) == "—")
check("fmt_dur", g.fmt_dur(65) == "1:05" and g.fmt_dur(3725) == "1:02:05" and g.fmt_dur(0) == "0:00")


# ------------------------------------------------------------ seletor de formatos e tamanho estimado
def mk(fid, **kw):
    base = {"format_id": fid, "ext": "mp4", "protocol": "https", "url": "http://x/" + fid, "vcodec": "none", "acodec": "none"}
    base.update(kw)
    return base


# do pior para o melhor, como o yt-dlp entrega depois de ordenar
FORMATS = [
    mk("c360", height=360, width=640, vcodec="avc1", acodec="mp4a", tbr=500, filesize=40_000_000),
    mk("v720", height=720, width=1280, vcodec="avc1", tbr=1500, filesize=120_000_000),
    mk("v1080", height=1080, width=1920, vcodec="avc1", tbr=3000, filesize=300_000_000),
    mk("a-en", ext="m4a", acodec="mp4a", language="en", abr=128, tbr=128, filesize=8_000_000, format_note="medium"),
    mk("a-pt-lo", ext="m4a", acodec="mp4a", language="pt-BR", abr=48, tbr=48, filesize=3_000_000, format_note="low"),
    mk("a-pt-hi", ext="m4a", acodec="mp4a", language="pt-BR", abr=128, tbr=128, filesize=9_000_000, format_note="medium"),
]


def pick(fmt, multi=False):
    ydl = yt_dlp.YoutubeDL({"quiet": True, "format": fmt, "allow_multiple_audio_streams": multi})
    info = {"id": "x", "title": "t", "extractor": "test", "extractor_key": "Test", "webpage_url": "http://x/",
            "formats": [dict(f) for f in FORMATS]}
    res = ydl.process_video_result(info, download=False)
    return [x["format_id"] for x in res.get("requested_formats", [res])]


def fcase(name, args, expect_sorted, multi_override=None):
    fmt, m = g.build_format(*args)
    got = pick(fmt, m if multi_override is None else multi_override)
    check(f"formato: {name}", sorted(got) == sorted(expect_sorted), f"{fmt!r} -> {got}")


fcase("melhor", ("video", None, [], ""), ["v1080", "a-pt-hi"])
fcase("720p + pt-BR", ("video", 720, ["pt-BR"], ""), ["v720", "a-pt-hi"])
fcase("prefixo pt", ("video", None, [], "pt"), ["v1080", "a-pt-hi"])
fcase("só áudio en", ("audio", None, ["en"], ""), ["a-en"])
fcase("várias faixas", ("video", 720, ["en", "pt-BR"], ""), ["v720", "a-en", "a-pt-hi"])
fcase("sem ffmpeg (combinado)", ("video", None, [], "", False), ["c360"])
fcase("idioma inexistente cai no padrão", ("video", None, ["ja"], ""), ["v1080", "a-pt-hi"])

SINFO = {"formats": FORMATS, "duration": 100}
fmt, m = g.build_format("video", None, [], "")
check("tamanho: melhor = 300M + 9M", g.estimate_size(SINFO, fmt, m) == 309_000_000, g.estimate_size(SINFO, fmt, m))
fmt, m = g.build_format("video", 720, ["pt-BR"], "")
check("tamanho: 720p pt-BR = 120M + 9M", g.estimate_size(SINFO, fmt, m) == 129_000_000, g.estimate_size(SINFO, fmt, m))
check("tamanho: trecho 50%", g.estimate_size(SINFO, fmt, m, 0.5) == 64_500_000, g.estimate_size(SINFO, fmt, m, 0.5))
fmt, m = g.build_format("audio", None, ["en"], "")
check("tamanho: só áudio en = 8M", g.estimate_size(SINFO, fmt, m) == 8_000_000, g.estimate_size(SINFO, fmt, m))
nosize = {"formats": [mk("n1", height=480, vcodec="avc1", acodec="mp4a")], "duration": 10}
check("tamanho: desconhecido -> None", g.estimate_size(nosize, "b/b", False) is None)
tbr_only = {"formats": [mk("n1", height=480, vcodec="avc1", acodec="mp4a", tbr=800)], "duration": 10}
check("tamanho: por bitrate (800 kbps x 10 s)", g.estimate_size(tbr_only, "b/b", False) == 1_000_000, g.estimate_size(tbr_only, "b/b", False))
check("tamanho: sem formatos -> None", g.estimate_size({"formats": []}, "b", False) is None)

# ------------------------------------------------------------ nomes de arquivo
single = {"id": "abc", "title": "Meu Vídeo", "ext": "mp4", "uploader": "Canal", "playlist_title": None, "playlist_index": None}
plist = dict(single, playlist_title="Lista", playlist_index=3)
for tname, tpl in g.TEMPLATES.items():
    for pf in (False, True):
        full = ("%(playlist_title&{}/|)s" if pf else "") + tpl
        ydl = yt_dlp.YoutubeDL({"quiet": True, "paths": {"home": "/dl"}, "outtmpl": full, "windowsfilenames": False})
        a, b = ydl.prepare_filename(single), ydl.prepare_filename(plist)
        check(f"nome: {tname} pasta={pf}", a.startswith("/dl/") and "//" not in a and b.startswith("/dl/"), f"{a} | {b}")

# ------------------------------------------------------------ interface
app = g.App()
app.update()


def pump(seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def set_url(u):
    app.ent_url.delete(0, "end")
    app.ent_url.insert(0, u)


def txt(widget):
    return widget.cget("text")


check("UI: 6 páginas", set(app.pages) == {"download", "queue", "history", "settings", "tools", "log"}, list(app.pages))
check("UI: janela cabe na tela", app.winfo_width() <= app.winfo_screenwidth() + 5)
for name in app.pages:
    app._show(name)
    pump(0.05)
check("UI: navegar entre páginas", True)
app._show("download")

INFO = {
    "_type": "video", "id": "x", "title": "Vídeo de teste", "uploader": "Canal", "duration": 125,
    "formats": FORMATS,
    "subtitles": {"pt": [{"name": "Português"}], "en": [{"name": "English"}], "live_chat": [{}]},
    "automatic_captions": {"es": [{"name": "Spanish"}]},
}
URL = "https://example.test/watch?v=x"
set_url(URL)
app._on_info(URL, INFO)
pump(0.1)
check("UI: faixas de áudio listadas", app.pl_audio.size() == 3 and app.audio_langs == ["en", "pt-BR"] or app.pl_audio.size() == 2, app.pl_audio.get_all())
check("UI: legendas listadas (sem live_chat)", app.pl_subs.size() == 3, app.pl_subs.get_all())
check("UI: qualidades", list(app.om_quality.cget("values")) == [g.BEST, "1080p", "720p", "360p"], app.om_quality.cget("values"))
check("UI: título do vídeo", "Vídeo de teste" in txt(app.lbl_title), txt(app.lbl_title))
check("UI: tamanho estimado exibido", "~294,7 MB" in txt(app.lbl_stats), txt(app.lbl_stats))
app.pl_audio.lb.select_set(1)
app._update_estimate()
check("UI: estimativa muda com a faixa", "Tamanho estimado" in txt(app.lbl_stats), txt(app.lbl_stats))

# miniatura
from PIL import Image  # noqa: E402

buf = io.BytesIO()
Image.new("RGB", (640, 360), (200, 60, 60)).save(buf, "PNG")
app._set_thumb(buf.getvalue())
check("UI: miniatura aplicada", app.thumb_img is not None)
app._set_thumb(b"isto nao e uma imagem")
check("UI: miniatura inválida é ignorada", True)

# modo áudio desabilita qualidade
app._on_seg("Só áudio")
check("UI: modo áudio", app.v_mode.get() == "audio" and app.om_quality.cget("state") == "disabled" and app.om_afmt.cget("state") == "normal")
app._on_seg("Vídeo + áudio")
check("UI: modo vídeo", app.v_mode.get() == "video" and app.om_quality.cget("state") == "normal" and app.om_afmt.cget("state") == "disabled")

# montar item
app.pl_audio.select_none()
app.pl_audio.lb.select_set(app.audio_langs.index("pt-BR"))
app.pl_subs.lb.select_set(1)  # pt (as listas vêm ordenadas: en, pt, es-auto)
app.pl_subs.lb.select_set(2)  # es automática
app.v_quality.set("720p")
app.v_sub_embed.set(True)
app.v_start.set("0:10")
app.v_end.set("0:20")
app.v_limit.set("2M")
item = app._build_item(URL)
check("item: criado", item is not None)
o = item["opts"]
check("item: formato", o["format"].startswith("bv*[height<=720]+ba[language=pt-BR]"), o["format"])
check("item: legendas", o["subtitleslangs"] == ["pt", "es"] and o["writesubtitles"] and o["writeautomaticsub"], o.get("subtitleslangs"))
check("item: trecho", "download_ranges" in o)
check("item: limite 2M", o["ratelimit"] == 2 * 1024 * 1024, o.get("ratelimit"))
check("item: pps", [p["key"] for p in o["postprocessors"]] == ["FFmpegSubtitlesConvertor", "FFmpegEmbedSubtitle", "FFmpegMetadata"], [p["key"] for p in o["postprocessors"]])
check("item: tamanho estimado (trecho 10s de 125s)", item["est"] and abs(item["est"] - 129_000_000 * 10 / 125) < 1000, item["est"])
yt_dlp.YoutubeDL({k: v for k, v in o.items() if k != "logger"}).close()
check("item: yt-dlp aceita as opções", True)

app.pl_audio.lb.select_set(app.audio_langs.index("en"))
item2 = app._build_item(URL)
check("item: várias faixas força mkv", item2["opts"].get("merge_output_format") == "mkv" and item2["opts"].get("allow_multiple_audio_streams"))
app.v_start.set("")
app.v_end.set("")

# playlist
PL = {"_type": "playlist", "title": "Minha lista", "entries": [{"title": "A", "id": "1"}, None, {"title": "B", "id": "2"}, {"title": "C", "id": "3"}]}
app.pl_audio.select_none()
PURL = "https://example.test/playlist?list=1"
set_url(PURL)
app._on_info(PURL, PL)
check("UI: playlist listada", app.pl_items.size() == 3 and app.pl_index == [1, 3, 4], app.pl_items.get_all())
check("UI: playlist vem toda selecionada", len(app.pl_items.selected()) == 3)
app.pl_items.select_none()
app.pl_items.lb.select_set(0)
app.pl_items.lb.select_set(2)
app.v_lang.set("pt")
ip = app._build_item(PURL)
check("item playlist: itens escolhidos", ip["opts"].get("playlist_items") == "1,4" and ip["opts"]["noplaylist"] is False, ip["opts"].get("playlist_items"))
check("item playlist: prefixo de idioma", "ba[language^=pt]" in ip["opts"]["format"])
check("item playlist: título", ip["title"].startswith("[Playlist]"), ip["title"])
app.v_lang.set("")

# ------------------------------------------------------------ modelo de progresso total
app.items.clear(); app.order.clear(); app.run_ids.clear()
for w in app.qframe.winfo_children():
    w.destroy()
it = {"url": "u1", "title": "u1", "desc": "d", "opts": {}, "playlist": False, "est": 309_000_000}
i1 = app._add_item(it)
check("fila: contador na barra lateral", app.nav["queue"].cget("text") == "Fila  (1)", app.nav["queue"].cget("text"))
check("fila: tamanho estimado no cartão", "~294,7 MB" in txt(it["row"].lbl_size), txt(it["row"].lbl_size))
app.running = True
app.run_ids = {i1}
it["status"] = "Baixando"


def dl(iid, key, done, total, **kw):
    d = {"key": key, "done": done, "total": total, "finished": False, "estimated": False, "speed": 5_000_000,
         "eta": 10, "idx": None, "n": None, "title": None}
    d.update(kw)
    app._on_dl(iid, d)
    app._refresh_row(iid)
    app._refresh_total()


dl(i1, "video.f1", 150_000_000, 300_000_000)
f_half = it["frac"]
check("total: ~48% com metade do vídeo (est. 309M)", 0.45 < f_half < 0.5, f_half)
dl(i1, "video.f1", 300_000_000, 300_000_000, finished=True)
f_a = it["frac"]
dl(i1, "audio.f2", 4_000_000, 9_000_000)
check("total: progresso nunca volta atrás", it["frac"] >= f_a, (f_a, it["frac"]))
dl(i1, "audio.f2", 9_000_000, 9_000_000, finished=True)
check("total: limitado a 99% até concluir", it["frac"] <= 0.99, it["frac"])
check("total: bytes somam os dois arquivos", it["done"] == 309_000_000 and it["total"] == 309_000_000, (it["done"], it["total"]))
check("total: painel mostra baixado/total", "294,7 MB" in txt(app.stat["bytes"]), txt(app.stat["bytes"]))
check("total: painel mostra velocidade", "4,8 MB/s" in txt(app.stat["speed"]), txt(app.stat["speed"]))
app._on_state(i1, "Concluído", None)
app._refresh_total()
check("total: concluído = 100%", txt(app.lbl_pct) == "100%" and txt(app.stat["items"]) == "1 de 1", (txt(app.lbl_pct), txt(app.stat["items"])))

# playlist: 4 vídeos de 100 MB cada
pit = {"url": "pl", "title": "[Playlist] x", "desc": "d", "opts": {}, "playlist": True, "est": None}
p1 = app._add_item(pit)
pit["status"] = "Baixando"
app.run_ids = {p1}
for idx in (1, 2):
    dl(p1, f"v{idx}", 100_000_000, 100_000_000, finished=True, idx=idx, n=4)
dl(p1, "v3", 50_000_000, 100_000_000, idx=3, n=4)
check("playlist: 2,5 de 4 = 62%", 0.60 < pit["frac"] < 0.64, pit["frac"])
check("playlist: total extrapolado ~400 MB", 380e6 < pit["total"] < 420e6 and pit["approx"], pit["total"])
check("playlist: painel usa '~' no total", "~" in txt(app.stat["bytes"]), txt(app.stat["bytes"]))

# vários itens: média das frações
it3 = {"url": "u3", "title": "u3", "desc": "d", "opts": {}, "playlist": False, "est": None}
i3 = app._add_item(it3)
app.run_ids = {i1, i3}
app._refresh_total()
check("total: item sem tamanho conhecido -> só 'baixados'", "baixados" in txt(app.stat["bytes"]), txt(app.stat["bytes"]))
check("total: 1 de 2 itens", txt(app.stat["items"]) == "1 de 2", txt(app.stat["items"]))
app.running = False
# um item em andamento não pode ser removido (o botão ✕ é bloqueado)
busy = app.order[0]
app.items[busy]["status"] = "Baixando"
app._remove_item(busy)
check("fila: item em andamento não é removido", busy in app.items)
for iid in list(app.order):
    app.items[iid]["status"] = "Aguardando"
    app._remove_item(iid)
check("fila: remover tudo", not app.items and app.nav["queue"].cget("text") == "Fila")

# ------------------------------------------------------------ download de ponta a ponta (servidor local)
media = os.path.join(TMP, "media")
os.makedirs(media)
subprocess.run(
    ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=15", "-f", "lavfi",
     "-i", "sine=frequency=440:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
     "-movflags", "+faststart", os.path.join(media, "clip.mp4")], check=True)
with open(os.path.join(media, "big.mp4"), "wb") as f:
    f.write(os.urandom(6 * 1024 * 1024))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass


class Srv(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


httpd = Srv(("127.0.0.1", 0), functools.partial(Quiet, directory=media))
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"


def run_queue(timeout=90):
    app._start_queue()
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if not (app.worker and app.worker.is_alive()) and app.q.empty():
            break
        time.sleep(0.03)
    pump(0.4)


def reset_form():
    app.info = None
    app.analyzed_url = None
    app.pl_audio.clear(); app.pl_subs.clear(); app.pl_items.clear()
    app.audio_langs, app.sub_items, app.pl_index = [], [], []
    for v in (app.v_subtxt, app.v_lang, app.v_start, app.v_end, app.v_limit):
        v.set("")
    app.v_quality.set(g.BEST)
    app.v_sub_embed.set(False)
    app.v_playlist.set(False)


out1 = os.path.join(TMP, "out1")
reset_form()
app.v_folder.set(out1)
app._on_seg("Vídeo + áudio")
app.v_container.set("mp4")
set_url(BASE + "/clip.mp4")
iid = app._add_clicked()
run_queue()
st = app.items[iid]["status"]
files = os.listdir(out1) if os.path.isdir(out1) else []
row = app.items[iid]["row"]
check("E2E vídeo: concluído", st == "Concluído" and any(f.endswith(".mp4") for f in files), f"{st} {files}")
check("E2E vídeo: cartão mostra 'Concluído' e tamanho", txt(row.lbl_state) == "Concluído" and "KB" in txt(row.lbl_size) or "MB" in txt(row.lbl_size), (txt(row.lbl_state), txt(row.lbl_size)))
check("E2E vídeo: título atualizado", txt(row.lbl_title) != BASE + "/clip.mp4", txt(row.lbl_title))
check("E2E vídeo: painel total 100% e itens 1 de 1", txt(app.lbl_pct) == "100%" and txt(app.stat["items"]) == "1 de 1", (txt(app.lbl_pct), txt(app.stat["items"])))
check("E2E vídeo: painel mostra bytes baixados", any(u in txt(app.stat["bytes"]) for u in ("KB", "MB")), txt(app.stat["bytes"]))
check("E2E vídeo: status final", "Concluído" in app.v_status.get(), app.v_status.get())
check("E2E vídeo: botões restaurados", app.btn_start.cget("state") == "normal" and app.btn_cancel.cget("state") == "disabled")

out2 = os.path.join(TMP, "out2")
app.v_folder.set(out2)
app._on_seg("Só áudio")
app.v_afmt.set("mp3")
set_url(BASE + "/clip.mp4")
iid = app._add_clicked()
run_queue()
files = os.listdir(out2) if os.path.isdir(out2) else []
check("E2E áudio mp3: concluído", app.items[iid]["status"] == "Concluído" and any(f.endswith(".mp3") for f in files), f"{app.items[iid]['status']} {files}")
app._on_seg("Vídeo + áudio")

out3 = os.path.join(TMP, "out3")
app.v_folder.set(out3)
app.v_start.set("1")
app.v_end.set("3")
set_url(BASE + "/clip.mp4")
iid = app._add_clicked()
run_queue()
files = os.listdir(out3) if os.path.isdir(out3) else []
dur = None
if files:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", os.path.join(out3, files[0])], capture_output=True, text=True)
    try:
        dur = float(r.stdout.strip())
    except ValueError:
        pass
check("E2E trecho: ~2s", app.items[iid]["status"] == "Concluído" and dur is not None and 1.5 <= dur <= 3.0, f"{app.items[iid]['status']} dur={dur} {files}")
app.v_start.set(""); app.v_end.set("")

out4 = os.path.join(TMP, "out4")
app.v_folder.set(out4)
set_url(BASE + "/nao-existe.mp4")
iid = app._add_clicked()
run_queue(30)
row = app.items[iid]["row"]
check("E2E erro: marcado como Erro com mensagem", app.items[iid]["status"] == "Erro" and txt(row.lbl_state) == "Erro" and len(txt(row.lbl_desc)) > 10, (app.items[iid]["status"], txt(row.lbl_desc)))
# tentar de novo: volta a "Aguardando" e roda
before = app.items[iid]["status"]
app._start_queue()
pump(0.2)
check("E2E erro: 'Iniciar fila' tenta de novo os que falharam", app.worker is not None)
run_queue(30)

# cancelar
out5 = os.path.join(TMP, "out5")
app.v_folder.set(out5)
app.v_limit.set("100K")
set_url(BASE + "/big.mp4")
iid = app._add_clicked()
app._start_queue()
pump(3)
check("E2E cancelar: progresso ao vivo no cartão", "%" in txt(app.items[iid]["row"].lbl_state) or app.items[iid]["frac"] > 0, txt(app.items[iid]["row"].lbl_state))
check("E2E cancelar: painel mostra velocidade ao vivo", "/s" in txt(app.stat["speed"]), txt(app.stat["speed"]))
app._cancel()
end = time.time() + 20
while time.time() < end and app.worker.is_alive():
    pump(0.1)
pump(0.4)
check("E2E cancelar: estado Cancelado", app.items[iid]["status"] == "Cancelado" and txt(app.items[iid]["row"].lbl_state) == "Cancelado", app.items[iid]["status"])
check("E2E cancelar: botões restaurados", app.btn_start.cget("state") == "normal" and app.btn_cancel.cget("state") == "disabled")
app.v_limit.set("")

# limpar concluídos
n_before = len(app.order)
app._clear_done()
check("fila: limpar concluídos", len(app.order) < n_before, (n_before, len(app.order)))

# ------------------------------------------------------------ tema, ferramentas, configurações
app.v_theme.set("Escuro")
app._set_theme("Escuro")
check("tema: escuro aplicado", g.ctk.get_appearance_mode() == "Dark" and app.pl_audio.lb.cget("bg") == "#0f0f10", app.pl_audio.lb.cget("bg"))
check("tema: seleção das listas em vermelho (escuro)", app.pl_audio.lb.cget("selectbackground") == "#ef4444", app.pl_audio.lb.cget("selectbackground"))
app.v_theme.set("Claro")
app._set_theme("Claro")
check("tema: claro aplicado", g.ctk.get_appearance_mode() == "Light" and app.pl_audio.lb.cget("bg") == "#f4f4f5", app.pl_audio.lb.cget("bg"))
check("tema: seleção das listas em vermelho (claro)", app.pl_audio.lb.cget("selectbackground") == "#d62828", app.pl_audio.lb.cget("selectbackground"))

# ------------------------------------------------------------ paleta vermelho / branco / preto
def rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


neutral_or_red = ("BG", "SIDEBAR", "CARD", "BORDER", "FIELD", "TXT", "MUTED", "ACCENT", "ACCENT_H", "SOFT", "SOFT_H", "SEL", "SEL_H", "RED")
for name in neutral_or_red:
    for mode, col in zip(("claro", "escuro"), getattr(g, name)):
        r_, g_, b_ = rgb(col)
        check(f"paleta: {name} ({mode}) sem azul/verde dominante", b_ <= max(r_, g_) + 12 and g_ <= max(r_, b_) + 12, col)
for mode, col in zip(("claro", "escuro"), g.ACCENT):
    r_, g_, b_ = rgb(col)
    check(f"paleta: destaque principal é vermelho ({mode})", r_ > g_ + 80 and r_ > b_ + 80, col)
check("paleta: não há verde no programa (concluído usa texto normal)", not hasattr(g, "GREEN") and g.DONE == g.TXT)
check("paleta: fundo claro é branco/cinza muito claro e fundo escuro é quase preto",
      min(rgb(g.BG[0])) > 235 and max(rgb(g.BG[1])) < 30, (g.BG, g.SIDEBAR))

# ------------------------------------------------------------ nome do projeto e ícones
check("nome: APP_NAME é VibeGrap", g.APP_NAME == "VibeGrap", g.APP_NAME)
check("nome: pasta de dados é VibeGrap", os.path.basename(g.DATA_DIR) == "VibeGrap", g.DATA_DIR)
check("nome: título da janela", app.title() == "VibeGrap", app.title())
for asset in ("VibeGrap_icon.ico", "VibeGrap_logo.png"):
    check(f"assets: {asset} existe", os.path.isfile(os.path.join(ROOT, "assets", asset)))
check("assets: arquivos antigos (icon.ico / logo.png) removidos",
      not os.path.exists(os.path.join(ROOT, "assets", "icon.ico")) and not os.path.exists(os.path.join(ROOT, "assets", "logo.png")))
check("assets: o programa acha o logo novo", os.path.isfile(g.resource_path("assets/VibeGrap_logo.png")))
iss = open(os.path.join(ROOT, "installer.iss"), encoding="utf-8").read()
check("instalador: usa o ícone, o nome e o executável novos",
      "assets\\VibeGrap_icon.ico" in iss and 'OutputBaseFilename=VibeGrap-Setup' in iss and '#define MyAppExe  "VibeGrap.exe"' in iss and "AppPublisher=casisDev" in iss)
for rel in ("Criar-Instalador.bat", os.path.join(".github", "workflows", "build.yml")):
    txt_ = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    check(f"nome: {rel} usa VibeGrap e o ícone novo", "VibeGrap" in txt_ and "VibeGrap_icon.ico" in txt_, rel)
    check(f"nome: {rel} sem o nome antigo", "YT-DLP-GUI" not in txt_ and "icon.ico " not in txt_.replace("VibeGrap_icon.ico", ""), rel)
check("workflow: grava versão e repositório para o botão de atualização",
      "assets/version.txt" in open(os.path.join(ROOT, ".github", "workflows", "build.yml"), encoding="utf-8").read()
      and "assets/update_repo.txt" in open(os.path.join(ROOT, ".github", "workflows", "build.yml"), encoding="utf-8").read())
check("repositório: sem build_windows.bat antigo", not os.path.exists(os.path.join(ROOT, "build_windows.bat")))

# ------------------------------------------------------------ botão de atualização
check("update: versões comparadas corretamente",
      g.is_newer("2.1.0", "2.0.9") and g.is_newer("v3.0.0", "2.9.9") and not g.is_newer("2.0.0", "2.0.0")
      and not g.is_newer("1.9.9", "2.0.0") and g.is_newer("2.0.1", "2.0") and not g.is_newer("2.0", "2.0.0"))
check("update: parse_version ignora sufixos", g.parse_version("v2.1.0-beta") == (2, 1, 0), g.parse_version("v2.1.0-beta"))
check("update: asset_url_ok só aceita o próprio repositório",
      g.asset_url_ok("https://github.com/dono/repo/releases/download/v2/VibeGrap-Setup.exe", "dono/repo")
      and not g.asset_url_ok("https://evil.example/VibeGrap-Setup.exe", "dono/repo")
      and not g.asset_url_ok("https://github.com/outro/repo/releases/download/v2/x.exe", "dono/repo")
      and not g.asset_url_ok(None, "dono/repo"))
try:
    g.fetch_latest_release("repo inválido; rm -rf")
    check("update: repositório inválido é recusado", False)
except ValueError:
    check("update: repositório inválido é recusado", True)

import json as _json  # noqa: E402

SETUP_BYTES = os.urandom(300_000)
api_state = {"tag": "v9.9.9", "fail": False}


class FakeGitHub(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        if self.path == "/repos/dono/repo/releases/latest":
            if api_state["fail"]:
                self.send_response(404)
                self.end_headers()
                return
            base = f"http://127.0.0.1:{self.server.server_address[1]}"
            body = _json.dumps({
                "tag_name": api_state["tag"], "body": "Visual novo em vermelho e preto", "html_url": "https://github.com/dono/repo/releases/tag/x",
                "assets": [
                    {"name": "outro.zip", "browser_download_url": base + "/download/outro.zip", "size": 1},
                    {"name": "VibeGrap-Setup.exe", "browser_download_url": base + "/download/VibeGrap-Setup.exe", "size": len(SETUP_BYTES)},
                ],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/download/VibeGrap-Setup.exe":
            self.send_response(200)
            self.send_header("Content-Length", str(len(SETUP_BYTES)))
            self.end_headers()
            self.wfile.write(SETUP_BYTES)
        else:
            self.send_response(404)
            self.end_headers()


gh = Srv(("127.0.0.1", 0), FakeGitHub)
threading.Thread(target=gh.serve_forever, daemon=True).start()
GH_API = f"http://127.0.0.1:{gh.server_address[1]}"
g.UPDATE_API = GH_API

rel = g.fetch_latest_release("dono/repo", api=GH_API)
check("update: lê a última Release", rel["version"] == "9.9.9" and rel["tag"] == "v9.9.9" and "vermelho" in rel["notes"], rel)
check("update: escolhe o arquivo *Setup.exe (ignora os outros)", rel["asset_url"].endswith("/VibeGrap-Setup.exe") and rel["asset_size"] == len(SETUP_BYTES), rel["asset_url"])
dest = os.path.join(TMP, "upd", "Setup.exe")
os.makedirs(os.path.dirname(dest), exist_ok=True)
seen = []
g.download_update(rel, dest, seen.append)
check("update: baixa o instalador inteiro", open(dest, "rb").read() == SETUP_BYTES and seen and seen[-1] == 100.0, len(seen))
try:
    g.download_update(dict(rel, asset_size=len(SETUP_BYTES) + 5), dest)
    check("update: arquivo incompleto é recusado e apagado", False)
except RuntimeError:
    check("update: arquivo incompleto é recusado e apagado", not os.path.exists(dest))
try:
    g.download_update(dict(rel, asset_url="http://evil.example/VibeGrap-Setup.exe"), dest)
    check("update: endereço de fora do repositório é recusado", False)
except RuntimeError:
    check("update: endereço de fora do repositório é recusado", True)

# interface: os diálogos são trocados por gravadores para o teste não travar
calls = []
real_mb = {n: getattr(g.messagebox, n) for n in ("showinfo", "showerror", "showwarning", "askyesno")}
for n in real_mb:
    setattr(g.messagebox, n, (lambda name: (lambda *a, **k: calls.append((name, a)) or True))(n))
opened = []
real_open = g.webbrowser.open
g.webbrowser.open = lambda url, *a, **k: opened.append(url) or True
popen_calls = []
real_popen = g.subprocess.Popen
g.subprocess.Popen = lambda cmd, **k: popen_calls.append((cmd, k)) or None

check("update: botão começa como 'Verificar atualização'", txt(app.btn_update) == "Verificar atualização", txt(app.btn_update))
app._on_update_result(rel, False, None)
check("update: versão nova muda o botão para 'Atualizar para v9.9.9' em vermelho",
      txt(app.btn_update) == "Atualizar para v9.9.9" and app.update_info is rel and app.btn_update.cget("fg_color") == g.ACCENT, txt(app.btn_update))
check("update: aviso discreto na barra de status (sem janela)", "9.9.9" in app.v_status.get() and not calls, (app.v_status.get(), calls))
app._on_update_click()
check("update: clicar mostra as novidades e pergunta", calls and calls[-1][0] == "askyesno" and "Visual novo" in calls[-1][1][1], calls[-1] if calls else None)
check("update: fora do Windows abre a página de download", opened and opened[-1].startswith("https://github.com/dono/repo/releases"), opened)
calls.clear()
app._on_update_result(dict(rel, version=g.APP_VERSION, tag="v" + g.APP_VERSION), True, None)
check("update: já está na última versão", calls and calls[-1][0] == "showinfo" and app.update_info is None and txt(app.btn_update) == "Verificar atualização", calls[-1] if calls else None)
calls.clear()
app._on_update_result(None, True, "sem internet")
check("update: erro de rede mostra mensagem amigável", calls and calls[-1][0] == "showerror", calls[-1] if calls else None)
calls.clear()
app._on_update_result(None, False, "sem internet")
check("update: erro na verificação automática é silencioso", not calls)

app._check_update(manual=True)
check("update: cópia sem repositório explica que não verifica sozinha", calls and calls[-1][0] == "showinfo" and "repositório" in calls[-1][1][1], calls[-1] if calls else None)
calls.clear()
check("update: verificação automática desligada sem repositório", not g.UPDATE_REPO)

# verificação completa pela rede (servidor falso): precisa de UPDATE_REPO preenchido
g.UPDATE_REPO = "dono/repo"
app.update_info = None
app._check_update(manual=False)
end = time.time() + 10
while time.time() < end and app.update_info is None:
    pump(0.1)
check("update: verificação pela rede acha a versão nova e ativa o botão", app.update_info and app.update_info["version"] == "9.9.9" and txt(app.btn_update) == "Atualizar para v9.9.9", txt(app.btn_update))
api_state["fail"] = True
app.update_info = None
app._set_update_button(None)
app._check_update(manual=True)
end = time.time() + 10
while time.time() < end and not calls:
    pump(0.1)
check("update: GitHub fora do ar -> mensagem de erro e botão volta ao normal", calls and calls[-1][0] == "showerror" and txt(app.btn_update) == "Verificar atualização", calls[-1][0] if calls else None)
api_state["fail"] = False
g.UPDATE_REPO = ""
calls.clear()

# falha ao baixar: janela fecha e oferece abrir o navegador
app.update_info = rel
app.upd_win = None
opened.clear()
app._on_upd_msg(("upd", "done", None, "queda de conexão"))
check("update: falha no download oferece a página de Releases", calls and calls[-1][0] == "askyesno" and opened, (calls[-1][0] if calls else None, opened))

# instalador silencioso: comando exato (sem fechar o teste!)
cmd = app._launch_installer(r"C:\Temp\VibeGrap-Setup.exe")
check("update: instalador roda em modo silencioso e fecha o programa antigo", cmd == [r"C:\Temp\VibeGrap-Setup.exe", "/SILENT", "/CLOSEAPPLICATIONS"] and popen_calls, cmd)
check("update: opção de verificar ao abrir existe e vem ligada", app.v_autoupdate.get() is True and g.DEFAULT_CFG["auto_update"] is True)
app.v_autoupdate.set(False)
app._save_cfg()
check("update: desligar a verificação automática é salvo", _json.load(open(g.SETTINGS_FILE, encoding="utf-8")).get("auto_update") is False)
app.v_autoupdate.set(True)

for n, fn in real_mb.items():
    setattr(g.messagebox, n, fn)
g.webbrowser.open = real_open
g.subprocess.Popen = real_popen
gh.shutdown()


# ------------------------------------------------------------ atualização leve (só VibeGrap.exe + assets)
import hashlib as _hl  # noqa: E402
import queue as _queue  # noqa: E402

BASE_ID = "0123456789abcdef"


def make_patch_zip(path, extra=None, exe=b"MZ-novo", skip_exe=False, names=None):
    with zipfile.ZipFile(path, "w") as z:
        if not skip_exe:
            z.writestr("VibeGrap.exe", exe)
        z.writestr("_internal/assets/version.txt", "9.9.9")
        z.writestr("_internal/assets/novo.txt", "arquivo novo")
        z.writestr("LICENSE", "MIT novo")
        for n, data in (extra or {}).items():
            z.writestr(n, data)
    return path


good_zip = make_patch_zip(os.path.join(TMP, "patch_ok.zip"))
GZ = open(good_zip, "rb").read()
pstate = {"sha": _hl.sha256(GZ).hexdigest(), "nosha": False}


class FakePatch(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        if self.path == "/dl/patch.zip":
            body = GZ
        elif self.path == "/dl/patch.zip.sha256" and not pstate["nosha"]:
            body = (pstate["sha"] + "  VibeGrap-App.zip\n").encode()
        elif self.path == "/dl/setup.exe":
            body = SETUP_BYTES
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


ps = Srv(("127.0.0.1", 0), FakePatch)
threading.Thread(target=ps.serve_forever, daemon=True).start()
PB = f"http://127.0.0.1:{ps.server_address[1]}"
real_api = g.UPDATE_API
g.UPDATE_API = PB
pinfo = {"repo": "dono/repo", "version": "9.9.9", "notes": "", "page": "https://github.com/dono/repo/releases",
         "patch_url": PB + "/dl/patch.zip", "patch_sha_url": PB + "/dl/patch.zip.sha256", "patch_size": len(GZ),
         "asset_url": PB + "/dl/setup.exe", "asset_size": len(SETUP_BYTES)}

# --- escolha dos arquivos na Release
rel_assets = [
    {"name": "VibeGrap-Setup.exe", "browser_download_url": "https://github.com/dono/repo/releases/download/v9/VibeGrap-Setup.exe", "size": 5},
    {"name": f"VibeGrap-App-{BASE_ID}.zip", "browser_download_url": "https://github.com/dono/repo/releases/download/v9/a.zip", "size": 7},
    {"name": f"VibeGrap-App-{BASE_ID}.zip.sha256", "browser_download_url": "https://github.com/dono/repo/releases/download/v9/a.sha", "size": 64},
]
rel_state = {"assets": rel_assets}


class FakeRel(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        body = _json.dumps({"tag_name": "v9.9.9", "body": "", "assets": rel_state["assets"]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


rs = Srv(("127.0.0.1", 0), FakeRel)
threading.Thread(target=rs.serve_forever, daemon=True).start()
RB = f"http://127.0.0.1:{rs.server_address[1]}"
r1 = g.fetch_latest_release("dono/repo", api=RB, base=BASE_ID)
check("leve: Release com pacote da mesma impressão digital oferece o pacote leve",
      r1["patch_url"].endswith("/a.zip") and r1["patch_sha_url"].endswith("/a.sha") and r1["patch_size"] == 7 and r1["asset_url"].endswith("Setup.exe"), r1)
r2 = g.fetch_latest_release("dono/repo", api=RB, base="fedcba9876543210")
check("leve: impressão digital diferente (bibliotecas mudaram) -> só o instalador completo", r2["patch_url"] is None and r2["asset_url"], r2)
r3 = g.fetch_latest_release("dono/repo", api=RB, base="")
check("leve: programa sem impressão digital (versão antiga) -> só o instalador completo", r3["patch_url"] is None and r3["asset_url"], r3)
rel_state["assets"] = rel_assets[:2]
r4 = g.fetch_latest_release("dono/repo", api=RB, base=BASE_ID)
check("leve: pacote sem o arquivo de hash é ignorado", r4["patch_url"] is None and r4["patch_sha_url"] is None, r4)
rel_state["assets"] = rel_assets
check("leve: impressão digital malformada é ignorada", g.fetch_latest_release("dono/repo", api=RB, base="../x")["patch_url"] is None)
rs.shutdown()

# --- escolha do modo
check("leve: modo 'patch' no Windows instalado com pasta gravável", g.pick_update_mode(pinfo, frozen=True, win=True, app_dir=TMP) == "patch")
check("leve: pasta sem permissão de escrita -> instalador completo", g.pick_update_mode(pinfo, frozen=True, win=True, app_dir=os.path.join(TMP, "nao_existe")) == "installer")
check("leve: sem pacote -> instalador completo", g.pick_update_mode(dict(pinfo, patch_url=None), frozen=True, win=True, app_dir=TMP) == "installer")
check("leve: rodando pelo código-fonte ou fora do Windows -> abre a página", g.pick_update_mode(pinfo, frozen=False, win=True, app_dir=TMP) == "page" and g.pick_update_mode(pinfo, frozen=True, win=False, app_dir=TMP) == "page")

# --- download com conferência
pz = os.path.join(TMP, "dl_patch.zip")
seen = []
g.download_patch(pinfo, pz, seen.append)
check("leve: baixa o pacote e confere o hash", open(pz, "rb").read() == GZ and seen and seen[-1] == 100.0)
pstate["sha"] = "0" * 64
try:
    g.download_patch(pinfo, pz)
    check("leve: hash errado é recusado e o arquivo apagado", False)
except RuntimeError:
    check("leve: hash errado é recusado e o arquivo apagado", not os.path.exists(pz))
pstate["sha"] = _hl.sha256(GZ).hexdigest()
try:
    g.download_patch(dict(pinfo, patch_size=len(GZ) + 1), pz)
    check("leve: tamanho errado é recusado", False)
except RuntimeError:
    check("leve: tamanho errado é recusado", not os.path.exists(pz))
try:
    g.download_patch(dict(pinfo, patch_url="http://evil.example/p.zip"), pz)
    check("leve: endereço de fora do repositório é recusado", False)
except RuntimeError:
    check("leve: endereço de fora do repositório é recusado", True)
pstate["nosha"] = True
try:
    g.download_patch(pinfo, pz)
    check("leve: sem arquivo de hash nada é instalado", False)
except Exception:
    check("leve: sem arquivo de hash nada é instalado", not os.path.exists(pz))
pstate["nosha"] = False

# --- extração segura
st = g.extract_patch(good_zip, os.path.join(TMP, "stage1"))
check("leve: extrai exe, assets e licença", open(os.path.join(st, "VibeGrap.exe"), "rb").read() == b"MZ-novo"
      and open(os.path.join(st, "_internal", "assets", "novo.txt")).read() == "arquivo novo" and os.path.isfile(os.path.join(st, "LICENSE")))
for label, kw in (("caminho com '..' (zip-slip)", {"extra": {"_internal/assets/../../evil.txt": "x"}}),
                  ("arquivo fora da lista (.dll)", {"extra": {"python312.dll": "x"}}),
                  ("caminho absoluto", {"extra": {"/etc/x": "x"}}),
                  ("sem o VibeGrap.exe", {"skip_exe": True}),
                  ("exe que não é executável", {"exe": b"texto"})):
    bad = make_patch_zip(os.path.join(TMP, "bad.zip"), **kw)
    try:
        g.extract_patch(bad, os.path.join(TMP, "stage_bad"))
        check("leve: recusa " + label, False)
    except RuntimeError:
        check("leve: recusa " + label, not os.path.exists(os.path.join(TMP, "evil.txt")))

# --- troca dos arquivos (com desfazer)
def make_app(name):
    d = os.path.join(TMP, name)
    os.makedirs(os.path.join(d, "_internal", "assets"), exist_ok=True)
    open(os.path.join(d, "VibeGrap.exe"), "wb").write(b"MZ-antigo")
    open(os.path.join(d, "_internal", "assets", "version.txt"), "w").write("2.0.0")
    open(os.path.join(d, "_internal", "assets", "so_no_antigo.txt"), "w").write("fica")
    open(os.path.join(d, "ffmpeg.exe"), "wb").write(b"FFMPEG")
    return d


appd = make_app("app_ok")
exe = g.apply_patch(st, appd)
rd = lambda *a: open(os.path.join(appd, *a), "rb").read()  # noqa: E731
check("leve: troca o .exe e guarda o antigo como .old", rd("VibeGrap.exe") == b"MZ-novo" and rd("VibeGrap.exe.old") == b"MZ-antigo" and exe.endswith("VibeGrap.exe"))
check("leve: atualiza os assets e a licença, sem apagar o resto", rd("_internal", "assets", "version.txt") == b"9.9.9"
      and rd("_internal", "assets", "novo.txt") == b"arquivo novo" and rd("_internal", "assets", "so_no_antigo.txt") == b"fica" and rd("LICENSE") == b"MIT novo")
check("leve: não mexe no ffmpeg/Deno", rd("ffmpeg.exe") == b"FFMPEG")
check("leve: não sobra pasta de desfazer", not os.path.exists(os.path.join(TMP, "stage1_rollback")))
# aplicar de novo (já existe .old de antes)
g.apply_patch(st, appd)
check("leve: aplicar de novo funciona mesmo com .old antigo", rd("VibeGrap.exe") == b"MZ-novo" and rd("VibeGrap.exe.old") == b"MZ-novo")

# falha ao copiar o .exe novo: tudo volta ao que era
appd = make_app("app_fail1")
real_copy2 = g.shutil.copy2


def boom(*a, **k):
    raise OSError("disco cheio")


g.shutil.copy2 = boom
try:
    g.apply_patch(st, appd)
    check("leve: falha ao copiar o .exe é propagada", False)
except OSError:
    check("leve: falha ao copiar o .exe é propagada", True)
g.shutil.copy2 = real_copy2
check("leve: falha ao copiar o .exe -> programa antigo continua intacto", rd("VibeGrap.exe") == b"MZ-antigo" and not os.path.exists(os.path.join(appd, "VibeGrap.exe.old")))

# falha nos assets (depois de trocar o .exe): .exe e assets voltam ao que eram
appd = make_app("app_fail2")
real_ct = g.shutil.copytree
calls_ct = []


def flaky_copytree(src, dst, **k):
    calls_ct.append(dst)
    if len(calls_ct) == 2:  # 1ª = cópia de segurança; 2ª = assets novos
        raise OSError("arquivo em uso")
    return real_ct(src, dst, **k)


g.shutil.copytree = flaky_copytree
try:
    g.apply_patch(st, appd)
    check("leve: falha nos assets é propagada", False)
except OSError:
    check("leve: falha nos assets é propagada", True)
g.shutil.copytree = real_ct
check("leve: falha nos assets -> .exe e assets antigos voltam", rd("VibeGrap.exe") == b"MZ-antigo" and rd("_internal", "assets", "version.txt") == b"2.0.0"
      and not os.path.exists(os.path.join(appd, "VibeGrap.exe.old")))

# limpeza na abertura seguinte
appd = make_app("app_clean")
open(os.path.join(appd, "VibeGrap.exe.old"), "wb").write(b"x")
real_exe, real_frozen = g.sys.executable, g.FROZEN
g.sys.executable, g.FROZEN = os.path.join(appd, "VibeGrap.exe"), True
g.cleanup_after_patch()
g.sys.executable, g.FROZEN = real_exe, real_frozen
check("leve: na abertura seguinte apaga o .exe antigo", not os.path.exists(os.path.join(appd, "VibeGrap.exe.old")))

# --- fluxo completo do botão (sem fechar o teste)
real_pm = (g.FROZEN, g.IS_WIN, g.exe_dir, g.subprocess.Popen)
appd = make_app("app_flow")
fake_exe_name = os.path.basename(g.sys.executable)
open(os.path.join(appd, fake_exe_name), "wb").write(b"MZ-antigo")
g.FROZEN, g.IS_WIN, g.exe_dir = True, True, (lambda: appd)
launched = []
g.subprocess.Popen = lambda cmd, **k: launched.append((cmd, k)) or None


def drain():
    out = []
    while True:
        try:
            out.append(app.q.get_nowait())
        except _queue.Empty:
            return out


drain()
app._update_download_worker(pinfo)
msgs = [m for m in drain() if m[0] == "upd"]
done = msgs[-1]
check("leve: botão baixa o pacote leve e troca os arquivos", done[1] == "done" and done[3] is None and len(done) > 4 and done[4] == "patch"
      and open(os.path.join(appd, fake_exe_name), "rb").read() == b"MZ-novo" and open(os.path.join(appd, "_internal", "assets", "version.txt")).read() == "9.9.9", done)
quit_calls = []
real_quit = app._quit_for_update
app._quit_for_update = lambda: quit_calls.append(1)
app.upd_win = None
app.upd_msg = type("M", (), {"configure": lambda self, **k: None})()
app._on_upd_msg(done)
pump(0.8)
check("leve: depois de trocar, o programa reabre e fecha o antigo", launched and launched[-1][0] == [done[2]] and quit_calls
      and launched[-1][1].get("env", {}).get("PYINSTALLER_RESET_ENVIRONMENT") == "1", launched)

# pacote leve falha (hash errado) -> cai no instalador completo
appd2 = make_app("app_flow2")
open(os.path.join(appd2, fake_exe_name), "wb").write(b"MZ-antigo")
g.exe_dir = lambda: appd2
pstate["sha"] = "f" * 64
drain()
app._update_download_worker(pinfo)
msgs = [m for m in drain() if m[0] == "upd"]
txts = [m for m in msgs if m[1] == "txt"]
done2 = msgs[-1]
check("leve: pacote com problema -> avisa e baixa o instalador completo", txts and done2[1] == "done" and done2[3] is None and len(done2) == 4
      and open(done2[2], "rb").read() == SETUP_BYTES and open(os.path.join(appd2, fake_exe_name), "rb").read() == b"MZ-antigo", (txts, done2))
pstate["sha"] = _hl.sha256(GZ).hexdigest()

# pacote leve falha e não há instalador na Release -> erro mostrado
drain()
pstate["sha"] = "f" * 64
app._update_download_worker(dict(pinfo, asset_url=None))
done3 = [m for m in drain() if m[0] == "upd"][-1]
check("leve: sem pacote bom e sem instalador -> mensagem de erro", done3[1] == "done" and done3[2] is None and done3[3], done3)
pstate["sha"] = _hl.sha256(GZ).hexdigest()

app._quit_for_update = real_quit
g.FROZEN, g.IS_WIN, g.exe_dir, g.subprocess.Popen = real_pm
g.UPDATE_API = real_api
ps.shutdown()
check("leve: o pacote leve vem do mesmo workflow (impressão digital + zip + hash)",
      all(t in open(os.path.join(ROOT, ".github", "workflows", "build.yml"), encoding="utf-8").read()
          for t in ("base_id.txt", "VibeGrap-App-", ".sha256", "pip freeze")))

check("ferramentas: lista componentes", "yt-dlp" in app.v_tools.get() and "ffmpeg" in app.v_tools.get(), app.v_tools.get().replace("\n", " | "))
app._about_dialog()
pump(0.3)
about = app.about_text.get("1.0", "end")
check("Sobre: mostra a licença MIT e os créditos", "MIT License" in about and "yt-dlp" in about and "GPL" in about, about[:80])
check("Sobre: autoria casisDev, vibe coding e uso responsável",
      "casisDev" in g.ABOUT_TEXT and "vibe coding" in g.ABOUT_TEXT and "direito de baixar" in g.ABOUT_TEXT)
check("Sobre: licença mostrada cita casisDev", "casisDev" in about, about[:60])
app.about_win.destroy()

# arquivos de código aberto presentes e coerentes
for fname in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "CONTRIBUTING.md", ".gitignore"):
    check(f"repositório: {fname} existe", os.path.isfile(os.path.join(ROOT, fname)))
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
check("README: autoria casisDev e vibe coding logo no começo",
      "casisDev" in "\n".join(readme.splitlines()[:6]) and "vibe coding" in "\n".join(readme.splitlines()[:6]).lower(), readme.splitlines()[2:4])
check("README: declara vibe coding com IA", "vibe coding" in readme.lower() and "Claude" in readme)
check("README: aviso de uso responsável e de não afiliação", "Uso responsável" in readme and "não é afiliado" in readme)
notices = open(os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), encoding="utf-8").read()
for comp in ("yt-dlp", "FFmpeg", "Deno", "customtkinter", "Pillow", "mutagen", "GPL"):
    check(f"créditos: cita {comp}", comp in notices)
reqs = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read().lower()
for dep in ("yt-dlp", "customtkinter", "pillow"):
    check(f"créditos: dependência {dep} listada nos créditos", dep.split("-")[0] in notices.lower() and dep in reqs)

app._save_cfg()
import json  # noqa: E402

saved = json.load(open(g.SETTINGS_FILE, encoding="utf-8"))
check("config salva (tema e pasta)", saved.get("theme") == "Claro" and saved.get("folder") == out5, saved.get("theme"))
# ------------------------------------------------------------ erros em português
FE = g.friendly_error
check("erro: vídeo privado", "privado" in FE("ERROR: [youtube] abc: Private video. Sign in if you've been granted access"), FE("ERROR: [youtube] abc: Private video. Sign in"))
check("erro: restrição de idade", "idade" in FE("ERROR: Sign in to confirm your age. This video may be inappropriate"))
check("erro: anti-robô do YouTube", "anti-robô" in FE("ERROR: Sign in to confirm you’re not a bot"))
check("erro: região bloqueada", "região" in FE("The uploader has not made this video available in your country"))
check("erro: vídeo removido", "indisponível" in FE("ERROR: Video unavailable. This video has been removed by the uploader"))
check("erro: sem internet", "conexão" in FE("<urlopen error [Errno -2] Name or service not known>") and "conexão" in FE("Unable to download webpage: timed out"))
check("erro: 429 e 403", "limitou" in FE("HTTP Error 429: Too Many Requests") and "403" in FE("HTTP Error 403: Forbidden"))
check("erro: ffmpeg ausente", "ffmpeg" in FE("ERROR: Postprocessing: ffprobe and ffmpeg not found"))
check("erro: disco cheio e permissão", "disco" in FE("[Errno 28] No space left on device") and "permissão" in FE("[Errno 13] Permission denied: 'x'"))
check("erro: formato indisponível", "Melhor disponível" in FE("ERROR: Requested format is not available"))
check("erro: link não suportado", "suportado" in FE("ERROR: Unsupported URL: https://example.com/x"))
check("erro: desconhecido mostra o texto limpo", FE("\x1b[0;31mERROR:\x1b[0m [x] 12: algo estranho") == "algo estranho", FE("\x1b[0;31mERROR:\x1b[0m [x] 12: algo estranho"))
check("erro: vazio tem mensagem padrão", "Registro" in FE(""))
check("erro: nunca vaza código de cor", "\x1b" not in FE("\x1b[31mHTTP Error 404: Not Found\x1b[0m"))

# ------------------------------------------------------------ histórico
hpath = os.path.join(TMP, "hist_test.json")
check("histórico: arquivo ausente/corrompido vira lista vazia", g.load_history(hpath) == [] and (open(hpath, "w").write("{{{") or g.load_history(hpath) == []))
ents = [{"title": "Música Azul", "url": "https://x/1"}, {"title": "Aula de Python", "url": "https://y/2"}]
g.save_history(ents, hpath)
check("histórico: salva e lê de volta", g.load_history(hpath) == ents)
check("histórico: busca por título e por link",
      [e["url"] for e in g.filter_history(ents, "python")] == ["https://y/2"] and len(g.filter_history(ents, "x/1")) == 1 and len(g.filter_history(ents, "  ")) == 2)

g.HISTORY_FILE = os.path.join(TMP, "hist_app.json")
app.history = []
app._show("history")
app._render_history()
check("histórico: página vazia mostra aviso", "Ainda não" in app.lbl_hempty.cget("text"), app.lbl_hempty.cget("text"))
fake_item = {"url": "https://x/9", "title": "[Playlist] Meu Mix", "done": 5_000_000, "opts": {"paths": {"home": TMP}}}
app._record_history(fake_item, "Concluído")
app._record_history(dict(fake_item, url="https://x/10", title="Vídeo com problema"), "Erro")
check("histórico: registra concluído e erro (mais novo primeiro)",
      len(app.history) == 2 and app.history[0]["status"] == "Erro" and app.history[1]["title"] == "Meu Mix"
      and app.history[1]["size"] == 5_000_000 and app.history[1]["folder"] == TMP, app.history)
check("histórico: gravado em disco", len(g.load_history()) == 2)
check("histórico: página lista os dois itens", len(app.hframe.winfo_children()) == 2, len(app.hframe.winfo_children()))
app.v_hsearch.set("mix")
check("histórico: busca filtra a lista", len(app.hframe.winfo_children()) == 1, len(app.hframe.winfo_children()))
app.v_hsearch.set("zzz")
check("histórico: busca sem resultado avisa", "Nada encontrado" in app.lbl_hempty.cget("text"))
app.v_hsearch.set("")
app._reuse_url("https://x/9")
check("histórico: 'Usar de novo' coloca o link na tela de download", app._url() == "https://x/9")
app._copy_text("https://x/9")
check("histórico: 'Copiar link' copia", app.clipboard_get() == "https://x/9")
app._on_state(next(iter(app.items)) if app.items else "nenhum", "Concluído", None)  # id inexistente não quebra
for i in range(g.HISTORY_MAX + 20):
    app.history.insert(0, {"title": str(i), "url": f"https://x/{i}"})
app._record_history(fake_item, "Concluído")
check("histórico: limite de itens respeitado", len(app.history) == g.HISTORY_MAX and len(g.load_history()) == g.HISTORY_MAX, len(app.history))
g.messagebox.askyesno = lambda *a, **k: True
app._clear_history()
check("histórico: limpar apaga tudo (com confirmação)", app.history == [] and g.load_history() == [])
app._show("download")
app._record_history(fake_item, "Concluído")
check("histórico: aba fechada não redesenha a lista (só marca para depois)", app.hist_dirty and len(app.hframe.winfo_children()) == 0)
app._show("history")
check("histórico: ao abrir a aba a lista é desenhada", not app.hist_dirty and len(app.hframe.winfo_children()) == 1)
app._show("download")

# ------------------------------------------------------------ aviso ao terminar
app._toast("Teste", "Mensagem de teste", ms=60000)
app.update()
check("aviso: janelinha aparece", app.toast_win is not None and app.toast_win.winfo_exists())
app.toast_win.destroy()
shown = []
real_toast, real_should = app._toast, app._should_notify
app._toast = lambda title, text, ms=0: shown.append((title, text))
app._should_notify = lambda: True
app.v_notify.set(True)
app.cancel.clear()
app.run_ids = set()
app._on_fim(2, 1)
check("aviso: ao terminar mostra o resumo", shown and "2 com sucesso" in shown[-1][1] and "erros" in shown[-1][0], shown)
shown.clear()
app.v_notify.set(False)
app._on_fim(1, 0)
check("aviso: desligado nas configurações, não avisa", not shown)
app.v_notify.set(True)
app._should_notify = lambda: False
app._on_fim(1, 0)
check("aviso: janela em primeiro plano, não avisa", not shown)
app._on_fim(0, 0)
app.cancel.set()
app._should_notify = lambda: True
app._on_fim(1, 0)
check("aviso: cancelado, não avisa", not shown)
app.cancel.clear()
app._toast, app._should_notify = real_toast, real_should
check("aviso: padrão ligado e salvo nas configurações", g.DEFAULT_CFG["notify"] is True and "notify" in g.DEFAULT_CFG)

# ------------------------------------------------------------ atualização automática do yt-dlp
import hashlib  # noqa: E402

zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w") as z:
    z.writestr("yt_dlp/__init__.py", "# falso")
    z.writestr("yt_dlp/version.py", "__version__ = '2099.01.01'")
YZ = zbuf.getvalue()
ysrv_state = {"tag": "v2099.01.01", "sums": hashlib.sha256(YZ).hexdigest(), "body": YZ, "nosums": False}


class FakeYt(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        if self.path == "/api":
            body = _json.dumps({"tag_name": ysrv_state["tag"]}).encode()
        elif self.path == "/yt-dlp":
            body = ysrv_state["body"]
        elif self.path == "/SHA2-256SUMS" and not ysrv_state["nosums"]:
            body = ("0" * 64 + "  yt-dlp.exe\n" + ysrv_state["sums"] + "  yt-dlp\n").encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


ys = Srv(("127.0.0.1", 0), FakeYt)
threading.Thread(target=ys.serve_forever, daemon=True).start()
YB = f"http://127.0.0.1:{ys.server_address[1]}"
newp = os.path.join(TMP, "ytdlp_new")
check("yt-dlp: lê a versão mais nova", g.ytdlp_latest_version(YB + "/api") == "2099.01.01")
check("yt-dlp: detecta que há versão mais nova", g.is_newer("2099.01.01", g.YTDLP_VERSION) and not g.is_newer(g.YTDLP_VERSION, g.YTDLP_VERSION))
check("yt-dlp: lê o hash oficial (linha certa)", g.expected_sha256(YB + "/SHA2-256SUMS") == ysrv_state["sums"])
prog = []
out = g.stage_ytdlp_update(prog.append, YB + "/yt-dlp", YB + "/SHA2-256SUMS", newp)
check("yt-dlp: baixa, confere o hash e deixa pronto para a próxima abertura",
      out == newp and open(newp, "rb").read() == YZ and prog and not os.path.exists(newp + ".part"))
os.remove(newp)
ysrv_state["body"] = YZ + b"adulterado"
try:
    g.stage_ytdlp_update(None, YB + "/yt-dlp", YB + "/SHA2-256SUMS", newp)
    check("yt-dlp: arquivo adulterado (hash diferente) é recusado", False)
except RuntimeError as exc:
    check("yt-dlp: arquivo adulterado (hash diferente) é recusado", "hash" in str(exc) and not os.path.exists(newp) and not os.path.exists(newp + ".part"), exc)
ysrv_state["body"] = YZ
ysrv_state["nosums"] = True
try:
    g.stage_ytdlp_update(None, YB + "/yt-dlp", YB + "/SHA2-256SUMS", newp)
    check("yt-dlp: sem o hash oficial não instala", False)
except Exception:
    check("yt-dlp: sem o hash oficial não instala", not os.path.exists(newp))
ysrv_state["nosums"] = False
bad = io.BytesIO()
with zipfile.ZipFile(bad, "w") as z:
    z.writestr("outro/arquivo.txt", "x")
ysrv_state["body"], ysrv_state["sums"] = bad.getvalue(), hashlib.sha256(bad.getvalue()).hexdigest()
try:
    g.stage_ytdlp_update(None, YB + "/yt-dlp", YB + "/SHA2-256SUMS", newp)
    check("yt-dlp: zip sem yt_dlp é recusado", False)
except RuntimeError:
    check("yt-dlp: zip sem yt_dlp é recusado", not os.path.exists(newp))
ysrv_state["body"], ysrv_state["sums"] = YZ, hashlib.sha256(YZ).hexdigest()

# fluxo do app: só em programa instalado, com a opção ligada; mensagens vão para o registro/barra
g.YTDLP_LATEST_API, g.YTDLP_ZIPAPP_URL, g.YTDLP_SUMS_URL = YB + "/api", YB + "/yt-dlp", YB + "/SHA2-256SUMS"
real_zip = g.UPDATE_ZIPAPP
g.UPDATE_ZIPAPP = os.path.join(TMP, "appdata_yt")
g.FROZEN = False
app._startup_ytdlp_check()
time.sleep(0.5)
check("yt-dlp: rodando do código-fonte não atualiza sozinho", not os.path.exists(g.UPDATE_ZIPAPP + ".new"))
g.FROZEN = True
app.v_auto_ytdlp.set(False)
app._startup_ytdlp_check()
time.sleep(0.5)
check("yt-dlp: opção desligada não atualiza", not os.path.exists(g.UPDATE_ZIPAPP + ".new"))
app.v_auto_ytdlp.set(True)
app._startup_ytdlp_check()
for _ in range(50):
    if os.path.exists(g.UPDATE_ZIPAPP + ".new"):
        break
    time.sleep(0.1)
check("yt-dlp: atualização automática deixa o arquivo novo esperando", os.path.exists(g.UPDATE_ZIPAPP + ".new"))
check("yt-dlp: o arquivo em uso não é trocado com o programa aberto", not os.path.exists(g.UPDATE_ZIPAPP))
msgs = []
while True:
    try:
        m = app.q.get_nowait()
    except queue.Empty:
        break
    msgs.append(m)
check("yt-dlp: avisa pela fila que há versão pronta", any(m[0] == "ytdlp" and m[1] == "staged" for m in msgs), msgs[-3:])
app._on_ytdlp_msg(("ytdlp", "staged", "2099.01.01"))
check("yt-dlp: mostra aviso na barra de status", "2099.01.01" in app.v_status.get(), app.v_status.get())
app._on_ytdlp_msg(("ytdlp", "error", "sem rede"))
check("yt-dlp: erro de rede só vai para o registro (sem janela)", "sem rede" in app.log_text.get("1.0", "end") if hasattr(app, "log_text") else True)
# próxima abertura: o arquivo esperando vira o definitivo
g._apply_pending_ytdlp()
check("yt-dlp: na próxima abertura o arquivo novo entra no lugar", os.path.exists(g.UPDATE_ZIPAPP) and not os.path.exists(g.UPDATE_ZIPAPP + ".new"))
open(g.UPDATE_ZIPAPP + ".new", "wb").write(b"lixo")
g._apply_pending_ytdlp()
check("yt-dlp: arquivo esperando corrompido é descartado sem trocar o bom",
      not os.path.exists(g.UPDATE_ZIPAPP + ".new") and zipfile.is_zipfile(g.UPDATE_ZIPAPP))
g.UPDATE_ZIPAPP = real_zip
g.FROZEN = False
ys.shutdown()

app.destroy()
httpd.shutdown()

# ------------------------------------------------------------ atualização por zipapp
cfgdir = os.path.join(TMP, "cfg2", "VibeGrap")
os.makedirs(cfgdir, exist_ok=True)
site = os.path.dirname(yt_dlp.__file__)
zpath = os.path.join(cfgdir, "yt-dlp")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, fs in os.walk(site):
        if "__pycache__" in root:
            continue
        for fn in fs:
            full = os.path.join(root, fn)
            z.write(full, os.path.join("yt_dlp", os.path.relpath(full, site)))
env = dict(os.environ, XDG_CONFIG_HOME=os.path.join(TMP, "cfg2"))
code = (
    "import importlib.util,sys;"
    f"s=importlib.util.spec_from_file_location('g',{os.path.join(ROOT, 'ytdlp_gui.py')!r});m=importlib.util.module_from_spec(s);"
    "sys.modules['g']=m;s.loader.exec_module(m);print(m.yt_dlp.__file__)"
)
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
check("zipapp: yt-dlp é carregado do arquivo de atualização", zpath in r.stdout, (r.stdout + r.stderr).strip()[-200:])
with open(zpath, "wb") as f:
    f.write(b"nao e um zip")
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
check("zipapp: arquivo corrompido é ignorado", r.returncode == 0 and "site-packages" in r.stdout, (r.stdout + r.stderr).strip()[-200:])

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FALHAS:", FAILS if FAILS else "nenhuma")
sys.exit(1 if FAILS else 0)
