import os
import re
import glob
from datetime import datetime
import pdfplumber

from app.database import (
    get_db_session, ExplodedDiagram, ExplodedDiagramItem, 
    Product, ProductLegacyCode
)

def normalize_machine_model(header_text: str, filename: str, full_text: str = "") -> str:
    """
    Normalizza e riconosce la famiglia/modello macchina.
    Dà priorità assoluta al nome del file e al cartiglio/intestazione della prima pagina,
    evitando che singole viti/accessori (es. ghiera ICT60-MINI) alterino il modello della macchina principale.
    """
    # 1. Analisi primaria: nome file + cartiglio/prima pagina
    primary = f"{filename} {header_text}".upper()
    
    # MAV 3150 (con distinzione esplicita solo se '3150 MINI' compare nel titolo/nome file)
    if "3150" in primary:
        if "3150 MINI" in primary or "3150_MINI" in primary or "3150-MINI" in primary:
            return "MAV 3150 MINI"
        return "MAV 3150"
    if "3024" in primary:
        return "MAV 3024"
    if "3100" in primary:
        return "MAV 3100"
    if "3140" in primary:
        return "MAV 3140"
    if "3200" in primary:
        return "MAV 3200"
    if "3230" in primary:
        return "MAV 3230"
    if "3250" in primary:
        return "MAV 3250"
    if "3300" in primary:
        return "MAV 3300"
    if "3350" in primary:
        return "MAV 3350"
    
    # ICT
    if "ICT" in primary:
        if "MINI" in primary or "60M" in primary:
            return "ICT 60 MINI"
        return "ICT 60"
        
    # ECOL
    if "ECOL" in primary:
        if "4150" in primary:
            return "ECOL 4150 MINI"
        if "4250" in primary:
            return "ECOL 4250 MINI"
        if "60" in primary:
            return "ECOL 60"
        return "ECOL MINI"
        
    # TERMO
    if "TERMO" in primary:
        if "450" in primary:
            return "TERMO 450"
        if "300" in primary:
            return "TERMO 300"
        if "610" in primary:
            return "TERMO 610"
        return "TERMO"
        
    # C87
    if "C87" in primary or "C/87" in primary:
        return "C87 DOPPIA"
        
    # RIGHELLATRICI
    if "RIGHELLATRICE" in primary or "RIG-C" in primary:
        if "HERMES" in primary:
            return "RIGHELLATRICE HERMES"
        return "RIGHELLATRICE"
        
    # LX
    if "LX" in primary:
        return "INCOLLATRICE LX"
        
    if "PISTOLA" in primary:
        return "PISTOLA COLLA"
        
    # 2. Fallback su testo completo (con controllo prudente)
    full_upper = full_text.upper()
    for mav_code in ["3150", "3024", "3100", "3140", "3200", "3230", "3250", "3300"]:
        if f"MAV {mav_code}" in full_upper or f"MAV{mav_code}" in full_upper:
            return f"MAV {mav_code}"

    if "ICT 60" in full_upper or "ICT60" in full_upper:
        return "ICT 60"
    if "ECOL" in full_upper:
        return "ECOL"

    return "OFFICINA / ACCESSORI"


def clean_description(desc: str) -> str:
    """Rende più leggibile la descrizione inserendo spazi dove mancano tra minuscole e maiuscole."""
    if not desc:
        return ""
    # Inserisce spazio tra minuscola e Maiuscola (es. BasamentoICT -> Basamento ICT, rullomorbido -> rullo morbido)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', desc)
    # Rimuove sequenze di caratteri speciali di cid o encoding
    s = re.sub(r'\(cid:\d+\)', ' ', s)
    return s.strip()


def clean_title_text(text: str) -> str:
    """Ripulisce il titolo da artefatti di data e formattazione OCR."""
    if not text:
        return ""
    # Rimuove sequenze tipo '04d/a1t2a/:14 ' o 'data: 06/02/08 '
    s = re.sub(r'\b\d{2}[a-zA-Z]/[a-zA-Z\d/:]+\s*', '', text)
    s = re.sub(r'data:\s*\d{2}/\d{2}/\d{2,4}\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'data:\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\(cid:\d+\)', ' ', s)
    return s.strip()


def parse_diagram_pdf(pdf_path: str):
    """
    Parsa un singolo file PDF e restituisce:
    - metadata: dict(code, title, machine_model, pages_count, file_name, file_path)
    - items: lista di dict(position_num, old_position_code, part_code, description, quantity, page_number)
    """
    file_name = os.path.basename(pdf_path)
    base_name = os.path.splitext(file_name)[0]
    
    # Codice disegno: se tipo M1-0002 o M3-0011 usa quello, altrimenti il nome ripulito
    m_code = re.match(r'^(M[1-3]-\d{4})', base_name, re.IGNORECASE)
    if m_code:
        code = m_code.group(1).upper()
    else:
        clean_code = base_name.replace("Esploso_", "").replace("Esploso ", "").replace("Assieme esploso ", "")
        code = clean_code[:40].strip()
        
    items = []
    title = base_name.replace("Esploso_", "").replace("Esploso ", "")
    first_page_text = ""
    all_text = ""
    
    with pdfplumber.open(pdf_path) as pdf:
        pages_count = len(pdf.pages)
        
        for p_idx, page in enumerate(pdf.pages):
            p_num = p_idx + 1
            text = page.extract_text() or ""
            all_text += " " + text
            
            # Se prima pagina, estrai titolo accurato dal cartiglio
            if p_idx == 0:
                first_page_text = text
                # Cerca esplicito "Descrizionedisegno" o "Descrizione disegno"
                m_cart = re.search(r'Descrizione\s*disegno\s+([^\n\r]+)', text, re.IGNORECASE)
                if m_cart:
                    title = m_cart.group(1).strip()
                else:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    for l in lines[:5]:
                        if any(kw in l.lower() for kw in ["tavola", "catalogo", "mini", "mav", "ecol", "ict", "termo", "c87"]):
                            cleaned = clean_title_text(l)
                            if cleaned and len(cleaned) > 3:
                                title = cleaned[:100]
                                break
                        
            # Cerca se la pagina contiene una distinta/elenco parti
            has_table = any(kw in text.lower() for kw in [
                'elenco parti', 'elencoparti', 'numerazione_old', 
                'codiceex', 'codiceordine', 'numero parte', 'numeroparte'
            ])
            
            if not has_table and p_num < pages_count and pages_count > 2:
                continue
                
            # Parsing delle righe della tabella
            lines = text.split('\n')
            for l in lines:
                l_str = l.strip()
                if not l_str or "NUMERAZIONE_OLD" in l_str or "Elenco parti" in l_str or "CodiceOrdine" in l_str:
                    continue
                    
                # Formato 1: OLD_POS CODICE_ORDINE QTÀ DESCRIZIONE (es: '80 L011-0096 1 PernorullomorbidoMAV3150')
                # oppure: '1 L050-0001 1 BasamentoICT60mini'
                m1 = re.match(r'^([0-9A-Za-z\+\.\/_-]+)\s+([A-Za-z0-9]{3,5}-[\w\.]+)\s+(\d+(?:[\.,]\d+)?)\s+(.+)$', l_str)
                if m1:
                    pos = m1.group(1).strip()
                    p_code = m1.group(2).strip().upper()
                    qty = float(m1.group(3).replace(',', '.'))
                    desc = clean_description(m1.group(4))
                    items.append({
                        'position_num': pos,
                        'old_position_code': pos,
                        'part_code': p_code,
                        'description': desc,
                        'quantity': qty,
                        'page_number': p_num
                    })
                    continue
                    
                # Formato 2: ELEM. QTÀ NUMERO_PARTE DESCRIZIONE (es: '1 2 L011-0026 Flangia rullo morbido MAV 3150')
                m2 = re.match(r'^([0-9A-Za-z\+\.\/_-]+)\s+(\d+(?:[\.,]\d+)?)\s+([A-Za-z0-9]{3,5}-[\w\.]+)\s+(.+)$', l_str)
                if m2:
                    pos = m2.group(1).strip()
                    qty = float(m2.group(2).replace(',', '.'))
                    p_code = m2.group(3).strip().upper()
                    desc = clean_description(m2.group(4))
                    items.append({
                        'position_num': pos,
                        'old_position_code': pos,
                        'part_code': p_code,
                        'description': desc,
                        'quantity': qty,
                        'page_number': p_num
                    })
                    continue
                    
                # Formato 3: Solo POSIZIONE e DESCRIZIONE se pezzo commerciale senza codice ordine esplicito
                # es. '80 1 Guarnizione' o '34 1 Raccordo'
                m3 = re.match(r'^([0-9A-Za-z\+\.\/_-]+)\s+(\d+(?:[\.,]\d+)?)\s+([A-Za-z\u00C0-\u017F].+)$', l_str)
                if m3 and len(m3.group(3).strip()) > 3:
                    pos = m3.group(1).strip()
                    qty = float(m3.group(2).replace(',', '.'))
                    desc = clean_description(m3.group(3))
                    # Escludi righe che sembrano intestazioni
                    if not any(hdr in desc.lower() for hdr in ['note', 'materiale', 'data', 'foglio', 'scala']):
                        items.append({
                            'position_num': pos,
                            'old_position_code': pos,
                            'part_code': None,
                            'description': desc,
                            'quantity': qty,
                            'page_number': p_num
                        })
                        continue

    machine_model = normalize_machine_model(first_page_text, file_name, all_text)
    
    metadata = {
        'code': code,
        'title': title if title else base_name,
        'machine_model': machine_model,
        'file_name': file_name,
        'file_path': os.path.relpath(pdf_path, os.getcwd()).replace('/', '\\'),
        'pages_count': pages_count,
        'has_parts_table': 1 if len(items) > 0 else 0
    }
    
    return metadata, items


def index_all_diagrams(esplosi_dir: str = None) -> dict:
    """
    Indicizza tutti gli esplosi PDF presenti nella cartella nel database PostgreSQL.
    Crea i collegamenti con la tabella Product e ProductLegacyCode.
    """
    if esplosi_dir is None:
        esplosi_dir = os.path.join(os.getcwd(), "File_per_progetto", "Esplosi")
        if not os.path.exists(esplosi_dir):
            esplosi_dir = os.path.join(os.getcwd(), "File per progetto", "Esplosi")
            
    if not os.path.exists(esplosi_dir):
        return {'status': 'error', 'message': f"Cartella non trovata: {esplosi_dir}"}
        
    pdf_files = glob.glob(os.path.join(esplosi_dir, "*.pdf")) + glob.glob(os.path.join(esplosi_dir, "*.PDF"))
    if not pdf_files:
        return {'status': 'error', 'message': "Nessun file PDF trovato nella cartella esplosi."}
        
    session = get_db_session()
    
    diagrams_indexed = 0
    items_indexed = 0
    links_to_products = 0
    new_legacy_codes = 0
    
    KNOWN_CAD_CORRECTIONS = {
        # File M1-0056.pdf: alla posizione 21 il cartiglio/tabella CAD indica L011-0091 con descrizione 'Pernoportapuleggiamav3150',
        # ma il codice corretto da catalogo master è L011-0090 (Perno porta puleggia MAV 3150 / 3150-21).
        # L011-0091 è invece l'Albero MAV 3150 (3150-64 / Albero innesto per rullo morbido).
        ('M1-0056.pdf', '21'): 'L011-0090',
    }

    try:
        # Crea mappa rapida dei codici Master già esistenti nel catalogo per link O(1)
        products_map = {p.code.upper().strip(): p.id for p in session.query(Product.id, Product.code).all()}
        
        for pdf_path in sorted(pdf_files):
            try:
                meta, items = parse_diagram_pdf(pdf_path)
            except Exception as e:
                print(f"Errore lettura {os.path.basename(pdf_path)}: {e}")
                continue
                
            # Verifica se l'esploso è già presente nel DB
            diag = session.query(ExplodedDiagram).filter_by(file_name=meta['file_name']).first()
            if not diag:
                diag = ExplodedDiagram(
                    code=meta['code'],
                    title=meta['title'],
                    machine_model=meta['machine_model'],
                    file_name=meta['file_name'],
                    file_path=meta['file_path'],
                    pages_count=meta['pages_count'],
                    has_parts_table=meta['has_parts_table']
                )
                session.add(diag)
                session.flush() # Ottiene diag.id
            else:
                diag.code = meta['code']
                diag.title = meta['title']
                diag.machine_model = meta['machine_model']
                diag.file_path = meta['file_path']
                diag.pages_count = meta['pages_count']
                diag.has_parts_table = meta['has_parts_table']
                # Pulisce vecchi items per reindicizzare in modo pulito
                session.query(ExplodedDiagramItem).filter_by(diagram_id=diag.id).delete()
                session.flush()
                
            diagrams_indexed += 1
            
            # Inserisce gli items estratti
            for it in items:
                pos_num = str(it.get('position_num') or '').strip()
                p_code = it.get('part_code')
                
                # Applicazione correzioni note refusi CAD
                cad_fix_key = (meta['file_name'], pos_num)
                if cad_fix_key in KNOWN_CAD_CORRECTIONS:
                    p_code = KNOWN_CAD_CORRECTIONS[cad_fix_key]

                prod_id = products_map.get(p_code) if p_code else None
                if prod_id:
                    links_to_products += 1
                
                d_item = ExplodedDiagramItem(
                    diagram_id=diag.id,
                    position_num=it.get('position_num'),
                    old_position_code=it.get('old_position_code'),
                    part_code=p_code,
                    product_id=prod_id,
                    description=it.get('description') or '-',
                    quantity=it.get('quantity', 1.0),
                    page_number=it.get('page_number', 1)
                )
                session.add(d_item)
                items_indexed += 1
                
        session.commit()
        return {
            'status': 'ok',
            'diagrams_indexed': diagrams_indexed,
            'items_indexed': items_indexed,
            'links_to_products': links_to_products,
            'new_legacy_codes': new_legacy_codes,
            'message': f"Indicizzati con successo {diagrams_indexed} esplosi e {items_indexed} componenti ({links_to_products} collegati al catalogo master)."
        }
    except Exception as e:
        session.rollback()
        return {'status': 'error', 'message': f"Errore durante l'indicizzazione: {str(e)}"}
    finally:
        session.close()
