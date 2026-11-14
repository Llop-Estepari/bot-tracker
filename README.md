# Bot tracker de Wallapop y Vinted → Telegram

Bot que vigila búsquedas en **Wallapop** y **Vinted** y te avisa por Telegram
en cuanto aparece un anuncio nuevo que encaja con tus filtros. Se instala y se
ejecuta **íntegramente en un móvil Android** con Termux: ni ordenador, ni
cable, ni servidor.

- Filtros por palabras clave, precio, envío y distancia (Wallapop), marcas,
  categorías y estado (Vinted).
- Palabras excluidas y **modo estricto** para eliminar resultados irrelevantes.
- Cada búsqueda tiene su propio intervalo (60 s – 1 h, por defecto 90 s).
- Deduplicación en SQLite: nunca recibes dos veces el mismo anuncio.
- Aviso de **bajada de precio** cuando un anuncio ya visto se abarata.
- Avisos con foto, precio, ubicación, distancia, país, vendedor y su nota.
- Un único botón para abrir el anuncio en su plataforma.
- Servicio **runit**: si el proceso cae, se levanta solo; arranca con el móvil.
- Todo se gestiona desde el chat: no hay que editar archivos para cambiar
  filtros.

> ⚠️ Ni Wallapop ni Vinted tienen API oficial para esto. El bot usa los
> endpoints internos de sus webs con un ritmo bajo. Pueden cambiar o bloquear
> peticiones en cualquier momento; el código está aislado en `sources/` para
> adaptarlo rápido. Úsalo de forma moderada y respeta sus términos de uso.

## Índice

1. [Instalación rápida en Android](#1-instalación-rápida-en-android)
2. [Uso](#2-uso)
3. [Mantenimiento](#3-mantenimiento)
4. [Cómo funciona](#4-cómo-funciona)
5. [Desarrollo local](#5-desarrollo-local)
6. [Versiones y releases](#6-versiones-y-releases)
7. [Problemas frecuentes](#7-problemas-frecuentes)
8. [Estructura del proyecto](#8-estructura-del-proyecto)
9. [Aviso legal](#9-aviso-legal)

---

## 1. Instalación rápida en Android

La instalación completa se hace desde el propio móvil en unos 5 minutos.

### 1.1 Qué necesitas

En el móvil:

| App | Enlace | Para qué |
| --- | --- | --- |
| F-Droid | https://f-droid.org | Instalar Termux |
| Termux | https://f-droid.org/packages/com.termux/ | Ejecutar el bot |
| Termux:Boot | https://f-droid.org/packages/com.termux.boot/ | Arrancar tras reiniciar |
| Termux:Widget | https://f-droid.org/packages/com.termux.widget/ | Atajos (opcional) |

> Instala siempre Termux desde **F-Droid**, no desde Play Store: la versión de
> Play está descontinuada y no funciona igual.

Además: Telegram, Wi-Fi, el móvil enchufado y Android 7 o superior.

### 1.2 Crear tu bot de Telegram (una vez, 30 s)

1. Abre Telegram y busca **@BotFather**.
2. Envía `/newbot`.
3. Elige un nombre (ej. *Mi tracker*) y un usuario que termine en `bot`
   (ej. `mi_tracker_2026_bot`).
4. Copia el **token** (`123456789:AA...`). No lo compartas.

No hace falta nada más: el instalador valida el token y detecta tu chat
automáticamente cuando pulsas **Start**.

> **¿Puedo compartir un bot entre varios móviles?** No. Un token de Telegram
> solo admite un proceso escuchando a la vez; si dos móviles lo usan, los
> avisos se mezclan. Cada usuario debe crear su bot (30 s) y alojarlo en su
> propio teléfono.

### 1.3 Instalar con una línea

Abre **Termux** y pega:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/install.sh)
```

El instalador:

1. instala `python`, `git`, `curl`, `tmux` y `termux-services`;
2. clona el repositorio público en `~/bot-tracker`;
3. crea el entorno virtual e instala las dependencias;
4. pide el **token enmascarado** y lo valida con Telegram;
5. te muestra `https://t.me/tu_bot`: pulsa **Start** y detecta tu **chat_id**;
6. escribe `.env` con permisos `600`;
7. registra el servicio **runit** y el arranque con Termux:Boot;
8. arranca, comprueba `sv status bot` y verifica la versión en el log.

Al terminar verás tu enlace de bot, la versión instalada, el diagnóstico
disponible y los ajustes de batería que faltan.

**Si no detecta tu chat_id**, envía `/start` al bot y repite la misma línea (es
idempotente), o fíjalo a mano:

```bash
bash ~/bot-tracker/deploy/phone-config.sh --chat-id 123456789 --restart
```

### 1.4 Ajustes obligatorios en HyperOS/MIUI

Sin esto, Xiaomi terminará matando el proceso:

- Ajustes → Aplicaciones → **Termux** → **Batería** → *Sin restricciones*.
- Ajustes → Aplicaciones → **Termux** → **Inicio automático** → activar.
- Recientes → mantén Termux → **candado**.
- Desactiva el ahorro de energía agresivo del sistema.

Abre **Termux:Boot una vez** (su icono) para que registre el arranque
automático. Recomendado: móvil enchufado y, si existe, límite de carga al 80 %.

### 1.5 Comprobar que funciona

En Telegram:

```text
/estado     → versión, uptime y búsquedas
/nuevo      → crear la primera búsqueda
/ubicacion  → origen para el filtro de distancia
```

En Termux:

```bash
sv status bot
bash ~/bot-tracker/deploy/phone-doctor.sh
tail -n 50 ~/bot-tracker/logs/current
```

---

## 2. Uso

### Crear una búsqueda

```text
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
| `/actualizar` | Actualizar el bot desde Telegram (solo administrador) |
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

### Avisos

Cada aviso incluye foto, título, precio, ubicación/distancia, vendedor y
plataforma. El botón abre el anuncio directamente:

```text
[ 🔗 Abrir en Wallapop ]
```

El vendedor se muestra con su nota sobre 5 cuando la plataforma la ofrece:

```text
👤 A3 A. ⭐ 5,0
```

Si no tiene valoraciones, aparece solo el nombre. Para silenciar una búsqueda,
usa `/pausar <id>`.

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

---

## 3. Mantenimiento

### Actualizar

#### Desde Telegram

Si eres el administrador (`ADMIN_CHAT_IDS`), envía:

```text
/actualizar
```

El bot consulta la última versión publicada. Si hay una nueva, muestra un botón
para confirmar y lanza la actualización en un proceso aparte, porque el servicio
se reinicia durante el proceso (unos 20-30 s). Al terminar recibirás un mensaje
con la versión nueva o con el error.

Si el bot no responde, usa el widget o el comando de abajo.

#### Desde Termux

Un toque en el widget **Actualizar bot** (Termux:Widget) o:

```bash
bash ~/bot-tracker/update.sh
```

El script baja el servicio runit, guarda un backup de `.env`, `tracker.db` y
del worktree, actualiza el código, instala dependencias si cambiaron, arranca y
verifica la nueva versión. Si algo falla, vuelve al commit anterior.

### Widgets de Termux

Solo se crean dos atajos:

| Widget | Acción |
| --- | --- |
| **Actualizar bot** | `update.sh` |
| **Estado** | `phone-doctor.sh` |

Se regeneran al instalar y al actualizar. Los atajos antiguos (*Backup*,
*Ver logs*, *Instalar bot*, *Reiniciar bot*) se eliminan automáticamente. Para
limpiarlos a mano:

```bash
rm -f ~/.shortcuts/"Backup" \
      ~/.shortcuts/"Ver logs" \
      ~/.shortcuts/"Instalar bot" \
      ~/.shortcuts/"Reiniciar bot"
```

Si el widget del escritorio no se refresca, quítalo y vuelve a añadirlo
(Widgets → Termux:Widget).

Las acciones que ya no tienen widget siguen disponibles:

```bash
sv restart bot
tail -f ~/bot-tracker/logs/current
cp ~/bot-tracker/tracker.db ~/storage/shared/bot-tracker-$(date +%F).db
```

### Diagnóstico

```bash
bash ~/bot-tracker/deploy/phone-doctor.sh
```

Comprueba servicio, proceso, arranque automático, batería, red, logs y disco.

### Logs

```bash
tail -n 50 ~/bot-tracker/logs/current
tail -f ~/bot-tracker/logs/current     # en vivo
sv status bot
```

Los logs rotan solos: 5 MB por fichero y 3 ficheros.

### Copias de seguridad y cambio de móvil

```bash
termux-setup-storage
cp ~/bot-tracker/tracker.db ~/storage/shared/bot-tracker-$(date +%F).db
```

El `.env` contiene el token: no lo copies al almacenamiento compartido.

Para restaurar en otro móvil, copia el `.db` al teléfono y ejecuta el
instalador indicando la ruta:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/install.sh) \
  --db ~/storage/shared/bot-tracker-2026-11-13.db
```

### Reparar o reinstalar

El instalador es idempotente y nunca borra `.env`, `tracker.db` ni `.venv`:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Llop-Estepari/bot-tracker/main/install.sh)
```

### Desactivar el bot permanentemente

#### Nivel 1 · Pararlo sin desinstalar (reversible)

```bash
sv down bot
touch $PREFIX/var/service/bot/down
tmux kill-session -t bot 2>/dev/null || true
pkill -f '[.]venv/bin/python main.py' 2>/dev/null || true
termux-wake-unlock
```

- `sv down` lo para ahora.
- El fichero `down` impide que runit lo arranque al reiniciar.
- `.env` y `tracker.db` se conservan.

Para volver a activarlo:

```bash
rm -f $PREFIX/var/service/bot/down
sv up bot
```

#### Nivel 2 · Desinstalar del móvil conservando los datos

```bash
bash ~/bot-tracker/deploy/phone-uninstall.sh
```

Elimina el servicio runit, el arranque con Termux:Boot y los atajos del widget,
pero **conserva** `~/bot-tracker` con `.env` y `tracker.db`.

Si además quieres borrar el proyecto (antes guarda un backup de `.env` y
`tracker.db` en `~/bot-tracker-backups`):

```bash
bash ~/bot-tracker/deploy/phone-uninstall.sh --purge
```

Comprueba que no queda nada activo:

```bash
sv status bot
pgrep -af '[.]venv/bin/python main.py'
ls ~/.termux/boot/start-bot.sh 2>/dev/null || echo "sin arranque automático"
```

---

## 4. Cómo funciona

- Un scheduler en segundo plano revisa cada alerta según su intervalo, con un
  pequeño *jitter* y unos segundos de separación entre búsquedas.
- La primera pasada de una alerta **siembra** los anuncios existentes sin
  avisar (salvo que hayas pedido lo contrario), para que no recibas un aluvión
  inicial.
- Cada anuncio se guarda en `seen_items`: si ya se avisó, no se repite.
- Si un anuncio ya visto **baja de precio**, se envía un aviso aparte con el
  precio anterior y el nuevo. Se desactiva por búsqueda con
  `/editar <id> precios off`. Solo se detecta mientras el anuncio siga
  apareciendo en los resultados y cumpla los filtros; las APIs devuelven las
  primeras posiciones ordenadas por novedad.
- Filtros server-side: palabras, precio, envío (Wallapop), distancia
  (Wallapop), categoría, marca y estado.
- Filtros client-side: modo estricto, palabras excluidas, comprobación
  defensiva de precio y de radio (haversine).
- Ante `429` la plataforma se enfría 3 minutos; ante `403` (bloqueo), 15
  minutos. El resto de plataformas siguen funcionando.
- Wallapop se consulta con `httpx` y las cabeceras de su web.
- Vinted exige cookies de sesión: el bot visita la web, las guarda y las
  renueva automáticamente si caducan.
- En el móvil, **runit** supervisa el proceso y **Termux:Boot** lo arranca al
  encender. La base de datos y el token viven solo en `~/bot-tracker`.

---

## 5. Desarrollo local

Esta sección es solo para probar o modificar el bot en un ordenador; no hace
falta para instalarlo en el móvil.

### Requisitos

- Linux (probado con Python 3.14; funciona desde 3.11)
- Un bot de Telegram de [@BotFather](https://t.me/BotFather)

### Puesta en marcha

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

### Autorizarte en desarrollo

El bot es privado: solo responde a los `chat_id` de `ALLOWED_CHAT_IDS`.

1. Con el bot arrancado, escribe `/start` desde tu Telegram.
2. El bot te responderá con **tu chat_id** y te dirá que no tienes acceso.
3. Añádelo al `.env`:

   ```env
   ALLOWED_CHAT_IDS=123456789
   ```

4. Reinicia el bot. Escribe `/ayuda` y ya podrás crear búsquedas.

Puedes autorizar a más personas separando IDs por comas. Si dejas
`ALLOWED_CHAT_IDS` vacío, el bot rechazará a todo el mundo (comportamiento
seguro por defecto). El instalador de Android rellena este campo por ti.

### Administradores

`ADMIN_CHAT_IDS` decide quién puede ejecutar `/actualizar`, que reinicia el
servicio y actualiza el código:

```env
ALLOWED_CHAT_IDS=123456789
ADMIN_CHAT_IDS=123456789
```

- Si `ADMIN_CHAT_IDS` está vacío, se usan los mismos chats que
  `ALLOWED_CHAT_IDS`.
- Puedes tener varios administradores separados por comas.
- El instalador de Android lo rellena con tu chat automáticamente.
- Cámbialo en el móvil con
  `bash ~/bot-tracker/deploy/phone-config.sh --admin-chat-id 123456789`.

### Tests y lint

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

Los tests cubren filtros, parseo de respuestas reales de ambas plataformas,
persistencia y la lógica del scheduler (siembra inicial, deduplicación,
límites de avisos) con fuentes simuladas. No hacen peticiones de red.

---

## 6. Versiones y releases

La versión vive en `version.py` y se muestra en `/estado` y en el log de
arranque. El esquema es:

```text
0.1.<build>
```

- `0.1` es **fijo**: identifica el esquema, no una versión que haya que subir.
- `<build>` es un contador que aumenta en cada publicación: `0.1.435464`,
  `0.1.435465`, `0.1.435466`…
- No hay `major`, `minor` ni `patch`. Cada release es una build nueva.
- El contador se guarda en `BUILD` y `version.py` debe coincidir con él.

### Publicar una build

Haz commit de los cambios y ejecuta:

```bash
python scripts/release.py "Añade el comando /actualizar"
```

El script:

1. actualiza `version.py` y `BUILD`;
2. añade la entrada al `CHANGELOG.md`;
3. ejecuta `ruff` y los tests (si fallan, revierte los cambios de versión);
4. crea el commit `release: v0.1.N`, el tag `v0.1.N` y empuja a GitHub.

`--dry-run` muestra el resultado sin tocar nada y `--no-push` deja el commit y
el tag en local.

### Comprobaciones

```bash
python scripts/check_version.py            # esquema, BUILD, fecha y changelog
python scripts/check_version.py v0.1.42    # además, que el tag coincida
```

La CI (`.github/workflows/ci.yml`):

- comprueba `bash -n` de todos los scripts;
- ejecuta `ruff` y `pytest` en cada push/PR;
- falla si un cambio no modifica `version.py`;
- en tags `v*`, verifica que el tag coincide con `version.py` y `BUILD`.

No se crean GitHub Releases: el historial vive en `CHANGELOG.md` y en los tags.
Los tags antiguos (`v2.x`) se conservan; las builds nuevas usan `v0.1.N`.

---

## 7. Problemas frecuentes

### Instalación

**El token no es válido**
Cópialo entero desde @BotFather (`/mybots` → tu bot → API Token). Debe tener el
formato `123456789:AA...`. El instalador no continúa sin un token válido.

**No detecta mi chat_id**
Abre `https://t.me/tu_bot`, pulsa **Start** y repite el instalador. También
puedes fijarlo con `phone-config.sh --chat-id`.

**`sv status bot` dice `down`**

```bash
tail -n 50 ~/bot-tracker/logs/current
```

Suele ser un token vacío o dependencias sin instalar; vuelve a ejecutar el
instalador.

### Funcionamiento

**El bot deja de responder por la noche**
Revisa los ajustes de batería de la sección 1.4 y ejecuta `phone-doctor.sh`.

**Wallapop responde 403 (Request blocked)**
El WAF de CloudFront ha bloqueado la IP temporalmente. El bot enfriará esa
plataforma 15 minutos. Desde una IP residencial/móvil no suele ocurrir.

**Vinted responde 401/403**
El bot renueva las cookies solo. Desde una IP residencial/móvil no suele
ocurrir. Si persiste, puede que Vinted haya cambiado el endpoint
(`/svc-catalogue/items`): revisa `sources/vinted.py`.

**No llegan avisos**
Comprueba `/estado` (¿la alerta está activa? ¿hay plataformas enfriando?),
lanza `/probar <id>` y revisa `tail -f ~/bot-tracker/logs/current`.

**La actualización no se aplica**
Revisa `~/bot-tracker/update.log`. El script descarta los cambios locales con
backup y hace rollback si falla; con runit baja el servicio antes de actualizar,
así que no hay que parar nada a mano. El comando `/actualizar` escribe además su
resultado en `~/bot-tracker/update-status`.

**`/actualizar` dice que no hay permiso**
Tu chat no está en `ADMIN_CHAT_IDS`. Añádelo:

```bash
bash ~/bot-tracker/deploy/phone-config.sh --admin-chat-id TU_ID --restart
```

**Cambiar de país en Vinted**
Ajusta en `.env`:

```env
VINTED_BASE_URL=https://www.vinted.fr
VINTED_LOCALE=fr-FR
```

Wallapop no permite filtrar por país: usa su feed por defecto. Los anuncios de
fuera de España aparecen marcados en el aviso (`🇵🇹 Portugal · fuera de
España`), y puedes acotar la zona con `/ubicacion` + `/editar <id> distancia`.

---

## 8. Estructura del proyecto

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
updates.py           Comprobación de la última versión publicada
install.sh           Instalador de una línea (desde el móvil)
update.sh            Lanzador corto: bash ~/bot-tracker/update.sh
deploy/              Scripts de Termux
  phone-install.sh     Compatibilidad: llama a install.sh
  phone-service.sh     Servicio runit + arranque con Termux:Boot
  phone-doctor.sh      Diagnóstico de 24/7
  phone-shortcuts.sh   Atajos de Termux:Widget
  phone-config.sh      Token y chats autorizados
  phone-uninstall.sh   Desinstalación (conserva datos)
  self-update.sh       Actualización lanzada desde /actualizar
  termux-update.sh     Actualización (lo usa update.sh)
scripts/             Release, control de versión y verificación de fuentes
tests/               Tests + fixtures reales de las APIs
version.py           Versión de la aplicación (0.1.N)
BUILD                Contador de build
CHANGELOG.md         Historial de versiones
.github/workflows/   CI (tests, lint y control de versión)
```

---

## 9. Aviso legal

Este proyecto es de uso personal y no está afiliado a Wallapop ni a Vinted.
Automatizar el acceso puede ir contra sus términos de servicio. El bot está
diseñado para hacer un número muy bajo de peticiones (una búsqueda cada 1–2
minutos), pero la responsabilidad del uso es de quien lo despliega.
