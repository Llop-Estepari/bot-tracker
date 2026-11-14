# Changelog

Todas las versiones notables de este proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
La versión es `0.1.<build>`: el último número es un contador que aumenta en
cada publicación.

## [0.1.435467] - 2026-11-14

### Cambios

- Quita la plataforma del texto del aviso; queda en el botón

## [0.1.435466] - 2026-11-14

### Cambios

- Muestra vendedor y valoración, botón con plataforma y limpia widgets

## [0.1.435465] - 2026-11-14

### Cambios

- Actualiza la cabecera del changelog al esquema de build

## [0.1.435464] - 2026-11-14

### Cambios

- Añade /actualizar desde Telegram y versionado por build

## [2.1.2] - 2026-11-14

### Cambios

- Documenta cómo desactivar el bot (niveles 1 y 2)

## [2.1.1] - 2026-11-14

### Cambios

- Reestructura el README con la instalación desde el móvil

## [2.1.0] - 2026-11-13

### Cambios

- Instalación solo desde el móvil, sin ADB

## [2.0.0] - 2026-11-13

### Cambios

- Instalación por USB, servicio runit y guía desde cero

## [1.3.0] - 2026-11-13

### Cambios

- Filtro de distancia en Wallapop y marca de anuncios de fuera de España

## [1.2.4] - 2026-11-13

### Cambios

- Actualización automática con un solo comando y widget de Termux

## [1.2.3] - 2026-11-13

### Cambios

- Mejora la actualización en Termux y muestra los cambios locales

## [1.2.2] - 2026-11-13

### Cambios

- Normaliza la rama main en termux-update.sh

## [1.2.1] - 2026-11-13

### Cambios

- Restaura el modo estricto (activado por defecto)

## [1.2.0] - 2026-11-13

### Cambios

- Elimina zona y modo estricto; añade envío en Wallapop y mejora los mensajes

## [1.1.0] - 2026-11-12

### Cambios

- Simplifica el despliegue: elimina Fly, VPS, proxies y curl_cffi

## [1.0.0] - 2026-11-12

### Añadido

- Alertas de anuncios nuevos de Wallapop y Vinted por Telegram.
- Filtros por palabras clave, precio, zona/radio (Wallapop), categorías,
  marcas y estado (Vinted).
- Modo estricto de palabras clave y listas de palabras excluidas.
- Avisos de bajadas de precio de anuncios ya vistos.
- Comandos `/nuevo`, `/lista`, `/ver`, `/probar`, `/editar`, `/avanzado`,
  `/pausar`, `/reanudar`, `/borrar`, `/estado` y `/ayuda`.
- Deduplicación en SQLite, migraciones automáticas y limpieza de históricos.
- Despliegue en Fly.io (worker con volumen persistente) y en Android/Termux
  con arranque automático y actualizaciones por Git.
- Versionado SemVer, changelog, script de release y CI con control de versión.
