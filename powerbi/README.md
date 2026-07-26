# Power BI — inicio rápido

1. Ejecuta `docker compose up --build` desde la raíz.
2. Comprueba `http://localhost:8000/health`.
3. Abre `LaLigaAIPredictor/LaLigaAIPredictor.pbip` en Power BI Desktop.
4. Actualiza las credenciales de PostgreSQL cuando Power BI las solicite.
5. Pulsa **Actualizar**.

Parámetros predeterminados:

- PostgreSQL: `localhost:5432`
- Base: `laliga_predictor`
- API: `http://localhost:8000`

La guía completa está en `docs/phase11_powerbi_report.md`.
