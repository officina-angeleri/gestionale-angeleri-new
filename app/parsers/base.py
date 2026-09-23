from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import date

@dataclass
class ParsedInvoiceItem:
    code: str # Codice Fornitore (ART.)
    customer_code: str # Codice Cliente (ART.CLI.)
    description: str
    quantity: float
    unit_price: float
    total_price: float

@dataclass
class ParsedInvoice:
    supplier_name: str
    date: date
    number: str
    total_amount: float # Some invoices might not explicitly have it, but we can sum items
    items: List[ParsedInvoiceItem]
    original_file_path: str
    supplier_piva: str = ""

class InvoiceParser(ABC):
    
    @abstractmethod
    def parse(self, file_path: str) -> List[ParsedInvoice]:
        """Parse the given file and return a list of ParsedInvoice objects."""
        pass
    
    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """Return True if this parser can handle the given file."""
        pass
