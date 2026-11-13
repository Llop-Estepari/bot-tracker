# Bot tracker de Wallapop y Vinted → Telegram

Bot personal que vigila búsquedas en **Wallapop** y **Vinted** y te avisa por
Telegram en cuanto aparece un anuncio nuevo que encaja con tus filtros.

- Filtros por palabras clave, precio, envío y distancia (Wallapop), marcas,
  categorías y estado (Vinted).
- Palabras excluidas y **modo estricto** para eliminar resultados irrelevantes.
- Cada búsqueda tiene su propio intervalo (60 s – 1 h, por defecto 90 s).
- Deduplicación en SQLite: nunca recibes dos veces el mismo anuncio.
- Aviso de **bajada de precio** cuando un anuncio ya visto se abarata
  (activable por búsqueda).
- Avisos con foto, precio, ubicación, distancia y país, con botón para
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
5. **Distancia** (solo Wallapop) — sin límite por defecto, o 5/10/25/50/100/200
   km desde tu ubicación.
6. **Palabras excluidas** — `roto, para piezas, sin mando` (puede quedar vacío
   con `-`).
7. **Intervalo** — segundos entre comprobaciones (mínimo 60, defecto 90).
8. **¿Avisar de anuncios ya publicados?** — normalmente **No**: solo
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
| `/ubicacion` | Definir tu ubicación para el filtro de distancia |
| `/editar <id> <campo> <valor>` | Modificar nombre, palabras, precio, envío, distancia, intervalo… |
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
/editar 3 distancia 25
/editar 3 distancia todo
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

### Distancia (solo Wallapop)

Wallapop devuelve anuncios de toda su red, incluidos Portugal, Italia y otros
países. El filtro de distancia es **opcional** y está **sin límite por
defecto**.

1. Define tu origen una sola vez con `/ubicacion`: pulsa el botón
   **📍 Enviar mi ubicación** (un toque) o escribe las coordenadas:
   `/ubicacion 41.3874, 2.1686`.
2. Limita cada búsqueda:

```text
/editar 3 distancia 25
/editar 3 distancia 25km
/editar 3 distancia todo
```

El radio se aplica **solo a Wallapop**; Vinted no permite filtrar por
distancia. Rango: 1–500 km. Si cambias de origen con `/ubicacion`, todas las
búsquedas con radio usan el nuevo punto automáticamente.

En los avisos, la ubicación muestra la distancia cuando hay origen
(`📍 Getafe (Madrid) · 12 km`). Los anuncios de fuera de España se marcan
siempre, aunque no haya límite:

```text
📍 Lisboa (Lisboa) · 🇵🇹 Portugal · fuera de España
```

El radio se envía a Wallapop (`distance_in_km`) y además se comprueba en local
con la distancia real del anuncio, para que el filtro sea fiable aunque la API
lo ignore.

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
- Filtros server-side: palabras, precio, envío (Wallapop), distancia
  (Wallapop), categoría, marca y estado.
- Filtros client-side: modo estricto, palabras excluidas, comprobación
  defensiva de precio y de radio (haversine).
- Ante `429` la plataforma se enfría 3 minutos; ante `403` (bloqueo), 15
  minutos. El resto de plataformas siguen funcionando.
- Wallapop se consulta con `httpx` y las cabeceras de su web; si responde 403, la plataforma se enfría.
- Vinted exige cookies de sesión: el bot visita la web, las guarda y las
  renueva automáticamente si caducan.

## 6. Hosting en Android con Termux

Termux es la opción más barata (0 €/mes) y, al usar una IP residencial/móvil,
permite **Wallapop y Vinted a la vez**. El bot corre como servicio supervisado
con **runit**: si el proceso cae, se levanta solo, y arranca con el móvil
gracias a Termux:Boot.

Requisitos: Android 7+, Wi-Fi, cable USB de datos, un ordenador y un móvil que
puedas dejar enchufado.

### 6.1 Instalación desde cero (recomendada, por USB)

#### En el móvil

1. **Opciones de desarrollador:** Ajustes → Información del teléfono → toca 7
   veces **Número de compilación**.
2. **Depuración USB:** Ajustes → Sistema → Opciones de desarrollador → activar.
3. En HyperOS/MIUI activa también **Instalar vía USB** (puede pedir cuenta Mi
   y SIM).
4. Conecta el móvil al ordenador con un cable **de datos**.

#### En el ordenador

Instala `adb` y `git`:

**Ubuntu / Debian / Mint**

```bash
sudo apt update
sudo apt install -y android-tools-adb android-tools-fastboot \
                    android-sdk-platform-tools-common git curl
```

**Fedora**

```bash
sudo dnf install -y android-tools git curl
```

**Arch / Manjaro**

```bash
sudo pacman -S --needed android-tools git curl
```

**macOS** (Homebrew)

```bash
brew install android-platform-tools git
```

**Windows 10/11** (PowerShell; ejecuta el instalador con **Git Bash**)

```powershell
winget install --id Git.Git -e
winget install --id Google.PlatformTools -e
```

Si `winget` no encuentra Platform Tools, descarga
https://dl.google.com/android/repository/platform-tools-latest-windows.zip,
descomprímelo en `C:\platform-tools` y añade esa carpeta al `PATH`.

Comprueba la conexión:

```bash
adb version
adb devices
```

Debe aparecer el móvil como `device`. Si sale `unauthorized`, acepta el aviso
en el móvil. Si no aparece nada:

- prueba otro cable o puerto USB;
- en Linux, comprueba las reglas udev (`android-sdk-platform-tools-common`) y
  ejecuta `adb kill-server && adb devices`;
- en Windows, instala el driver USB del fabricante;
- en WSL, usa `adb` desde Windows (o configura `usbipd-win`).

#### Instalar el bot

```bash
git clone https://github.com/Llop-Estepari/bot-tracker.git
cd bot-tracker
bash deploy/provision-adb.sh --token "123456789:AA..." --chat-id 123456789
```

El script:

1. descarga e instala **Termux**, **Termux:Boot**, **Termux:Widget** y
   **Termux:API** desde F-Droid;
2. exime a Termux del ahorro de batería y desactiva el *phantom process killer*
   de Android 12+;
3. copia `.env` y, si se pasa `--db`, `tracker.db`;
4. clona el repo, crea el `.venv` e instala las dependencias;
5. registra el servicio **runit** y el arranque con Termux:Boot;
6. crea los atajos del widget y verifica que arranca con la versión correcta.

Si el móvil bloquea la ejecución remota, el script te deja **un único comando**
para pegar en Termux:

```bash
bash /sdcard/Download/bot-install.sh --yes --env-file /sdcard/Download/bot.env
```

#### Opciones útiles de `provision-adb.sh`

| Opción | Para qué |
| --- | --- |
| `--chat-id 1,2` | Autorizar varios chats |
| `--env-file RUTA` | Usar un `.env` ya preparado en vez de `--token` |
| `--db RUTA` | Restaurar un `tracker.db` existente |
| `--serial SERIAL` | Elegir móvil si hay varios conectados |
| `--no-apks` | No reinstalar las apps de F-Droid |
| `--no-remote` | Solo preparar el móvil y mostrar el comando |

### 6.2 Instalación sin ordenador

1. Instala desde F-Droid: **Termux**, **Termux:Boot** y **Termux:Widget**.
2. Abre Termux y pega:

```bash
curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/deploy/phone-install.sh | bash
```

3. Introduce el token y el chat_id cuando pregunte.

El script es idempotente: puedes volver a ejecutarlo para reparar la instalación
sin perder `.env`, `tracker.db` ni los datos.

### 6.3 Servicio runit y atajos

Comandos útiles en Termux:

```bash
sv status bot      # estado del servicio
sv restart bot     # reiniciar
sv down bot        # parar
sv up bot          # arrancar
tail -f ~/bot-tracker/logs/current   # logs en vivo
```

Los logs rotan solos: 5 MB por fichero y 3 ficheros (`~/bot-tracker/logs`).

Atajos de **Termux:Widget** (se crean automáticamente): *Instalar bot*,
*Actualizar bot*, *Estado*, *Reiniciar bot*, *Ver logs* y *Backup*. Añade el
widget desde la pantalla de inicio.

### 6.4 Ajustes obligatorios en HyperOS/MIUI

Sin esto, Xiaomi terminará matando el bot:

- Ajustes → Aplicaciones → **Termux** → **Batería** → *Sin restricciones*.
- Ajustes → Aplicaciones → **Termux** → **Inicio automático** → activar.
- Recientes → mantén Termux → **candado**.
- Desactiva el ahorro de energía agresivo del sistema.

Recomendado: móvil enchufado y, si existe, **límite de carga al 80 %**.

### 6.5 Comprobar y actualizar

En Telegram:

```text
/estado     → versión, uptime y búsquedas
/ubicacion  → origen para el filtro de distancia
/nuevo      → crear una búsqueda
```

En el móvil:

```bash
bash ~/bot-tracker/deploy/phone-doctor.sh
```

Para cambiar el token o los chats autorizados sin editar el archivo:

```bash
bash ~/bot-tracker/deploy/phone-config.sh --chat-id 123456789 --restart
bash ~/bot-tracker/deploy/phone-config.sh --token "123:ABC" --restart
bash ~/bot-tracker/deploy/phone-config.sh --show
```

Para actualizar, un toque en el widget **Actualizar bot** o:

```bash
bash ~/bot-tracker/update.sh
```

El script para el servicio, guarda backups, actualiza, reinstala dependencias si
cambiaron, arranca y verifica la versión. Si algo falla, vuelve al commit
anterior.

### 6.6 Copias de seguridad y cambio de móvil

```bash
cp ~/bot-tracker/tracker.db ~/storage/shared/bot-tracker-$(date +%F).db
```

El `.env` contiene el token: no lo copies al almacenamiento compartido. Las
actualizaciones ya guardan una copia en `~/bot-tracker-backups/`.

Para cambiar de móvil: conecta el nuevo por USB y ejecuta en el ordenador

```bash
bash deploy/provision-adb.sh --token "…" --chat-id … --db /ruta/tracker.db
```

Para desinstalar el servicio conservando los datos:

```bash
bash deploy/phone-uninstall.sh
```

Y para borrarlo todo (antes guarda `.env` y `tracker.db` en
`~/bot-tracker-backups`):

```bash
bash deploy/phone-uninstall.sh --purge
```

### 6.7 Instalación manual (avanzada)

Si prefieres no usar el instalador, `deploy/termux-install.sh` sigue
disponible para copiar el proyecto desde `/sdcard/Download` y arrancar con
tmux. El repositorio es **público**, así que ya no hacen falta claves SSH ni
deploy keys: `git clone https://github.com/Llop-Estepari/bot-tracker.git`.

### 6.8 Problemas frecuentes del hosting

**`adb: command not found`**
Instala Platform Tools (sección 6.1) y reabre la terminal.

**`adb devices` no muestra el móvil**
Cable de datos, otro puerto, reglas udev en Linux, driver en Windows. Prueba
`adb kill-server && adb devices`.

**El bot deja de responder por la noche**
Batería/phantom killer. Ejecuta `phone-doctor.sh` y revisa la sección 6.4.

**`sv status bot` dice `down`**
```bash
tail -n 50 ~/bot-tracker/logs/current
```
y corrige el error (token, dependencias, base de datos).

**La instalación por USB no arranca sola**
Pega el comando que muestra el script en Termux; es el único paso manual
posible si HyperOS bloquea la ejecución remota.

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
bash ~/bot-tracker/update.sh
```

Hace backup, actualiza, reinicia el servicio runit y verifica la versión.
Comprueba con `/estado` que aparece la nueva versión.

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
lanza `/probar <id>` y revisa `tail -f ~/bot-tracker/logs/current` (el log del
servicio runit).

**La actualización no se aplica**
Revisa `~/bot-tracker/update.log`. El script descarta los cambios locales con
backup y hace rollback si falla; el log indica el paso exacto. Con runit, el
script baja el servicio (`sv down bot`) antes de actualizar, así que no hay que
parar nada a mano.

**Cambiar de país en Vinted**
Ajusta en `.env`:

```env
VINTED_BASE_URL=https://www.vinted.fr
VINTED_LOCALE=fr-FR
```

Wallapop no permite filtrar por país: usa su feed por defecto. Los anuncios de
fuera de España aparecen marcados en el aviso (`🇵🇹 Portugal · fuera de
España`), y puedes acotar la zona con `/ubicacion` + `/editar <id> distancia`.

## 10. Estructura del proyecto

```text
main.py              Arranque: Telegram + scheduler
config.py            Configuración desde .env
db.py                SQLite: alertas, anuncios vistos y ubicación
filters.py           Filtros de cliente (precio, radio, estricto, exclusiones)
geo.py               Distancias (haversine), coordenadas y países
notifier.py          Mensajes de Telegram
scheduler.py         Bucle de comprobación y deduplicación
sources/wallapop.py  Cliente de Wallapop
sources/vinted.py    Cliente de Vinted
bot/handlers.py      Comandos, asistente y callbacks
update.sh            Lanzador corto: bash ~/bot-tracker/update.sh
deploy/              Scripts de Termux
  provision-adb.sh     Aprovisionamiento por USB desde el ordenador
  phone-install.sh     Instalador en el móvil (idempotente)
  phone-service.sh     Servicio runit + arranque con Termux:Boot
  phone-doctor.sh      Diagnóstico de 24/7
  phone-shortcuts.sh   Atajos de Termux:Widget
  phone-config.sh      Token y chats autorizados
  phone-uninstall.sh   Desinstalación (conserva datos)
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
