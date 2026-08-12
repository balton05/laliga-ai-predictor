# Fase 17: publicación y despliegue gratuito

## Arquitectura elegida

La aplicación pública utiliza una sola URL y mantiene `/api` en el mismo
origen:

| Componente | Servicio | Plan |
|---|---|---|
| Angular + FastAPI | Render Web Service con `Dockerfile.render` | Free |
| PostgreSQL | Neon | Free |
| CI y actualización de temporada | GitHub Actions | Repositorio público |
| URL | `laliga-ai-predictor-josue.onrender.com` | Subdominio gratuito |

El frontend y FastAPI se empaquetan en una sola imagen. Esto evita CORS,
conserva la política CSP estricta y permite que Angular siga consumiendo
`/api`. PostgreSQL es externo porque el disco de un servicio gratuito de
Render es efímero.

## 1. Publicar el repositorio

El repositorio debe llamarse `laliga-ai-predictor` y ser público. Antes de
publicarlo:

```powershell
cd "D:\Josue\DATASETS\laliga-ai-predictor"

git status
git check-ignore .env
git ls-files .env
```

El segundo comando debe devolver `.env`; el tercero no debe devolver nada.

Después crea el repositorio vacío en GitHub y ejecuta:

```powershell
git branch -M main
git remote add origin https://github.com/TU_USUARIO/laliga-ai-predictor.git
git push -u origin main
```

No añadas README, licencia ni `.gitignore` desde GitHub al crear el
repositorio, porque el proyecto ya los contiene.

## 2. Crear PostgreSQL en Neon

1. Crea una cuenta y un proyecto gratuito en Neon.
2. Conserva la región recomendada por Neon o la más cercana disponible.
3. Copia la cadena de conexión con SSL.
4. Cambia únicamente el prefijo:

```text
postgresql://...
```

por:

```text
postgresql+psycopg://...
```

El resto de la cadena, incluido `sslmode=require`, debe mantenerse. Esta
cadena es el secreto `LALIGA_DATABASE_URL`; nunca se guarda en Git.

## 3. Desplegar en Render

1. En Render elige **New > Blueprint**.
2. Conecta el repositorio público `laliga-ai-predictor`.
3. Render detectará `render.yaml`.
4. Cuando solicite `LALIGA_DATABASE_URL`, pega la cadena preparada de Neon.
5. Confirma el Blueprint y espera el primer despliegue.

El servicio inicializa las tablas y los 380 partidos solo si la base está
vacía. En redeploys posteriores conserva resultados, predicciones,
evaluaciones y versiones de modelos.

La URL prevista es:

```text
https://laliga-ai-predictor-josue.onrender.com
```

Si Render exige otro nombre porque ese subdominio ya existe, cambia el campo
`name` y la URL de `LALIGA_CORS_ORIGINS` en `render.yaml`, confirma el cambio
en Git y vuelve a sincronizar el Blueprint.

## 4. Configurar la automatización

En Render abre el servicio, entra en **Environment** y copia el valor generado
para `LALIGA_ADMIN_API_KEY`.

En GitHub abre:

```text
Settings > Secrets and variables > Actions > New repository secret
```

Crea exactamente estos dos secretos:

| Nombre | Valor |
|---|---|
| `LALIGA_DATABASE_URL` | La cadena de conexión de Neon |
| `LALIGA_ADMIN_API_KEY` | La clave administrativa generada por Render |

Después abre **Actions > season automation > Run workflow**. La primera
ejecución manual debe terminar en verde. El flujo también se ejecuta
automáticamente a las `08:17` y `23:17`, zona `America/Lima`.

## 5. Verificación final

Desde PowerShell:

```powershell
cd "D:\Josue\DATASETS\laliga-ai-predictor"

.venv\Scripts\python.exe scripts\verify_phase17.py `
  --base-url "https://laliga-ai-predictor-josue.onrender.com"
```

El resultado correcto es `status: passed`, sin controles fallidos.

También comprueba:

- La portada y `/rendimiento` conservan sus estilos.
- `/api/health` devuelve `status: ok` y `database: connected`.
- El favicon aparece.
- GitHub Actions muestra `quality` y `season automation` en verde.
- Render muestra el despliegue como `Live`.

## Límites del plan gratuito

- Render suspende el servicio web después de un periodo sin tráfico; la
  primera visita puede tardar alrededor de un minuto.
- El sistema no depende del disco de Render para el estado histórico. Neon
  conserva la base y el modelo activo se restaura desde ella al arrancar.
- Los workflows programados de repositorios públicos pueden desactivarse tras
  60 días sin actividad en el repositorio. GitHub permite reactivarlos desde
  la pestaña Actions.
- Si la base supera el almacenamiento gratuito de Neon o el proyecto requiere
  disponibilidad continua, el siguiente paso será migrar a un plan de pago.
