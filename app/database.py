import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey, Text, DateTime, Index
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

Base = declarative_base()

# ==========================================
# ANAGRAFICA FORNITORI & CLIENTI
# ==========================================

class Supplier(Base):
    __tablename__ = 'suppliers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    piva = Column(String(50), nullable=True)
    
    invoices = relationship("Invoice", back_populates="supplier")
    supplier_products = relationship("SupplierProduct", back_populates="supplier")

    def __repr__(self):
        return f"<Supplier(name='{self.name}')>"


class Customer(Base):
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    piva_cf = Column(String(50), nullable=True, index=True)
    address = Column(String(255), nullable=True)
    country = Column(String(10), default="IT")
    notes = Column(Text, nullable=True)
    
    sales_invoices = relationship("SalesInvoice", back_populates="customer")
    work_orders = relationship("WorkOrder", back_populates="customer")

    def __repr__(self):
        return f"<Customer(name='{self.name}', country='{self.country}')>"


# ==========================================
# ANAGRAFICA ARTICOLI, EQUIVALENZE & VECCHI CODICI
# ==========================================

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False, index=True) # Codice Master (es. A850-0050, L010-0001, SP-0001)
    name = Column(String(255), nullable=False) # Descrizione principale
    type = Column(String(50), default="ALTRO") # ACQUISTO, LAVORAZIONE, RICAMBIO, FUSIONE, ALTRO
    category = Column(String(100), nullable=True) # Alluminio, Ferro, Carpenteria, Commerciale, ecc.
    unit_measure = Column(String(20), default="NR")
    production_cost = Column(Float, default=0.0) # Costo produzione / STD interno
    list_price = Column(Float, default=0.0) # Listino vendita pezzi ricambio
    customer_code = Column(String(100), nullable=True) # Per compatibilità
    notes = Column(Text, nullable=True)
    
    # Relazioni
    legacy_codes = relationship("ProductLegacyCode", back_populates="product", cascade="all, delete-orphan")
    supplier_products = relationship("SupplierProduct", back_populates="product", cascade="all, delete-orphan")
    purchase_items = relationship("InvoiceItem", back_populates="product")
    sales_items = relationship("SalesInvoiceItem", back_populates="product")
    exploded_items = relationship("ExplodedDiagramItem", back_populates="product")

    # Retro-compatibilità con vecchio codice che usa `items`
    items = relationship("InvoiceItem", back_populates="product", viewonly=True)

    def __repr__(self):
        return f"<Product(code='{self.code}', name='{self.name}', type='{self.type}')>"


class ProductLegacyCode(Base):
    """Mappatura N a 1 tra codici vecchi/esplosi di macchine diverse e il codice nuovo master."""
    __tablename__ = 'product_legacy_codes'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)
    legacy_code = Column(String(100), nullable=False, index=True) # es. 3150-12, 00ICT60-01
    legacy_description = Column(String(255), nullable=True)
    machine_reference = Column(String(100), nullable=True) # es. MAV 3150, ICT 60
    cost_std = Column(Float, default=0.0)
    list_price = Column(Float, default=0.0)
    
    product = relationship("Product", back_populates="legacy_codes")

    def __repr__(self):
        return f"<ProductLegacyCode(legacy='{self.legacy_code}' -> product_id={self.product_id})>"


class SupplierProduct(Base):
    """Equivalenze e codici articolo fornitore (da Articoli_fornitori.pdf)."""
    __tablename__ = 'supplier_products'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=True, index=True)
    supplier_name = Column(String(255), nullable=True)
    supplier_code = Column(String(100), nullable=False, index=True) # Codice che usa il fornitore
    supplier_description = Column(String(255), nullable=True)
    
    product = relationship("Product", back_populates="supplier_products")
    supplier = relationship("Supplier", back_populates="supplier_products")

    def __repr__(self):
        return f"<SupplierProduct(supplier='{self.supplier_name}', code='{self.supplier_code}')>"


# ==========================================
# FATTURE ACQUISTO (FORNITORI)
# ==========================================

class Invoice(Base):
    __tablename__ = 'invoices'
    
    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    number = Column(String(100), nullable=False)
    total_amount = Column(Float, default=0.0)
    file_path = Column(String(500), nullable=True)
    
    supplier = relationship("Supplier", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Invoice(number='{self.number}', date={self.date}, total={self.total_amount})>"


class InvoiceItem(Base):
    __tablename__ = 'invoice_items'
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True, index=True)
    
    code = Column(String(100), nullable=True, index=True) # Raw Code in fattura fornitore
    customer_code = Column(String(100), nullable=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0)
    
    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", back_populates="purchase_items")

    def __repr__(self):
        return f"<InvoiceItem(code='{self.code}', desc='{self.description[:25]}', qty={self.quantity}, price={self.unit_price})>"


# ==========================================
# FATTURE VENDITA (CLIENTI 2019-2026)
# ==========================================

class SalesInvoice(Base):
    __tablename__ = 'sales_invoices'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    number = Column(String(100), nullable=False) # es. "1", "45/E"
    date = Column(Date, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    doc_type = Column(String(50), default="FATTURA") # TD01, TD24, ecc.
    total_amount = Column(Float, default=0.0)
    file_path = Column(String(500), nullable=True)
    
    customer = relationship("Customer", back_populates="sales_invoices")
    items = relationship("SalesInvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SalesInvoice(num='{self.number}', year={self.year}, date={self.date}, total={self.total_amount})>"


class SalesInvoiceItem(Base):
    __tablename__ = 'sales_invoice_items'
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('sales_invoices.id'), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True, index=True)
    
    line_number = Column(Integer, nullable=True)
    raw_code = Column(String(100), nullable=True, index=True) # Codice articolo inserito in fattura cliente
    description = Column(String(500), nullable=False)
    unit_measure = Column(String(20), default="NR")
    quantity = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    discount = Column(Float, default=0.0) # Sconto applicato %
    total_price = Column(Float, default=0.0) # Importo riga netto
    
    invoice = relationship("SalesInvoice", back_populates="items")
    product = relationship("Product", back_populates="sales_items")

    def __repr__(self):
        return f"<SalesInvoiceItem(code='{self.raw_code}', desc='{self.description[:25]}', qty={self.quantity}, price={self.unit_price})>"


# ==========================================
# COMMESSE & SCHEDE DI LAVORO OFFICINA
# ==========================================

class WorkOrder(Base):
    __tablename__ = 'work_orders'
    
    id = Column(Integer, primary_key=True)
    number = Column(String(50), unique=True, nullable=False, index=True) # es. COMM-2026-001
    date_opened = Column(Date, nullable=False, default=datetime.utcnow)
    date_closed = Column(Date, nullable=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    machine_model = Column(String(100), nullable=True) # es. MAV 3150, ICT 60
    machine_serial = Column(String(100), nullable=True) # Matricola macchinario
    status = Column(String(50), default="APERTA", index=True) # APERTA, IN_LAVORAZIONE, ATTESA_RICAMBI, PRONTA, CHIUSA
    notes = Column(Text, nullable=True)
    
    customer = relationship("Customer", back_populates="work_orders")
    items = relationship("WorkOrderItem", back_populates="work_order", cascade="all, delete-orphan")
    labors = relationship("WorkOrderLabor", back_populates="work_order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WorkOrder(number='{self.number}', status='{self.status}')>"


class WorkOrderItem(Base):
    """Ricambi prelevati e montati sulla macchina per questa commessa."""
    __tablename__ = 'work_order_items'
    
    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey('work_orders.id'), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True, index=True)
    
    code = Column(String(100), nullable=True)
    description = Column(String(255), nullable=False)
    quantity = Column(Float, default=1.0)
    unit_cost = Column(Float, default=0.0) # Costo interno di produzione o fornitore
    unit_price = Column(Float, default=0.0) # Prezzo addebitato al cliente
    total_price = Column(Float, default=0.0)
    
    work_order = relationship("WorkOrder", back_populates="items")
    product = relationship("Product")

    def __repr__(self):
        return f"<WorkOrderItem(desc='{self.description[:25]}', qty={self.quantity}, tot={self.total_price})>"


class WorkOrderLabor(Base):
    """Ore di manodopera o lavorazioni esterne su commessa."""
    __tablename__ = 'work_order_labors'
    
    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey('work_orders.id'), nullable=False, index=True)
    operator_name = Column(String(100), nullable=True)
    hours = Column(Float, default=0.0)
    hourly_rate = Column(Float, default=45.0)
    description = Column(String(255), nullable=True) # es. "Revisione gruppo musone e sostituzione rasatore"
    total_price = Column(Float, default=0.0)
    
    work_order = relationship("WorkOrder", back_populates="labors")

    def __repr__(self):
        return f"<WorkOrderLabor(op='{self.operator_name}', h={self.hours}, tot={self.total_price})>"



# ==========================================
# ESPLOSI MACCHINE & DISTINTE BASE (PDF)
# ==========================================

class ExplodedDiagram(Base):
    """Archivio degli esplosi grafici PDF delle macchine e relative distinte ricambi."""
    __tablename__ = 'exploded_diagrams'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False, index=True) # es. M1-0002, M1-0056, MAV-3150
    title = Column(String(255), nullable=False) # es. ICT 60 mini 18, MAV 3150 Incollatrice
    machine_model = Column(String(100), nullable=True, index=True) # es. MAV 3150, ICT 60, ECOL 60, TERMO 450
    file_name = Column(String(255), nullable=False) # es. M1-0002.pdf
    file_path = Column(String(500), nullable=False) # Percorso su disco
    pages_count = Column(Integer, default=1)
    has_parts_table = Column(Integer, default=0) # 1 se contiene distinte parti indicizzate, 0 se solo schema grafico
    created_at = Column(DateTime, default=datetime.utcnow)
    
    items = relationship("ExplodedDiagramItem", back_populates="diagram", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ExplodedDiagram(code='{self.code}', title='{self.title}', machine='{self.machine_model}')>"


class ExplodedDiagramItem(Base):
    """Singole parti/componenti estratti dalle tavole e distinte degli esplosi."""
    __tablename__ = 'exploded_diagram_items'
    
    id = Column(Integer, primary_key=True)
    diagram_id = Column(Integer, ForeignKey('exploded_diagrams.id'), nullable=False, index=True)
    position_num = Column(String(50), nullable=True, index=True) # Posizione / pallinatura nel disegno (es. "1", "80", "56-A")
    old_position_code = Column(String(100), nullable=True, index=True) # NUMERAZIONE_OLD o CODICEEX storico
    part_code = Column(String(100), nullable=True, index=True) # Codice ordine / codice master (es. L011-0096)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True, index=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Float, default=1.0)
    page_number = Column(Integer, default=1)
    notes = Column(String(255), nullable=True)
    
    diagram = relationship("ExplodedDiagram", back_populates="items")
    product = relationship("Product", back_populates="exploded_items")

    def __repr__(self):
        return f"<ExplodedDiagramItem(pos='{self.position_num}', part='{self.part_code}', desc='{self.description[:25]}')>"


# Indici per ricerche veloci
Index('idx_sales_inv_uniq', SalesInvoice.customer_id, SalesInvoice.year, SalesInvoice.number, unique=True)
Index('idx_purch_inv_uniq', Invoice.supplier_id, Invoice.date, Invoice.number)
Index('idx_exploded_item_search', ExplodedDiagramItem.part_code, ExplodedDiagramItem.old_position_code)



# ==========================================
# SETUP & GESTIONE SESSIONE DATABASE
# ==========================================

engine = None
SessionLocal = None

def init_db(db_url=None):
    """Inizializza la connessione al database (PostgreSQL o SQLite)."""
    global engine, SessionLocal
    
    if not db_url:
        try:
            from app.utils.settings import SettingsManager
            settings = SettingsManager()
            saved_path = settings.get_db_path()
            if saved_path and (saved_path.startswith("postgresql://") or saved_path.startswith("postgresql+psycopg2://")):
                db_url = saved_path
            elif saved_path and not saved_path.startswith("sqlite:///"):
                db_url = f"sqlite:///{os.path.abspath(saved_path).replace('\\', '/')}"
            else:
                db_url = saved_path or "postgresql+psycopg2://angeleri:AngeleriPassword2026!@192.168.1.38:5433/angeleri_db"
        except Exception:
            db_url = "postgresql+psycopg2://angeleri:AngeleriPassword2026!@192.168.1.38:5433/angeleri_db"

    # Se il driver SQLite necessita di path formattato
    if db_url and not (db_url.startswith("sqlite:///") or db_url.startswith("postgresql://") or db_url.startswith("postgresql+psycopg2://")):
        db_url = f"sqlite:///{db_url.replace('\\', '/')}"
        
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine

def get_db_session():
    """Restituisce una nuova sessione database."""
    global SessionLocal
    if SessionLocal is None:
        init_db()
    return SessionLocal()
