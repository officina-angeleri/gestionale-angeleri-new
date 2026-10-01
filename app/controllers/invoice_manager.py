import os
import sys
import re
from sqlalchemy import func, or_, and_, desc
from sqlalchemy.orm import Session
from ..database import get_db_session, Supplier, Invoice, InvoiceItem
from ..parsers.base import InvoiceParser
from ..parsers.html import HTMLInvoiceParser
from ..parsers.pdf import PDFInvoiceParser
from ..parsers.xml_sdi import XMLSDIInvoiceParser

from .product_matcher import ProductMatcher

# ---------------------------------------------------------------------------
# Mappa alias -> nome canonico del fornitore.
# Aggiungere qui nuove varianti ogni volta che un XML usa una denominazione
# diversa da quella gia' presente nel DB.
# ---------------------------------------------------------------------------
SUPPLIER_ALIASES: dict[str, str] = {
    # MATTI
    "MATTI S.r.l.": "MATTI SRL OFFICINE MECCANICHE",
    "MATTI SRL":    "MATTI SRL OFFICINE MECCANICHE",
    "MATTI S.R.L.": "MATTI SRL OFFICINE MECCANICHE",
    # ALUSIC
    "ALUSIC S.p.a.": "ALUSIC S.r.l.",
    "ALUSIC S.P.A.": "ALUSIC S.r.l.",
    "ALUSIC SRL":    "ALUSIC S.r.l.",
    # ICS FIRPO
    "I.C.S. FIRPO S.P.A.": "I.C.S. FIRPO S.R.L.",
    "ICS FIRPO SPA":       "I.C.S. FIRPO S.R.L.",
    "ICS FIRPO S.P.A.":    "I.C.S. FIRPO S.R.L.",
    # ELVINOX
    "ELVINOX S.r.l.": "ELVINOX S.r.l.",
    "ELVINOX S.R.L.": "ELVINOX S.r.l.",
    "ELVINOX SRL":    "ELVINOX S.r.l.",
    # BARATE'
    "BARATE' SPA":    "BARATE' S.P.A.",
    "BARATE' S.P.A.": "BARATE' S.P.A.",
}

class InvoiceManager:
    def __init__(self):
        self.session: Session = get_db_session()
        self.parsers = [
            XMLSDIInvoiceParser(),
            HTMLInvoiceParser(),
            PDFInvoiceParser(),
        ]
        self.matcher = ProductMatcher(self.session)

    @staticmethod
    def _normalize_supplier(name: str) -> str:
        """Pulisce spazi multipli e risolve varianti di denominazione al nome canonico."""
        if not name:
            return "Sconosciuto"
        cleaned = " ".join(name.split())
        return SUPPLIER_ALIASES.get(cleaned, cleaned)

    def _get_parser(self, file_path: str) -> InvoiceParser:
        for parser in self.parsers:
            if parser.can_handle(file_path):
                return parser
        return None

    def import_invoice(self, file_path: str):
        """Processes a single file (which may contain multiple invoices) and saves them to the DB."""
        parser = self._get_parser(file_path)
        if not parser:
            raise ValueError(f"Nessun parser disponibile per il file: {file_path}")

        try:
            parsed_invoices_list = parser.parse(file_path)
        except Exception as e:
            raise RuntimeError(f"Errore durante il parsing di {os.path.basename(file_path)}: {e}")

        saved_invoices = []
        
        for parsed_data in parsed_invoices_list:
            # Normalizza il nome fornitore (gestisce varianti di denominazione e spazi multipli)
            canonical_name = self._normalize_supplier(parsed_data.supplier_name)
            piva = getattr(parsed_data, 'supplier_piva', '').strip().replace("IT", "") or None

            # Get or Create Supplier con prioritario matching per P.IVA
            supplier = None
            if piva:
                supplier = self.session.query(Supplier).filter(
                    (Supplier.piva == piva) | (Supplier.piva == f"IT{piva}")
                ).first()

            if not supplier:
                # Cerca per nome canonico o case-insensitive
                supplier = self.session.query(Supplier).filter_by(name=canonical_name).first()
                if not supplier:
                    supplier = self.session.query(Supplier).filter(
                        func.lower(Supplier.name) == canonical_name.lower()
                    ).first()

            if not supplier:
                supplier = Supplier(name=canonical_name, piva=piva)
                self.session.add(supplier)
                self.session.flush()
            else:
                # Se il fornitore esistente non aveva la P.IVA ma ora ce l'abbiamo, salvala
                if piva and not supplier.piva:
                    supplier.piva = piva
                    self.session.flush()

            # Check if invoice already exists (usa supplier.id per certezza assoluta)
            existing = self.session.query(Invoice).filter(
                Invoice.supplier_id == supplier.id,
                Invoice.number == parsed_data.number,
                Invoice.date == parsed_data.date
            ).first()

            if existing:
                 print(f"Skipping existing invoice {parsed_data.number}")
                 continue

            # Create Invoice
            invoice = Invoice(
                supplier_id=supplier.id,
                date=parsed_data.date,
                number=parsed_data.number,
                total_amount=parsed_data.total_amount,
                file_path=parsed_data.original_file_path
            )
            self.session.add(invoice)
            self.session.flush()

            # Create Items
            for item in parsed_data.items:
                product = self.matcher.get_or_create_product(item.code, item.description, item.customer_code)
                
                inv_item = InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=product.id,
                    code=item.code,
                    customer_code=item.customer_code,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price
                )
                self.session.add(inv_item)
            
            saved_invoices.append(invoice)
        
        self.session.commit()
        return saved_invoices[0] if saved_invoices else None

    def get_all_invoices(self):
        return self.session.query(Invoice).all()
        
    def get_dashboard_stats(self):
        """Returns basic stats for dashboard."""
        total_invoices = self.session.query(Invoice).count()
        
        # Total spent Gross (from Invoice)
        total_gross = self.session.query(func.sum(Invoice.total_amount)).scalar() or 0.0
        
        # Total spent Net (from InvoiceItems)
        total_net = self.session.query(func.sum(InvoiceItem.total_price)).scalar() or 0.0
            
        # Top 5 Supplier by Gross spend
        invoices = self.session.query(Invoice).all()
        suppliers = {}
        for inv in invoices:
            s_name = inv.supplier.name
            suppliers[s_name] = suppliers.get(s_name, 0) + inv.total_amount
        
        top_suppliers = sorted(suppliers.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "total_count": total_invoices,
            "total_gross": total_gross,
            "total_net": total_net,
            "top_suppliers": top_suppliers
        }

    def _build_exact_code_condition(self, column, code: str):
        """
        Costruisce una condizione SQL ad alta precisione per codici ricambio,
        evitando che un codice come '3024-10' agganci '3024-108' (catena) o '3024-106' (pignone).
        """
        import re
        from sqlalchemy import or_
        clean = (code or '').strip()
        if not clean or len(clean) < 2:
            return None
            
        # Filtra categoricamente parole generiche o rumore (MAV, ECOL, ICT, ecc.)
        GENERIC = {'MAV', 'ECOL', 'ICT', 'TERMO', 'RIG', 'LX', 'MINI', 'C87', 'DOC', 'NR', 'PAG', 'TH'}
        if clean.upper() in GENERIC:
            return None

        # Su PostgreSQL usa operatore regex con confini precisi
        dialect = getattr(getattr(self.session, 'bind', None), 'dialect', None)
        if dialect and dialect.name == 'postgresql':
            pattern = rf'(^|[^0-9A-Za-z]){re.escape(clean)}($|[^0-9])'
            return column.op('~*')(pattern)

        # Fallback universale (esatto o delimitato da spazio/slash/trattino)
        return or_(
            column == clean,
            column.ilike(f"{clean} %"),
            column.ilike(f"% {clean}"),
            column.ilike(f"% {clean} %"),
            column.ilike(f"%/{clean}"),
            column.ilike(f"%_{clean}")
        )

    def search_items(self, search_steps):
        """
        Search for invoice items based on multiple search steps (FOR incremental search).
        search_steps: list of dicts like {'words': [...], 'search_code': bool, 'search_desc': bool, 'supplier': str|None, 'equivalent_codes': [...]}
        """
        import re
        from sqlalchemy import or_, and_
        from app.database import Invoice, InvoiceItem, Supplier
        
        query = self.session.query(InvoiceItem).join(Invoice).join(Supplier)
        all_conditions = []
        supplier_filter = None

        for step in search_steps:
            if step.get('supplier'):
                supplier_filter = step['supplier']

            step_conditions = []

            # 1. Ricerca multi-codice su codici master, legacy e fornitore associati all'articolo
            equiv_codes = step.get('equivalent_codes', [])
            equiv_conds = []
            if equiv_codes and step.get('search_code', True):
                for c in equiv_codes:
                    c1 = self._build_exact_code_condition(InvoiceItem.code, c)
                    if c1 is not None:
                        equiv_conds.append(c1)
                    c2 = self._build_exact_code_condition(InvoiceItem.customer_code, c)
                    if c2 is not None:
                        equiv_conds.append(c2)

            # 2. Ricerca per parole digitate con logica AND rigorosa
            word_conds = []
            for word in step.get('words', []):
                if not word:
                    continue
                
                m = re.match(r'^([a-zA-Z]+)(\d+)$', word)
                patterns = [f"%{word}%"]
                if m:
                    l, n = m.group(1), m.group(2)
                    patterns.extend([f"%{l} {n}%", f"%{l}={n}%", f"%{l}.{n}%", f"%{l}-{n}%"])

                w_pats = []
                w_lower = word.lower()
                for pat in patterns:
                    if step.get('search_desc', True):
                        w_pats.append(InvoiceItem.description.ilike(pat))
                    if step.get('search_code', True):
                        c1 = self._build_exact_code_condition(InvoiceItem.code, word)
                        if c1 is not None:
                            w_pats.append(c1)
                        else:
                            w_pats.append(InvoiceItem.code.ilike(pat))
                        c2 = self._build_exact_code_condition(InvoiceItem.customer_code, word)
                        if c2 is not None:
                            w_pats.append(c2)
                    w_pats.append(Supplier.name.ilike(pat))
                    w_pats.append(Invoice.number.ilike(pat))

                # Sinonimi meccanici (ingranaggio <-> pignone)
                if w_lower in ('ingranaggio', 'ingranaggi'):
                    w_pats.append(InvoiceItem.description.ilike('%pignon%'))
                elif w_lower in ('pignone', 'pignoni'):
                    w_pats.append(InvoiceItem.description.ilike('%ingranagg%'))

                # Riconoscimento sigle fornitori es. imbg -> I.M.B.G. S.r.l.
                w_alpha = re.sub(r'[^a-zA-Z0-9]', '', w_lower)
                if len(w_alpha) >= 3:
                    matched_supps = [s.id for s in self.session.query(Supplier.id, Supplier.name).all() if w_alpha in re.sub(r'[^a-zA-Z0-9]', '', (s.name or '').lower())]
                    if matched_supps:
                        w_pats.append(Invoice.supplier_id.in_(matched_supps))

                if w_pats:
                    word_conds.append(or_(*w_pats))

            all_words_matched = and_(*word_conds) if word_conds else None

            if equiv_conds and all_words_matched is not None:
                step_conditions.append(or_(or_(*equiv_conds), all_words_matched))
            elif equiv_conds:
                step_conditions.append(or_(*equiv_conds))
            elif all_words_matched is not None:
                step_conditions.append(all_words_matched)

            if step_conditions:
                all_conditions.append(and_(*step_conditions))
        
        if all_conditions:
            query = query.filter(and_(*all_conditions))
        if supplier_filter:
            query = query.filter(Supplier.name == supplier_filter)
            
        return query.order_by(Invoice.date.desc(), Invoice.number.desc()).limit(500).all()

    def search_sales_items(self, search_steps):
        """
        Cerca tra le righe delle fatture clienti (vendite 2019-2026),
        supportando la ricerca multi-codice (codice master + vecchi codici legacy da disegno macchina)
        con logica AND precisa tra le parole digitate.
        """
        import re
        from sqlalchemy import or_, and_
        from app.database import SalesInvoice, SalesInvoiceItem, Customer
        
        query = self.session.query(SalesInvoiceItem).join(SalesInvoice).join(Customer)
        all_conditions = []
        customer_filter = None

        for step in search_steps:
            if step.get('customer'):
                customer_filter = step['customer']

            step_conditions = []

            # 1. Ricerca multi-codice per corrispondenze esatte
            equiv_codes = step.get('equivalent_codes', [])
            equiv_conds = []
            if equiv_codes and step.get('search_code', True):
                for c in equiv_codes:
                    cond = self._build_exact_code_condition(SalesInvoiceItem.raw_code, c)
                    if cond is not None:
                        equiv_conds.append(cond)

            # 2. Ricerca per parole digitate con logica AND
            word_conds = []
            for word in step.get('words', []):
                if not word:
                    continue
                
                m = re.match(r'^([a-zA-Z]+)(\d+)$', word)
                patterns = [f"%{word}%"]
                if m:
                    l, n = m.group(1), m.group(2)
                    patterns.extend([f"%{l} {n}%", f"%{l}={n}%", f"%{l}.{n}%", f"%{l}-{n}%"])

                w_pats = []
                for pat in patterns:
                    if step.get('search_desc', True):
                        w_pats.append(SalesInvoiceItem.description.ilike(pat))
                    if step.get('search_code', True):
                        cond = self._build_exact_code_condition(SalesInvoiceItem.raw_code, word)
                        if cond is not None:
                            w_pats.append(cond)
                        else:
                            w_pats.append(SalesInvoiceItem.raw_code.ilike(pat))
                    w_pats.append(Customer.name.ilike(pat))
                    w_pats.append(SalesInvoice.number.ilike(pat))

                if w_pats:
                    word_conds.append(or_(*w_pats))

            all_words_matched = and_(*word_conds) if word_conds else None

            if equiv_conds and all_words_matched is not None:
                step_conditions.append(or_(or_(*equiv_conds), all_words_matched))
            elif equiv_conds:
                step_conditions.append(or_(*equiv_conds))
            elif all_words_matched is not None:
                step_conditions.append(all_words_matched)

            if step_conditions:
                all_conditions.append(and_(*step_conditions))

        if all_conditions:
            query = query.filter(and_(*all_conditions))
        if customer_filter:
            query = query.filter(Customer.name == customer_filter)

        return query.order_by(SalesInvoice.date.desc(), SalesInvoice.number.desc()).limit(500).all()

    def get_product_360(self, term: str):
        """
        Restituisce la scheda a 360° dell'articolo:
        - Dati master (codice, descrizione, costi interni, listino)
        - Codici vecchi / posizioni esplosi macchina collegati (N:1)
        - Codici fornitori collegati
        - Storico ultimi acquisti
        - Storico ultime vendite clienti
        """
        from app.database import Product, ProductLegacyCode, SupplierProduct, SalesInvoiceItem, SalesInvoice, InvoiceItem, Invoice
        clean = term.strip().replace('\u200b', '')
        if not clean:
            return None

        # 1. Cerca per codice master esatto
        prod = self.session.query(Product).filter(Product.code.ilike(clean)).first()

        # 2. Cerca per codice vecchio/esploso esatto o parziale
        if not prod:
            leg = self.session.query(ProductLegacyCode).filter(ProductLegacyCode.legacy_code.ilike(clean)).first()
            if leg:
                prod = leg.product

        # 3. Cerca per codice fornitore esatto
        if not prod:
            sp = self.session.query(SupplierProduct).filter(SupplierProduct.supplier_code.ilike(clean)).first()
            if sp:
                prod = sp.product

        # 4. Cerca per codice master parziale
        if not prod:
            prod = self.session.query(Product).filter(Product.code.ilike(f"%{clean}%")).first()

        # 5. Cerca per codice o descrizione legacy parziale
        if not prod:
            leg = self.session.query(ProductLegacyCode).filter(
                (ProductLegacyCode.legacy_code.ilike(f"%{clean}%")) |
                (ProductLegacyCode.legacy_description.ilike(f"%{clean}%"))
            ).first()
            if leg:
                prod = leg.product

        # 6. Cerca per descrizione articolo master
        if not prod:
            prod = self.session.query(Product).filter(Product.name.ilike(f"%{clean}%")).first()

        # 7. Cerca parole chiave multiple anche combinando prodotto, legacy e fornitore
        if not prod and len(clean.split()) > 1:
            import re
            from sqlalchemy import or_
            from app.database import Supplier
            norm = re.sub(r'\b([a-zA-Z])\s+(\d+)\b', r'\1\2', clean, flags=re.IGNORECASE)
            stopwords = {'il', 'lo', 'la', 'i', 'gli', 'le', 'di', 'da', 'in', 'con', 'su', 'per', 'del', 'della', 'dei', 'degli'}
            words = [w for w in norm.split() if len(w) > 1 and w.lower() not in stopwords]
            if words:
                q = self.session.query(Product)\
                    .outerjoin(SupplierProduct, Product.id == SupplierProduct.product_id)\
                    .outerjoin(Supplier, SupplierProduct.supplier_id == Supplier.id)\
                    .outerjoin(ProductLegacyCode, Product.id == ProductLegacyCode.product_id)
                for w in words:
                    m = re.match(r'^([a-zA-Z]+)(\d+)$', w)
                    patterns = [f"%{w}%"]
                    if m:
                        l, n = m.group(1), m.group(2)
                        patterns.extend([f"%{l} {n}%", f"%{l}={n}%", f"%{l}.{n}%", f"%{l}-{n}%"])
                    
                    or_pats = []
                    for pat in patterns:
                        or_pats.extend([
                            Product.name.ilike(pat),
                            Product.code.ilike(pat),
                            Supplier.name.ilike(pat),
                            SupplierProduct.supplier_code.ilike(pat),
                            SupplierProduct.supplier_description.ilike(pat),
                            ProductLegacyCode.legacy_code.ilike(pat),
                            ProductLegacyCode.legacy_description.ilike(pat)
                        ])
                    q = q.filter(or_(*or_pats))
                prod = q.first()

        # 8. Cerca per fornitore collegato
        if not prod:
            from app.database import Supplier
            sp = self.session.query(SupplierProduct).join(Supplier).filter(
                (Supplier.name.ilike(f"%{clean}%")) | (SupplierProduct.supplier_description.ilike(f"%{clean}%"))
            ).first()
            if sp:
                prod = sp.product

        if not prod:
            return None

        legacy_codes = self.session.query(ProductLegacyCode).filter_by(product_id=prod.id).all()
        supplier_products = self.session.query(SupplierProduct).filter_by(product_id=prod.id).all()
        
        recent_purchases = (self.session.query(InvoiceItem)
                            .join(Invoice)
                            .filter(InvoiceItem.product_id == prod.id)
                            .order_by(Invoice.date.desc())
                            .limit(10).all())
                            
        recent_sales = (self.session.query(SalesInvoiceItem)
                        .join(SalesInvoice)
                        .filter(SalesInvoiceItem.product_id == prod.id)
                        .order_by(SalesInvoice.date.desc())
                        .limit(10).all())

        from app.database import ProductMaterial, ProductOperation
        materials = (self.session.query(ProductMaterial)
                     .filter_by(product_id=prod.id)
                     .order_by(ProductMaterial.line_num)
                     .all())
        operations = (self.session.query(ProductOperation)
                      .filter_by(product_id=prod.id)
                      .order_by(ProductOperation.sequence)
                      .all())

        return {
            'product': prod,
            'legacy_codes': legacy_codes,
            'supplier_products': supplier_products,
            'recent_purchases': recent_purchases,
            'recent_sales': recent_sales,
            'materials': materials,
            'operations': operations
        }

    def search_matching_products(self, text: str, supplier_name: str = None, search_code: bool = True, search_desc: bool = True, limit: int = 150):
        """
        Cerca gli articoli a catalogo corrispondenti al testo inserito.
        Supporta codice master esatto, codice vecchio/legacy esatto, codice fornitore esatto,
        e ricerca multi-parola nella descrizione e nei codici dell'articolo.
        Restituisce una lista di oggetti Product.
        """
        import re
        from sqlalchemy import or_, and_
        from app.database import Product, ProductLegacyCode, SupplierProduct, Supplier

        clean = text.strip().replace('\u200b', '')
        if not clean:
            return []

        if not search_code and not search_desc:
            search_code = search_desc = True

        # 1. Se il testo corrisponde esattamente a un codice (master, legacy, o fornitore)
        if search_code:
            p_exact = self.session.query(Product).filter(Product.code.ilike(clean)).all()
            if p_exact:
                return p_exact

            p_leg = self.session.query(Product).join(ProductLegacyCode).filter(ProductLegacyCode.legacy_code.ilike(clean)).all()
            if p_leg:
                return p_leg

            p_supp = self.session.query(Product).join(SupplierProduct).filter(SupplierProduct.supplier_code.ilike(clean)).all()
            if p_supp:
                return p_supp

        # 2. Ricerca multi-parola per descrizione e/o codice
        norm = re.sub(r'\b([a-zA-Z])\s+(\d+)\b', r'\1\2', clean, flags=re.IGNORECASE)
        stopwords = {'il', 'lo', 'la', 'i', 'gli', 'le', 'di', 'da', 'in', 'con', 'su', 'per', 'del', 'della', 'dei', 'degli'}
        raw_words = [w for w in re.split(r'[\s%]+', norm) if len(w) > 1]
        words = [w for w in raw_words if w.lower() not in stopwords]
        if not words and raw_words:
            words = raw_words

        if not words:
            return []

        q = self.session.query(Product).outerjoin(SupplierProduct).outerjoin(Supplier).outerjoin(ProductLegacyCode)

        if supplier_name and supplier_name != 'Tutti i fornitori':
            q = q.filter(Supplier.name == supplier_name)

        word_conds = []
        for w in words:
            m = re.match(r'^([a-zA-Z]+)(\d+)$', w)
            patterns = [f"%{w}%"]
            if m:
                l, n = m.group(1), m.group(2)
                patterns.extend([f"%{l} {n}%", f"%{l}={n}%", f"%{l}.{n}%", f"%{l}-{n}%"])

            w_pats = []
            for pat in patterns:
                if search_desc:
                    w_pats.append(Product.name.ilike(pat))
                    w_pats.append(SupplierProduct.supplier_description.ilike(pat))
                    w_pats.append(ProductLegacyCode.legacy_description.ilike(pat))
                if search_code:
                    w_pats.append(Product.code.ilike(pat))
                    w_pats.append(ProductLegacyCode.legacy_code.ilike(pat))
                    w_pats.append(SupplierProduct.supplier_code.ilike(pat))

            if w_pats:
                word_conds.append(or_(*w_pats))

        if not word_conds:
            return []

        results = q.filter(and_(*word_conds)).distinct().order_by(Product.code).limit(limit).all()
        return results

    def calculate_raw_material_cut(self, product_code: str, length_mm: float) -> dict:
        """
        Calcola il costo di uno spezzone di materiale commerciale (es. barra di ottone/alluminio/acciaio).
        Lunghezza in mm -> convertita in metri -> moltiplicata per fattore di conversione (kg/m) -> peso in kg -> moltiplicato per costo al kg.
        """
        from app.database import Product, InvoiceItem, Invoice
        clean = product_code.strip()
        prod = self.session.query(Product).filter(Product.code.ilike(clean)).first()
        if not prod:
            return {"error": f"Articolo non trovato: {product_code}"}

        conv = float(prod.conversion_factor or 1.0)
        length_m = float(length_mm) / 1000.0
        weight_kg = length_m * conv

        last_item = (self.session.query(InvoiceItem)
                     .join(Invoice)
                     .filter(InvoiceItem.product_id == prod.id, InvoiceItem.unit_price > 0)
                     .order_by(Invoice.date.desc())
                     .first())
        price_per_kg = float(last_item.unit_price) if last_item else float(prod.production_cost or 0.0)
        total_cost = weight_kg * price_per_kg

        return {
            "code": prod.code,
            "name": prod.name,
            "length_mm": length_mm,
            "length_m": length_m,
            "conversion_factor": conv,
            "weight_kg": round(weight_kg, 4),
            "purchase_um": prod.purchase_um or "KG",
            "warehouse_um": prod.unit_measure or "MT",
            "price_per_kg": round(price_per_kg, 4),
            "total_cost": round(total_cost, 2),
            "price_source": f"Fattura {last_item.invoice.number} del {last_item.invoice.date.strftime('%d/%m/%Y')}" if last_item else "Costo standard interno"
        }

    def calculate_production_piece_cost(self, product_code: str) -> dict:
        """
        Calcola il costo totale di produzione per un pezzo (Distinta Materiali + Ciclo Lavorazioni).
        """
        from app.database import Product, ProductMaterial, ProductOperation, InvoiceItem
        clean = product_code.strip()
        prod = self.session.query(Product).filter(Product.code.ilike(clean)).first()
        if not prod:
            return {"error": f"Articolo non trovato: {product_code}"}

        materials = self.session.query(ProductMaterial).filter_by(product_id=prod.id).order_by(ProductMaterial.line_num).all()
        operations = self.session.query(ProductOperation).filter_by(product_id=prod.id).order_by(ProductOperation.sequence).all()

        mat_breakdown = []
        tot_materials_cost = 0.0
        for m in materials:
            unit_c = float(m.unit_cost or 0.0)
            if unit_c == 0 and m.component_product:
                last_p = (self.session.query(InvoiceItem)
                          .filter(InvoiceItem.product_id == m.component_product_id, InvoiceItem.unit_price > 0)
                          .order_by(InvoiceItem.id.desc()).first())
                if last_p:
                    unit_c = float(last_p.unit_price)

            subtot = float(m.quantity or 1.0) * unit_c
            tot_materials_cost += subtot
            mat_breakdown.append({
                "line": m.line_num,
                "code": m.component_code,
                "description": m.description,
                "quantity": m.quantity,
                "um": m.unit_measure,
                "unit_cost": unit_c,
                "total_cost": round(subtot, 2)
            })

        ops_breakdown = []
        tot_ops_cost = 0.0
        tot_run_hours = 0.0
        tot_setup_hours = 0.0

        for op in operations:
            run_h = float(op.operation_hours or 0.0)
            set_h = float(op.setup_hours or 0.0)
            rate = float(op.hourly_rate or 0.0)
            line_cost = (run_h + set_h) * rate
            tot_ops_cost += line_cost
            tot_run_hours += run_h
            tot_setup_hours += set_h
            ops_breakdown.append({
                "sequence": op.sequence,
                "phase": op.phase_code,
                "description": op.description,
                "setup_hours": set_h,
                "run_hours": run_h,
                "rate": rate,
                "total_cost": round(line_cost, 2)
            })

        total_production_cost = tot_materials_cost + tot_ops_cost

        return {
            "code": prod.code,
            "name": prod.name,
            "type": prod.type,
            "materials": mat_breakdown,
            "total_materials_cost": round(tot_materials_cost, 2),
            "operations": ops_breakdown,
            "total_setup_hours": round(tot_setup_hours, 2),
            "total_run_hours": round(tot_run_hours, 2),
            "total_operations_cost": round(tot_ops_cost, 2),
            "total_production_cost": round(total_production_cost, 2),
            "catalog_std_cost": float(prod.production_cost or 0.0),
            "catalog_list_price": float(prod.list_price or 0.0)
        }


    # ==========================================
    # GESTIONE ANAGRAFICA CLIENTI
    # ==========================================
    def get_customers_summary(self, search_text=None):
        """Restituisce il riepilogo di tutti i clienti con fatturato totale e numero fatture."""
        from app.database import Customer, SalesInvoice
        from sqlalchemy import func, desc

        query = self.session.query(
            Customer.id,
            Customer.name,
            Customer.piva_cf,
            Customer.country,
            func.count(SalesInvoice.id).label('num_fatture'),
            func.coalesce(func.sum(SalesInvoice.total_amount), 0.0).label('totale_fatturato'),
            func.max(SalesInvoice.date).label('ultima_fattura')
        ).outerjoin(SalesInvoice, Customer.id == SalesInvoice.customer_id)

        if search_text:
            s = f"%{search_text.strip()}%"
            query = query.filter((Customer.name.ilike(s)) | (Customer.piva_cf.ilike(s)))

        query = query.group_by(Customer.id).order_by(desc('totale_fatturato'))
        return query.all()

    def get_customer_detail(self, customer_id: int):
        """Restituisce la scheda completa 360° di un cliente con tutte le sue fatture e ricambi acquistati."""
        from app.database import Customer, SalesInvoice, SalesInvoiceItem, WorkOrder
        customer = self.session.query(Customer).filter_by(id=customer_id).first()
        if not customer:
            return None

        invoices = self.session.query(SalesInvoice).filter_by(customer_id=customer_id).order_by(SalesInvoice.date.desc()).all()
        
        # Righe articoli acquistati dal cliente
        items = (self.session.query(SalesInvoiceItem)
                 .join(SalesInvoice)
                 .filter(SalesInvoice.customer_id == customer_id)
                 .order_by(SalesInvoice.date.desc())
                 .limit(200).all())

        work_orders = self.session.query(WorkOrder).filter_by(customer_id=customer_id).order_by(WorkOrder.date_opened.desc()).all()

        return {
            'customer': customer,
            'invoices': invoices,
            'items': items,
            'work_orders': work_orders
        }

    # ==========================================
    # GESTIONE ANAGRAFICA FORNITORI
    # ==========================================
    def get_suppliers_summary(self, search_text=None, filter_type="all"):
        """Restituisce il riepilogo di tutti i fornitori con spesa totale, numero fatture e articoli a catalogo."""
        from app.database import Supplier, Invoice, SupplierProduct
        from sqlalchemy import func, desc

        # Subquery conteggio articoli a catalogo
        prod_subq = self.session.query(
            SupplierProduct.supplier_id,
            func.count(SupplierProduct.id).label('num_articoli')
        ).group_by(SupplierProduct.supplier_id).subquery()

        # Subquery riepilogo fatture d'acquisto
        inv_subq = self.session.query(
            Invoice.supplier_id,
            func.count(Invoice.id).label('num_fatture'),
            func.coalesce(func.sum(Invoice.total_amount), 0.0).label('totale_speso'),
            func.max(Invoice.date).label('ultima_fattura')
        ).group_by(Invoice.supplier_id).subquery()

        query = self.session.query(
            Supplier.id,
            Supplier.name,
            Supplier.piva,
            func.coalesce(inv_subq.c.num_fatture, 0).label('num_fatture'),
            func.coalesce(inv_subq.c.totale_speso, 0.0).label('totale_speso'),
            inv_subq.c.ultima_fattura,
            func.coalesce(prod_subq.c.num_articoli, 0).label('num_articoli')
        ).outerjoin(inv_subq, Supplier.id == inv_subq.c.supplier_id)\
         .outerjoin(prod_subq, Supplier.id == prod_subq.c.supplier_id)

        if search_text:
            clean_s = search_text.strip()
            s = f"%{clean_s}%"
            clean_alpha = re.sub(r'[^a-zA-Z0-9]', '', clean_s).lower()
            matched_ids = []
            if len(clean_alpha) >= 2:
                all_s = self.session.query(Supplier.id, Supplier.name).all()
                for s_id, s_name in all_s:
                    s_alpha = re.sub(r'[^a-zA-Z0-9]', '', (s_name or '').lower())
                    if clean_alpha in s_alpha or s_alpha in clean_alpha:
                        matched_ids.append(s_id)
            if matched_ids:
                query = query.filter(or_(Supplier.id.in_(matched_ids), Supplier.name.ilike(s), Supplier.piva.ilike(s)))
            else:
                query = query.filter((Supplier.name.ilike(s)) | (Supplier.piva.ilike(s)))

        if filter_type == "invoices_only":
            query = query.filter(inv_subq.c.num_fatture > 0)
        elif filter_type == "catalog_only":
            query = query.filter(prod_subq.c.num_articoli > 0)

        query = query.order_by(desc('totale_speso'), Supplier.name)
        return query.all()

    def get_supplier_detail(self, supplier_id: int):
        """Restituisce la scheda completa del fornitore con fatture e catalogo articoli forniti."""
        from app.database import Supplier, Invoice, SupplierProduct
        supplier = self.session.query(Supplier).filter_by(id=supplier_id).first()
        if not supplier:
            return None

        invoices = self.session.query(Invoice).filter_by(supplier_id=supplier_id).order_by(Invoice.date.desc()).all()
        products = self.session.query(SupplierProduct).filter_by(supplier_id=supplier_id).all()

        return {
            'supplier': supplier,
            'invoices': invoices,
            'products': products
        }

    # ==========================================
    # GESTIONE CATALOGO ARTICOLI MASTER
    # ==========================================
    def get_product_categories_with_counts(self):
        """Restituisce l'elenco delle categorie presenti nel database con il numero totale di articoli."""
        from app.database import Product
        from sqlalchemy import func
        rows = (self.session.query(Product.category, func.count(Product.id))
                .filter(Product.category.isnot(None), Product.category != '')
                .group_by(Product.category)
                .order_by(Product.category)
                .all())
        return rows

    def get_products_catalog(self, category=None, search_text=None, limit=200):
        """Restituisce gli articoli dal catalogo master."""
        from app.database import Product
        query = self.session.query(Product)
        if category and not category.startswith("Tutte"):
            query = query.filter(Product.category == category)
        if search_text:
            s = f"%{search_text.strip()}%"
            query = query.filter((Product.code.ilike(s)) | (Product.name.ilike(s)))
        if limit and limit > 0:
            query = query.limit(limit)
        return query.order_by(Product.code).all()

    def get_products_catalog_with_count(self, category=None, search_text=None, limit=300):
        """Restituisce (articoli, conteggio_totale) per il catalogo master."""
        from app.database import Product
        query = self.session.query(Product)
        if category and not category.startswith("Tutte"):
            query = query.filter(Product.category == category)
        if search_text:
            s = f"%{search_text.strip()}%"
            query = query.filter((Product.code.ilike(s)) | (Product.name.ilike(s)))
            
        total_count = query.count()
        if limit and limit > 0:
            items = query.order_by(Product.code).limit(limit).all()
        else:
            items = query.order_by(Product.code).all()
        return items, total_count

    # ==========================================
    # GESTIONE COMMESSE & LAVORAZIONI OFFICINA
    # ==========================================
    def get_work_orders(self, status_filter=None, search_text=None):
        """Restituisce l'elenco delle commesse di lavoro in officina."""
        from app.database import WorkOrder, Customer
        from sqlalchemy import desc

        query = self.session.query(WorkOrder).join(Customer)
        if status_filter and status_filter != "Tutte":
            query = query.filter(WorkOrder.status == status_filter)
        if search_text:
            s = f"%{search_text.strip()}%"
            query = query.filter(
                (WorkOrder.number.ilike(s)) | 
                (Customer.name.ilike(s)) | 
                (WorkOrder.machine_model.ilike(s)) |
                (WorkOrder.machine_serial.ilike(s))
            )
        return query.order_by(desc(WorkOrder.date_opened)).all()

    def create_work_order(self, customer_id: int, machine_model: str, machine_serial: str = "", notes: str = ""):
        """Crea una nuova commessa di lavorazione."""
        from app.database import WorkOrder
        from datetime import datetime
        now = datetime.now()
        # Genera progressivo numero commessa: COMM-ANNO-PROGRESSIVO
        count_year = self.session.query(WorkOrder).filter(WorkOrder.number.like(f"COMM-{now.year}-%")).count() + 1
        num_commessa = f"COMM-{now.year}-{count_year:03d}"

        wo = WorkOrder(
            number=num_commessa,
            date_opened=now.date(),
            customer_id=customer_id,
            machine_model=machine_model.strip(),
            machine_serial=machine_serial.strip() if machine_serial else None,
            status="APERTA",
            notes=notes.strip() if notes else None
        )
        self.session.add(wo)
        self.session.commit()
        return wo

    # ==========================================
    # GESTIONE ESPLOSI MACCHINE & DISTINTE BASE
    # ==========================================
    def get_machine_models_with_counts(self):
        """Restituisce l'elenco dei modelli macchina con il conteggio degli esplosi archiviati."""
        from app.database import ExplodedDiagram
        from sqlalchemy import func
        rows = (self.session.query(ExplodedDiagram.machine_model, func.count(ExplodedDiagram.id))
                .filter(ExplodedDiagram.machine_model.isnot(None))
                .group_by(ExplodedDiagram.machine_model)
                .order_by(ExplodedDiagram.machine_model)
                .all())
        return rows

    def get_exploded_diagrams(self, machine_model=None, search_text=None):
        """Restituisce l'elenco degli esplosi filtrati per modello o testo di ricerca."""
        from app.database import ExplodedDiagram, ExplodedDiagramItem
        query = self.session.query(ExplodedDiagram)
        if machine_model and not machine_model.startswith("Tutti"):
            query = query.filter(ExplodedDiagram.machine_model == machine_model)
        if search_text and search_text.strip():
            s = f"%{search_text.strip()}%"
            # Cerca nel titolo, codice tavola o tra i componenti contenuti
            subq_items = (self.session.query(ExplodedDiagramItem.diagram_id)
                          .filter(
                              (ExplodedDiagramItem.part_code.ilike(s)) |
                              (ExplodedDiagramItem.old_position_code.ilike(s)) |
                              (ExplodedDiagramItem.description.ilike(s))
                          ).subquery())
            query = query.filter(
                (ExplodedDiagram.title.ilike(s)) |
                (ExplodedDiagram.code.ilike(s)) |
                (ExplodedDiagram.file_name.ilike(s)) |
                (ExplodedDiagram.id.in_(subq_items))
            )
        return query.order_by(ExplodedDiagram.machine_model, ExplodedDiagram.code).all()

    def get_diagram_detail(self, diagram_id: int):
        """Restituisce l'esploso e la lista dei suoi componenti."""
        from app.database import ExplodedDiagram, ExplodedDiagramItem
        diag = self.session.query(ExplodedDiagram).filter_by(id=diagram_id).first()
        if not diag:
            return None, []
        items = (self.session.query(ExplodedDiagramItem)
                 .filter_by(diagram_id=diagram_id)
                 .order_by(ExplodedDiagramItem.page_number, ExplodedDiagramItem.id)
                 .all())
        return diag, items

    def get_diagrams_for_product(self, product_code: str):
        """Trova tutti gli esplosi in cui compare un codice articolo (master o vecchio codice esploso)."""
        if not product_code or not product_code.strip():
            return []
        from app.database import ExplodedDiagram, ExplodedDiagramItem, ProductLegacyCode
        from sqlalchemy.orm import joinedload
        clean = product_code.strip()
        s = f"%{clean}%"
        
        # 1. Cerca per part_code diretto
        items = (self.session.query(ExplodedDiagramItem)
                 .options(joinedload(ExplodedDiagramItem.diagram))
                 .filter((ExplodedDiagramItem.part_code.ilike(clean)) | (ExplodedDiagramItem.part_code.ilike(s)))
                 .all())
                 
        # 2. Se non ha trovato nulla o per arricchire, cerca per old_position_code
        if not items:
            items = (self.session.query(ExplodedDiagramItem)
                     .options(joinedload(ExplodedDiagramItem.diagram))
                     .filter((ExplodedDiagramItem.old_position_code.ilike(clean)) | (ExplodedDiagramItem.old_position_code.ilike(s)))
                     .all())
                     
        # 3. Cerca tramite eventuali codici legacy collegati
        if not items:
            leg_codes = [r[0] for r in self.session.query(ProductLegacyCode.legacy_code).filter(ProductLegacyCode.legacy_code.ilike(s)).all()]
            for lc in leg_codes[:5]:
                sub_items = (self.session.query(ExplodedDiagramItem)
                             .options(joinedload(ExplodedDiagramItem.diagram))
                             .filter((ExplodedDiagramItem.old_position_code.ilike(lc)) | (ExplodedDiagramItem.part_code.ilike(lc)))
                             .all())
                items.extend(sub_items)
                
        # Deduplica per (diagram_id, position_num)
        seen = set()
        unique_results = []
        for it in items:
            key = (it.diagram_id, it.position_num, it.part_code)
            if key not in seen and it.diagram:
                seen.add(key)
                unique_results.append({
                    'diagram_id': it.diagram.id,
                    'code': it.diagram.code,
                    'title': it.diagram.title,
                    'machine_model': it.diagram.machine_model,
                    'file_path': it.diagram.file_path,
                    'position_num': it.position_num,
                    'old_position_code': it.old_position_code,
                    'part_code': it.part_code,
                    'description': it.description,
                    'quantity': it.quantity,
                    'page_number': it.page_number
                })
        return unique_results

    def open_diagram_pdf(self, file_path: str):
        """Apre il file PDF dell'esploso nel visualizzatore nativo del sistema operativo."""
        import os
        import sys
        import subprocess
        if not file_path:
            return False, "Percorso file non specificato."
            
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        candidates = [
            file_path,
            os.path.join(base_dir, file_path),
            os.path.join(base_dir, "Esplosi", os.path.basename(file_path)),
            os.path.join(base_dir, "File_per_progetto", "Esplosi", os.path.basename(file_path)),
            os.path.join(os.getcwd(), file_path),
            os.path.join(os.getcwd(), "File_per_progetto", file_path),
            os.path.join(os.getcwd(), "File_per_progetto", "Esplosi", os.path.basename(file_path)),
            os.path.join(r"\\angeleri_new\Pubblica\Database\Esplosi", os.path.basename(file_path)),
            os.path.join(r"\\192.168.1.38\Pubblica\Database\Esplosi", os.path.basename(file_path)),
        ]
        resolved = None
        for c in candidates:
            try:
                if os.path.exists(c):
                    resolved = os.path.abspath(c)
                    break
            except Exception:
                continue
                
        if not resolved:
            return False, f"File PDF non trovato sul disco: {file_path}"
            
        try:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            url = QUrl.fromLocalFile(resolved)
            if QDesktopServices.openUrl(url):
                return True, resolved
        except Exception:
            pass

        try:
            os.startfile(resolved)
            return True, resolved
        except Exception as e:
            try:
                subprocess.Popen(['cmd', '/c', 'start', '', resolved], shell=False)
                return True, resolved
            except Exception as ex:
                return False, f"Impossibile aprire il file: {ex}"

    def reindex_all_diagrams(self, esplosi_dir: str = None):
        """Avvia la reindicizzazione degli esplosi PDF da cartella predefinita o personalizzata."""
        from app.utils.diagram_indexer import index_all_diagrams
        return index_all_diagrams(esplosi_dir=esplosi_dir)

    def import_comparativo_codes(self, pdf_path: str):
        """Importa o aggiorna le corrispondenze storiche da un file PDF comparativo."""
        from scripts.rebuild_legacy_codes import rebuild
        try:
            # Invoca la logica di importazione pulita
            from scripts.import_master_catalog import import_comparativo_codici
            count = import_comparativo_codici(self.session, pdf_path)
            return {'status': 'ok', 'count': count, 'message': f"Importate con successo {count} corrispondenze storiche."}
        except Exception as e:
            return {'status': 'error', 'message': f"Errore durante l'importazione: {e}"}



