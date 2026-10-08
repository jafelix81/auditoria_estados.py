import io
import os
import requests
import pandas as pd
import numpy as np

# ============================================================
# CONFIGURACIÓN
# ============================================================

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "").strip()

if not APPS_SCRIPT_URL:
    raise RuntimeError(
        "Falta la variable de entorno APPS_SCRIPT_URL."
    )

# Variables estadísticas que queremos auditar
VARIABLES = [
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
]

# Estados que consideramos válidos para la auditoría
STATUS_VALIDOS = {"OK"}


# ============================================================
# FUNCIONES
# ============================================================

def obtener_datos():
    """
    Solicita a Apps Script los datos actuales de CERE_CURRENT.

    El endpoint debe aceptar:
        {"action": "get_cere_current"}
    """

    payload = {
        "action": "get_cere_current"
    }

    response = requests.post(
        APPS_SCRIPT_URL,
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") != "success":
        raise RuntimeError(
            f"Apps Script respondió con error: {data}"
        )

    rows = data.get("rows", [])

    if not rows:
        raise RuntimeError(
            "Apps Script no devolvió filas."
        )

    return pd.DataFrame(rows)


def convertir_numericas(df):
    """
    Convierte las variables estadísticas a formato numérico.
    """

    for col in VARIABLES:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

    return df


def resumen_variable(series):
    """
    Calcula estadísticas robustas para una variable.
    """

    s = pd.to_numeric(series, errors="coerce")

    total = len(s)
    missing = int(s.isna().sum())

    finite = s[np.isfinite(s)]

    nan_count = int(s.isna().sum())

    if len(finite) == 0:
        return {
            "n": total,
            "validos": 0,
            "missing": missing,
            "nan_inf": nan_count,
            "min": np.nan,
            "p01": np.nan,
            "p05": np.nan,
            "p25": np.nan,
            "mediana": np.nan,
            "p75": np.nan,
            "p95": np.nan,
            "p99": np.nan,
            "max": np.nan,
        }

    return {
        "n": total,
        "validos": len(finite),
        "missing": missing,
        "nan_inf": nan_count,
        "min": finite.min(),
        "p01": finite.quantile(0.01),
        "p05": finite.quantile(0.05),
        "p25": finite.quantile(0.25),
        "mediana": finite.median(),
        "p75": finite.quantile(0.75),
        "p95": finite.quantile(0.95),
        "p99": finite.quantile(0.99),
        "max": finite.max(),
    }


def detectar_outliers(series):
    """
    Detecta outliers mediante regla IQR.

    No significa que sean errores.
    Solamente los marca para revisión.
    """

    s = pd.to_numeric(series, errors="coerce")
    s = s[np.isfinite(s)]

    if len(s) < 10:
        return 0, np.nan, np.nan

    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)

    iqr = q3 - q1

    if iqr == 0:
        return 0, q1, q3

    lower = q1 - 3.0 * iqr
    upper = q3 + 3.0 * iqr

    count = int(((s < lower) | (s > upper)).sum())

    return count, lower, upper


def revisar_consistencia(df):
    """
    Revisa condiciones básicas que sí podemos considerar
    potencialmente problemáticas.
    """

    problemas = []

    # Volatilidades no pueden ser negativas
    for col in [
        "Vol5",
        "Vol20",
        "Vol60",
        "Vol252",
    ]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            negativos = int((s < 0).sum())

            if negativos:
                problemas.append(
                    f"{col}: {negativos} valores negativos"
                )

    # Ratios de volatilidad deberían ser positivos
    for col in [
        "VolRatio20",
        "VolRatio60",
    ]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            invalidos = int((s <= 0).sum())

            if invalidos:
                problemas.append(
                    f"{col}: {invalidos} valores <= 0"
                )

    # Precios deben ser positivos
    for col in [
        "Price_Actual",
        "Price_Close",
    ]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            invalidos = int((s <= 0).sum())

            if invalidos:
                problemas.append(
                    f"{col}: {invalidos} valores <= 0"
                )

    # Retornos extremadamente grandes.
    # No se consideran automáticamente errores.
    # Solo se reportan.
    for col in [
        "R1",
        "R5",
        "R20",
        "R60",
        "R120",
    ]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            extremos = int(
                (np.abs(s) > 2.0).sum()
            )

            if extremos:
                problemas.append(
                    f"{col}: {extremos} valores con "
                    f"|retorno| > 200%"
                )

    return problemas


# ============================================================
# EJECUCIÓN
# ============================================================

print("=" * 70)
print("🔬 CERE — AUDITORÍA DE ESTADOS")
print("=" * 70)

print("\n📥 Obteniendo CERE_CURRENT desde Google Sheets...")

df = obtener_datos()

print(f"Filas recibidas: {len(df)}")

# ------------------------------------------------------------
# Filtrar solamente OK
# ------------------------------------------------------------

if "STATUS" not in df.columns:
    raise RuntimeError(
        "La columna STATUS no existe en CERE_CURRENT."
    )

df_ok = df[
    df["STATUS"].astype(str).str.upper().isin(STATUS_VALIDOS)
].copy()

print(f"Filas STATUS=OK: {len(df_ok)}")

# ------------------------------------------------------------
# Verificación de columnas
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("📋 VERIFICACIÓN DE VARIABLES")
print("=" * 70)

faltantes = []

for col in VARIABLES:
    if col not in df_ok.columns:
        faltantes.append(col)

if faltantes:
    print("\n❌ VARIABLES FALTANTES:")
    for col in faltantes:
        print(f"  • {col}")

    raise RuntimeError(
        "Faltan variables necesarias para la auditoría."
    )

print("✅ Todas las variables requeridas están presentes.")

# ------------------------------------------------------------
# Conversión numérica
# ------------------------------------------------------------

df_ok = convertir_numericas(df_ok)

# ------------------------------------------------------------
# RESUMEN ESTADÍSTICO
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("📊 RESUMEN ESTADÍSTICO")
print("=" * 70)

resultados = []

for col in VARIABLES:

    stats = resumen_variable(df_ok[col])

    outliers, lower, upper = detectar_outliers(
        df_ok[col]
    )

    stats["variable"] = col
    stats["outliers_IQR_3x"] = outliers
    stats["limite_inferior"] = lower
    stats["limite_superior"] = upper

    resultados.append(stats)

    print(
        f"\n{col}"
    )

    print(
        f"  N válido      : {stats['validos']}"
    )

    print(
        f"  Missing       : {stats['missing']}"
    )

    print(
        f"  Min           : {stats['min']:.6g}"
    )

    print(
        f"  P01           : {stats['p01']:.6g}"
    )

    print(
        f"  P05           : {stats['p05']:.6g}"
    )

    print(
        f"  P25           : {stats['p25']:.6g}"
    )

    print(
        f"  Mediana       : {stats['mediana']:.6g}"
    )

    print(
        f"  P75           : {stats['p75']:.6g}"
    )

    print(
        f"  P95           : {stats['p95']:.6g}"
    )

    print(
        f"  P99           : {stats['p99']:.6g}"
    )

    print(
        f"  Max           : {stats['max']:.6g}"
    )

    print(
        f"  Outliers IQR  : {outliers}"
    )

# ------------------------------------------------------------
# CONSISTENCIA
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("🧪 PRUEBAS DE CONSISTENCIA")
print("=" * 70)

problemas = revisar_consistencia(df_ok)

if not problemas:
    print("✅ No se encontraron inconsistencias básicas.")
else:
    print(
        f"⚠️ Se encontraron {len(problemas)} "
        f"observaciones para revisar:"
    )

    for p in problemas:
        print(f"  • {p}")

# ------------------------------------------------------------
# COMPLETITUD POR VARIABLE
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("📈 COMPLETITUD")
print("=" * 70)

for col in VARIABLES:

    s = pd.to_numeric(
        df_ok[col],
        errors="coerce"
    )

    validos = int(
        np.isfinite(s).sum()
    )

    porcentaje = (
        validos / len(df_ok) * 100
        if len(df_ok) else 0
    )

    print(
        f"{col:15s} "
        f"{validos:3d}/{len(df_ok):3d} "
        f"({porcentaje:6.2f}%)"
    )

# ------------------------------------------------------------
# TOP EXTREMOS
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("🚨 EXTREMOS PARA REVISIÓN")
print("=" * 70)

for col in [
    "VolRatio20",
    "VolRatio60",
    "Skew20",
    "Kurt20",
    "AC1",
]:

    if col not in df_ok.columns:
        continue

    temp = df_ok[
        ["Ticker", col]
    ].copy()

    temp[col] = pd.to_numeric(
        temp[col],
        errors="coerce"
    )

    temp = temp[
        np.isfinite(temp[col])
    ]

    if temp.empty:
        continue

    temp["abs"] = temp[col].abs()

    top = temp.sort_values(
        "abs",
        ascending=False
    ).head(10)

    print(f"\n{col} — 10 valores más extremos:")

    for _, row in top.iterrows():
        print(
            f"  {row['Ticker']:8s} "
            f"{row[col]: .6g}"
        )

# ------------------------------------------------------------
# RESULTADO FINAL
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("🏁 RESULTADO DE LA AUDITORÍA")
print("=" * 70)

print(
    f"Universo recibido : {len(df)}"
)

print(
    f"STATUS=OK         : {len(df_ok)}"
)

print(
    f"Variables auditadas: {len(VARIABLES)}"
)

if not problemas:
    print(
        "Estado general    : ✅ SIN INCONSISTENCIAS BÁSICAS"
    )
else:
    print(
        "Estado general    : ⚠️ REQUIERE REVISIÓN"
    )

print("=" * 70)
