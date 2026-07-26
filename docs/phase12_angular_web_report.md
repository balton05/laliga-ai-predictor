# Fase 12 — Aplicación web Angular

## Objetivo

Convertir los servicios de FastAPI y PostgreSQL en una experiencia web clara,
responsive y lista para portafolio. La aplicación no cambia las probabilidades:
consume los contratos operativos de la Fase 10 y representa la fotografía
validada de la Fase 11.

## Módulos

- **Resumen:** partido destacado, KPIs y metodología del ensemble.
- **Pronósticos:** probabilidades 1X2, marcador, xG, confianza y filtros.
- **Calendario:** las 38 jornadas y los 380 encuentros.
- **Clasificación:** tabla actual y proyección de posición/puntos.
- **Simulación:** campeón, Top 4, Top 7, descenso e intervalos P05–P95.

## Integración

La aplicación intenta conectarse a `http://localhost:8000`. Si la API no está
disponible, utiliza una fotografía estática generada desde los CSV validados.
La interfaz siempre indica si está mostrando **API en línea** o **Datos de
pretemporada**.

FastAPI habilita CORS únicamente para los orígenes declarados en
`LALIGA_CORS_ORIGINS`. En desarrollo, el valor predeterminado permite
`localhost:4200`.

## Ejecución

La ruta recomendada levanta PostgreSQL, FastAPI y Angular:

```powershell
docker compose up --build
```

Después se abre:

- Aplicación: `http://localhost:4200`
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

También puede ejecutarse Angular por separado:

```powershell
cd frontend
npm install
npm start
```

## Decisiones visuales

La interfaz conserva el sistema de la Fase 11: fondo azul noche, superficies
azul pizarra, celeste para probabilidades deportivas, amarillo para empates y
rojo para descenso. La tipografía, el espaciado y los estados responsive se
adaptaron a navegación web, teclado y pantallas táctiles.

## Alcance de la predicción

Las cifras son estimaciones de pretemporada. Los resultados y cuotas reales
deben incorporarse mediante el flujo de actualización de las Fases 9–10 para
que la aplicación muestre el estado vigente de la competición.
