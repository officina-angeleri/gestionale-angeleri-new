"""
Script di estrazione Distinta Base (BOM / Materiali) e Ciclo Lavorazioni da B-Kode.
Utilizza la sequenza verificata:
1. GET mgartForm (inizializza la sessione PHP sull'articolo attivo)
2. POST mgadisList (estrae componenti e materiali)
3. POST mgacicList (estrae fasi e ore macchina)
"""

import os
import sys
import time
import requests
import json
import urllib3
from datetime import datetime
from sqlalchemy import text

# Forza unbuffered output per visualizzazione in tempo reale
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.database import init_db, get_db_session, Product, ProductMaterial, ProductOperation

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

COOKIE_VAL = "VzNVbQRjVW1VelAiCzcHYFViXjgCd1d6B2VXIwB8UGpXNQA5Vl4BaVc2UnJVPlEgVzkHNVRgVjpUcQtiUT5UPw8xVTFWaw48BzpXZgw5AGBXMVVuBGJVYVU2UDULbwdoVWReMgJlVzgHYldpADdQZVc8AGJWMgFlV2pSclU%2BUSBXOQc3VGJWOlRxCz5RdlRVD2lVNlY9Di8Hb1dzDCgAI1dpVSQEblVmVTBQawsvB2JVY14sAmRXPAc2V34AOVAtV2wAYVYjATtXIVJqVTRRY1c5ByRUJ1ZzVDYLJVFZVGsPb1U3VjcOKQcoVzsMKAA7V2dVZwRuVXVVTFA%2BC3cHOFU%2BXm4CNFcmBzVXfgA%2FUCNXcgAAVmgBblc2Uj9VclEgVyMHSFQGViBUYgtnUShUOg8zVXJWDg40B2RXNgxvADpXclUvBGJVY1UoUHELTAchVSJebgIwV14HZVcyAC1QOFcpAG1WMAEzV2hSclVpUTJXcAdyVA1WYVQwCyNRb1R8D2FVJlYgDn8HMVdzDGEAMFdiVW0EdlVmVTZQaAs9B2ZVa146AmFXOgc5V3IANFBwV2AAY1Y7ASJXIVIPVWxRN1chBz1UIVY6VGALZVE8VCgPaVVqVmEOaAdrVzgMOQA4VzFVMQQwVWFVYlBhCz0HN1UzXmACN1dsBzJXYAA3UDFXPwAyVjkBN1dnUmZVZ1FgVyEHPVQhVjpUZQttUSRUeQ9XVSdWKg44B3hXIgxgAHJXaFViBG5VdVVsUDALPQdhVWBeIAJuV3oHOldoADVQIVcpAAhWdAFsVz1SN1VsUT1XIQc9VCFWOlRmC21RJFRnD2lVYlZpDm8HKFc7DCY%3D"

def get_bkode_session():
    s = requests.Session()
    s.verify = False
    s.cookies.set("ci_session", requests.utils.unquote(COOKIE_VAL), domain="www.bkode.cloud")
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.bkode.cloud",
        "Referer": "https://www.bkode.cloud/panel/grid/mgartList/angeleri/401015/",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": f"ci_session={COOKIE_VAL}"
    })
    return s

def safe_float(val, default=0.0):
    if not val:
        return default
    try:
        return float(str(val).replace(',', '.'))
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0):
    if not val:
        return default
    try:
        return int(float(str(val).replace(',', '.')))
    except (ValueError, TypeError):
        return default

def run_import():
    print("="*70, flush=True)
    print("ESTRAZIONE COMPLETA DISTINTE BASE & CICLI LAVORAZIONE (B-KODE)", flush=True)
    print("="*70, flush=True)
    
    init_db()
    db = get_db_session()
    bkode = get_bkode_session()
    
    # Costruisci dizionario di lookup codice -> Product
    all_products = db.query(Product).all()
    code_to_product = {p.code.strip(): p for p in all_products}
    print(f"Prodotti totali nel DB locale: {len(all_products)}", flush=True)
    
    # Seleziona gli articoli di produzione con un bkode_id valido
    # Prioritizza prima i codici L... e C... (produzione Angeleri), poi type == PRODUZIONE, poi il resto di tipo P
    def get_priority(p):
        code = p.code.upper()
        if code.startswith('L') or code.startswith('C'):
            return 1
        if p.type == 'PRODUZIONE':
            return 2
        return 3
        
    production_prods = [p for p in all_products if p.bkode_id and p.bkode_type in ('P', 'S')]
    production_prods.sort(key=get_priority)
    
    total = len(production_prods)
    print(f"Articoli di produzione identificati con bkode_id: {total}", flush=True)
    
    # Contatori
    total_materials = 0
    total_operations = 0
    articles_with_materials = 0
    articles_with_operations = 0
    start_time = time.time()
    
    for idx, prod in enumerate(production_prods, 1):
        art_id = prod.bkode_id
        code = prod.code
        
        # 1. Visita form dell'articolo per attivare il contesto nella sessione B-Kode
        url_form = f"https://www.bkode.cloud/panel/mixed/mgartForm/mgartList/0/{art_id}/{art_id}/obj_0/angeleri/0/0/0/"
        try:
            rf = bkode.get(url_form, timeout=12)
            if rf.status_code != 200:
                print(f"  [!] HTTP {rf.status_code} su Form per art_id={art_id} ({code})", flush=True)
                continue
        except Exception as e:
            print(f"  [!] Timeout/Errore su Form per {code}: {e}", flush=True)
            continue
            
        # 2. Scarica Distinta Materiali (mgadisList)
        url_mat = "https://www.bkode.cloud/panel/gridjson/mgadisList/angeleri/"
        mat_items = []
        try:
            rm = bkode.post(url_mat, data={
                "start": "0",
                "limit": "200",
                "master_key": str(art_id),
                "inner": "true",
                "store_filter": f" AND dco_dis_id = '{art_id}'"
            }, timeout=12)
            if rm.status_code == 200:
                mat_items = rm.json().get("items", [])
        except Exception as e:
            print(f"  [!] Errore mgadisList per {code}: {e}", flush=True)
            
        # 3. Scarica Ciclo Lavorazioni (mgacicList)
        url_ops = "https://www.bkode.cloud/panel/gridjson/mgacicList/angeleri/"
        ops_items = []
        try:
            ro = bkode.post(url_ops, data={
                "start": "0",
                "limit": "200",
                "master_key": str(art_id),
                "inner": "true",
                "store_filter": f" AND cic_dis_id = '{art_id}'"
            }, timeout=12)
            if ro.status_code == 200:
                ops_items = ro.json().get("items", [])
        except Exception as e:
            print(f"  [!] Errore mgacicList per {code}: {e}", flush=True)

        # 4. Salva nel DB locale (se presenti)
        if mat_items:
            articles_with_materials += 1
            db.query(ProductMaterial).filter(ProductMaterial.product_id == prod.id).delete()
            for m in mat_items:
                comp_code = (m.get("dco_figlio") or "").strip()
                comp_prod = code_to_product.get(comp_code)
                pm = ProductMaterial(
                    product_id=prod.id,
                    bkode_id=safe_int(m.get("dco_id")),
                    line_num=safe_int(m.get("dco_seq"), 10),
                    component_code=comp_code,
                    component_product_id=comp_prod.id if comp_prod else None,
                    description=(m.get("art_des1") or "").strip(),
                    unit_measure=(m.get("art_um") or "NR").strip(),
                    quantity=safe_float(m.get("dco_qta"), 1.0),
                    unit_cost=safe_float(m.get("dco_costo"), 0.0),
                    scrap_factor=safe_float(m.get("dco_ft_scarto"), 0.0),
                    notes=(m.get("dco_note") or "").strip()
                )
                db.add(pm)
                total_materials += 1
                
        if ops_items:
            articles_with_operations += 1
            db.query(ProductOperation).filter(ProductOperation.product_id == prod.id).delete()
            for op in ops_items:
                po = ProductOperation(
                    product_id=prod.id,
                    bkode_id=safe_int(op.get("cic_id")),
                    sequence=safe_int(op.get("cic_seq"), 10),
                    phase_code=(op.get("cic_figlio") or "").strip(),
                    description=(op.get("art_des1") or "").strip(),
                    setup_hours=safe_float(op.get("cic_t_atrz"), 0.0),
                    operation_hours=safe_float(op.get("cic_t_ese"), 0.0),
                    hourly_rate=safe_float(op.get("cic_cos_uni"), 0.0),
                    notes=(op.get("cic_note") or "").strip()
                )
                db.add(po)
                total_operations += 1

        # Commit ogni 10 articoli o se ha trovato dati
        if mat_items or ops_items or idx % 20 == 0:
            db.commit()
            
        # Logging informativo ogni 20 articoli o per articoli con distinte/lavorazioni
        if mat_items or ops_items:
            tot_h = sum(safe_float(op.get("cic_t_ese")) for op in ops_items)
            print(f"[{idx:>4}/{total}] {code:<15} -> {len(mat_items)} materiali, {len(ops_items)} lavorazioni ({tot_h:.1f}h macch.)", flush=True)
        elif idx % 50 == 0:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 1
            eta_min = (total - idx) / rate / 60
            print(f"[{idx:>4}/{total}] Progresso: {idx/total*100:.1f}% - Con BOM: {articles_with_materials}, Con Lavorazioni: {articles_with_operations} (ETA: {eta_min:.1f} min)", flush=True)
            
        time.sleep(0.02)
        
    db.commit()
    elapsed = time.time() - start_time
    print("="*70, flush=True)
    print(f"ESTRAZIONE COMPLETATA IN {elapsed/60:.1f} MINUTI!", flush=True)
    print(f"  Articoli analizzati: {total}", flush=True)
    print(f"  Articoli con Distinta Materiali (BOM): {articles_with_materials} (Righe totali: {total_materials})", flush=True)
    print(f"  Articoli con Ciclo Lavorazioni: {articles_with_operations} (Fasi totali: {total_operations})", flush=True)
    print("="*70, flush=True)

if __name__ == '__main__':
    run_import()
