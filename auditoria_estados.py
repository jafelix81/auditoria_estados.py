import os
import json
import math
import requests
import pandas as pd
from datetime import datetime, timezone


# ============================================================
# CONFIGURACIÓN
# ============================================================

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")

if not APPS_SCRIPT_URL:
    raise RuntimeError(
        "No se encontró la variable de entorno APPS_SCRIPT_URL."
    )

OUTPUT_CSV = "auditoria_estados.csv"
OUTPUT_JSON = "auditoria_resumen.json"
OUTPUT_TXT = "auditoria_estados.txt"


EXPECTED_COLUMNS = [
    "RUN_ID",
    "CAPTURED_AT_UTC",
    "CAPTURED_AT_LOCAL",
    "Ticker",
    "STATUS",
    "ERROR",
    "DATA_ATTEMPTS",
    "DATA_SOURCE",
    "DATA_OBSERVATIONS",
    "DATA_FIRST_DATE",
    "DATA_LAST_DATE",
    "DATA_DIAGNOSIS",
    "Price_Actual",
    "Price_Close",
    "R1",
    "R5",
    "R20",
    "R60",
    "R120",
    "Vol5",
    "Vol20",
    "Vol60",
    "Vol252",
    "VolRatio20",
    "VolRatio60",
    "Skew20",
    "Kurt20",
    "AC1",
    "Forward5",
    "Forward10",
    "Forward20",
    "Forward40",
    "EV5",
    "EV10",
    "EV20",
    "EV40",
    "Confidence5",
    "Confidence10",
    "Confidence20",
    "Confidence40",
    "ESS5",
    "ESS10",
    "ESS20",
    "ESS40",
    "ES95_5",
    "ES95_10",
    "ES95_20",
    "ES95_40",
    "Kelly25",
]


STATE_COLUMNS = [
    "R1",
    "R5",
    "R20",
    "R60",
    "R120",
    "Vol5",
    "Vol20",
    "Vol60",
    "Vol252",
    "VolRatio20",
    "VolRatio60",
    "Skew20",
    "Kurt20",
    "AC1",
]


# ============================================================
# UTILIDADES
# ============================================================

def is_finite(value):
    """Determina si un valor es numéricamente válido."""
    try:
        x = float(value)
        return math.isfinite(x)
    except (TypeError, ValueError):
        return False


def pct(value):
    if value is None:
        return "N/A"

    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def obtener_datos():
    """Solicita CERE_CURRENT a Apps Script."""

    payload = {
        "action": "get_cere_current"
    }

    print("=" * 70)
    print("AUDITORÍA CERE — LECTURA DE CERE_CURRENT")
    print("=" * 70)

    print("\nConsultando Google Apps Script...")

    response = requests.post(
        APPS_SCRIPT_URL,
        json=payload,
        timeout=60
    )

    print(f"HTTP status: {response.status_code}")

    if response.status_code != 200:
        raise RuntimeError(
            f"Apps Script respondió HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(
            "La respuesta de Apps Script no es JSON válido.\n"
            f"Respuesta recibida:\n{response.text[:2000]}"
        ) from e

    if data.get("status") != "success":
        raise RuntimeError(
            "Apps Script reportó un error:\n"
            + json.dumps(data, ensure_ascii=False, indent=2)
        )

    return data


# ============================================================
# AUDITORÍA
# ============================================================

def ejecutar_auditoria(data):

    headers = data.get("headers", [])
    rows = data.get("rows", [])

    print("\n" + "=" * 70)
    print("1. ESTRUCTURA")
    print("=" * 70)

    print(f"Columnas recibidas : {len(headers)}")
    print(f"Filas recibidas    : {len(rows)}")

    # --------------------------------------------------------
    # COLUMNAS
    # --------------------------------------------------------

    missing_columns = [
        col for col in EXPECTED_COLUMNS
        if col not in headers
    ]

    extra_columns = [
        col for col in headers
        if col not in EXPECTED_COLUMNS
    ]

    if missing_columns:
        print("\n❌ COLUMNAS FALTANTES:")
        for col in missing_columns:
            print(f"   - {col}")
    else:
        print("\n✓ Todas las columnas esperadas están presentes.")

    if extra_columns:
        print("\n⚠ COLUMNAS ADICIONALES:")
        for col in extra_columns:
            print(f"   - {col}")
    else:
        print("✓ No existen columnas adicionales.")

    # --------------------------------------------------------
    # DATAFRAME
    # --------------------------------------------------------

    df = pd.DataFrame(rows, columns=headers)

    # --------------------------------------------------------
    # TICKERS
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("2. TICKERS")
    print("=" * 70)

    if "Ticker" not in df.columns:
        raise RuntimeError("No existe la columna Ticker.")

    tickers = df["Ticker"].astype(str).str.strip()

    print(f"Tickers totales: {len(tickers)}")
    print(f"Tickers únicos : {tickers.nunique()}")

    duplicates = tickers[tickers.duplicated()].unique().tolist()

    if duplicates:
        print("\n❌ TICKERS DUPLICADOS:")
        for ticker in duplicates:
            print(f"   - {ticker}")
    else:
        print("✓ No hay tickers duplicados.")

    blank_tickers = df[
        df["Ticker"].isna()
        | (df["Ticker"].astype(str).str.strip() == "")
    ]

    if len(blank_tickers):
        print(f"❌ Tickers vacíos: {len(blank_tickers)}")
    else:
        print("✓ No hay tickers vacíos.")

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("3. STATUS")
    print("=" * 70)

    status_counts = (
        df["STATUS"]
        .fillna("BLANK")
        .astype(str)
        .value_counts()
        .to_dict()
    )

    for status, count in status_counts.items():
        print(f"{status:15s}: {count}")

    # --------------------------------------------------------
    # ESTADOS OK
    # --------------------------------------------------------

    df_ok = df[
        df["STATUS"].astype(str).str.upper() == "OK"
    ].copy()

    print(f"\nRegistros OK: {len(df_ok)}")

    # --------------------------------------------------------
    # VARIABLES DEL ESTADO
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("4. VARIABLES ESTADÍSTICAS DEL ESTADO")
    print("=" * 70)

    state_report = {}

    for col in STATE_COLUMNS:

        if col not in df.columns:
            state_report[col] = {
                "missing_column": True
            }
            print(f"\n❌ {col}: columna inexistente")
            continue

        numeric = pd.to_numeric(
            df_ok[col],
            errors="coerce"
        )

        total = len(numeric)
        valid = numeric.notna().sum()
        missing = numeric.isna().sum()

        finite = numeric.apply(is_finite).sum()

        unique = numeric.dropna().nunique()

        if valid > 0:
            minimum = float(numeric.min())
            maximum = float(numeric.max())
            mean = float(numeric.mean())
            std = float(numeric.std())
        else:
            minimum = None
            maximum = None
            mean = None
            std = None

        state_report[col] = {
            "total_ok": int(total),
            "valid": int(valid),
            "missing": int(missing),
            "finite": int(finite),
            "unique": int(unique),
            "min": minimum,
            "max": maximum,
            "mean": mean,
            "std": std,
        }

        if missing == 0 and finite == total:
            symbol = "✓"
        else:
            symbol = "⚠"

        print(
            f"{symbol} {col:12s} "
            f"válidos={valid:3d} "
            f"faltantes={missing:3d} "
            f"únicos={unique:3d}"
        )

    # --------------------------------------------------------
    # PRECIOS
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("5. PRECIOS")
    print("=" * 70)

    for col in ["Price_Actual", "Price_Close"]:

        if col not in df_ok.columns:
            continue

        numeric = pd.to_numeric(
            df_ok[col],
            errors="coerce"
        )

        print(
            f"{col:15s}: "
            f"válidos={numeric.notna().sum():3d} / {len(df_ok)}"
        )

    # --------------------------------------------------------
    # FECHAS
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("6. FECHAS DE DATOS")
    print("=" * 70)

    if "DATA_LAST_DATE" in df_ok.columns:

        dates = pd.to_datetime(
            df_ok["DATA_LAST_DATE"],
            errors="coerce"
        )

        valid_dates = dates.dropna()

        if len(valid_dates):

            print(
                "Fecha más antigua : "
                f"{valid_dates.min().date()}"
            )

            print(
                "Fecha más reciente: "
                f"{valid_dates.max().date()}"
            )

            print(
                "Fechas válidas    : "
                f"{len(valid_dates)} / {len(df_ok)}"
            )

    # --------------------------------------------------------
    # FORWARD / EV
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("7. CAMPOS CERE V2")
    print("=" * 70)

    v2_columns = [
        "Forward5",
        "Forward10",
        "Forward20",
        "Forward40",
        "EV5",
        "EV10",
        "EV20",
        "EV40",
        "Confidence5",
        "Confidence10",
        "Confidence20",
        "Confidence40",
        "ESS5",
        "ESS10",
        "ESS20",
        "ESS40",
        "ES95_5",
        "ES95_10",
        "ES95_20",
        "ES95_40",
        "Kelly25",
    ]

    for col in v2_columns:

        if col not in df.columns:
            print(f"❌ {col}: no existe")
            continue

        numeric = pd.to_numeric(
            df_ok[col],
            errors="coerce"
        )

        valid = numeric.notna().sum()

        print(
            f"{col:15s}: "
            f"{valid:3d}/{len(df_ok)} valores"
        )

    # --------------------------------------------------------
    # EXPORTAR CSV
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    summary = {
        "audit_timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "sheet": data.get("sheet"),

        "row_count": len(df),

        "column_count": len(headers),

        "expected_row_count": 339,

        "expected_column_count": 46,

        "row_count_ok": len(df) == 339,

        "column_count_ok": len(headers) == 46,

        "missing_columns": missing_columns,

        "extra_columns": extra_columns,

        "unique_tickers": int(tickers.nunique()),

        "duplicate_tickers": duplicates,

        "status_counts": status_counts,

        "ok_count": len(df_ok),

        "state_report": state_report,
    }

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # REPORTE TXT
    # --------------------------------------------------------

    with open(
        OUTPUT_TXT,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "AUDITORÍA CERE — CERE_CURRENT\n"
        )

        f.write("=" * 70 + "\n\n")

        f.write(
            f"Filas: {len(df)}\n"
        )

        f.write(
            f"Columnas: {len(headers)}\n"
        )

        f.write(
            f"Tickers únicos: {tickers.nunique()}\n"
        )

        f.write(
            f"Registros OK: {len(df_ok)}\n\n"
        )

        f.write("STATUS\n")
        f.write("-" * 30 + "\n")

        for status, count in status_counts.items():
            f.write(
                f"{status}: {count}\n"
            )

        f.write("\nVARIABLES DE ESTADO\n")
        f.write("-" * 30 + "\n")

        for col, info in state_report.items():

            f.write(
                f"{col}: {json.dumps(info, ensure_ascii=False)}\n"
            )

    # --------------------------------------------------------
    # RESULTADO FINAL
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESULTADO DE LA AUDITORÍA")
    print("=" * 70)

    problems = []

    if len(df) != 339:
        problems.append(
            f"Se esperaban 339 filas y se recibieron {len(df)}."
        )

    if len(headers) != 46:
        problems.append(
            f"Se esperaban 46 columnas y se recibieron {len(headers)}."
        )

    if missing_columns:
        problems.append(
            f"Faltan {len(missing_columns)} columnas."
        )

    if duplicates:
        problems.append(
            f"Hay {len(duplicates)} tickers duplicados."
        )

    if problems:

        print("\n⚠ AUDITORÍA CON OBSERVACIONES\n")

        for problem in problems:
            print(f" - {problem}")

    else:

        print("\n✓ ESTRUCTURA CORRECTA")
        print("✓ 339 registros recibidos")
        print("✓ 46 columnas recibidas")
        print("✓ Sin tickers duplicados")
        print("✓ Estructura CERE_CURRENT compatible")

    print("\nArchivos generados:")
    print(f" - {OUTPUT_CSV}")
    print(f" - {OUTPUT_JSON}")
    print(f" - {OUTPUT_TXT}")

    return summary


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        data = obtener_datos()

        ejecutar_auditoria(data)

    except Exception as e:

        print("\n" + "=" * 70)
        print("❌ ERROR EN AUDITORÍA")
        print("=" * 70)

        print(str(e))

        raise
