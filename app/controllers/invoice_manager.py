import os
from sqlalchemy import func
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
        """Risolve varianti di denominazione al nome canonico tramite SUPPLIER_ALIASES."""
        return SUPPLIER_ALIASES.get(name, name)

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
            # Normalizza il nome fornitore (gestisce varianti di denominazione)
            canonical_name = self._normalize_supplier(parsed_data.supplier_name)

            # Check if invoice already exists (usa il nome canonico)
            existing = self.session.query(Invoice).join(Supplier).filter(
                Supplier.name == canonical_name,
                Invoice.number == parsed_data.number,
                Invoice.date == parsed_data.date
            ).first()

            if existing:
                 print(f"Skipping existing invoice {parsed_data.number}")
                 continue

            # Get or Create Supplier (usa il nome canonico)
            supplier = self.session.query(Supplier).filter_by(name=canonical_name).first()
            if not supplier:
                supplier = Supplier(name=canonical_name)
                self.session.add(supplier)
                self.session.flush()

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

    def search_items(self, search_steps):
        """
        Search for invoice items based on multiple search steps (FOR incremental search).
        search_steps: list of dicts like {'words': [...], 'search_code': bool, 'search_desc': bool, 'supplier': str|None}
        """
        from sqlalchemy import or_, and_
        import re
        
        query = self.session.query(InvoiceItem).join(Invoice).join(Supplier)
        
        all_conditions = []
        supplier_filter = None  # Prende l'ultimo step che ha un fornitore impostato

        for step in search_steps:
            step_conditions = []
            # Filtro fornitore dal primo step che lo definisce (non None)
            if step.get('supplier'):
                supplier_filter = step['supplier']

            for word in step['words']:
                if not word: continue
                
                pattern = f"%{word}%" if '%' not in word else word
                
                field_filters = []
                if step.get('search_desc', True):
                    field_filters.append(InvoiceItem.description.ilike(pattern))
                if step.get('search_code', True):
                    field_filters.append(InvoiceItem.code.ilike(pattern))
                
                if field_filters:
                    step_conditions.append(or_(*field_filters))
            
            if step_conditions:
                all_conditions.append(and_(*step_conditions))
        
        if all_conditions:
            query = query.filter(and_(*all_conditions))

        # Filtro fornitore
        if supplier_filter:
            query = query.filter(Supplier.name == supplier_filter)
            
        return query.order_by(Invoice.date.desc(), Invoice.number.desc()).all()
