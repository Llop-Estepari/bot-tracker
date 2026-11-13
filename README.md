# Bot tracker de Wallapop y Vinted → Telegram

Bot personal que vigila búsquedas en **Wallapop** y **Vinted** y te avisa por
Telegram en cuanto aparece un anuncio nuevo que encaja con tus filtros.

- Filtros por palabras clave, precio, envío (Wallapop), marcas, categorías y
  estado (Vinted).
- Palabras excluidas y **modo estricto** para eliminar resultados irrelevantes.
- Cada búsqueda tiene su propio intervalo (60 s – 1 h, por defecto 90 s).
- Deduplicación en SQLite: nunca recibes dos veces el mismo anuncio.
- Aviso de **bajada de precio** cuando un anuncio ya visto se abarata
  (activable por búsqueda).
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
- Un móvil Android con Termux para el hosting 24/7 (ver sección 6)

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
5. **Palabras excluidas** — `roto, para piezas, sin mando` (puede quedar vacío
   con `-`).
6. **Intervalo** — segundos entre comprobaciones (mínimo 60, defecto 90).
7. **¿Avisar de anuncios ya publicados?** — normalmente **No**: solo
   recibirás los que se publiquen a partir de ahora.

En Wallapop se busca por defecto **solo con envío disponible**. Se cambia con
`/editar <id> envio off`.

### Comandos

| Comando | Qué hace |
| --- | --- |
| `/nuevo` | Crear una búsqueda paso a paso |
| `/lista` | Ver todas tus búsquedas |
| `/ver <id>` | Detalle de una búsqueda |
| `/probar <id>` | Consultar ahora y ver resultados sin guardar nada |
| `/editar <id> <campo> <valor>` | Modificar nombre, palabras, precio, envío, intervalo… |
| `/avanzado <id> clave=valor` | Categorías, marcas y estado (IDs de las webs) |
| `/pausar <id>` / `/reanudar <id>` | Pausar o reactivar |
| `/borrar <id>` | Eliminar (con confirmación) |
| `/estado` | Versión, uptime, búsquedas y avisos registrados |
| `/ayuda` | Ayuda |

### Editar filtros

```text
/editar 3 min 100
/editar 3 max 400
/editar 3 palabras iphone 13 pro
/editar 3 excluir roto, sin caja
/editar 3 plataformas ambas
/editar 3 intervalo 120
/editar 3 envio off
/editar 3 estricto off
/editar 3 precios off
```

El **modo estricto** está activo por defecto: descarta anuncios cuyo título no
contenga al menos una palabra clave (con al menos 3 letras). Desactívalo con
`/editar <id> estricto off` si crees que se te escapan anuncios por usar
siglas (por ejemplo, títulos que solo dicen «PS5» para una búsqueda
«playstation 5»).

El **filtro de envío** de Wallapop está activo por defecto: solo se avisan
anuncios con envío disponible. Desactívalo con `/editar <id> envio off`.

Los **términos excluidos** son opcionales y pueden quedar vacíos:
`/editar <id> excluir -`.

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
- Si un anuncio ya visto **baja de precio**, se envía un aviso aparte con el
  precio anterior y el nuevo. Se puede desactivar por búsqueda con
  `/editar <id> precios off`. Solo se detecta mientras el anuncio siga
  apareciendo en los resultados y siga cumpliendo los filtros; las APIs
  devuelven las primeras posiciones ordenadas por novedad, así que un anuncio
  muy antiguo puede salir de esa ventana.
- Filtros server-side: palabras, precio, envío (Wallapop), categoría, marca y
  estado.
- Filtros client-side: modo estricto, palabras excluidas y comprobación
  defensiva de precio.
- Ante `429` la plataforma se enfría 3 minutos; ante `403` (bloqueo), 15
  minutos. El resto de plataformas siguen funcionando.
- Wallapop se consulta con `httpx` y las cabeceras de su web; si responde 403, la plataforma se enfría.
- Vinted exige cookies de sesión: el bot visita la web, las guarda y las
  renueva automáticamente si caducan.

## 6. Hosting en Android con Termux

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
3. Crea el `.venv` e instala `requirements.txt`.
4. Coloca el `.env` y migra `tracker.db`.
5. Ajusta las búsquedas a 300 s de intervalo.
6. Comprueba Wallapop y Vinted desde la red del móvil.
7. Configura `~/.termux/boot/start-bot.sh` para arrancar con el teléfono.

### Arrancar el bot

```bash
cd ~/bot-tracker
tmux new -s bot '.venv/bin/python main.py 2>&1 | tee -a bot.log'
# salir sin matar el bot: Ctrl+B, D
```

### Conectar el móvil al repositorio (una sola vez)

El repositorio es privado. Crea una **deploy key de solo lectura** en Termux:

```bash
pkg install -y openssh
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "termux-bot" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Añade esa clave pública al repositorio como deploy key de solo lectura (sin
`--allow-write`):

```bash
gh repo deploy-key add clave-publica.pub --title "Termux" \
  -R Llop-Estepari/bot-tracker
```

Configura SSH y convierte la instalación existente en un clon conservando
`.env` y `tracker.db`:

```bash
cat > ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

cd ~/bot-tracker
git init
git remote add origin git@github.com:Llop-Estepari/bot-tracker.git
git fetch origin
git reset --hard origin/main
```

`.env`, `tracker.db` y `.venv` están en `.gitignore` y no se tocan.

### Actualizar

```bash
bash ~/bot-tracker/deploy/termux-update.sh
```

El script para el bot, guarda copias con fecha de `tracker.db` y `.env` en
`~/bot-tracker-backups/`, hace `git pull --ff-only`, instala dependencias solo
si cambiaron los `requirements`, valida que el código compila, reinicia en
`tmux` y vuelve al commit anterior si algo falla. Nunca toca `.env`, `.venv`,
`tracker.db` ni `bot.log`. Muestra la versión antes y después de actualizar.

### Persistencia y batería

- `termux-wake-lock` mantiene la CPU despierta (el instalador ya lo activa).
- Ajustes de Android → Apps → Termux → Batería → **Sin restricciones**.
- En Xiaomi/MIUI: activa **Autostart** para Termux y Termux:Boot y quita
  cualquier restricción de ahorro de energía.
- Mantén el móvil enchufado y en Wi-Fi. Con 5 minutos de intervalo el consumo
  ronda 30–60 MB/día.
- Termux:Boot ejecuta `start-bot.sh` al encender el móvil (tras desbloquearlo).

### Copias de seguridad

El script de actualización guarda copias con fecha en `~/bot-tracker-backups/`.
Para una copia manual del SQLite:

```bash
cp ~/bot-tracker/tracker.db ~/storage/shared/tracker-$(date +%F).db
```

## 7. Versiones y releases

La versión vive en `version.py` (única fuente de verdad) y se muestra en
`/estado` y en el log de arranque.

### Política de versiones

| Tipo | Cuándo | Ejemplo |
| --- | --- | --- |
| **PATCH** | Arreglos, documentación, dependencias | `1.0.1` |
| **MINOR** | Nueva funcionalidad, comandos o filtros | `1.1.0` |
| **MAJOR** | Cambios incompatibles (config, BD, comandos) | `2.0.0` |

Ningún cambio llega a `main` sin subir `version.py` y sin entrada en
`CHANGELOG.md`.

### Publicar una versión

```bash
python scripts/release.py patch "Corrige el filtrado de palabras"
python scripts/release.py minor "Añade el comando /version"
python scripts/release.py major "Cambia el formato de configuración"
```

El script ejecuta ruff y los tests, sube la versión, añade la entrada al
changelog, crea el commit `release: vX.Y.Z`, el tag `vX.Y.Z` y empuja todo a
GitHub. `--dry-run` muestra el resultado sin tocar nada y `--no-push` deja el
commit y el tag en local.

### Comprobaciones

```bash
python scripts/check_version.py          # SemVer, fecha y changelog
python scripts/check_version.py v1.0.0   # además, que el tag coincida
```

La CI (`.github/workflows/ci.yml`):

- ejecuta `ruff` y `pytest` en cada push/PR;
- falla si un cambio no modifica `version.py`;
- en tags `v*`, verifica que el tag coincide con `version.py`.

No se crean GitHub Releases: el historial vive en `CHANGELOG.md` y en los tags.

### Actualizar el móvil

```bash
bash ~/bot-tracker/deploy/termux-update.sh
```

Hace `git pull`, instala dependencias si cambiaron y reinicia. Comprueba con
`/estado` que aparece la nueva versión.

## 8. Desarrollo y tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Los tests cubren filtros, parseo de respuestas reales de ambas plataformas,
persistencia y la lógica del scheduler (siembra inicial, deduplicación,
límites de avisos) con fuentes simuladas. No hacen peticiones de red.

## 9. Problemas frecuentes

**Wallapop responde 403 (Request blocked)**
El WAF de CloudFront ha bloqueado la IP temporalmente. El bot enfriará esa
plataforma 15 minutos. Desde una IP residencial/móvil no suele ocurrir.

**Vinted responde 401/403**
El bot renueva las cookies solo. Desde una IP residencial/móvil no suele
ocurrir. Si persiste, puede que Vinted haya cambiado el endpoint
(`/svc-catalogue/items`): revisa `sources/vinted.py`.

**No llegan avisos**
Comprueba `/estado` (¿la alerta está activa? ¿hay plataformas enfriando?),
lanza `/probar <id>` y revisa `tail -f ~/bot-tracker/bot.log` (o entra con
`tmux attach -t bot`).

**Cambiar de país en Vinted**
Ajusta en `.env`:

```env
VINTED_BASE_URL=https://www.vinted.fr
VINTED_LOCALE=fr-FR
```

Wallapop no permite filtrar por país: usa su feed por defecto.

## 10. Estructura del proyecto

```text
main.py              Arranque: Telegram + scheduler
config.py            Configuración desde .env
db.py                SQLite: alertas y anuncios vistos
filters.py           Filtros de cliente (modo estricto, exclusiones y precio)
notifier.py          Mensajes de Telegram
scheduler.py         Bucle de comprobación y deduplicación
sources/wallapop.py  Cliente de Wallapop
sources/vinted.py    Cliente de Vinted
bot/handlers.py      Comandos, asistente y callbacks
deploy/              Scripts de Termux (instalación, actualización y arranque)
scripts/             Release, control de versión y verificación de fuentes
tests/               Tests + fixtures reales de las APIs
version.py           Versión de la aplicación
CHANGELOG.md         Historial de versiones
.github/workflows/   CI (tests, lint y control de versión)
```

## 11. Aviso legal

Este proyecto es de uso personal y no está afiliado a Wallapop ni a Vinted.
Automatizar el acceso puede ir contra sus términos de servicio. El bot está
diseñado para hacer un número muy bajo de peticiones (una búsqueda cada 1–2
minutos), pero la responsabilidad del uso es de quien lo despliega.
