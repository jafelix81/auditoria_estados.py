import os
import json
import csv
import math
from datetime import datetime

import requests


# ============================================================
# CONFIGURACIÓN
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

EXPECTED_COLUMN_COUNT = len(EXPECTED_COLUMNS)

# Variables que describen el estado estadístico actual.
STATE_FEATURES = [
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

# Campos que deliberadamente todavía NO deben contener datos.
# Se llenarán cuando construyamos el histórico CERE.
CERE_PLACEHOLDER_FIELDS = [
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

PRICE_FIELDS = [
    "Price_Actual",
    "Price_Close",
]

DATE_FIELDS = [
    "DATA_FIRST_DATE",
    "DATA_LAST_DATE",
]

NUMERIC_METADATA_FIELDS = [
    "DATA_ATTEMPTS",
    "DATA_OBSERVATIONS",
]

EXPECTED_ACTIVE_STATUSES = {
    "OK",
}

KNOWN_STATUSES = {
    "OK",
    "DELISTED",
    "INACTIVE",
    "INSUFFICIENT",
    "ERROR",
}

OUTPUT_CSV = "auditoria_estados.csv"
OUTPUT_JSON = "auditoria_resumen.json"
OUTPUT_TXT = "auditoria_estados.txt"


# ============================================================
# UTILIDADES
# ============================================================

def print_separator():
    print("=" * 70)


def is_blank(value):
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip() == ""

    return False


def to_float(value):
    """
    Convierte un valor a float.
    Devuelve None si está vacío o no es numérico.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = float(value)

        if math.isfinite(number):
            return number

        return None

    text = str(value).strip()

    if text == "":
        return None

    try:
        number = float(text)

        if math.isfinite(number):
            return number

    except (TypeError, ValueError):
        pass

    return None


def parse_date(value):
    """
    Intenta interpretar una fecha proveniente de Google Sheets.
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    if not text:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    return None


# ============================================================
# LECTURA DE GOOGLE APPS SCRIPT
# ============================================================

def obtener_datos():
    """
    Lee CERE_CURRENT mediante GET.

    El endpoint utilizado es:

        .../exec?action=get_cere_current

    Importante:
    No utilizamos POST para esta operación.

    Apps Script puede devolver un HTTP 302 antes de entregar
    el JSON final. requests.get(... allow_redirects=True)
    sigue automáticamente esa redirección.
    """

    print_separator()
    print("Consultando Google Apps Script...")
    print_separator()

    url = os.environ.get("APPS_SCRIPT_URL", "").strip()

    if not url:
        raise RuntimeError(
            "No existe la variable de entorno APPS_SCRIPT_URL."
        )

    separator = "&" if "?" in url else "?"

    get_url = (
        url
        + separator
        + "action=get_cere_current"
    )

    try:
        respuesta = requests.get(
            get_url,
            timeout=120,
            allow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": "CERE-Auditoria/1.0",
            },
        )

    except requests.RequestException as error:
        raise RuntimeError(
            "No fue posible conectar con Google Apps Script:\n"
            + str(error)
        )

    print(f"HTTP inicial/final: {respuesta.status_code}")
    print(f"URL final: {respuesta.url}")

    if respuesta.status_code != 200:

        cuerpo = respuesta.text[:5000]

        raise RuntimeError(
            f"Apps Script respondió HTTP "
            f"{respuesta.status_code}:\n{cuerpo}"
        )

    try:
        data = respuesta.json()

    except ValueError:

        raise RuntimeError(
            "Apps Script respondió HTTP 200, "
            "pero la respuesta no es JSON válido.\n\n"
            "Respuesta recibida:\n"
            + respuesta.text[:5000]
        )

    if not isinstance(data, dict):

        raise RuntimeError(
            "La respuesta de Apps Script no tiene "
            "el formato JSON esperado."
        )

    if data.get("status") != "success":

        raise RuntimeError(
            "Apps Script reportó un error:\n"
            + json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            )
        )

    headers = data.get("headers", [])
    rows = data.get("rows", [])

    if not isinstance(headers, list):

        raise RuntimeError(
            "La respuesta no contiene una lista válida "
            "en 'headers'."
        )

    if not isinstance(rows, list):

        raise RuntimeError(
            "La respuesta no contiene una lista válida "
            "en 'rows'."
        )

    print(f"Hoja: {data.get('sheet')}")
    print(f"Filas recibidas: {data.get('row_count')}")
    print(f"Columnas recibidas: {data.get('column_count')}")

    return {
        "headers": headers,
        "rows": rows,
        "sheet": data.get("sheet"),
        "row_count": data.get("row_count"),
        "column_count": data.get("column_count"),
    }


# ============================================================
# CONVERSIÓN DE FILAS
# ============================================================

def convertir_filas(headers, rows):

    registros = []

    for index, row in enumerate(rows, start=2):

        if not isinstance(row, list):

            raise RuntimeError(
                f"La fila {index} no tiene formato de lista."
            )

        if len(row) != len(headers):

            raise RuntimeError(
                f"La fila {index} tiene {len(row)} valores, "
                f"pero existen {len(headers)} columnas."
            )

        registro = dict(
            zip(headers, row)
        )

        registro["_ROW_NUMBER"] = index

        registros.append(registro)

    return registros


# ============================================================
# AUDITORÍA DE ESTRUCTURA
# ============================================================

def auditar_estructura(headers, resumen, problemas):

    print_separator()
    print("1. ESTRUCTURA")
    print_separator()

    cantidad = len(headers)

    print(f"Columnas recibidas : {cantidad}")

    if cantidad == EXPECTED_COLUMN_COUNT:
        print(
            f"Columnas esperadas: {EXPECTED_COLUMN_COUNT}"
        )
    else:
        print(
            f"Columnas esperadas: {EXPECTED_COLUMN_COUNT}"
        )

        problemas.append(
            "La estructura no tiene la cantidad esperada "
            f"de columnas: esperadas={EXPECTED_COLUMN_COUNT}, "
            f"recibidas={cantidad}."
        )

    faltantes = [
        col
        for col in EXPECTED_COLUMNS
        if col not in headers
    ]

    adicionales = [
        col
        for col in headers
        if col not in EXPECTED_COLUMNS
    ]

    resumen["columnas_faltantes"] = faltantes
    resumen["columnas_adicionales"] = adicionales

    if faltantes:

        print("❌ Columnas faltantes:")

        for col in faltantes:
            print(f"   - {col}")

        problemas.append(
            "Existen columnas esperadas que no están presentes: "
            + ", ".join(faltantes)
        )

    else:

        print("✓ Todas las columnas esperadas están presentes.")

    if adicionales:

        print("⚠ Columnas adicionales:")

        for col in adicionales:
            print(f"   - {col}")

        problemas.append(
            "Existen columnas adicionales: "
            + ", ".join(adicionales)
        )

    else:

        print("✓ No existen columnas adicionales.")

    resumen["columnas_recibidas"] = cantidad
    resumen["columnas_esperadas"] = EXPECTED_COLUMN_COUNT


# ============================================================
# AUDITORÍA DE TICKERS
# ============================================================

def auditar_tickers(registros, resumen, problemas):

    print_separator()
    print("2. TICKERS")
    print_separator()

    tickers = [
        str(r.get("Ticker", "")).strip()
        for r in registros
    ]

    vacios = [
        i + 2
        for i, ticker in enumerate(tickers)
        if not ticker
    ]

    tickers_no_vacios = [
        ticker
        for ticker in tickers
        if ticker
    ]

    unicos = set(tickers_no_vacios)

    duplicados = sorted(
        {
            ticker
            for ticker in tickers_no_vacios
            if tickers_no_vacios.count(ticker) > 1
        }
    )

    print(f"Tickers totales: {len(tickers)}")
    print(f"Tickers únicos : {len(unicos)}")

    if duplicados:

        print("❌ Tickers duplicados:")

        for ticker in duplicados:
            print(f"   - {ticker}")

        problemas.append(
            "Existen tickers duplicados: "
            + ", ".join(duplicados)
        )

    else:

        print("✓ No hay tickers duplicados.")

    if vacios:

        print(
            f"❌ Hay {len(vacios)} filas con ticker vacío."
        )

        problemas.append(
            f"Existen {len(vacios)} filas con ticker vacío."
        )

    else:

        print("✓ No hay tickers vacíos.")

    resumen["tickers_totales"] = len(tickers)
    resumen["tickers_unicos"] = len(unicos)
    resumen["tickers_duplicados"] = duplicados
    resumen["tickers_vacios"] = len(vacios)


# ============================================================
# AUDITORÍA DE STATUS
# ============================================================

def auditar_status(registros, resumen, problemas):

    print_separator()
    print("3. STATUS")
    print_separator()

    conteo = {}

    for registro in registros:

        status = str(
            registro.get("STATUS", "")
        ).strip().upper()

        if not status:
            status = "VACIO"

        conteo[status] = conteo.get(status, 0) + 1

    orden_preferido = [
        "OK",
        "DELISTED",
        "INACTIVE",
        "INSUFFICIENT",
        "ERROR",
        "VACIO",
    ]

    for status in orden_preferido:

        if status in conteo:

            print(
                f"{status:<15}: "
                f"{conteo[status]}"
            )

    otros = sorted(
        set(conteo)
        - set(orden_preferido)
    )

    for status in otros:

        print(
            f"{status:<15}: "
            f"{conteo[status]}"
        )

    estados_desconocidos = [
        status
        for status in conteo
        if status not in KNOWN_STATUSES
    ]

    if estados_desconocidos:

        problemas.append(
            "Existen STATUS desconocidos: "
            + ", ".join(
                sorted(estados_desconocidos)
            )
        )

    if conteo.get("OK", 0) > 0:

        print(
            f"Registros OK: "
            f"{conteo.get('OK', 0)}"
        )

    resumen["status_counts"] = conteo


# ============================================================
# AUDITORÍA DE VARIABLES ESTADÍSTICAS
# ============================================================

def auditar_variables_estado(
    registros,
    resumen,
    problemas
):

    print_separator()
    print("4. VARIABLES ESTADÍSTICAS DEL ESTADO")
    print_separator()

    registros_ok = [
        r
        for r in registros
        if str(
            r.get("STATUS", "")
        ).strip().upper() == "OK"
    ]

    resumen["registros_ok"] = len(registros_ok)

    validacion = {}

    for campo in STATE_FEATURES:

        validos = 0
        faltantes = 0
        invalidos = 0
        valores = []

        for registro in registros_ok:

            valor = registro.get(campo)

            if is_blank(valor):

                faltantes += 1
                continue

            numero = to_float(valor)

            if numero is None:

                invalidos += 1
                continue

            validos += 1
            valores.append(numero)

        unicos = len(
            set(
                round(v, 12)
                for v in valores
            )
        )

        validacion[campo] = {
            "validos": validos,
            "faltantes": faltantes,
            "invalidos": invalidos,
            "unicos": unicos,
        }

        print(
            f"✓ {campo:<12} "
            f"válidos={validos:3d} "
            f"faltantes={faltantes:3d} "
            f"invalidos={invalidos:3d} "
            f"únicos={unicos:3d}"
        )

        if faltantes > 0:

            problemas.append(
                f"{campo}: existen {faltantes} "
                "valores faltantes entre registros OK."
            )

        if invalidos > 0:

            problemas.append(
                f"{campo}: existen {invalidos} "
                "valores no numéricos entre registros OK."
            )

    resumen["state_features"] = validacion


# ============================================================
# AUDITORÍA DE PRECIOS
# ============================================================

def auditar_precios(
    registros,
    resumen,
    problemas
):

    print_separator()
    print("5. PRECIOS")
    print_separator()

    registros_ok = [
        r
        for r in registros
        if str(
            r.get("STATUS", "")
        ).strip().upper() == "OK"
    ]

    validacion = {}

    for campo in PRICE_FIELDS:

        validos = 0
        faltantes = 0
        invalidos = 0
        no_positivos = 0

        for registro in registros_ok:

            valor = registro.get(campo)

            if is_blank(valor):

                faltantes += 1
                continue

            numero = to_float(valor)

            if numero is None:

                invalidos += 1
                continue

            if numero <= 0:

                no_positivos += 1
                continue

            validos += 1

        validacion[campo] = {
            "validos": validos,
            "faltantes": faltantes,
            "invalidos": invalidos,
            "no_positivos": no_positivos,
        }

        print(
            f"{campo:<15}: "
            f"válidos={validos:3d} "
            f"faltantes={faltantes:3d} "
            f"invalidos={invalidos:3d} "
            f"<=0={no_positivos:3d}"
        )

        if faltantes > 0:

            problemas.append(
                f"{campo}: hay {faltantes} "
                "valores faltantes."
            )

        if invalidos > 0:

            problemas.append(
                f"{campo}: hay {invalidos} "
                "valores no numéricos."
            )

        if no_positivos > 0:

            problemas.append(
                f"{campo}: hay {no_positivos} "
                "precios menores o iguales a cero."
            )

    resumen["prices"] = validacion


# ============================================================
# AUDITORÍA DE FECHAS Y DATOS DE YAHOO
# ============================================================

def auditar_datos_fuente(
    registros,
    resumen,
    problemas
):

    print_separator()
    print("6. INTEGRIDAD DE DATOS DE FUENTE")
    print_separator()

    registros_ok = [
        r
        for r in registros
        if str(
            r.get("STATUS", "")
        ).strip().upper() == "OK"
    ]

    resumen_fuente = {
        "first_date_valid": 0,
        "last_date_valid": 0,
        "attempts_valid": 0,
        "observations_valid": 0,
    }

    for registro in registros_ok:

        ticker = str(
            registro.get("Ticker", "")
        ).strip()

        for campo in DATE_FIELDS:

            valor = registro.get(campo)

            if is_blank(valor):

                problemas.append(
                    f"{ticker}: {campo} está vacío."
                )

                continue

            fecha = parse_date(valor)

            if fecha is None:

                problemas.append(
                    f"{ticker}: {campo} no tiene "
                    "una fecha válida."
                )

            else:

                if campo == "DATA_FIRST_DATE":
                    resumen_fuente["first_date_valid"] += 1

                elif campo == "DATA_LAST_DATE":
                    resumen_fuente["last_date_valid"] += 1

        for campo in NUMERIC_METADATA_FIELDS:

            valor = registro.get(campo)

            numero = to_float(valor)

            if numero is None:

                problemas.append(
                    f"{ticker}: {campo} no es numérico."
                )

                continue

            if campo == "DATA_ATTEMPTS":

                if numero < 1:

                    problemas.append(
                        f"{ticker}: DATA_ATTEMPTS "
                        "es menor que 1."
                    )

                else:

                    resumen_fuente[
                        "attempts_valid"
                    ] += 1

            elif campo == "DATA_OBSERVATIONS":

                if numero < 0:

                    problemas.append(
                        f"{ticker}: DATA_OBSERVATIONS "
                        "es negativo."
                    )

                else:

                    resumen_fuente[
                        "observations_valid"
                    ] += 1

    print(
        "DATA_FIRST_DATE válidos: "
        f"{resumen_fuente['first_date_valid']}/"
        f"{len(registros_ok)}"
    )

    print(
        "DATA_LAST_DATE válidos : "
        f"{resumen_fuente['last_date_valid']}/"
        f"{len(registros_ok)}"
    )

    print(
        "DATA_ATTEMPTS válidos   : "
        f"{resumen_fuente['attempts_valid']}/"
        f"{len(registros_ok)}"
    )

    print(
        "DATA_OBSERVATIONS válidos: "
        f"{resumen_fuente['observations_valid']}/"
        f"{len(registros_ok)}"
    )

    resumen["source_integrity"] = resumen_fuente


# ============================================================
# AUDITORÍA DE CAMPOS CERE FUTUROS
# ============================================================

def auditar_placeholders(
    registros,
    resumen,
    problemas
):

    print_separator()
    print("7. CAMPOS CERE PENDIENTES")
    print_separator()

    registros_ok = [
        r
        for r in registros
        if str(
            r.get("STATUS", "")
        ).strip().upper() == "OK"
    ]

    resultados = {}

    for campo in CERE_PLACEHOLDER_FIELDS:

        con_valor = 0
        vacios = 0

        for registro in registros_ok:

            valor = registro.get(campo)

            if is_blank(valor):

                vacios += 1

            else:

                con_valor += 1

        resultados[campo] = {
            "vacios": vacios,
            "con_valor": con_valor,
        }

        print(
            f"{campo:<15}: "
            f"{vacios:3d}/{len(registros_ok)} vacíos"
        )

        # Por ahora estos campos DEBEN estar vacíos.
        # Si alguno contiene información, lo reportamos
        # porque significaría que la etapa siguiente
        # ya fue ejecutada o que existe información inesperada.

        if con_valor > 0:

            problemas.append(
                f"{campo}: existen {con_valor} "
                "valores cuando todavía debería estar vacío."
            )

    resumen["cere_placeholders"] = resultados


# ============================================================
# AUDITORÍA DE RUN_ID
# ============================================================

def auditar_run_id(
    registros,
    resumen,
    problemas
):

    print_separator()
    print("8. CONSISTENCIA DEL RUN")
    print_separator()

    run_ids = sorted(
        {
            str(
                r.get("RUN_ID", "")
            ).strip()
            for r in registros
            if not is_blank(
                r.get("RUN_ID")
            )
        }
    )

    print(
        f"RUN_ID distintos: {len(run_ids)}"
    )

    for run_id in run_ids:

        print(
            f"   - {run_id}"
        )

    if len(run_ids) == 0:

        problemas.append(
            "No existe ningún RUN_ID válido."
        )

    elif len(run_ids) > 1:

        problemas.append(
            "CERE_CURRENT contiene más de un RUN_ID: "
            + ", ".join(run_ids)
        )

    resumen["run_ids"] = run_ids


# ============================================================
# GENERAR CSV
# ============================================================

def generar_csv(
    headers,
    registros
):

    with open(
        OUTPUT_CSV,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as archivo:

        writer = csv.DictWriter(
            archivo,
            fieldnames=headers,
            extrasaction="ignore",
        )

        writer.writeheader()

        for registro in registros:

            writer.writerow(
                {
                    campo: registro.get(
                        campo,
                        ""
                    )
                    for campo in headers
                }
            )


# ============================================================
# GENERAR TXT
# ============================================================

def generar_txt(
    resumen,
    problemas
):

    with open(
        OUTPUT_TXT,
        "w",
        encoding="utf-8",
    ) as archivo:

        archivo.write(
            "AUDITORÍA CERE — CERE_CURRENT\n"
        )

        archivo.write(
            "=" * 70
            + "\n\n"
        )

        archivo.write(
            "RESULTADO\n"
        )

        archivo.write(
            "-" * 70
            + "\n"
        )

        if problemas:

            archivo.write(
                "AUDITORÍA CON OBSERVACIONES\n\n"
            )

            for problema in problemas:

                archivo.write(
                    "- "
                    + problema
                    + "\n"
                )

        else:

            archivo.write(
                "AUDITORÍA COMPLETADA "
                "SIN OBSERVACIONES\n"
            )

        archivo.write(
            "\n\nRESUMEN\n"
        )

        archivo.write(
            "-" * 70
            + "\n"
        )

        archivo.write(
            json.dumps(
                resumen,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        archivo.write("\n")


# ============================================================
# GENERAR JSON
# ============================================================

def generar_json(
    resumen,
    problemas
):

    resultado = dict(resumen)

    resultado["audit_status"] = (
        "OK"
        if not problemas
        else "OBSERVATIONS"
    )

    resultado["problems"] = problemas

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8",
    ) as archivo:

        json.dump(
            resultado,
            archivo,
            ensure_ascii=False,
            indent=2,
            default=str,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print_separator()
    print("AUDITORÍA CERE — LECTURA DE CERE_CURRENT")
    print_separator()

    problemas = []

    resumen = {
        "audit_timestamp_utc": (
            datetime.utcnow().isoformat()
            + "Z"
        ),
        "expected_column_count": (
            EXPECTED_COLUMN_COUNT
        ),
        "expected_columns": (
            EXPECTED_COLUMNS
        ),
    }

    # --------------------------------------------------------
    # 1. Obtener datos
    # --------------------------------------------------------

    data = obtener_datos()

    headers = data["headers"]
    rows = data["rows"]

    resumen["sheet"] = data.get("sheet")
    resumen["row_count_reported"] = (
        data.get("row_count")
    )
    resumen["column_count_reported"] = (
        data.get("column_count")
    )

    # --------------------------------------------------------
    # 2. Convertir filas
    # --------------------------------------------------------

    registros = convertir_filas(
        headers,
        rows
    )

    resumen["row_count_local"] = len(
        registros
    )

    # --------------------------------------------------------
    # 3. Auditorías
    # --------------------------------------------------------

    auditar_estructura(
        headers,
        resumen,
        problemas
    )

    auditar_tickers(
        registros,
        resumen,
        problemas
    )

    auditar_status(
        registros,
        resumen,
        problemas
    )

    auditar_variables_estado(
        registros,
        resumen,
        problemas
    )

    auditar_precios(
        registros,
        resumen,
        problemas
    )

    auditar_datos_fuente(
        registros,
        resumen,
        problemas
    )

    auditar_placeholders(
        registros,
        resumen,
        problemas
    )

    auditar_run_id(
        registros,
        resumen,
        problemas
    )

    # --------------------------------------------------------
    # 4. Resultado final
    # --------------------------------------------------------

    print_separator()
    print("RESULTADO DE LA AUDITORÍA")
    print_separator()

    if problemas:

        print(
            "⚠ AUDITORÍA CON OBSERVACIONES"
        )

        for problema in problemas:

            print(
                f"- {problema}"
            )

    else:

        print(
            "✓ AUDITORÍA COMPLETADA "
            "SIN OBSERVACIONES"
        )

    # --------------------------------------------------------
    # 5. Generar archivos
    # --------------------------------------------------------

    generar_csv(
        headers,
        registros
    )

    generar_json(
        resumen,
        problemas
    )

    generar_txt(
        resumen,
        problemas
    )

    print()
    print("Archivos generados:")
    print(f"- {OUTPUT_CSV}")
    print(f"- {OUTPUT_JSON}")
    print(f"- {OUTPUT_TXT}")

    print_separator()

    # --------------------------------------------------------
    # 6. Exit code
    # --------------------------------------------------------

    if problemas:

        raise SystemExit(1)

    raise SystemExit(0)


if __name__ == "__main__":
    main()
