# Bot tracker de Wallapop y Vinted → Telegram

Bot personal que vigila búsquedas en **Wallapop** y **Vinted** y te avisa por
Telegram en cuanto aparece un anuncio nuevo que encaja con tus filtros.

- Filtros por palabras clave, precio, zona/radio (Wallapop), marcas,
  categorías y estado (Vinted).
- Palabras excluidas y **modo estricto** para eliminar resultados irrelevantes.
- Cada búsqueda tiene su propio intervalo (60 s – 1 h, por defecto 90 s).
- Deduplicación en SQLite: nunca recibes dos veces el mismo anuncio.
- Avisos con foto, precio, ubicación y enlace directo, con botón para
  silenciar la búsqueda.
- Todo se gestiona desde el chat: no hay que editar archivos para cambiar
  filtros.

> ⚠️ Ni Wallapop ni Vinted tienen API oficial para esto. El bot usa los
> endpoints internos de sus webs con un ritmo bajo. Pueden cambiar o bloquear
> peticiones en cualquier momento; el código está aislado en `sources/` para
> adaptarlo rápido. Úsalo de forma moderada y respeta sus términos de uso.

---

## 1. Requisitos

- Linux (probado en Python 3.14; funciona desde 3.11)
- Un bot de Telegram (se crea gratis con [@BotFather](https://t.me/BotFather))
- Un VPS o equipo encendido 24/7 (opcional, pero recomendable)

## 2. Instalación local

```bash
cd bot-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y pon al menos el token:

```env
TELEGRAM_BOT_TOKEN=123456789:AAEjemploDeTokenDeBotFather
```

Arranca el bot:

```bash
.venv/bin/python main.py
```

## 3. Autorizarte (whitelist)

El bot es privado: solo responde a los `chat_id` de `ALLOWED_CHAT_IDS`.

1. Con el bot arrancado, escribe `/start` desde tu Telegram.
2. El bot te responderá con **tu chat_id** y te dirá que no tienes acceso.
3. Añádelo al `.env`:

   ```env
   ALLOWED_CHAT_IDS=123456789
   ```

4. Reinicia el bot. Escribe `/ayuda` y ya podrás crear búsquedas.

Puedes autorizar a más personas separando IDs por comas.
Si dejas `ALLOWED_CHAT_IDS` vacío, el bot rechazará a todo el mundo (es el
comportamiento seguro por defecto).

## 4. Uso

### Crear una búsqueda

```
/nuevo
```

El asistente pide, paso a paso:

1. **Nombre** — para identificarla luego.
2. **Plataformas** — Wallapop, Vinted o ambas.
3. **Palabras clave** — lo que buscará la plataforma.
4. **Precio** — `100-400`, `100-` (solo mínimo), `-400` (solo máximo),
   `-` (sin filtro).
5. **Zona** (solo Wallapop) — `Madrid`, `Madrid 30` (30 km de radio),
   `40.4168,-3.7038` o `-` para toda España.
6. **Palabras excluidas** — `roto, para piezas, sin mando`.
7. **Intervalo** — segundos entre comprobaciones (mínimo 60, defecto 90).
8. **¿Avisar de anuncios ya publicados?** — normalmente **No**: solo
   recibirás los que se publiquen a partir de ahora.

### Comandos

| Comando | Qué hace |
| --- | --- |
| `/nuevo` | Crear una búsqueda paso a paso |
| `/lista` | Ver todas tus búsquedas |
| `/ver <id>` | Detalle de una búsqueda |
| `/probar <id>` | Consultar ahora y ver resultados sin guardar nada |
| `/editar <id> <campo> <valor>` | Modificar nombre, palabras, precio, zona, intervalo… |
| `/avanzado <id> clave=valor` | Categorías, marcas y estado (IDs de las webs) |
| `/pausar <id>` / `/reanudar <id>` | Pausar o reactivar |
| `/borrar <id>` | Eliminar (con confirmación) |
| `/estado` | Uptime, búsquedas y avisos registrados |
| `/ayuda` | Ayuda |

### Editar filtros

```text
/editar 3 min 100
/editar 3 max 400
/editar 3 palabras iphone 13 pro
/editar 3 excluir roto, sin caja
/editar 3 zona Madrid 30
/editar 3 plataformas ambas
/editar 3 intervalo 120
/editar 3 estricto off
```

El **modo estricto** está activo por defecto: descarta anuncios cuyo título no
contenga al menos una palabra clave (con al menos 3 letras). Vinted devuelve
resultados bastante difusos, así que ayuda mucho. Desactívalo si crees que se
te escapan anuncios por usar siglas (por ejemplo, títulos que solo dicen
«PS5» para una búsqueda «playstation 5»).

### Filtros avanzados

Los IDs salen de la URL de cada web (por ejemplo, una categoría de Vinted
aparece como `?catalog[]=1904`):

```text
/avanzado 3 vinted_catalog=1904
/avanzado 3 vinted_brand=53,417
/avanzado 3 vinted_condition=6
/avanzado 3 wallapop_category=100
/avanzado 3 vinted_brand=-
```

| Clave | Plataforma | Qué filtra |
| --- | --- | --- |
| `wallapop_category` | Wallapop | Categoría |
| `vinted_catalog` | Vinted | Categoría |
| `vinted_brand` | Vinted | Marcas (varias separadas por comas) |
| `vinted_condition` | Vinted | Estado del artículo |

Usa `-` como valor para borrar un filtro.

## 5. Cómo funciona

- Un scheduler en segundo plano revisa cada alerta según su intervalo, con un
  pequeño *jitter* y unos segundos de separación entre búsquedas.
- La primera pasada de una alerta **siembra** los anuncios existentes sin
  avisar (salvo que hayas pedido lo contrario), para que no recibas un aluvión
  inicial.
- Cada anuncio se guarda en `seen_items`: si ya se avisó, no se repite.
- Filtros server-side: palabras, precio, zona, categoría, marca y estado.
- Filtros client-side: modo estricto, palabras excluidas y comprobación
  defensiva de precio.
- Ante `429` la plataforma se enfría 3 minutos; ante `403` (bloqueo), 15
  minutos. El resto de plataformas siguen funcionando.
- Wallapop exige parecer un navegador: se usa `curl_cffi` con TLS de Chrome.
- Vinted exige cookies de sesión: el bot visita la web, las guarda y las
  renueva automáticamente si caducan.

## 6. Despliegue en un VPS (systemd)

```bash
# En el servidor, como root:
useradd --system --home /opt/bot-tracker --shell /usr/sbin/nologin tracker
mkdir -p /opt/bot-tracker
# Copia el proyecto (rsync/scp/git) a /opt/bot-tracker y luego:
cd /opt/bot-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env                      # token + ALLOWED_CHAT_IDS + DATABASE_PATH
chown -R tracker:tracker /opt/bot-tracker
chmod 600 .env

cp deploy/tracker.service /etc/systemd/system/tracker.service
systemctl daemon-reload
systemctl enable --now tracker
```

Ver logs en directo:

```bash
journalctl -u tracker -f
```

Reiniciar tras cambiar el `.env`:

```bash
systemctl restart tracker
```

### Copias de seguridad

Todo el estado vive en el SQLite (`DATABASE_PATH`, por defecto
`/opt/bot-tracker/tracker.db`). Basta con copiar ese archivo:

```bash
sqlite3 /opt/bot-tracker/tracker.db ".backup /root/tracker-$(date +%F).db"
```

## 7. Despliegue en Fly.io

La app se ejecuta como **worker** (sin HTTP): solo necesita una máquina y un
volumen persistente para SQLite. El `Dockerfile` y `fly.toml` ya están
incluidos.

```bash
# 1. Instalar flyctl y autenticarse
curl -L https://fly.io/install.sh | sh
export PATH="$HOME/.fly/bin:$PATH"
fly auth login

# 2. Crear la app en la organización y el volumen de datos
fly apps create vinpop-bot --org llop
fly volumes create vinpop_data --region mad --size 1 --app vinpop-bot --yes

# 3. Secretos (nunca en fly.toml)
fly secrets set --app vinpop-bot \
  TELEGRAM_BOT_TOKEN=... \
  ALLOWED_CHAT_IDS=<tu_chat_id>

# 4. Desplegar y comprobar
fly deploy --app vinpop-bot
fly status --app vinpop-bot
fly logs --app vinpop-bot
```

Notas:

- **No escales a más de una máquina**: el polling de Telegram y SQLite son
  singleton. Dos instancias provocan errores 409 y avisos duplicados.
- La base de datos vive en el volumen, en `/data/tracker.db`
  (`DATABASE_PATH`).
- Si Wallapop bloquea la IP del datacenter, añade el secreto
  `WALLAPOP_PROXY` con un proxy residencial:
  `fly secrets set --app vinpop-bot WALLAPOP_PROXY=socks5h://...`
- **Vinted bloquea las IPs de datacenter** (Fly, AWS, Hetzner…). Para que
  funcione en Fly necesitas un proxy residencial:
  `fly secrets set --app vinpop-bot VINTED_PROXY=http://usuario:clave@host:puerto`
  Sin proxy, el bot solo avisará de Wallapop y Vinted quedará enfriado.
- Copia de seguridad del SQLite:
  ```bash
  fly ssh console --app vinpop-bot \
    -C "sqlite3 /data/tracker.db '.backup /data/tracker-backup.db'"
  fly sftp get /data/tracker-backup.db --app vinpop-bot
  ```

## 8. Hosting en Android con Termux

Termux es la opción más barata (0 €/mes) y, al usar una IP residencial/móvil,
permite **Wallapop y Vinted a la vez**. Requiere Termux y Termux:Boot desde
**F-Droid** (no desde Play Store), Android 7+ y un móvil que puedas dejar
enchufado y en Wi-Fi.

### Preparar el móvil

```bash
# En Termux, una sola vez
termux-setup-storage
```

Copia el proyecto y los datos al almacenamiento compartido del móvil:

```bash
# En el portátil
adb push bot-tracker /sdcard/Download/bot-tracker
adb push tracker.db /sdcard/Download/bot-tracker/tracker.db
# .env.termux con el token y ALLOWED_CHAT_IDS
adb push .env.termux /sdcard/Download/bot-tracker/.env.termux
```

### Instalación automática

```bash
# En Termux
bash ~/storage/downloads/bot-tracker/deploy/termux-install.sh
```

El instalador:

1. Instala `python` y `tmux`.
2. Copia el proyecto a `~/bot-tracker`.
3. Crea el `.venv` e instala `requirements-termux.txt` (sin `curl_cffi`).
4. Coloca el `.env` y migra `tracker.db`.
5. Ajusta las búsquedas a 300 s de intervalo.
6. Comprueba Wallapop y Vinted desde la red del móvil.
7. Configura `~/.termux/boot/start-bot.sh` para arrancar con el teléfono.

### Arrancar (cuando Fly esté parado)

```bash
cd ~/bot-tracker
tmux new -s bot '.venv/bin/python main.py 2>&1 | tee -a bot.log'
# salir sin matar el bot: Ctrl+B, D
```

### Persistencia y batería

- `termux-wake-lock` mantiene la CPU despierta (el instalador ya lo activa).
- Ajustes de Android → Apps → Termux → Batería → **Sin restricciones**.
- En Xiaomi/MIUI: activa **Autostart** para Termux y Termux:Boot y quita
  cualquier restricción de ahorro de energía.
- Mantén el móvil enchufado y en Wi-Fi. Con 5 minutos de intervalo el consumo
  ronda 30–60 MB/día.
- Termux:Boot ejecuta `start-bot.sh` al encender el móvil (tras desbloquearlo).

### Cambiar entre móvil y Fly

Solo puede haber **un poller de Telegram activo**:

```bash
# Pasar a móvil
fly machine stop <id-de-la-maquina> -a vinpop-bot
# y arrancar tmux en el móvil

# Volver a Fly
# (parar tmux en el móvil) y luego:
fly machine start <id-de-la-maquina> -a vinpop-bot
```

Sincroniza `tracker.db` en la dirección del nuevo host si quieres conservar
las búsquedas y los anuncios vistos.

## 9. Desarrollo y tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Los tests cubren filtros, parseo de respuestas reales de ambas plataformas,
persistencia y la lógica del scheduler (siembra inicial, deduplicación,
límites de avisos) con fuentes simuladas. No hacen peticiones de red.

## 10. Problemas frecuentes

**Wallapop responde 403 (Request blocked)**
El WAF de CloudFront ha bloqueado la IP. El bot enfriará esa plataforma 15
minutos. Si tu VPS está bloqueado de forma persistente, configura un proxy en
el `.env`:

```env
WALLAPOP_PROXY=socks5h://usuario:clave@host:puerto
```

**Vinted responde 401/403**
El bot renueva las cookies solo. Si persiste y estás en un VPS/datacenter, es
un bloqueo por IP: configura `VINTED_PROXY` con un proxy residencial. Si el
403 aparece también con proxy, puede que Vinted haya cambiado el endpoint
(`/svc-catalogue/items`): revisa `sources/vinted.py`.

**La geocodificación falla**
Se usa Nominatim (OpenStreetMap). Si no encuentra la ciudad, introduce las
coordenadas directamente: `/editar 3 zona 40.4168,-3.7038`.

**No llegan avisos**
Comprueba `/estado` (¿la alerta está activa? ¿hay plataformas enfriando?),
lanza `/probar <id>` y revisa `journalctl -u tracker -f`.

**Cambiar de país**
Ajusta en `.env`:

```env
WALLAPOP_BASE_URL=https://it.wallapop.com
VINTED_BASE_URL=https://www.vinted.fr
VINTED_LOCALE=fr-FR
```

## 11. Estructura del proyecto

```text
main.py              Arranque: Telegram + scheduler
config.py            Configuración desde .env
db.py                SQLite: alertas y anuncios vistos
filters.py           Filtros de cliente (modo estricto, exclusiones, precio)
geocode.py           Ciudades → coordenadas (Nominatim)
notifier.py          Mensajes de Telegram
scheduler.py         Bucle de comprobación y deduplicación
sources/wallapop.py  Cliente de Wallapop
sources/vinted.py    Cliente de Vinted
bot/handlers.py      Comandos, asistente y callbacks
deploy/              systemd, Fly y scripts de Termux
scripts/             Verificación de fuentes (check_sources.py)
tests/               Tests + fixtures reales de las APIs
Dockerfile           Imagen para Fly.io y otros contenedores
fly.toml             Worker + volumen persistente en Fly.io
requirements-termux.txt  Dependencias sin curl_cffi para Android
```

## 12. Aviso legal

Este proyecto es de uso personal y no está afiliado a Wallapop ni a Vinted.
Automatizar el acceso puede ir contra sus términos de servicio. El bot está
diseñado para hacer un número muy bajo de peticiones (una búsqueda cada 1–2
minutos), pero la responsabilidad del uso es de quien lo despliega.
