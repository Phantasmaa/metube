# MeTube — plan de rediseño premium

## Alcance
Solo el indicador de plataformas se implementa ahora. Este documento no autoriza ejecutar el rediseño. No cambiar el motor, autenticación, permisos ni configuración de descarga.

## Dirección visual
Un único modo claro premium: fondo #F6F7F9, tarjetas blancas, texto #17202A, acento índigo #5146E5. Inspiración en sobriedad Apple y dashboards SaaS, sin copiar marcas. Tipografía de sistema, espaciado de 8 px, bordes suaves, sombras discretas. Sin neón, degradados masivos ni apariencia de panel técnico.

## Jerarquía
1. Cabecera compacta: identidad, conexión y ajustes.
2. Tarjeta principal: pegar enlace, selector Video/Audio, calidad y CTA Descargar.
3. Estado de sitios: verificado/bloqueado/no probado, fecha y explicación; nunca fingir monitorización en vivo.
4. Cola activa: miniatura si existe, título, origen, progreso, velocidad, tiempo restante y cancelar.
5. Historial: terminadas/fallidas; descargar archivo, reintentar y detalles del error.
6. Opciones avanzadas colapsadas manteniendo todas las funciones existentes.

## Móvil y accesibilidad
Sin desplazamiento horizontal a 360 px. Controles táctiles de al menos 44 px. Etiquetas visibles, estados no expresados solo con color, foco de teclado y contraste WCAG AA. Respetar movimiento reducido. No ocultar errores ni presentar fallos como éxitos.

## Implementación propuesta
1. Inventariar componentes y pruebas existentes; respaldar fuentes y dist.
2. Definir tokens y reorganizar la plantilla Angular existente, sin migrar framework.
3. Refinar formularios, cola, historial y estados vacíos/carga/error.
4. Integrar indicadores manuales fechados y mensajes claros de YouTube sin cookies.
5. Construir y ejecutar suite backend; lint y pruebas frontend disponibles.
6. Verificar en navegador autenticado público: móvil y escritorio, nueva descarga autorizada, progreso, archivo, fallo y reintento.
7. Desplegar solo MeTube, verificar assets públicos y mantener rollback del build previo.

## Criterios de aceptación
Descargas y SSO sin regresiones. TikTok/Instagram/X etiquetados como muestras verificadas, no garantías universales. YouTube marcado bloqueado mientras no exista nueva evidencia. Ningún estado de compatibilidad se presenta como automático. Capturas reales móvil/escritorio antes de aprobar. No añadir compras, servicios de pago, cookies ni cambios de otras apps.
