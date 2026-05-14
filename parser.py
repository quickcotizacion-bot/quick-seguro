"""
parser.py — Lee PDFs de Ciminari Brokers y extrae datos estructurados.
Soporta múltiples PDFs por cliente (merge automático).
"""

import pdfplumber
import re
import math

# ─── ORDEN CANÓNICO DE ASEGURADORAS ───────────────────────────────────────────

INSURER_ORDER = ['zurich', 'sancor', 'swiss', 'allianz', 'fed_patronal', 'experta', 'mercantil', 'san_cristobal']

# ─── DETECCIÓN DE ASEGURADORAS ────────────────────────────────────────────────

# ─── IDENTIFICACIÓN DE ASEGURADORA POR NOMBRE DE COBERTURA ───────────────────
# Los logos de las aseguradoras son imágenes en el PDF (no texto legible).
# Identificamos cada cobertura por sus nombres de plan, únicos por aseguradora.

def identify_insurer_from_coverage(coverage_name):
    """
    Dado el nombre de una cobertura, retorna el insurer_key correspondiente.
    Retorna None si no reconoce la cobertura.
    """
    cu = coverage_name.upper().strip()

    # ── San Cristóbal ──────────────────────────────────────────────────────────
    if re.match(r'CPLUS', cu) or cu.startswith('C PLUS') or cu.startswith('C+'):
        return 'san_cristobal'
    if re.match(r'CM\b', cu) or cu.startswith('CM -'):
        return 'san_cristobal'
    if re.match(r'D\d{2,3}\s*[-–]', cu) and 'TODO RIESGO' in cu:
        return 'san_cristobal'
    if re.match(r'AUTO MEGA', cu) or re.match(r'AUTO EXTRA', cu) or re.match(r'AUTO PLUS', cu):
        return 'san_cristobal'

    # ── Sancor ────────────────────────────────────────────────────────────────
    if 'MAX TOTALES' in cu:
        return 'sancor'
    if 'PREMIUM MAX' in cu:
        return 'sancor'
    if 'AUTO TODO RIESGO' in cu:
        return 'sancor'

    # ── Swiss Medical ─────────────────────────────────────────────────────────
    if re.search(r'\bTC25\b', cu) or re.search(r'\bTC4\b', cu):
        return 'swiss'
    if re.match(r'SSN\s*G\s*TC', cu):
        return 'swiss'
    if re.match(r'TR\d\b', cu) or re.match(r'SSN\s*G\s*TR', cu):
        return 'swiss'

    # ── Allianz ───────────────────────────────────────────────────────────────
    if re.match(r'C2\s*[-–]', cu) or 'CLASICA SEGMENTADA' in cu:
        return 'allianz'
    if re.match(r'C4\s*[-–]', cu) or 'DT INC' in cu:
        return 'allianz'
    if 'TR C/FRANQ' in cu and 'VALOR DEL' in cu:
        return 'allianz'
    if 'TR C/FRANQ' in cu and 'VALOR DEL' in cu.replace('VEHÍCULO', 'VEHICULO'):
        return 'allianz'

    # ── Experta ───────────────────────────────────────────────────────────────
    if 'TERCEROS COMPLETOS L' in cu:
        return 'experta'
    if 'TERCEROS COMPLETO XL' in cu:
        return 'experta'
    if 'TODO RIESGO FRANQ' in cu and 'VARIABLE' in cu:
        return 'experta'

    # ── Mercantil Andina ──────────────────────────────────────────────────────
    if re.search(r'\bM\s*PLUS\b', cu) and 'TERCEROS' in cu:
        return 'mercantil'
    if re.search(r'\bM\s*B[ÁA]SICA\b', cu):
        return 'mercantil'
    if re.match(r'D2\s*[-–]', cu) and 'TODO RIESGO' in cu:
        return 'mercantil'

    # ── Zurich ────────────────────────────────────────────────────────────────
    if re.match(r'CG\s*[-–]', cu) or ('TERCEROS PREMIUM CON GRANIZO' in cu and 'COMPLETO' not in cu):
        return 'zurich'
    if 'TODO RIESGO' in cu and 'PLAN DV' in cu:
        return 'zurich'
    if 'TODO RIESGO' in cu and re.search(r'\bDV\s*\d', cu):
        return 'zurich'

    # ── Federación Patronal ───────────────────────────────────────────────────
    if re.match(r'CF\s*[-–]', cu) or 'RC PTAC' in cu:
        return 'fed_patronal'

    return None  # no reconocida

# Líneas que no son coberturas con precio
SKIP_PATTERNS = [
    'Refacturacion:', 'Plan de pago:', 'Suma asegurada:', 'Cobertura', 'Costo',
    'Presupuesto Automotor', 'Página', 'Cerrito', 'www.ciminari', 'ciminaribrokers',
    'marcadas con *', 'Las coberturas', 'Estimado', 'Datos del', 'Fecha nacimiento',
    'Provincia:', 'Forma de pago:', 'Tipo IVA:', 'Tipo uso', 'Código Postal',
    'Marca:', 'Modelo:', 'Año:', 'Código Infoauto', 'GNC:', 'Refactur',
]

# ─── UTILIDADES DE PRECIO Y PORCENTAJE ────────────────────────────────────────

def extract_price(text):
    """Ciminari $65.254,00->65254  |  SC propio $ 129.838->129838"""
    m = re.search(r'\$([ ]*)([\d.]+,[0-9]{2})', text)
    if m:
        s = m.group(2).replace('.', '').replace(',', '.')
        val = float(s)
        frac = val - int(val)
        return math.ceil(val) if frac >= 0.5 else int(round(val))
    m = re.search(r'\$[ ]*(\d{1,3}(?:[.]\d{3})+)', text)
    if m:
        val = int(m.group(1).replace('.', ''))
        return val if val >= 1000 else None
    return None

def extract_all_prices_from_line(text):
    """Extrae todos los precios de una linea."""
    prices = []
    for m in re.finditer(r'\$[ ]*([\d.]+,[0-9]{2})', text):
        s = m.group(1).replace('.', '').replace(',', '.')
        val = float(s)
        frac = val - int(val)
        prices.append(math.ceil(val) if frac >= 0.5 else int(round(val)))
    if prices:
        return prices
    for m in re.finditer(r'\$[ ]*(\d{1,3}(?:[.]\d{3})+)', text):
        val = int(m.group(1).replace('.', ''))
        if val >= 1000:
            prices.append(val)
    return prices

def extract_pct(text):
    """'3,5%' → 3.5  |  '3%' → 3.0  |  None si no encuentra"""
    m = re.search(r'(\d+)[,.](\d+)\s*%', text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r'(\d+)\s*%', text)
    if m:
        return float(m.group(1))
    return None

def format_pct(pct):
    """3.0 → '3%'  |  2.5 → '2,50%'  |  3.5 → '3,50%'"""
    if pct == int(pct):
        return f"{int(pct)}%"
    return f"{pct:.2f}%".replace('.', ',')

# ─── SELECCIÓN TR POR ASEGURADORA ─────────────────────────────────────────────

def closest_to_3(options):
    """options: [(pct, price), ...] → (pct, price) más cercano a 3%. Empate → mayor."""
    if not options:
        return None
    best, best_dist = None, float('inf')
    for pct, price in options:
        dist = abs(pct - 3.0)
        if dist < best_dist or (dist == best_dist and best and pct > best[0]):
            best, best_dist = (pct, price), dist
    return best

def select_tr(insurer, options):
    """Aplica la regla específica de cada aseguradora para elegir TR."""
    if not options:
        return None
    pct_map = {p: v for p, v in options}

    if insurer == 'san_cristobal':
        for p in [2.5, 3.0, 5.0, 2.0, 3.5]:
            if p in pct_map:
                return (p, pct_map[p])
        return closest_to_3(options)

    elif insurer == 'sancor':
        return (3.0, pct_map[3.0]) if 3.0 in pct_map else closest_to_3(options)

    elif insurer == 'allianz':
        return (5.0, pct_map[5.0]) if 5.0 in pct_map else closest_to_3(options)

    elif insurer == 'swiss':
        # Siempre TR1 (label "3%" por convención). options guardadas como pct=3.0 para TR1.
        tr1 = [(p, v) for p, v in options if p == 3.0]
        return tr1[0] if tr1 else options[0]

    elif insurer == 'experta':
        e2 = [o for o in options if o[0] == 2.0]
        e5 = [o for o in options if o[0] == 5.0]
        if e2 and e5:
            return e2[0]
        return closest_to_3(options)

    else:
        return closest_to_3(options)

# ─── EXTRACCIÓN DE TEXTO DEL PDF ──────────────────────────────────────────────

def extract_text(pdf_path):
    """Extrae texto. Si el PDF es imagen, usa OCR como fallback."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:2]:
            t = page.extract_text()
            if t:
                text += t + "\n"
    if text.strip():
        return text
    # Fallback OCR (para PDFs de formato propio como San Cristóbal)
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(pdf_path, dpi=200)
        for img in images[:2]:
            text += pytesseract.image_to_string(img, lang='spa') + "\n"
    except Exception as e:
        print(f'  ⚠️  OCR fallback error: {e}')
    return text

# ─── PARSEO DE CLIENTE Y VEHÍCULO ─────────────────────────────────────────────

def parse_client_vehicle(text):
    """Extrae nombre del cliente y datos del vehículo."""
    client_name = None
    vehicle_make = None

    vehicle_model = None
    for line in text.split('\n'):
        line = line.strip()

        if 'Estimado' in line and not client_name:
            m = re.search(r'Estimado\s+(.+)', line)
            if m:
                raw = m.group(1).strip()
                client_name = raw.title().replace(' ,', ',')

        if 'Marca:' in line:
            m = re.search(r'Marca:\s*(\S+)', line)
            if m:
                vehicle_make = m.group(1).strip().upper()
            # "Modelo: FOCUS L/08..." → extraer nombre comercial (primer token)
            m2 = re.search(r'Modelo:\s*(\S+)', line)
            if m2:
                vehicle_model = m2.group(1).strip().upper()

        # Formato SC propio: "Modelo: PEUGEOT 3008 - 2.0 HDI..."
        if 'Modelo:' in line and not vehicle_make:
            m = re.search(r'Modelo:\s*(\S+)\s+(\S+)', line)
            if m:
                vehicle_make  = m.group(1).strip().upper()
                vehicle_model = m.group(2).strip().upper()

    # Banner: "FORD FOCUS", "PEUGEOT 2008", etc.
    banner = vehicle_make
    if vehicle_model:
        banner = f"{vehicle_make} {vehicle_model}"

    return client_name, banner

# ─── PARSEO DE COBERTURAS Y PRECIOS ───────────────────────────────────────────

def parse_coverage_lines(text):
    """
    Parsea coberturas con precio del texto extraído.
    Maneja:
      - Formato Ciminari: precio en la misma línea que la cobertura
      - Formato SC propio (imagen/OCR): dos columnas CM/C+ con precios
        en la misma línea pero nombres en líneas anteriores
    Retorna [(insurer_key, coverage_name, price), ...]
    """
    results = []
    lines = text.split('\n')
    sc_two_col = False  # True cuando detectamos header CM + C+ del formato SC

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if any(s in line for s in SKIP_PATTERNS):
            continue

        cu = line.upper()

        # ── Detectar header del formato SC dos columnas ───────────────────────
        # La línea contiene tanto "CM:" como "C+:" side-by-side
        if 'CM:' in cu and ('C+:' in cu or 'C+' in cu or 'CPLUS' in cu):
            sc_two_col = True
            continue

        # ── Precio en la línea ────────────────────────────────────────────────
        price = extract_price(line)
        if not price:
            continue

        all_prices = extract_all_prices_from_line(line)

        # ── Caso SC dos columnas: dos precios en una línea ───────────────────
        if sc_two_col and len(all_prices) == 2:
            # Columna izquierda = CM (TCF), columna derecha = C+/CPLUS (TCB)
            results.append(('san_cristobal', 'CM',    all_prices[0]))
            results.append(('san_cristobal', 'CPLUS', all_prices[1]))
            sc_two_col = False
            continue

        # ── Caso SC una sola cobertura en el frame ───────────────────────────
        # (para cuando solo aparece CM o solo CPLUS en formato propio SC)
        if len(all_prices) == 1 and sc_two_col:
            # look back to determine which plan
            for back_line in lines[max(0, i-10):i]:
                bcu = back_line.upper().strip()
                if bcu.startswith('C+') or bcu.startswith('CPLUS'):
                    results.append(('san_cristobal', 'CPLUS', price))
                    break
                if bcu.startswith('CM'):
                    results.append(('san_cristobal', 'CM', price))
                    break
            sc_two_col = False
            continue

        # ── Caso Ciminari: precio y cobertura en la misma línea ──────────────
        cov = re.sub(r'\$[\d\.\s,]+', '', line).strip().strip('-:').strip()
        cov = re.sub(r'\s+', ' ', cov)
        if len(cov) >= 2:
            insurer = identify_insurer_from_coverage(cov)
            if insurer:
                results.append((insurer, cov, price))

    return results

# ─── CONSTRUCCIÓN DE FILAS ────────────────────────────────────────────────────

def build_rows(coverage_lines):
    """
    coverage_lines: [(insurer, coverage_name, price), ...]
    Retorna dict {insurer_key: {logo_key, tcb, tcf, tr, fr}}
    aplicando todas las reglas del handoff.
    """
    by_insurer = {}
    for ins, cov, price in coverage_lines:
        by_insurer.setdefault(ins, []).append((cov, price))

    rows = {}

    for insurer, coverages in by_insurer.items():
        tcb = tcf = tr_val = fr_str = None
        tr_options = []

        for cov, price in coverages:
            cu = cov.upper()

            # ── San Cristóbal ──────────────────────────────────────────────────
            if insurer == 'san_cristobal':
                if re.match(r'CPLUS', cu):
                    tcb = price
                elif re.match(r'CM\b', cu) or cu.startswith('CM -'):
                    tcf = price
                elif 'TODO RIESGO' in cu or re.match(r'D\d+\s*[-–]', cu):
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))

            # ── Sancor ────────────────────────────────────────────────────────
            elif insurer == 'sancor':
                if 'MAX TOTALES' in cu:
                    tcb = price
                elif 'PREMIUM MAX' in cu:
                    tcf = price
                elif 'TODO RIESGO' in cu or 'AUTO TODO' in cu:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))

            # ── Swiss Medical ─────────────────────────────────────────────────
            elif insurer == 'swiss':
                if 'TC25' in cu:
                    tcb = price
                elif 'TC4' in cu:
                    tcf = price
                elif re.search(r'\bTR\d\b', cu) or 'TODO RIESGO' in cu:
                    # TR1 siempre → representamos como pct=3.0 (label "3%" por convención)
                    if 'TR1' in cu:
                        tr_options.append((3.0, price))
                    elif 'TR5' in cu:
                        tr_options.append((5.0, price))
                    else:
                        pct = extract_pct(cov) or 3.0
                        tr_options.append((pct, price))

            # ── Allianz ───────────────────────────────────────────────────────
            elif insurer == 'allianz':
                if re.search(r'\bC2\b', cu):
                    tcb = price
                elif re.search(r'\bC4\b', cu):
                    tcf = price
                elif ('TR' in cu or 'FRANQ' in cu) and 'VALOR' in cu:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))

            # ── Experta ───────────────────────────────────────────────────────
            elif insurer == 'experta':
                if ('COMPLETOS L' in cu or cu.endswith(' L')) and 'TODO RIESGO' not in cu:
                    tcb = price
                elif 'XL' in cu and 'TODO RIESGO' not in cu and 'FRANQ' not in cu:
                    tcf = price
                elif 'TODO RIESGO' in cu or 'FRANQ. VARIABLE' in cu or 'FRANQ VARIABLE' in cu:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))

            # ── Mercantil Andina ──────────────────────────────────────────────
            elif insurer == 'mercantil':
                if re.search(r'M\s*B[ÁA]SICA', cu) or 'MBASICA' in cu:
                    tcb = price
                elif 'M PLUS' in cu or 'MPLUS' in cu:
                    tcf = price
                elif 'TODO RIESGO' in cu or re.match(r'D2\b', cu):
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))

            # ── Zurich ────────────────────────────────────────────────────────
            elif insurer == 'zurich':
                if re.search(r'\bCG\b', cu) and 'TODO RIESGO' not in cu:
                    tcf = price
                elif 'TODO RIESGO' in cu or re.search(r'\bDV\s*\d', cu):
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))

            # ── Federación Patronal ───────────────────────────────────────────
            elif insurer == 'fed_patronal':
                if re.search(r'\bCF\b', cu) or 'RC PTAC' in cu:
                    tcf = price
                elif 'TODO RIESGO' in cu:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))

        # Seleccionar mejor TR
        best_tr = select_tr(insurer, tr_options)
        if best_tr:
            tr_val = best_tr[1]
            # Swiss: siempre mostrar "3%" aunque la franquicia real sea TR1
            if insurer == 'swiss':
                fr_str = "3%"
            else:
                fr_str = format_pct(best_tr[0])

        # Regla universal: si TCF < TCB → TCB vacío
        if tcb and tcf and tcf < tcb:
            tcb = None

        rows[insurer] = {
            'logo_key': insurer,
            'tcb': tcb,
            'tcf': tcf,
            'tr': tr_val,
            'fr': fr_str,
        }

    return rows

# ─── FUNCIÓN PRINCIPAL: PARSEAR Y MERGEAR N PDFs ──────────────────────────────

def parse_and_merge(pdf_paths):
    """
    Parsea 1 o más PDFs del mismo cliente y retorna datos unificados.

    Regla duplicados: si la misma aseguradora aparece en dos PDFs,
    se queda con la más barata (comparando TCF, o TCB si no hay TCF).

    Retorna: (client_name, vehicle_make, rows_list, has_tr)
    """
    all_rows = {}
    client_name = None
    vehicle_make = None

    for path in pdf_paths:
        text = extract_text(path)
        name, make = parse_client_vehicle(text)
        coverage_lines = parse_coverage_lines(text)
        rows = build_rows(coverage_lines)

        if client_name is None and name:
            client_name = name
        if vehicle_make is None and make:
            vehicle_make = make

        for key, row in rows.items():
            if key in all_rows:
                # Duplicado: quedarse con el más barato
                existing_price = all_rows[key].get('tcf') or all_rows[key].get('tcb') or float('inf')
                new_price      = row.get('tcf') or row.get('tcb') or float('inf')
                if new_price < existing_price:
                    all_rows[key] = row
            else:
                all_rows[key] = row

    # Ordenar según INSURER_ORDER
    rows_list = [all_rows[k] for k in INSURER_ORDER if k in all_rows]

    has_tr = any(r.get('tr') is not None for r in rows_list)

    return client_name, vehicle_make, rows_list, has_tr
