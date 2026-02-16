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
        2. Exact Match su Code se Customer Code assente.
        3. Fuzzy match su descrizione (TODO).
        4. Crea nuovo.
        """
        
        # 1. Exact Match Strong (Code + CustomerCode)
        if code and customer_code:
            existing = self.session.query(Product).filter_by(code=code, customer_code=customer_code).first()
            if existing: return existing
            
        # 2. Exact Match by Supplier Code only
        if code:
            existing = self.session.query(Product).filter_by(code=code).first()
            if existing: return existing

        # 3. Create new
        # Se abbiamo il codice tecnico, usiamolo come NOME per la visualizzazione tabellare (richiesta utente)
        product_name = code if (code and len(code.strip()) > 2) else description
        
        new_product = Product(
            code=code if code and len(code.strip()) > 2 else None,
            customer_code=customer_code,
            name=product_name
        )
        self.session.add(new_product)
        self.session.flush() # Get ID
        return new_product
