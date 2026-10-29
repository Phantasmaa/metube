# Verificación independiente durante implementación

Consulta real sin cookies: scsearch3:Rick Astley Never Gonna Give You Up.
La búsqueda devolvió 3 resultados con título, uploader, duración y webpage_url, incluidos dos de rick-astley-official y un cover.
Extracción real del primer resultado https://soundcloud.com/rick-astley-official/never-gonna-give-you-up: falló con `This video is DRM protected`.

Consecuencia: aparecer en búsqueda NO garantiza descarga ni audio completo. UI debe indicar candidatos no verificados, respetar DRM y reportar fallo sin intentar eludirlo. No presentar 3 resultados como 3 descargas disponibles. La selección por el usuario tampoco autoriza eludir DRM. No se modificó código en esta verificación.
