import os
import json
import math
import requests
import pandas as pd
from datetime import datetime, timezone
from urllib.parse import urljoin


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


# ============================================================
# ESTRUCTURA ESPERADA DE CERE_CURRENT
# ============================================================

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


# ============================================================
# VARIABLES DEL ESTADO ACTUAL
# ============================================================

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
# CAMPOS RESERVADOS PARA CERE V2
# ============================================================

CERE_V2_COLUMNS = [
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


# ============================================================
# UTILIDADES
# ============================================================

def is_finite(value):
    """
    Determina si un valor puede convertirse a número
    y es finito.
    """

    try:
        x = float(value)
        return math.isfinite(x)

    except (TypeError, ValueError):
        return False


# ============================================================
# OBTENER CERE_CURRENT DESDE APPS SCRIPT
# ============================================================

def obtener_datos():

    """
    Solicita CERE_CURRENT a Google Apps Script.

    IMPORTANTE:
    Google Apps Script puede responder inicialmente con una
    redirección HTTP. Por eso NO usamos allow_redirects=True
    en el primer POST.

    Si existe una redirección, recuperamos explícitamente
    la URL y volvemos a enviar el POST.
    """

    payload = {
        "action": "get_cere_current"
    }

    print("=" * 70)
    print("AUDITORÍA CERE — LECTURA DE CERE_CURRENT")
    print("=" * 70)

    print("\nConsultando Google Apps Script...")

    # --------------------------------------------------------
    # PRIMER POST
    # --------------------------------------------------------

    response = requests.post(
        APPS_SCRIPT_URL,
        json=payload,
        timeout=60,
        allow_redirects=False
    )

    print(f"HTTP inicial: {response.status_code}")

    # --------------------------------------------------------
    # MANEJO DE REDIRECCIÓN
    # --------------------------------------------------------

    if response.status_code in (301, 302, 303, 307, 308):

        redirect_url = response.headers.get("Location")

        if not redirect_url:

            raise RuntimeError(
                "Apps Script respondió con una redirección "
                f"HTTP {response.status_code}, pero no proporcionó "
                "el header Location."
            )

        redirect_url = urljoin(
            APPS_SCRIPT_URL,
            redirect_url
        )

        print("Redirección detectada.")
        print("Enviando nuevamente el POST al destino...")

        response = requests.post(
            redirect_url,
            json=payload,
            timeout=60,
            allow_redirects=True
        )

    # --------------------------------------------------------
    # STATUS HTTP FINAL
    # --------------------------------------------------------

    print(f"HTTP final: {response.status_code}")

    if response.status_code != 200:

        raise RuntimeError(
            f"Apps Script respondió HTTP {response.status_code}:\n"
            f"{response.text[:2000]}"
        )

    # --------------------------------------------------------
    # PARSEAR JSON
    # --------------------------------------------------------

    try:

        data = response.json()

    except Exception as e:

        raise RuntimeError(
            "La respuesta de Apps Script no es JSON válido.\n"
            f"Respuesta recibida:\n{response.text[:2000]}"
        ) from e

    # --------------------------------------------------------
    # VALIDAR RESPUESTA DEL SCRIPT
    # --------------------------------------------------------

    if data.get("status") != "success":

        raise RuntimeError(
            "Apps Script reportó un error:\n"
            + json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            )
        )

    return data


# ============================================================
# AUDITORÍA
# ============================================================

def ejecutar_auditoria(data):

    headers = data.get("headers", [])
    rows = data.get("rows", [])

    # ========================================================
    # 1. ESTRUCTURA
    # ========================================================

    print("\n" + "=" * 70)
    print("1. ESTRUCTURA")
    print("=" * 70)

    print(f"Columnas recibidas : {len(headers)}")
    print(f"Filas recibidas    : {len(rows)}")

    missing_columns = [
        col
        for col in EXPECTED_COLUMNS
        if col not in headers
    ]

    extra_columns = [
        col
        for col in headers
        if col not in EXPECTED_COLUMNS
    ]

    if missing_columns:

        print("\n❌ COLUMNAS FALTANTES:")

        for col in missing_columns:
            print(f"   - {col}")

    else:

        print(
            "\n✓ Todas las columnas esperadas "
            "están presentes."
        )

    if extra_columns:

        print("\n⚠ COLUMNAS ADICIONALES:")

        for col in extra_columns:
            print(f"   - {col}")

    else:

        print("✓ No existen columnas adicionales.")

    # ========================================================
    # CREAR DATAFRAME
    # ========================================================

    df = pd.DataFrame(
        rows,
        columns=headers
    )

    # ========================================================
    # 2. TICKERS
    # ========================================================

    print("\n" + "=" * 70)
    print("2. TICKERS")
    print("=" * 70)

    if "Ticker" not in df.columns:

        raise RuntimeError(
            "No existe la columna Ticker."
        )

    tickers = (
        df["Ticker"]
        .astype(str)
        .str.strip()
    )

    print(
        f"Tickers totales: {len(tickers)}"
    )

    print(
        f"Tickers únicos : {tickers.nunique()}"
    )

    duplicates = (
        tickers[
            tickers.duplicated()
        ]
        .unique()
        .tolist()
    )

    if duplicates:

        print("\n❌ TICKERS DUPLICADOS:")

        for ticker in duplicates:
            print(f"   - {ticker}")

    else:

        print("✓ No hay tickers duplicados.")

    blank_tickers = df[
        df["Ticker"].isna()
        |
        (
            df["Ticker"]
            .astype(str)
            .str.strip()
            == ""
        )
    ]

    if len(blank_tickers):

        print(
            f"❌ Tickers vacíos: "
            f"{len(blank_tickers)}"
        )

    else:

        print("✓ No hay tickers vacíos.")

    # ========================================================
    # 3. STATUS
    # ========================================================

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

        print(
            f"{status:15s}: {count}"
        )

    # ========================================================
    # REGISTROS OK
    # ========================================================

    df_ok = df[
        df["STATUS"]
        .astype(str)
        .str.upper()
        == "OK"
    ].copy()

    print(
        f"\nRegistros OK: {len(df_ok)}"
    )

    # ========================================================
    # 4. VARIABLES ESTADÍSTICAS DEL ESTADO
    # ========================================================

    print("\n" + "=" * 70)
    print("4. VARIABLES ESTADÍSTICAS DEL ESTADO")
    print("=" * 70)

    state_report = {}

    for col in STATE_COLUMNS:

        if col not in df.columns:

            state_report[col] = {
                "missing_column": True
            }

            print(
                f"\n❌ {col}: "
                "columna inexistente"
            )

            continue

        numeric = pd.to_numeric(
            df_ok[col],
            errors="coerce"
        )

        total = len(numeric)

        valid = int(
            numeric.notna().sum()
        )

        missing = int(
            numeric.isna().sum()
        )

        finite = int(
            numeric.apply(is_finite).sum()
        )

        unique = int(
            numeric.dropna().nunique()
        )

        if valid > 0:

            minimum = float(
                numeric.min()
            )

            maximum = float(
                numeric.max()
            )

            mean = float(
                numeric.mean()
            )

            std = float(
                numeric.std()
            )

        else:

            minimum = None
            maximum = None
            mean = None
            std = None

        state_report[col] = {

            "total_ok": total,

            "valid": valid,

            "missing": missing,

            "finite": finite,

            "unique": unique,

            "min": minimum,

            "max": maximum,

            "mean": mean,

            "std": std,
        }

        if (
            missing == 0
            and finite == total
        ):

            symbol = "✓"

        else:

            symbol = "⚠"

        print(
            f"{symbol} {col:12s} "
            f"válidos={valid:3d} "
            f"faltantes={missing:3d} "
            f"únicos={unique:3d}"
        )

    # ========================================================
    # 5. PRECIOS
    # ========================================================

    print("\n" + "=" * 70)
    print("5. PRECIOS")
    print("=" * 70)

    for col in [
        "Price_Actual",
        "Price_Close"
    ]:

        if col not in df_ok.columns:
            continue

        numeric = pd.to_numeric(
            df_ok[col],
            errors="coerce"
        )

        print(
            f"{col:15s}: "
            f"válidos="
            f"{numeric.notna().sum():3d} "
            f"/ {len(df_ok)}"
        )

    # ========================================================
    # 6. FECHAS
    # ========================================================

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
                f"{len(valid_dates)} "
                f"/ {len(df_ok)}"
            )

        else:

            print(
                "⚠ No se encontraron "
                "fechas válidas."
            )

    # ========================================================
    # 7. CAMPOS RESERVADOS PARA CERE V2
    # ========================================================

    print("\n" + "=" * 70)
    print("7. CAMPOS CERE V2")
    print("=" * 70)

    print(
        "\nEstos campos todavía deben permanecer "
        "vacíos en CERE v1.1."
    )

    for col in CERE_V2_COLUMNS:

        if col not in df.columns:

            print(
                f"❌ {col}: no existe"
            )

            continue

        numeric = pd.to_numeric(
            df_ok[col],
            errors="coerce"
        )

        valid = int(
            numeric.notna().sum()
        )

        print(
            f"{col:15s}: "
            f"{valid:3d}/{len(df_ok)} valores"
        )

    # ========================================================
    # 8. EXPORTAR CSV
    # ========================================================

    df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # 9. RESUMEN JSON
    # ========================================================

    summary = {

        "audit_timestamp_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "sheet":
            data.get("sheet"),

        "row_count":
            len(df),

        "column_count":
            len(headers),

        "expected_row_count":
            339,

        "expected_column_count":
            50,

        "row_count_ok":
            len(df) == 339,

        "column_count_ok":
            len(headers) == 50,

        "missing_columns":
            missing_columns,

        "extra_columns":
            extra_columns,

        "unique_tickers":
            int(
                tickers.nunique()
            ),

        "duplicate_tickers":
            duplicates,

        "status_counts":
            status_counts,

        "ok_count":
            len(df_ok),

        "state_report":
            state_report,
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

    # ========================================================
    # 10. REPORTE TXT
    # ========================================================

    with open(
        OUTPUT_TXT,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "AUDITORÍA CERE — CERE_CURRENT\n"
        )

        f.write(
            "=" * 70 + "\n\n"
        )

        f.write(
            f"Filas: {len(df)}\n"
        )

        f.write(
            f"Columnas: {len(headers)}\n"
        )

        f.write(
            f"Tickers únicos: "
            f"{tickers.nunique()}\n"
        )

        f.write(
            f"Registros OK: "
            f"{len(df_ok)}\n\n"
        )

        f.write(
            "STATUS\n"
        )

        f.write(
            "-" * 30 + "\n"
        )

        for status, count in status_counts.items():

            f.write(
                f"{status}: {count}\n"
            )

        f.write(
            "\nVARIABLES DE ESTADO\n"
        )

        f.write(
            "-" * 30 + "\n"
        )

        for col, info in state_report.items():

            f.write(
                f"{col}: "
                f"{json.dumps(info, ensure_ascii=False)}\n"
            )

    # ========================================================
    # 11. RESULTADO FINAL
    # ========================================================

    print("\n" + "=" * 70)
    print("RESULTADO DE LA AUDITORÍA")
    print("=" * 70)

    problems = []

    if len(df) != 339:

        problems.append(
            "Se esperaban 339 filas "
            f"y se recibieron {len(df)}."
        )

    if len(headers) != 46:

        problems.append(
            "La estructura actual debería "
            f"tener 46 columnas y se recibieron "
            f"{len(headers)}."
        )

    if missing_columns:

        problems.append(
            f"Faltan {len(missing_columns)} columnas."
        )

    if duplicates:

        problems.append(
            f"Hay {len(duplicates)} "
            "tickers duplicados."
        )

    if problems:

        print(
            "\n⚠ AUDITORÍA CON OBSERVACIONES\n"
        )

        for problem in problems:

            print(
                f" - {problem}"
            )

    else:

        print(
            "\n✓ ESTRUCTURA CORRECTA"
        )

        print(
            "✓ 339 registros recibidos"
        )

        print(
            "✓ 46 columnas recibidas"
        )

        print(
            "✓ Sin tickers duplicados"
        )

        print(
            "✓ Estructura CERE_CURRENT compatible"
        )

    print(
        "\nArchivos generados:"
    )

    print(
        f" - {OUTPUT_CSV}"
    )

    print(
        f" - {OUTPUT_JSON}"
    )

    print(
        f" - {OUTPUT_TXT}"
    )

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
