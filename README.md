# ⚽ WC2026 Football Intelligence Pipeline

> Pipeline de inteligencia táctica para el Mundial 2026 — arquitectura medallón completa con ingesta diaria, transformaciones dbt, modelo predictivo Random Forest, API REST y dashboard interactivo con simulador de bracket.

---

## 🎯 ¿Por qué existe este proyecto?

En junio de 2026, con el Mundial ya en marcha, había una pregunta concreta que no podía responder con ninguna herramienta disponible:

> **¿Cuánto mejora realmente la predicción si usas xG de StatsBomb en vez de confiar en las probabilidades de Onside Arena?**

La respuesta requería cruzar datos de tres fuentes completamente distintas — eventos con xG de Qatar 2022 y Copa América 2024, probabilidades Monte Carlo de Onside Arena para WC2026 y los resultados en vivo de worldcup26.ir — de una forma que ningún dashboard comercial permitía hacer.

Así nació este lakehouse: no como un ejercicio académico, sino como una herramienta real para responder esa pregunta y mantener el análisis actualizado cada día mientras durase el torneo.

**Lo que descubrimos:**
- El modelo Random Forest entrenado sobre xG de StatsBomb alcanzó **58% de accuracy en CV** contra un baseline de Onside Arena del **47.6%** — +10 puntos porcentuales
- Onside predijo un 10% de probabilidad de empate en España–Cabo Verde; nuestro modelo dijo 19%. El partido terminó 0–0
- El λ global histórico del Mundial es **1.30 goles/equipo/partido** (no 1.5 como se suele citar en medios)
- La jornada 1 del WC2026 tuvo **37.5% de empates** — casi el doble de la media histórica (22%)

---

## 🏗️ Arquitectura

```
worldcup26.ir ─────┐
StatsBombPy ────────┤                                                         gold.dim_teams
Onside Arena ───────┼──► Airflow DAGs ──► MinIO (Bronze/Parquet) ──► Neon ── gold.fact_matches
Rising Transfers ───┤       ↓                                                 gold.mart_*
Kaggle CSV ─────────┘   dbt run/test                                              │
                                                                    ┌─────────────┴───────────────┐
                                                               FastAPI                      Streamlit
                                                         /matches · /predict            5 páginas:
                                                         /standings · /team             Standings · Predicciones
                                                                                        Bracket · Analytics · Modelo
```

| Capa | Tecnología | Por qué esta elección |
|------|-----------|----------------------|
| 🥉 Bronze | MinIO + Parquet | Simula un data lake real; el particionado por fecha permite re-ingestas incrementales sin tocar datos históricos |
| 🥈 Silver | dbt views en Neon | Vistas (no tablas) porque los cambios de esquema de la fuente se propagan automáticamente; tests en esta capa atrapan problemas de la fuente antes de que lleguen al Gold |
| 🥇 Gold | dbt tables en Neon | Tablas materializadas para que FastAPI y Streamlit respondan en < 100ms sin recalcular cada vez |

---

## 🛠️ Stack y decisiones técnicas clave

| Área | Herramientas | Por qué |
|------|-------------|---------|
| **Orquestación** | Apache Airflow (LocalExecutor) | DAGs como código, reintentos automáticos, log de cada run. LocalExecutor es suficiente para un torneo de 8 semanas |
| **Almacenamiento** | MinIO + [Neon PostgreSQL](https://neon.tech) | MinIO en Docker para Bronze sin costos; Neon para Silver/Gold porque ofrece PostgreSQL serverless con branch por PR y SSL nativo |
| **Transformación** | [dbt-core 1.8](https://www.getdbt.com/) | SQL con linaje, tests declarativos y documentación automática. 20 modelos, 20 tests, 0 queries ad-hoc en el pipeline |
| **Ingesta HTTP** | `subprocess` + curl de Git for Windows | worldcup26.ir hace TLS renegotiation post-handshake que OpenSSL 3.x bloquea. `requests`, `httpx` y cualquier wrapper Python son inútiles aquí. Schannel (Windows) + curl de Git resuelve el problema |
| **API REST** | FastAPI + SQLAlchemy | Endpoints asíncronos sobre el Gold layer; Swagger docs automáticos; dependency injection para el pool de conexiones |
| **ML** | scikit-learn Random Forest | Interpretable, robusto con datasets pequeños (226 partidos), feature importances directas. No tiene sentido usar redes neuronales con estos volúmenes |
| **Simulación** | NumPy — distribución de Poisson | La distribución de Poisson modela llegada de goles por construcción matemática. 10,000 simulaciones dan intervalos estables en < 1 segundo |
| **Dashboard** | Streamlit + Plotly | Looker Studio no puede ejecutar Python en tiempo real — el simulador de bracket necesita recalcular probabilidades Poisson mientras el usuario elige equipos. Streamlit sí |
| **Tests** | pytest — 39/39 | DB y HTTP completamente mockeados; CI corre en segundos sin credenciales reales |
| **CI/CD** | GitHub Actions | ruff + pytest + `dbt parse` en cada push. El dbt parse valida los 20 modelos sin conectarse a Neon |
| **Empaquetado** | [uv](https://github.com/astral-sh/uv) | 10–100x más rápido que pip; lock file reproducible; extras para notebooks y dashboard sin instalar todo en producción |

---

## 📡 Fuentes de datos — y por qué cada una

### worldcup26.ir — resultados en vivo
La opción obvia era API-Football. Pero el plan gratuito no cubre el WC2026 en vivo — solo datos históricos. worldcup26.ir proporciona resultados, fixtures y standings del torneo en tiempo real, de forma gratuita y sin límite de llamadas.

**Problema encontrado:** La API devuelve `finished: TRUE` incluso para partidos futuros pre-rellenos con 0-0. También hace TLS renegotiation que Python no tolera (ver sección de gotchas). Ambos problemas están resueltos en `ingestion/worldcup26_client.py`.

### StatsBomb Open Data — xG histórico
StatsBomb es la única fuente gratuita que proporciona **Expected Goals a nivel de evento** para torneos FIFA. Descargamos WC2022 (completo), Copa América 2024 y Euro 2020/2024: 34 de los 48 equipos del WC2026 tienen cobertura xG directa con StatsBomb. Sin estos datos, el modelo Poisson tendría que caer al fallback de goles históricos para la mayoría de los equipos.

**Problema encontrado:** StatsBombPy >= 1.0 expande los dicts anidados en columnas planas. El modelo `stg_matches_sb.sql` no puede hacer `cast(home_team::jsonb ->> 'name')` — `home_team` ya es un string. Este error es silencioso y produce resultados incorrectos si no se conoce.

### Onside Arena — predicciones Monte Carlo como baseline
No construimos el modelo en el vacío — necesitábamos un benchmark real. Onside Arena publica predicciones Monte Carlo (10,000 simulaciones) para cada partido del WC2026 bajo licencia CC BY 4.0. Sirve como gold standard: si nuestro modelo no lo supera, no aporta nada.

### Rising Transfers — planteles y métricas per-90
1,363 jugadores de los 48 equipos con métricas per-90 de la temporada 2025-26. Es la única fuente que conecta jugadores actuales (no el plantel de Qatar 2022) con métricas de rendimiento reciente. Alimenta `mart_player_scouting`.

### Kaggle — historia 1930–2022
Necesitábamos el λ global histórico del Mundial para calibrar el modelo Poisson. La fórmula `λ_home = xG_ataque × (GA_defensa_visitante / λ_global)` requiere ese parámetro. Lo calculamos en [el notebook 02](notebooks/02_wc_history.ipynb): **1.30 goles/equipo/partido**.

---

## 🔄 Modelos dbt — 20/20 · todos pasan

### Por qué dbt y no SQL directo
Con cinco fuentes distintas que tienen esquemas distintos, necesitábamos una forma de documentar cómo se transforman los datos, detectar cuando una fuente cambia de formato y asegurarnos de que los marts de Gold no mezclen datos incorrectamente. dbt da linaje visual, tests declarativos y un DAG de dependencias que Airflow puede ejecutar en orden.


<details>
<summary><strong>Silver — 12 staging views</strong></summary>

| Modelo | Fuente | Decisión destacada |
|--------|--------|-------------------|
| `stg_matches_wc2026` | worldcup26.ir | Cast `::numeric::int` (Parquet serializa int con nulls como float "1.0"); incluye partidos `Scheduled` no solo `Match Finished` |
| `stg_matches_sb` | StatsBomb | Sin casts `::jsonb` — columnas planas desde StatsBombPy >= 1.0 |
| `stg_events_sb` | StatsBomb | Eventos granulares: tiros, pases, presiones, porteos |
| `stg_player_stats_sb` | StatsBomb | Stats por jugador agregadas desde eventos |
| `stg_player_stats_wc2026` | WC2026 | Schema correcto con cero filas (`WHERE FALSE`) — worldcup26.ir no expone player stats |
| `stg_wc_history` | Kaggle | 904 partidos 1930–2022 para λ global y análisis de tendencias |
| `stg_wc_goalscorers` | Kaggle | Goleadores históricos por torneo |
| `stg_wc_shootouts` | Kaggle | Tandas de penales históricas |
| `stg_wc2026_squads` | Rising Transfers | 1,363 jugadores + posición, edad, valor de mercado |
| `stg_wc2026_per90` | Rising Transfers | Métricas per-90 temporada 2025-26 |
| `stg_onside_predictions` | Onside Arena | % local/empate/visitante por partido |
| `stg_onside_champions` | Onside Arena | % campeón por equipo (columna `team_name`, no `team`) |

</details>

<details>
<summary><strong>Gold — 8 mart tables</strong></summary>

| Modelo | Qué contiene | Por qué existe |
|--------|-------------|---------------|
| `dim_teams` | 48 equipos con IDs de todas las fuentes, código FIFA y confederación | Punto único de resolución de nombres; evita que cada mart repita el mapeo |
| `dim_players` | Jugadores con IDs cruzados | Futura extensión para scouting detallado |
| `fact_matches` | Tabla de hechos unificada — WC2026 + StatsBomb (284 filas: jugados + programados) | JOINs por nombre para WC2026, por ID para StatsBomb |
| `mart_performance` | Forma reciente, goles, xG y GA por equipo/competición | Alimenta directamente el modelo Poisson y la página Analytics |
| `mart_xg_compare` | xG promedio por competición — WC2022 → Copa → Euro → WC2026 | Permite ver si el nivel de juego del WC2026 es comparable al histórico |
| `mart_predictions` | Predicciones Onside vs resultados reales | Mide accuracy del baseline de referencia partido a partido |
| `mart_champion_odds` | Probabilidades de campeón con `confederation` y `team_canonical` | `confederation` ya viene integrada — no requiere JOIN adicional |
| `mart_player_scouting` | Métricas per-90 combinadas StatsBomb + Rising Transfers | Cruza rendimiento en torneos pasados con datos de forma actual |

</details>


---

## ✈️ Airflow — tres DAGs en producción

```
dag_ingest_wc2026   ──── diario 06:00 UTC ───► fetch worldcup26.ir (ayer + 14 días ahead)
                                              ──► bronze_to_neon (api_fixtures)
                                              ──► trigger dag_dbt_transform
                                                         │
dag_dbt_transform   ◄───────────────────────────────────┘
                         staging → test → marts
                         (se dispara también desde Airflow UI manualmente)

dag_retrain_model   ──── lunes 07:00 UTC ────► build_features desde Gold
                                              ──► train Random Forest
                                              ──► verificar artefacto pkl
```

**Por qué `--days-ahead 14` en el DAG de ingesta:** worldcup26.ir devuelve todos los partidos en una sola llamada (`/get/games`), filtrados por fecha en el cliente. Las fechas futuras tienen scores pre-rellenos con 0-0 y `status=Match Finished` (bug documentado de la API). El cliente corrige esto: para cualquier fecha > hoy, fuerza `goals_home = NULL`, `goals_away = NULL`, `status = Scheduled`. Así el Gold layer siempre tiene el calendario completo con scores reales solo donde corresponde.

---

## 🌐 FastAPI — 5 endpoints sobre el Gold layer

```bash
uvicorn api.main:app --reload   # http://localhost:8000/docs
```

| Endpoint | Descripción |
|----------|-------------|
| `GET /health` | Health check |
| `GET /matches` | Partidos WC2026 con filtros: `?group=Group+A&date=2026-06-20&status=finished` |
| `GET /matches/standings` | Tabla de posiciones por grupo calculada on-the-fly desde `fact_matches` |
| `GET /team/{code}/stats` | Stats de un equipo — acepta nombre o código FIFA (`ESP`, `BRA`…) |
| `GET /team` | Resumen de todos los equipos |
| `POST /predict/winner` | Simulación Monte Carlo Poisson — 10,000 runs por defecto |

**Por qué FastAPI y no Flask:** El endpoint `/predict/winner` corre 10,000 simulaciones NumPy. En Flask bloqueaba el thread; con FastAPI + Starlette se sirve de forma asíncrona sin bloquear otros requests. Además, los Swagger docs automáticos son invaluables para el Streamlit que consume la API.

```bash
# Ejemplo de predicción
curl -X POST http://localhost:8000/predict/winner \
     -H "Content-Type: application/json" \
     -d '{"home": "Argentina", "away": "France"}'
```

```json
{
  "home": "Argentina",  "away": "France",
  "lambda_home": 2.636, "lambda_away": 1.879,
  "home_win_pct": 54.5, "draw_pct": 18.0, "away_win_pct": 27.5,
  "simulations": 10000
}
```

---

## 🤖 Modelo ML — Random Forest

Clasificador de 3 clases (`home_win` · `draw` · `away_win`) entrenado sobre partidos con cobertura StatsBomb:

| Métrica | Valor |
|---------|-------|
| **CV accuracy (5-fold)** | **58.0% ± 3.7%** |
| Baseline Onside Arena | 47.6% |
| Mejora sobre baseline | **+10.4 pp** |
| Dataset de entrenamiento | 226 partidos (StatsBomb + WC2026 completados) |
| Features | 16 (xG, goles, puntos/partido, wins/draws/losses, diferencia goles) |

**Por qué Random Forest y no XGBoost o una red neuronal:** 226 partidos es un dataset pequeño. Random Forest con 5-fold CV da estimaciones de accuracy estables; XGBoost sobreajustaría; una red neuronal no convergería de forma fiable. La interpretabilidad también importa — los feature importances explican qué está usando el modelo.

**Features más importantes** (en orden de `feature_importances_`):
1. `win_rate_diff` — diferencia de tasa de victorias entre ambos equipos
2. `home_attack` — xG ofensivo promedio del local (StatsBomb)
3. `home_pts_per_match` — puntos por partido del local en torneos recientes
4. `attack_diff` — diferencia de xG promedio entre equipos

```bash
python -m ml.train      # entrena y guarda models/model_winner_predictor.pkl
python -m ml.evaluate   # evaluación con breakdown por competición y confianza
```

El artefacto `model_winner_predictor.pkl` se reemplaza semanalmente por `dag_retrain_model`. A medida que el WC2026 genera más partidos, el modelo se recalibra automáticamente.

---

## 🎲 Modelo Monte Carlo — distribución de Poisson + xG

Cada partido se simula con distribuciones de Poisson independientes para local y visitante:

```
λ_home = xG_ataque_local  × (GA_defensa_visitante / λ_global)
λ_away = xG_ataque_visita × (GA_defensa_local     / media_global)

λ_global = 1.30 goles/equipo/partido  ← calculado desde Kaggle 1930–2022
```

**Por qué Poisson y no un modelo de regresión directo:** La distribución de Poisson modela procesos de llegada de eventos independientes en el tiempo — exactamente lo que es un gol. La probabilidad de empate emerge matemáticamente cuando `λ_home ≈ λ_away`: no hay que estimarla por separado. Esto es fidelidad al proceso generador real.

Con 10,000 simulaciones, los intervalos de confianza son estables (varianza < 0.5%) y el cálculo tarda < 1 segundo.

**Cobertura para los 48 equipos:**

| Capa | Equipos | Fuente de λ |
|------|---------|-------------|
| Capa 1 | ~34 equipos | xG promedio StatsBomb (WC2022 + Copa América + Euro) |
| Capa 2 | ~4 equipos | Media de goles en Mundiales recientes (Kaggle) |
| Fallback | ~10 equipos | λ_global = 1.30 |

---

## 📊 Dashboard Streamlit — 5 páginas

```bash
uv run streamlit run streamlit_app/app.py   # http://localhost:8501
```

**Por qué Streamlit y no Looker Studio:** Looker Studio conecta a datos estáticos y genera gráficas fijas. El simulador de bracket necesita recalcular probabilidades Poisson en tiempo real mientras el usuario decide qué equipo pasa de ronda — eso requiere Python ejecutándose en el servidor. Streamlit es exactamente eso: un servidor Python con UI reactiva.

### Home — KPIs en vivo
Métricas del torneo actualizadas desde Gold: partidos jugados, pendientes, goles totales y media goles/partido. Últimos 8 resultados + próximos 8 partidos (con "TBD" para cruces de eliminatorias cuyo cuadro no está definido aún).

### 📊 Standings — tabla de posiciones
12 grupos en vivo. Semáforo de clasificación: 🟢 clasificado (top 2) · 🟡 posible mejor tercero · 🔴 eliminado. El umbral de puntos para "mejor tercero" se calcula comparando los 12 terceros entre sí en tiempo real — no es un número fijo.


### 🔮 Predicciones — próximos partidos con probabilidades
Lista de partidos pendientes (solo aquellos con equipos conocidos — el modelo no puede predecir "TBD vs TBD") con barras de probabilidad calculadas en vivo via `POST /predict/winner`. Tabla compacta con % L / % E / % V / Favorito. Los partidos jugados muestran resultado real vs predicción del modelo.

### 🏆 Bracket — simulador interactivo
Dos tabs:

**Fase de grupos:** Muestra todos los partidos del grupo con resultado real (✅) para los jugados y `st.number_input` para simular scores en los pendientes. Las tablas de posición se recalculan en vivo combinando resultados reales + simulados via `st.session_state.sim_scores`.

**Bracket eliminatorio:** Los 32 cruces del R32 según la tabla oficial FIFA (ganador grupo A vs 2° grupo B, etc.), más los 8 mejores terceros. Para cada cruce, barras de probabilidad Poisson + radio button para elegir el ganador. El bracket se propaga automáticamente: R32 → R16 → Cuartos → Semis → Final → Campeón.

### 📈 Analytics — análisis táctico
- **xG por equipo:** Scatter 4-cuadrantes ataque (xG/partido) vs defensa (GA/partido). Cuadrante inferior-derecho = equipos elite. Fallback a goles reales cuando StatsBomb no cubre al equipo.
- **Favoritos al título:** Barras horizontales con las 32 probabilidades de campeón de Onside Arena. Coloreadas por confederación.
- **Distribución de resultados:** Donut chart local/empate/visitante en WC2026 vs media histórica desde Kaggle.

### 🤖 Modelo — comparativa de accuracy
CV accuracy 58% (RF) vs accuracy real de Onside Arena calculado desde `mart_predictions`. Tabla partido a partido con predicción Onside y resultado real. Feature importances del RF cargadas desde el pkl si está disponible.

---

## 📓 Notebooks de análisis

7 notebooks que documentan el proceso de descubrimiento — cada uno termina en una decisión de diseño del pipeline:

| # | Notebook | Hallazgo → Decisión |
|---|----------|--------------------|
| 01 | [Fixtures WC2026](notebooks/01_wc2026_fixtures.ipynb) | 37.5% empates jornada 1 → verificamos que el filtro de `has_scores` es correcto |
| 02 | [Historia del Mundial](notebooks/02_wc_history.ipynb) | λ_global = 1.30 → parámetro de calibración del modelo Poisson |
| 03 | [StatsBomb Matches](notebooks/03_statsbomb_matches.ipynb) | 34/48 equipos con cobertura xG → estrategia de tres capas para λ |
| 04 | [StatsBomb xG](notebooks/04_statsbomb_xg.ipynb) | Argentina y Brasil top-2 en xG ofensivo → validación del modelo |
| 05 | [Planteles & Per-90](notebooks/05_squads_per90.ipynb) | 1,363 jugadores — distribuciones de edad y valor de mercado |
| 06 | [Onside Predictions](notebooks/06_onside_predictions.ipynb) | 9/11 errores de Onside fueron empates → el modelo Poisson los captura mejor |
| 07 | [Monte Carlo Propio](notebooks/07_monte_carlo.ipynb) | P(empate) emerge de Poisson sin forzarla → confirmación de que el enfoque es correcto |

---

## 🚀 Cómo ejecutarlo localmente

**Requisitos:** Docker Desktop · Python 3.12 · [uv](https://github.com/astral-sh/uv) · Git for Windows (necesario para el workaround SSL de worldcup26.ir)

```powershell
# 1. Clonar y configurar variables de entorno
git clone <repo>
cd Mundial_2026
cp .env.example .env   # completar WORLDCUP26_EMAIL, WORLDCUP26_PASSWORD, DATABASE_URL (Neon)

# 2. Levantar infraestructura
docker-compose up -d   # MinIO + Airflow + PostgreSQL (metadatos Airflow)

# 3. Instalar dependencias Python
uv sync                            # dependencias base
uv sync --extra notebooks          # agrega Jupyter, matplotlib, seaborn
uv sync --extra dashboard          # agrega Streamlit, Plotly

# 4. Cargar variables de entorno (PowerShell — obligatorio antes de cualquier comando Python)
Get-Content .env | ForEach-Object {
    if ($_ -match "^([^#=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim())
    }
}
$env:PYTHONUTF8 = "1"   # evita UnicodeEncodeError con emoji en Windows

# 5. Bootstrap dbt (solo la primera vez)
uv run dbt seed --project-dir ./dbt --profiles-dir ./dbt   # carga 48 equipos en seeds.team_codes
uv run dbt run  --project-dir ./dbt --profiles-dir ./dbt   # construye las 20 modelos
uv run dbt test --project-dir ./dbt --profiles-dir ./dbt   # verifica los 20 tests

# 6. Ingestar datos históricos (carga única)
python -m ingestion.statsbomb_loader          # WC2022 + Copa América + Euro → Bronze
python -m ingestion.kaggle_loader             # histórico 1930–2022 → Bronze
python -m ingestion.rising_transfers_loader   # planteles + per-90 → Bronze
python -m ingestion.onside_loader             # predicciones Monte Carlo → Bronze
python -m ingestion.bronze_to_neon            # sube todo → Neon bronze_raw

# 7. Ingestar fixtures WC2026 (diario desde Airflow, o manual)
python -m ingestion.worldcup26_client --all --days-ahead 14   # backfill + 14 días ahead
python -m ingestion.bronze_to_neon --table api_fixtures        # solo api_fixtures

# 8. Entrenar el modelo ML
python -m ml.train

# 9. Levantar la API
uvicorn api.main:app --reload                    # http://localhost:8000/docs

# 10. Levantar el dashboard Streamlit
uv run streamlit run streamlit_app/app.py        # http://localhost:8501
```

> **Tip:** Los comandos frecuentes están en el `Makefile`:
> `make up` · `make dbt-run` · `make test` · `make train` · `make ingest` · `make dashboard`

---

## 🐛 Gotchas técnicos críticos resueltos

Estos son los problemas no obvios que encontramos durante el desarrollo. Están documentados aquí para no repetirlos.

### worldcup26.ir — TLS renegotiation
worldcup26.ir hace TLS renegotiation post-handshake. Python 3.12 + OpenSSL 3.x bloquea esto con `OP_NO_RENEGOTIATION`. Ningún workaround funciona desde Python nativo (`verify=False`, SSLContext personalizado, TLS 1.2 forzado).

**Solución:** `worldcup26_client.py` usa `subprocess.run` con el curl de Git for Windows, que usa Schannel (el stack TLS de Windows) y maneja la renegotiation sin problemas.

### worldcup26.ir — scores 0-0 en partidos futuros
La API pre-rellena todos los partidos futuros con `home_score: 0`, `away_score: 0` y `finished: TRUE`. El único indicador fiable de si un partido fue jugado es si la **fecha ya pasó**.

**Solución:** `fetch_fixtures()` detecta `target_date > date.today()` y fuerza `goals_home = NULL`, `goals_away = NULL`, `status = Scheduled` independientemente de lo que devuelva la API.

### worldcup26.ir — IDs de equipo colisionan con API-Football
worldcup26.ir tiene su propio namespace de IDs. El ID 42 en worldcup26.ir es DR Congo; el ID 42 en los seeds de API-Football es Canada. Un JOIN por ID mezclaba partidos incorrectamente.

**Solución:** `fact_matches.sql` hace el JOIN entre partidos WC2026 y `dim_teams` por nombre en minúsculas (`lower(home_team_name) = lower(canonical_name)`), no por ID.

### Pandas + Parquet — enteros con nulls se serializan como float
Cuando una columna de enteros tiene valores `None` (nulls), Pandas la convierte a `float64` antes de escribir el Parquet (no existe `Int64` con null en Parquet estándar). Al leer en Neon, la columna aparece como texto `"1.0"` en vez de `1`, y `::int` falla.

**Solución:** Los casts en dbt usan `::numeric::int` para pasar por el tipo decimal intermedio que acepta `"1.0"`.

### StatsBombPy >= 1.0 — columnas planas, no dicts anidados
StatsBombPy >= 1.0 expande automáticamente los dicts. `home_team` ya no es `{"home_team_id": 782, "home_team_name": "Brazil"}` — es directamente `"Brazil"`. Los casts `::jsonb` provocan el error silencioso `invalid input syntax for type json`.

**Solución:** Los modelos Silver de StatsBomb hacen referencia directa a las columnas planas sin casts jsonb.

### Streamlit + Pandas Styler — incompatibilidad con Arrow
Las versiones recientes de Streamlit usan Apache Arrow como backend de renderizado. `DataFrame.style.apply()` en este contexto produce celdas vacías; `.style.background_gradient()` requiere `matplotlib` como dependencia opcional que no está en el entorno base.

**Solución:** Todo el coloreado usa columnas de emoji explícitas (`🟢 Clasificado`) y `st.column_config.NumberColumn(format="%.1f%%")`, que sí funciona con Arrow.

---

---

## 📁 Estructura del repositorio

```
Mundial_2026/
├── ingestion/              # Clientes y loaders de cada fuente
│   ├── worldcup26_client.py   ★ fuente activa WC2026 (workaround SSL incluido)
│   ├── statsbomb_loader.py
│   ├── onside_loader.py
│   ├── rising_transfers_loader.py
│   ├── kaggle_loader.py
│   ├── bronze_to_neon.py      # MinIO → Neon bridge
│   └── minio_client.py        # utilidades Bronze
├── dbt/
│   ├── models/
│   │   ├── staging/           # 12 Silver views
│   │   └── marts/             # 8 Gold tables
│   ├── seeds/
│   │   └── team_codes.csv     # 48 equipos WC2026 con IDs cruzados
│   └── macros/
│       └── generate_schema_name.sql  # evita prefijo de usuario en schema
├── airflow/dags/
│   ├── dag_ingest_wc2026.py
│   ├── dag_dbt_transform.py
│   └── dag_retrain_model.py
├── api/
│   ├── main.py
│   ├── database.py            # SQLAlchemy engine + get_db()
│   └── routers/               # matches · teams · predict
├── ml/
│   ├── features.py            # build_features() → (X, y, meta) desde Gold
│   ├── train.py               # Random Forest → models/model_winner_predictor.pkl
│   └── evaluate.py            # accuracy con breakdown por competición
├── streamlit_app/
│   ├── app.py                 # Home — KPIs en vivo
│   ├── pages/
│   │   ├── 1_📊_Standings.py
│   │   ├── 2_🔮_Predicciones.py
│   │   ├── 3_🏆_Bracket.py
│   │   ├── 4_📈_Analytics.py
│   │   └── 5_🤖_Modelo.py
│   └── utils/
│       ├── db.py              # query() con @st.cache_resource
│       └── charts.py          # funciones Plotly reutilizables
├── models/                    # artefactos ML (gitignored)
│   └── model_winner_predictor.pkl
├── notebooks/                 # 7 EDA notebooks
├── tests/                     # 39 pytest tests
├── docker-compose.yml
├── pyproject.toml
├── Makefile
└── .github/workflows/ci.yml
```

---

## 🔮 Próximos pasos naturales

**Integrar el modelo RF en la API:** `POST /predict/winner` actualmente usa Poisson puro. El RF entrenado vive en `models/model_winner_predictor.pkl` y acepta el mismo vector de 16 features que `ml/features.py` construye. El cambio es un `pickle.load` + `model.predict_proba()` en `api/routers/predict.py`.

**Re-evaluar el RF con datos de eliminatorias:** El modelo se entrenó mayoritariamente con partidos de fase de grupos. Los cruces eliminatorios tienen dinámica distinta. A partir del R32 (~28 junio), correr `python -m ml.evaluate` para ver si el accuracy sube o baja con los nuevos datos.

**Migración a BigQuery:** La arquitectura está diseñada para esto. El cambio requiere: (1) target `bigquery` en `dbt/profiles.yml`, (2) `BQ_PROJECT_ID` y `BQ_DATASET_GOLD` en `.env`. Los modelos SQL de dbt no cambian.

---

*Datos: worldcup26.ir · StatsBomb Open Data (CC BY-SA 4.0) · Onside Arena (CC BY 4.0) · Rising Transfers · Kaggle*

---

## 👤 Autor

**William Botero**

Data Engineer apasionado por el fútbol y la inteligencia analítica aplicada al deporte. Este proyecto nació durante el Mundial 2026 como una exploración end-to-end de ingeniería de datos moderna: desde la ingesta en crudo hasta un dashboard interactivo con predicciones en tiempo real.

📧 [boterowilliam32@gmail.com](mailto:boterowilliam32@gmail.com)
🐙 [github.com/willyoung21](https://github.com/willyoung21)
