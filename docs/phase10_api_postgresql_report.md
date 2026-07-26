# Fase 10 — API FastAPI y PostgreSQL

## Objetivo

Convertir el flujo dinámico de la Fase 9 en un servicio consumible por un
dashboard o una aplicación web. La API no modifica la metodología de modelado:
continúa usando solo información disponible antes del partido, mantiene
congelados los clasificadores entrenados hasta 2025/26 y reentrena Poisson
únicamente cuando se incorporan resultados de 2026/27.

## Arquitectura

1. **Fase 9** genera resultados normalizados, probabilidades y simulaciones.
2. **Servicio de sincronización** carga el estado validado en una transacción.
3. **PostgreSQL** conserva calendario, resultados, cuotas, pronósticos, tabla,
   simulación, distribución de posiciones e historial de actualizaciones.
4. **FastAPI** expone consultas y una operación controlada de actualización.

La base se sincroniza al arrancar. Si una carga falla, no se confirma la
transacción ni se reemplazan las plantillas canónicas de entrada.

Los modelos serializados fueron entrenados con scikit-learn 1.8. La dependencia
queda limitada a `>=1.8,<1.9` para impedir cargas incompatibles en producción.

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health` | Estado de API, base y última ejecución |
| GET | `/fixtures` | Calendario; filtros por jornada, estado o equipo |
| GET | `/predictions` | Probabilidades 1X2 y marcador; filtros por jornada, equipo o modelo |
| GET | `/standings` | Tabla actual |
| GET | `/simulation` | Probabilidades de campeón, Top 4, Top 7 y descenso |
| GET | `/updates/latest` | Metadatos de la última actualización |
| POST | `/update-matchday` | Incorporar resultados/cuotas y ejecutar la Fase 9 |

Swagger está disponible en `/docs` y OpenAPI en `/openapi.json`.

## Reglas de actualización

- Por defecto, una jornada debe contener sus 10 resultados.
- `allow_partial=true` habilita una actualización parcial explícita.
- Un resultado confirmado no se sobrescribe silenciosamente.
- Las cuotas conservan el sello `captured_at`; para predecir se usa la captura
  más reciente de cada partido.
- Las cuotas incompletas no activan el ensemble de mercado.
- Cada ejecución produce un `update_id`, snapshot y control de calidad.
- Las probabilidades 1X2 deben sumar 1 y las zonas de Monte Carlo deben
  conciliar exactamente.

## Ejecución recomendada

```powershell
docker compose up --build
```

Luego abrir:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Salud: `http://localhost:8000/health`

También se puede ejecutar localmente:

```powershell
.venv\Scripts\python.exe scripts\serve_api.py
```

En ese caso PostgreSQL debe estar disponible y
`LALIGA_DATABASE_URL` debe apuntar a la instancia correcta.
