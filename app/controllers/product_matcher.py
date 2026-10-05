import re
from sqlalchemy.orm import Session
from ..database import Product
from difflib import SequenceMatcher

class ProductMatcher:
    def __init__(self, session: Session):
        self.session = session
        
    def get_or_create_product(self, code: str, description: str, customer_code: str = None) -> Product:
        """
        Tenta di trovare un prodotto esistente o ne crea uno nuovo.
        Logica:
        1. Exact Match su Code (Fornitore) AND Customer Code (Cliente) se presenti.
        2. Exact Match su Code se presente.
        3. Match su descrizione / nome se code assente.
        4. Crea nuovo garantendo sempre code NOT NULL e univoco.
        """
        code = (code or "").strip()
        description = (description or "").strip()
        customer_code = (customer_code or "").strip() or None
        
        # 1. Exact Match Strong (Code + CustomerCode)
        if code and customer_code:
            existing = self.session.query(Product).filter_by(code=code, customer_code=customer_code).first()
            if existing: return existing
            
        # 2. Exact Match by Supplier Code only
        if code:
            existing = self.session.query(Product).filter_by(code=code).first()
            if existing:
                if customer_code and not existing.customer_code:
                    existing.customer_code = customer_code
                    self.session.flush()
                return existing

        # 3. Match su descrizione / nome se code non presente
        if not code and description:
            existing = self.session.query(Product).filter(
                (Product.name == description) | (Product.code == description)
            ).first()
            if existing:
                return existing

        # 4. Create new
        product_name = code if (code and len(code) > 2) else (description or "ARTICOLO SENZA CODICE")
        
        final_code = code
        if not final_code or len(final_code) <= 1:
            slug = re.sub(r'[^A-Za-z0-9_-]', '', description.upper().replace(' ', '_'))[:30]
            if not slug:
                slug = "ITEM"
            candidate = slug
            idx = 1
            while self.session.query(Product).filter_by(code=candidate).first():
                candidate = f"{slug[:25]}_{idx}"
                idx += 1
            final_code = candidate

        new_product = Product(
            code=final_code,
            customer_code=customer_code,
            name=product_name
        )
        self.session.add(new_product)
        self.session.flush() # Get ID
        return new_product
