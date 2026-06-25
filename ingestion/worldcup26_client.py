"""Cliente para worldcup26.ir — datos en vivo del WC2026.

Reemplaza api_football_client.py. Normaliza la respuesta de worldcup26.ir
al mismo esquema columnar que api_football_client.fetch_fixtures(), para que
bronze_to_neon.py y los modelos dbt no requieran cambios.

Registro gratuito en https://worldcup26.ir/api-docs
El JWT se obtiene automáticamente en cada ejecución con email + password del .env.
Tokens válidos 84 días — el cliente los renueva sin intervención manual.

Nota SSL: worldcup26.ir hace TLS renegotiation que OpenSSL 3.x no tolera.
Usamos subprocess curl (Windows Schannel) como backend HTTP.

Ejecutar diariamente desde Airflow (dag_ingest_wc2026) o manualmente:
  python -m ingestion.worldcup26_client --date 2026-06-15
  python -m ingestion.worldcup26_client --all   # todas las fechas desde inicio del torneo
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta

import pandas as pd
from dotenv import load_dotenv

from ingestion.minio_client import write_parquet

WC26_BASE_URL = "https://worldcup26.ir"
WC2026_START_DATE = date(2026, 6, 11)
REQUEST_DELAY = 0.5

_req_count = 0

# worldcup26.ir uses TLS renegotiation that Python's OpenSSL 3.x doesn't support on Windows.
# On Linux (Airflow container, Python 3.11) the issue doesn't apply — system curl works fine.
if sys.platform == "win32":
    # Windows: Git for Windows curl (8.8.0) + Schannel handles TLS renegotiation.
    # System curl 8.19+ also fails; must use the older Git curl with minimal env.
    _GIT_BIN_DIRS = [
        r"C:\Program Files\Git\mingw64\bin",
        r"C:\Program Files (x86)\Git\mingw64\bin",
        r"C:\Program Files\Git\usr\bin",
        r"C:\Program Files\Git\bin",
    ]
    _GIT_CURL_EXE = next(
        (
            os.path.join(d, "curl.exe")
            for d in _GIT_BIN_DIRS
            if os.path.isfile(os.path.join(d, "curl.exe"))
        ),
        None,
    )
    _CURL_EXE = _GIT_CURL_EXE or r"C:\WINDOWS\system32\curl.EXE"
    _CURL_ENV: dict | None = {
        "PATH": os.pathsep.join(d for d in _GIT_BIN_DIRS if os.path.isdir(d)),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "TEMP": os.environ.get("TEMP", r"C:\Windows\Temp"),
        "TMP": os.environ.get("TMP", r"C:\Windows\Temp"),
    }
else:
    # Linux / macOS (Airflow Docker container): system curl works, inherit full env.
    _CURL_EXE = "/usr/bin/curl"
    _CURL_ENV = None


def _curl(
    method: str,
    endpoint: str,
    body: dict | None = None,
    jwt: str | None = None,
    max_retries: int = 4,
) -> dict | list:
    """HTTP request via curl con Git en PATH (Schannel, maneja TLS renegotiation del servidor).

    Reintentos con backoff: el LB de worldcup26.ir es inconsistente y a veces retorna exit 35.
    """
    global _req_count
    url = f"{WC26_BASE_URL}/{endpoint}"
    cmd = [_CURL_EXE, "-s", "--max-time", "30", "-X", method, url]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data", json.dumps(body)]
    if jwt is not None:
        cmd += ["-H", f"Authorization: Bearer {jwt}"]

    last_error: Exception | None = None
    for attempt in range(max_retries):
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", env=_CURL_ENV, timeout=35
        )
        raw = proc.stdout.strip()

        if proc.returncode == 0 and raw:
            try:
                result = json.loads(raw)
                _req_count += 1
                return result
            except json.JSONDecodeError:
                # El servidor devolvio HTML u otro error no-JSON
                last_error = ValueError(f"respuesta no-JSON de /{endpoint}: {raw[:150]}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                break

        if proc.returncode in (35, 52, 0) and attempt < max_retries - 1:
            wait = 2**attempt
            print(
                f"  [retry {attempt + 1}/{max_retries - 1}] exit {proc.returncode}, esperando {wait}s..."
            )
            time.sleep(wait)
            last_error = OSError(f"curl exit {proc.returncode}")
            continue

        stderr = proc.stderr.strip()[:200] if proc.stderr else ""
        last_error = OSError(
            f"curl error (exit {proc.returncode}): {stderr}"
            if proc.returncode != 0
            else f"curl: respuesta vacia de {method} /{endpoint}"
        )
        break

    raise last_error  # type: ignore[misc]


def _get_jwt() -> str:
    """Autentica con WORLDCUP26_EMAIL + WORLDCUP26_PASSWORD y retorna el JWT."""
    resp = _curl(
        "POST",
        "auth/authenticate",
        body={
            "email": os.environ["WORLDCUP26_EMAIL"],
            "password": os.environ["WORLDCUP26_PASSWORD"],
        },
    )
    jwt = resp.get("token")
    if not jwt:
        raise ValueError(f"JWT no encontrado en respuesta de /auth/authenticate: {resp}")
    print("  [auth] JWT obtenido")
    return jwt


def _build_stadium_lookup(jwt: str) -> dict[str, dict]:
    """Retorna stadium_id → {name, city}. Falla silenciosamente si hay error."""
    try:
        raw = _curl("GET", "get/stadiums", jwt=jwt)
        items = raw if isinstance(raw, list) else raw.get("stadiums", [])
        lookup = {
            str(s.get("id") or s.get("_id", "")): {
                "name": s.get("name") or s.get("stadium_name"),
                "city": s.get("city"),
            }
            for s in items
        }
        print(f"  [stadiums] {len(lookup)} estadios cargados")
        return lookup
    except Exception as e:
        print(f"  WARN: /get/stadiums no disponible ({e}), venue_name sera None")
        return {}


def _parse_local_date(local_date_str: str) -> str:
    """Convierte 'MM/DD/YYYY HH:MM' a 'YYYY-MM-DD' para filtrado por fecha."""
    try:
        date_part = str(local_date_str).split(" ")[0]  # '06/11/2026'
        month, day, year = date_part.split("/")
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except Exception:
        return str(local_date_str)[:10]


def _parse_int(value) -> int | None:
    """Convierte string a int; retorna None para strings vacíos o no numéricos."""
    if value is None or str(value).strip() in ("", "null"):
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _to_bool(value) -> bool:
    """Convierte 'true'/'false'/'1'/'0' o bool a bool Python."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _derive_league_round(game: dict) -> str:
    """Convierte type/group de worldcup26 al formato league_round de API-Football."""
    match_type = str(game.get("type") or "group").lower().strip()
    if match_type == "group":
        group = str(game.get("group", "")).strip()
        return f"Group {group}" if group else "Group Stage"
    round_map = {
        "round_of_32": "Round of 32",
        "round of 32": "Round of 32",
        "round_of_16": "Round of 16",
        "round of 16": "Round of 16",
        "quarter_final": "Quarter-final",
        "quarterfinal": "Quarter-final",
        "semi_final": "Semi-final",
        "semifinal": "Semi-final",
        "final": "Final",
        "third_place": "3rd Place Final",
        "third place": "3rd Place Final",
    }
    return round_map.get(match_type, match_type.replace("_", " ").title())


def fetch_fixtures(target_date: str, jwt: str, stadiums: dict) -> pd.DataFrame:
    """Obtiene partidos WC2026 para target_date (YYYY-MM-DD).

    Normaliza a las mismas columnas que api_football_client.fetch_fixtures()
    para que bronze_to_neon.py y stg_matches_wc2026.sql funcionen sin cambios.
    """
    raw = _curl("GET", "get/games", jwt=jwt)
    all_games: list[dict] = raw if isinstance(raw, list) else raw.get("games", [])
    n_total = len(all_games)

    # worldcup26.ir pre-rellena futuros partidos con 0-0 y finished=TRUE.
    # Para fechas futuras ignoramos el score de la API y marcamos como Scheduled.
    target_date_obj = date.fromisoformat(target_date)
    is_future_date = target_date_obj > date.today()

    rows = []
    for game in all_games:
        game_date = _parse_local_date(str(game.get("local_date", "")))
        if game_date != target_date:
            continue

        # Nombres de equipo: para eliminatorias futuras la API devuelve None (TBD)
        home_name = game.get("home_team_name_en") or game.get("home_team_name") or None
        away_name = game.get("away_team_name_en") or game.get("away_team_name") or None

        if is_future_date:
            # Fecha futura: los scores 0-0 son placeholders, no resultados reales
            home_score = None
            away_score = None
            has_scores = False
            time_elapsed = None
            status = "Scheduled"
            home_winner = None
            away_winner = None
        else:
            home_score = _parse_int(game.get("home_score"))
            away_score = _parse_int(game.get("away_score"))
            # finished=TRUE en API no es fiable: futuros juegos también lo tienen.
            # Solo consideramos finalizado si hay scores reales (no null).
            has_scores = home_score is not None and away_score is not None
            time_elapsed = _parse_int(game.get("time_elapsed"))

            if has_scores and time_elapsed is None:
                status = "Match Finished"
            elif time_elapsed:
                status = "In Progress"
            else:
                status = "Scheduled"

            if has_scores:
                home_winner = home_score > away_score
                away_winner = away_score > home_score
            else:
                home_winner = None
                away_winner = None

        stadium_id = str(game.get("stadium_id", ""))
        stadium_info = stadiums.get(stadium_id, {})

        fixture_id = _parse_int(game.get("id") or game.get("_id")) or hash(
            str(game.get("_id", ""))
        ) % (2**31)

        rows.append(
            {
                "fixture_id": fixture_id,
                "date": f"{game_date}T00:00:00+00:00",
                "status": status,
                "elapsed": time_elapsed,
                "venue_name": stadium_info.get("name"),
                "venue_city": stadium_info.get("city"),
                "referee": None,
                "league_round": _derive_league_round(game),
                "home_team_id": _parse_int(game.get("home_team_id")),
                "home_team_name": home_name,
                "home_winner": home_winner,
                "away_team_id": _parse_int(game.get("away_team_id")),
                "away_team_name": away_name,
                "away_winner": away_winner,
                "goals_home": home_score,
                "goals_away": away_score,
                "score_ht_home": None,
                "score_ht_away": None,
            }
        )

    print(f"  [{_req_count} req] GET /get/games - {n_total} total, {len(rows)} en {target_date}")
    time.sleep(REQUEST_DELAY)
    return pd.DataFrame(rows)


def run_daily_ingestion(target_date: str) -> None:
    """Orquesta la ingesta de un día: auth → fixtures → MinIO.

    Misma interfaz que api_football_client.run_daily_ingestion().
    """
    print(f"\n{'=' * 55}")
    print(f"  Ingesta WC2026 (worldcup26.ir) - {target_date}")
    print(f"{'=' * 55}")

    jwt = _get_jwt()
    stadiums = _build_stadium_lookup(jwt)
    fixtures = fetch_fixtures(target_date, jwt, stadiums)

    if fixtures.empty:
        print(f"  Sin partidos para {target_date}")
        return

    date_partition = f"date={target_date}"
    write_parquet(fixtures, f"raw_fixtures_2026/{date_partition}/fixtures.parquet")
    print(
        f"\n  OK: {len(fixtures)} partido(s) -> raw_fixtures_2026/{date_partition}/fixtures.parquet"
    )
    print(f"  Total requests: {_req_count}")


WC2026_END_DATE = date(2026, 7, 19)  # Final del torneo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta diaria WC2026 desde worldcup26.ir")
    parser.add_argument(
        "--date",
        default=str(date.today() - timedelta(days=1)),
        help="Fecha a ingestar (YYYY-MM-DD). Default: ayer.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"Ingestar todas las fechas desde {WC2026_START_DATE} hasta ayer.",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=0,
        metavar="N",
        help="Además de las fechas pasadas, también fetear los próximos N días (fixtures futuros). Default: 0.",
    )
    args = parser.parse_args()

    load_dotenv()

    if args.all:
        # Rango: desde inicio del torneo hasta ayer + días hacia adelante
        start = WC2026_START_DATE
        end_past = date.today() - timedelta(days=1)
        end_future = date.today() + timedelta(days=args.days_ahead)
        end = min(max(end_past, end_future), WC2026_END_DATE)
        d = start
        while d <= end:
            run_daily_ingestion(str(d))
            d += timedelta(days=1)
    elif args.days_ahead > 0:
        # Solo futuros: hoy + N días
        d = date.today()
        end = min(d + timedelta(days=args.days_ahead), WC2026_END_DATE)
        while d <= end:
            run_daily_ingestion(str(d))
            d += timedelta(days=1)
    else:
        run_daily_ingestion(args.date)
