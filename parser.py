"""
parser.py — Lee PDFs de Ciminari Brokers + formatos propios de aseguradoras.
Soporta múltiples PDFs por cliente (merge automático).
"""
 
import pdfplumber
import re
import math
 
# ─── ORDEN CANÓNICO DE ASEGURADORAS ───────────────────────────────────────────
 
INSURER_ORDER = ['zurich', 'sancor', 'swiss', 'allianz', 'fed_patronal', 'experta', 'mercantil', 'san_cristobal']
 
# ─── UTILIDADES DE PRECIO Y PORCENTAJE ────────────────────────────────────────
 
def extract_price(text):
    """Ciminari $65.254,00->65254  |  SC propio $ 129.838->129838"""
    m = re.search(r'\$[ ]*([\d.]+,[0-9]{2})', text)
    if m:
        s = m.group(1).replace('.', '').replace(',', '.')
        val = float(s)
        frac = val - int(val)
        return math.ceil(val) if frac >= 0.5 else int(round(val))
    m = re.search(r'\$[ ]*(\d{1,3}(?:[.]\d{3})+)(?![,\d])', text)
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
 
def extract_sc_amounts(text):
    """
    Extrae montos para el formato OCR de San Cristóbal, donde el OCR de Render
    a veces NO detecta el símbolo $. Busca números tipo 214.251 o 146.625
    (1 a 3 dígitos + grupos de .XXX) que representan precios de cuota.
    Ignora años (2016, 2026), porcentajes y números cortos.
    """
    amounts = []
    # Primero intentar con $ (más confiable)
    with_dollar = extract_all_prices_from_line(text)
    if with_dollar:
        return with_dollar
    # Sin $: números con separador de miles (ej. 214.251, 146.625, 145.435)
    for m in re.finditer(r'(?<![\d.])(\d{1,3}(?:\.\d{3})+)(?![\d])', text):
        val = int(m.group(1).replace('.', ''))
        if val >= 10000:  # precios de cuota son >= 5 dígitos
            amounts.append(val)
    return amounts
 
def extract_pct(text):
    """'3,5%' → 3.5  |  '3%' → 3.0"""
    m = re.search(r'(\d+)[,.](\d+)\s*%', text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r'(\d+)\s*%', text)
    if m:
        return float(m.group(1))
    return None
 
def format_pct(pct):
    """3.0 → '3%'  |  2.5 → '2,50%'"""
    if pct == int(pct):
        return f"{int(pct)}%"
    return f"{pct:.2f}%".replace('.', ',')
 
def extract_deducible_pct_map(text):
    """
    Escanea el texto buscando patrones '$X.XXX,XX - N%' (ej. en Sancor pág 2).
    Retorna dict {monto_entero: porcentaje_float}
    """
    pct_map = {}
    for m in re.finditer(r'\$([\d.]+,\d{2})\s*-\s*(\d+)\s*%', text):
        try:
            amount = int(m.group(1).replace('.', '').split(',')[0])
            pct = float(m.group(2))
            pct_map[amount] = pct
        except:
            pass
    return pct_map
 
# ─── SELECCIÓN TR POR ASEGURADORA ─────────────────────────────────────────────
 
def closest_to_3(options):
    if not options:
        return None
    best, best_dist = None, float('inf')
    for pct, price in options:
        dist = abs(pct - 3.0)
        if dist < best_dist or (dist == best_dist and best and pct > best[0]):
            best, best_dist = (pct, price), dist
    return best
 
def select_tr(insurer, options):
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
        for page in pdf.pages[:3]:
            t = page.extract_text()
            if t:
                text += t + "\n"
    if text.strip():
        return text
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(pdf_path, dpi=200)
        for img in images[:2]:
            text += pytesseract.image_to_string(img, lang='spa') + "\n"
    except Exception as e:
        print(f'  OCR fallback error: {e}')
    return text
 
# ─── PARSEO DE CLIENTE Y VEHÍCULO ─────────────────────────────────────────────
 
def parse_client_vehicle(text):
    """Extrae nombre del cliente y banner de vehículo."""
    client_name = None
    vehicle_make = None
    vehicle_model = None
 
    all_lines = text.split('\n')
    for i, line in enumerate(all_lines):
        line = line.strip()
 
        # Formato Ciminari: "Estimado APELLIDO, NOMBRE"
        if 'Estimado' in line and not client_name:
            m = re.search(r'Estimado\s+(.+)', line)
            if m:
                client_name = m.group(1).strip().title().replace(' ,', ',')
 
        # Formato Ciminari: "Marca: FORD  Modelo: FOCUS L/08..."
        if 'Marca:' in line:
            m = re.search(r'Marca:\s*(\S+)', line)
            if m:
                vehicle_make = m.group(1).strip().upper()
            m2 = re.search(r'Modelo:\s*(\S+)', line)
            if m2:
                vehicle_model = m2.group(1).strip().upper()
 
        # Formato SC propio: "Modelo: RENAULT KANGOO - EXPRESS L/18..."
        if 'Modelo:' in line and not vehicle_make:
            m = re.search(r'Modelo:\s*(\S+)\s+(\S+)', line)
            if m:
                vehicle_make  = m.group(1).strip().upper()
                vehicle_model = m.group(2).strip().upper()
 
        # Formato Experta/Sancor propio: línea "RENAULT KANGOO EX.L/18..."
        if not vehicle_make:
            m = re.search(r'(RENAULT|FORD|CHEVROLET|VW|VOLKSWAGEN|PEUGEOT|FIAT|TOYOTA|CITROEN|NISSAN|HONDA|HYUNDAI|KIA|JEEP|RAM|JAC|CHERY)\s+(\S+)', line.upper())
            if m:
                vehicle_make  = m.group(1)
                vehicle_model = m.group(2).strip('.,')
 
        # Formato Sancor propio: "Marca/Modelo: RENAULT KANGOO EX. 1.6..."
        if 'Marca/Modelo:' in line and not vehicle_make:
            m = re.search(r'Marca/Modelo:\s*(\S+)\s+(\S+)', line)
            if m:
                vehicle_make  = m.group(1).strip().upper()
                vehicle_model = m.group(2).strip().upper()
 
        # Formato SC propio: "Cotización para NOMBRE APELLIDO"
        if 'Cotización para' in line and not client_name:
            m = re.search(r'Cotización para\s+(.+)', line)
            if m:
                raw = m.group(1).strip()
                stop_words = ['Vehiculo','Vigencia','Modelo','DNI','CP/','GNC','Uso:','IVA:']
                for sw in stop_words:
                    idx = raw.find(sw)
                    if idx > 0:
                        raw = raw[:idx].strip()
                # El OCR puede partir el apellido a la línea siguiente (layout
                # de columnas). Si la línea próxima es una sola palabra tipo
                # apellido (mayúscula inicial, sin números ni ":"), anexarla.
                if raw and i + 1 < len(all_lines):
                    nxt = all_lines[i + 1].strip()
                    if (re.match(r'^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+$', nxt) and
                            len(nxt) >= 3 and ':' not in nxt):
                        raw = f"{raw} {nxt}"
                if raw:
                    client_name = raw.title()
 
        # Formato Experta propio: "OSCAR ENRIQUE CAPPA 18/03/2026"
        if not client_name:
            m = re.match(r'^([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s]{5,50})\s+\d{2}/\d{2}/\d{4}', line)
            if m:
                name_candidate = m.group(1).strip()
                if len(name_candidate.split()) >= 2 and 'KANGOO' not in name_candidate:
                    client_name = name_candidate.title()
 
    banner = vehicle_make or "VEHÍCULO"
    if vehicle_model:
        banner = f"{vehicle_make} {vehicle_model}"
 
    return client_name, banner
 
# ─── IDENTIFICACIÓN DE ASEGURADORA POR NOMBRE DE COBERTURA ───────────────────
 
def identify_insurer_from_coverage(coverage_name):
    """
    Dado el nombre de una cobertura, retorna el insurer_key.
    Maneja formatos Ciminari y formatos propios de cada aseguradora.
    """
    cu = coverage_name.upper().strip()
 
    # ── San Cristóbal ──────────────────────────────────────────────────────────
    if re.match(r'CPLUS', cu) or cu.startswith('C PLUS') or cu.startswith('C+'):
        return 'san_cristobal'
    if re.match(r'CM\b', cu) or cu.startswith('CM -') or cu.startswith('CM:'):
        return 'san_cristobal'
    if re.match(r'D\d{2,3}\s*[-–]', cu) and 'TODO RIESGO' in cu:
        return 'san_cristobal'
    if re.match(r'AUTO MEGA', cu) or re.match(r'AUTO EXTRA', cu) or re.match(r'AUTO PLUS', cu):
        return 'san_cristobal'
 
    # ── Sancor ────────────────────────────────────────────────────────────────
    if 'MAX TOTALES' in cu:
        return 'sancor'
    if 'PREMIUM MAX' in cu or 'MAX PREMIUM' in cu:
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
    if re.match(r'TERCEROS COMPLETO\s+L\b', cu):
        return 'experta'
    if 'TERCEROS COMPLETO XL' in cu:
        return 'experta'
    if 'TODO RIESGO' in cu and 'XL' in cu:
        return 'experta'
    if 'TODO RIESGO FRANQ' in cu and 'VARIABLE' in cu:
        return 'experta'
 
    # ── Mercantil Andina ──────────────────────────────────────────────────────
    if re.search(r'\bM\s*B[ÁA]SICA\b', cu) or 'MBASICA' in cu:
        return 'mercantil'
    if re.search(r'\bM\s*PLUS\b', cu) and 'TERCEROS' in cu:
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
 
    return None
 
# ─── LÍNEAS QUE NO SON COBERTURAS ─────────────────────────────────────────────
 
SKIP_PATTERNS = [
    'Refacturacion:', 'Plan de pago:', 'Suma asegurada:', 'Cobertura', 'Costo',
    'Presupuesto Automotor', 'Página', 'Cerrito', 'www.ciminari', 'ciminaribrokers',
    'marcadas con *', 'Las coberturas', 'Estimado', 'Datos del', 'Fecha nacimiento',
    'Provincia:', 'Forma de pago:', 'Tipo IVA:', 'Tipo uso', 'Código Postal',
    'Marca:', 'Modelo:', 'Año:', 'Código Infoauto', 'GNC:', 'Refactur',
    'Importe Mensual', 'Vigencia:', 'Suma asegurada total', 'Frecuencia de Pago',
    'DATOS DEL VEHICULO', 'SUMAS ASEGURADAS', 'Tipo: Pick', 'Año Modelo',
    'Origen:', 'Uso:', 'Ubicación', 'Kms anuales', 'Guarda en', 'AUTOMOTORES',
    'Cotización 0', 'Sucursal Cap', 'Hola,', 'Ofertas Cotizadas',
    'PLANES CON', 'Tercero Completo', 'PLANES SIN', 'Forma de pago:',
    'PRODUCTOR', 'DATOS DEL VEH', 'MONTO ASEGURADO',
]
 
# ─── PARSEO PRINCIPAL DE COBERTURAS ───────────────────────────────────────────
 
def _looks_like_experta_table_row(line):
    """
    True si la línea parece una fila de la tabla del formato propio de Experta:
    'SI SI(4) SI NO NO 12 Meses SI 2 Mensuales 4300000 $ 120.130,00'
    Esto evita que descripciones largas con montos sueltos se confundan
    con la fila de precio de una cobertura partida.
    """
    cu = line.upper()
    has_si_no = bool(re.search(r'\bSI\b', cu) or re.search(r'\bNO\b', cu))
    has_table_tokens = ('MENSUALES' in cu or 'ANUALES' in cu or
                        'ILIMITADO' in cu or 'MESES' in cu)
    return has_si_no or has_table_tokens
 
 
def parse_coverage_lines(text):
    """
    Parsea coberturas con precio del texto extraído.
    Maneja múltiples formatos:
      - Ciminari (precio en la misma línea)
      - SC propio imagen OCR (2 o 3 columnas)
      - Sancor propio (4 columnas con comillas)
      - Experta propio (coverage name partida en varias líneas)
    Retorna [(insurer_key, coverage_name, price), ...]
    """
    results = []
    lines = text.split('\n')
    sc_multicol = False
    sc_has_tr_col = False
    sc_tr_pct = None
    sc_accum = []
    pending_experta_tcf = False
    sancor_4col_done = False
 
    # ── Pre-scan: Sancor formato propio (3 o 4 columnas) ─────────────────────
    # El header puede tener "Max Totales" + "Max Premium" + "Todo Riesgo"...
    # o variantes donde falta alguna (ej. solo "Max Premium" + 2x "Todo Riesgo").
    for i, line in enumerate(lines):
        cu = line.upper()
        has_max = '"MAX TOTALES"' in cu or '"MAX PREMIUM"' in cu
        n_tr = cu.count('"TODO RIESGO"')
        if has_max and (('"MAX TOTALES"' in cu and '"MAX PREMIUM"' in cu) or n_tr >= 1):
            # Es el header de Sancor propio si tiene comillas de planes
            if cu.count('"') >= 4:  # al menos 2 planes entre comillas
                sancor_entries = _parse_sancor_cols(lines, i, text)
                if sancor_entries:
                    results.extend(sancor_entries)
                    sancor_4col_done = True
                    break
 
    # ── Parseo línea a línea ──────────────────────────────────────────────────
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if any(s in line for s in SKIP_PATTERNS):
            continue
 
        cu = line.upper()
 
        if sancor_4col_done and ('"MAX TOTALES"' in cu or '"MAX PREMIUM"' in cu or
                                  ('"TODO RIESGO"' in cu and 'IMPORTE' not in cu)):
            continue
 
        # ── Detectar header SC multi-columna (OCR) ──────────────────────────
        if 'CM:' in cu and ('C+:' in cu or 'C+' in cu or 'CPLUS' in cu):
            sc_multicol = True
            sc_has_tr_col = bool(re.search(r'\bD[:\s]', cu) or 'D -' in cu or 'TODO RIESGO' in cu)
            if sc_has_tr_col:
                sc_tr_pct = extract_pct(line)
            continue
 
        # ── SC multi-col activo: extraer montos con o SIN $ (OCR Render) ─────
        # El OCR de Render a veces omite el "$", dejando "214.251" suelto.
        # Por eso, estando en sc_multicol, intentamos extraer montos primero
        # con la función tolerante, antes del check normal de precio.
        if sc_multicol:
            line_no_parens = re.sub(r'\([^)]*\)', '', line)
            sc_amounts = extract_sc_amounts(line_no_parens)
            if sc_amounts:
                sc_accum.extend(sc_amounts)
                target = 3 if sc_has_tr_col else 2
                if len(sc_accum) >= target:
                    tr_pct = sc_tr_pct if sc_tr_pct else 2.5
                    if sc_has_tr_col:
                        results.append(('san_cristobal', f'D - TODO RIESGO {tr_pct}%', sc_accum[0]))
                        results.append(('san_cristobal', 'CM',    sc_accum[1]))
                        results.append(('san_cristobal', 'CPLUS', sc_accum[2]))
                    else:
                        results.append(('san_cristobal', 'CM',    sc_accum[0]))
                        results.append(('san_cristobal', 'CPLUS', sc_accum[1]))
                    sc_multicol = False
                    sc_has_tr_col = False
                    sc_accum = []
                continue
 
        # ── Precio en la línea ────────────────────────────────────────────────
        price = extract_price(line)
        if not price:
            # Sin precio: ¿es un nombre de cobertura Experta partido en líneas?
            # FIX bug $400.000: solo activar pending si la cobertura NO se
            # identifica ya como de otra aseguradora. Líneas como
            # "M PLUS - TERCEROS COMPLETO" (Mercantil), "PREMIUM MAX -TERCEROS
            # COMPLETO PREMIUM" (Sancor) o "CM - Terceros Completos Premium..."
            # (San Cristóbal) contienen el texto 'TERCEROS COMPLETO' pero NO son
            # el formato propio de Experta, y activaban un pending erróneo que
            # después enganchaba montos sueltos de las descripciones.
            if 'TERCEROS COMPLETO' in cu and 'TODO RIESGO' not in cu:
                cov_candidate = re.sub(r'\s+', ' ', line).strip()
                already_identified = identify_insurer_from_coverage(cov_candidate)
                has_xl = 'XL' in cu
                has_l  = bool(re.search(r'\bL\b', cu) and not has_xl)
                if not has_xl and not has_l and already_identified is None:
                    pending_experta_tcf = True
            continue
 
        all_prices = extract_all_prices_from_line(line)
 
        # ── Cobertura y precio en la misma línea ─────────────────────────────
        cov = re.sub(r'\$[ ]*[\d.,]+', '', line).strip().strip('-:').strip()
        cov = re.sub(r'\s+', ' ', cov)
 
        insurer = identify_insurer_from_coverage(cov) if len(cov) >= 2 else None
 
        if insurer:
            results.append((insurer, cov, price))
            pending_experta_tcf = False
        elif pending_experta_tcf:
            # FIX bug $400.000: cerrar el pending SOLO si la línea parece una
            # fila de la tabla de Experta (tokens SI/NO/Meses/Mensuales...).
            # Montos sueltos dentro de descripciones largas no cierran pending.
            if _looks_like_experta_table_row(line):
                results.append(('experta', 'TERCEROS COMPLETO XL + GRANIZO FULL', price))
                pending_experta_tcf = False
            # Si no parece fila de tabla, ignorar el monto y mantener pending
            # solo una línea más; después descartarlo para no arrastrarlo.
            else:
                pending_experta_tcf = False
 
    return results
 
 
def _parse_sancor_cols(lines, header_idx, full_text):
    """
    Parsea el formato propio de Sancor con 3 o 4 columnas.
    Lee los nombres de plan del header (entre comillas) en orden, y los
    asocia a los precios de la línea siguiente, columna por columna.
 
    Planes posibles:
      "Max Totales"  → TC Básico
      "Max Premium"  → TC Full
      "Todo Riesgo"  → opción TR (puede haber 1 o 2, con deducibles distintos)
    """
    results = []
 
    # 1. Extraer los nombres de plan del header en orden (entre comillas)
    header_line = lines[header_idx]
    plan_names = re.findall(r'"([^"]+)"', header_line)
    if not plan_names:
        return results
 
    # 2. Buscar la línea con los precios (misma cantidad que planes idealmente)
    prices = []
    price_line_idx = None
    for j in range(header_idx + 1, min(header_idx + 6, len(lines))):
        ap = extract_all_prices_from_line(lines[j])
        if len(ap) >= 2:
            prices = ap
            price_line_idx = j
            break
    if not prices:
        return results
 
    # 3. Buscar deducibles (línea con "$X - N%") para mapear % de los TR
    deducibles = []  # lista de (monto, pct)
    if price_line_idx:
        for k in range(price_line_idx + 1, min(price_line_idx + 4, len(lines))):
            d_line = lines[k]
            for m in re.finditer(r'\$([\d.]+),\d{2}\s*-\s*(\d+)\s*%', d_line):
                amount = int(m.group(1).replace('.', ''))
                pct = float(m.group(2))
                deducibles.append((amount, pct))
            if deducibles:
                break
 
    # 4. Asociar cada plan con su precio (columna por columna)
    pct_map = extract_deducible_pct_map(full_text)
    tr_count = 0
    for idx, plan in enumerate(plan_names):
        if idx >= len(prices):
            break
        plan_u = plan.upper()
        price = prices[idx]
 
        if 'MAX TOTALES' in plan_u:
            results.append(('sancor', 'MAX TOTALES', price))
        elif 'MAX PREMIUM' in plan_u or 'PREMIUM MAX' in plan_u:
            results.append(('sancor', 'PREMIUM MAX', price))
        elif 'TODO RIESGO' in plan_u:
            # Determinar % de franquicia para este TR
            pct = None
            # Intentar por deducible en la misma posición
            if tr_count < len(deducibles):
                pct = deducibles[tr_count][1]
            if pct is None:
                pct = pct_map.get(price)
            if pct is None:
                pct = 3.0  # fallback
            results.append(('sancor', f'AUTO TODO RIESGO {int(pct)}%', price))
            tr_count += 1
 
    return results
 
    if len(prices) >= 1:
        results.append(('sancor', 'MAX TOTALES', prices[0]))
    if len(prices) >= 2:
        results.append(('sancor', 'PREMIUM MAX', prices[1]))
 
    pct_map = extract_deducible_pct_map(full_text)
 
    tr_options_raw = []
    if len(prices) >= 3:
        tr_options_raw.append(prices[2])
    if len(prices) >= 4:
        tr_options_raw.append(prices[3])
 
    for idx, tr_price in enumerate(tr_options_raw):
        pct = None
        if idx < len(deducibles):
            ded_amount = deducibles[idx]
            pct = pct_map.get(ded_amount)
        if pct is None:
            pct = 3.0 if tr_price == max(tr_options_raw) else 4.0
        results.append(('sancor', f'AUTO TODO RIESGO {int(pct)}%', tr_price))
 
    return results
 
# ─── CONSTRUCCIÓN DE FILAS ────────────────────────────────────────────────────
 
def build_rows(coverage_lines):
    """
    coverage_lines: [(insurer, coverage_name, price), ...]
    Retorna dict {insurer_key: {logo_key, tcb, tcf, tr, fr}}
 
    FIX bug $400.000: el primer precio encontrado para cada celda GANA.
    Los precios de tabla aparecen al principio del PDF; las descripciones
    (que pueden contener montos sueltos) vienen después. Asignación
    first-wins evita que un monto tardío pise el precio correcto.
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
                if re.match(r'CPLUS', cu) or cu.startswith('C+') or cu.startswith('C PLUS'):
                    tcb = tcb or price
                elif re.match(r'CM\b', cu) or cu.startswith('CM -') or cu.startswith('CM:'):
                    tcf = tcf or price
                elif 'TODO RIESGO' in cu or re.match(r'D\d{2,3}\s*[-–]', cu) or cu.startswith('D -'):
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))
 
            # ── Sancor ────────────────────────────────────────────────────────
            elif insurer == 'sancor':
                if 'MAX TOTALES' in cu:
                    tcb = tcb or price
                elif 'PREMIUM MAX' in cu or 'MAX PREMIUM' in cu:
                    tcf = tcf or price
                elif 'TODO RIESGO' in cu or 'AUTO TODO' in cu:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))
 
            # ── Swiss Medical ─────────────────────────────────────────────────
            elif insurer == 'swiss':
                if 'TC25' in cu:
                    tcb = tcb or price
                elif 'TC4' in cu:
                    tcf = tcf or price
                elif re.search(r'\bTR\d\b', cu) or 'TODO RIESGO' in cu:
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
                    tcb = tcb or price
                elif re.search(r'\bC4\b', cu):
                    tcf = tcf or price
                elif ('TR' in cu or 'FRANQ' in cu) and 'VALOR' in cu:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))
 
            # ── Experta ───────────────────────────────────────────────────────
            elif insurer == 'experta':
                is_tcb = (('COMPLETOS L' in cu or 'COMPLETO L' in cu or
                           cu.endswith(' L')) and
                          'TODO RIESGO' not in cu and 'XL' not in cu)
                is_tcf = ('XL' in cu and 'TODO RIESGO' not in cu and 'FRANQ' not in cu)
                is_tr  = ('TODO RIESGO' in cu or 'FRANQ. VARIABLE' in cu or
                          'FRANQ VARIABLE' in cu)
 
                if is_tcb:
                    tcb = tcb or price
                elif is_tcf:
                    tcf = tcf or price
                elif is_tr:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))
 
            # ── Mercantil Andina ──────────────────────────────────────────────
            elif insurer == 'mercantil':
                if re.search(r'M\s*B[ÁA]SICA', cu) or 'MBASICA' in cu:
                    tcb = tcb or price
                elif 'M PLUS' in cu or 'MPLUS' in cu:
                    tcf = tcf or price
                elif 'TODO RIESGO' in cu or re.match(r'D2\b', cu):
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))
 
            # ── Zurich ────────────────────────────────────────────────────────
            elif insurer == 'zurich':
                if re.search(r'\bCG\b', cu) and 'TODO RIESGO' not in cu:
                    tcf = tcf or price
                elif 'TODO RIESGO' in cu or re.search(r'\bDV\s*\d', cu):
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))
 
            # ── Federación Patronal ───────────────────────────────────────────
            elif insurer == 'fed_patronal':
                if re.search(r'\bCF\b', cu) or 'RC PTAC' in cu:
                    tcf = tcf or price
                elif 'TODO RIESGO' in cu:
                    pct = extract_pct(cov)
                    if pct:
                        tr_options.append((pct, price))
 
        # Seleccionar mejor TR
        best_tr = select_tr(insurer, tr_options)
        if best_tr:
            tr_val = best_tr[1]
            fr_str = "3%" if insurer == 'swiss' else format_pct(best_tr[0])
 
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
    Retorna: (client_name, vehicle_banner, rows_list, has_tr)
    """
    all_rows = {}
    client_name = None
    vehicle_banner = None
 
    for path in pdf_paths:
        text = extract_text(path)
        name, banner = parse_client_vehicle(text)
        coverage_lines = parse_coverage_lines(text)
        rows = build_rows(coverage_lines)
 
        # Preferir el nombre más completo (más palabras)
        if name and (client_name is None or len(name.split()) > len((client_name or '').split())):
            client_name = name
        if vehicle_banner is None and banner and banner != 'VEHÍCULO':
            vehicle_banner = banner
 
        for key, row in rows.items():
            if key in all_rows:
                existing_price = all_rows[key].get('tcf') or all_rows[key].get('tcb') or float('inf')
                new_price      = row.get('tcf') or row.get('tcb') or float('inf')
                if new_price < existing_price:
                    all_rows[key] = row
            else:
                all_rows[key] = row
 
    rows_list = [all_rows[k] for k in INSURER_ORDER if k in all_rows]
    has_tr = any(r.get('tr') is not None for r in rows_list)
 
    return client_name, vehicle_banner, rows_list, has_tr
 
