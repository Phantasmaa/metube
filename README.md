# MeTube - Phantasmaa edition

Web UI self-hosted para [yt-dlp](https://github.com/yt-dlp/yt-dlp). Fork personalizado de [alexta69/metube](https://github.com/alexta69/metube) con tema oscuro, descargas a `/root/metube/downloads` y exposición via nginx en `:8102`.

## Live

- **URL:** http://173.249.3.113:8102
- **Stack:** Python 3.14 (uv) + aiohttp + SocketIO + Angular 22 + yt-dlp 2026.7.4
- **Sitios soportados:** [1800+](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) — YouTube, TikTok, Instagram, Twitter/X, Vimeo, SoundCloud, Twitch, Reddit, Archive.org, Facebook, etc.

## Features

- Descarga video/audio en múltiples formatos y calidades
- Subtítulos y metadata (cuando yt-dlp los extrae)
- Descarga de playlists y canales
- Tema oscuro por default
- Cola de descargas concurrente (3 simultáneas)
- Auto-limpieza de archivos completados a 1h

## Setup local (no es necesario en VPS, esto corre en systemd)

```bash
git clone https://github.com/Phantasmaa/metube.git
cd metube
uv sync --no-dev
cd ui && pnpm install --frozen-lockfile && pnpm run build && cd ..

# Configurar puerto y descarga
export PORT=8099
export DEFAULT_THEME=dark
export DOWNLOAD_DIR=./downloads

PYTHONPATH=.:app uv run python -m app.main
```

## Systemd (cómo está montado en el VPS)

`/etc/systemd/system/metube.service`:

```ini
[Service]
WorkingDirectory=/root/metube
Environment="PYTHONPATH=/root/metube:/root/metube/app"
Environment="PORT=8099"
Environment="HOST=127.0.0.1"
Environment="DEFAULT_THEME=dark"
Environment="DOWNLOAD_DIR=/root/metube/downloads"
# STATE_DIR debe estar SEPARADO de DOWNLOAD_DIR. El middleware `state_dir_guard`
# rechaza servir cualquier archivo cuyo path real caiga dentro de STATE_DIR
# (anti-path-traversal). Si se solapan, todos los links de descarga dan 404.
Environment="STATE_DIR=/root/metube/state"
ExecStart=/root/metube/.venv/bin/python -m app.main
Restart=always
```

Nginx `proxy_pass http://127.0.0.1:8099` en `:8102` con soporte de Socket.IO upgrade.

## Limitaciones VPS

- **YouTube sin cookies** puede fallar con "No video formats found" (bot detection). Workaround: exportar cookies con `yt-dlp --cookies-from-browser chrome` o agregar `--cookies /path/cookies.txt` via opciones custom en la UI.
- **Sin deno** por default — yt-dlp baja EJS desde internet cuando hace falta.
- **Deno opcional** — algunos extractores (YouTube especialmente) lo requieren. Para habilitar: `curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y` y reiniciar servicio.
- **Sin GPU** — convierte con ffmpeg CPU.

## Test E2E verificado

```bash
curl -X POST http://127.0.0.1:8099/add \
  -H "Content-Type: application/json" \
  -d '{"url":"https://archive.org/details/BigBuckBunny_124","quality":"best","format":"mp4"}'
# → descarga en /root/metube/downloads/
# → ffprobe confirma H.264 640x360 MP4 ISO Media
```

## Repo upstream

[alexta69/metube](https://github.com/alexta69/metube) — mantenido por la comunidad. Este fork NO modifica la lógica de MeTube, solo agrega:

1. `metube.service` para systemd
2. nginx config
3. `.gitignore` para no commitear downloads/builds
4. este README con instrucciones de deployment

Si MeTube upstream se actualiza, podés merge-ar sin conflictos.

## License

MIT (mismo que upstream).
