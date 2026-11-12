# Changelog

Todas las versiones notables de este proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el versionado [SemVer](https://semver.org/lang/es/).

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
