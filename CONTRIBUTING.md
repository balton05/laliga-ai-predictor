# Contribuir

## Preparación

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
```

## Antes de enviar cambios

Desde la raíz:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\verify_release.py --offline
cd frontend
npm run build
```

Mantén estas reglas:

- No uses resultados futuros en variables prepartido.
- No sobrescribas capturas históricas ni versiones de modelos.
- No confirmes `.env`, claves, contraseñas, bases locales o copias de
  seguridad.
- Añade pruebas para cualquier cambio de API, datos o reglas de promoción.
- Documenta cambios que alteren contratos, métricas o despliegue.
