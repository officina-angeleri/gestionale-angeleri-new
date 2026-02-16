from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime

Base = declarative_base()

class Supplier(Base):
    __tablename__ = 'suppliers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    piva = Column(String, nullable=True)
    
    invoices = relationship("Invoice", back_populates="supplier")

class Invoice(Base):
    __tablename__ = 'invoices'
    
    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    date = Column(Date, nullable=False)
    number = Column(String, nullable=False)
    total_amount = Column(Float, default=0.0)
    file_path = Column(String, nullable=True) # Source file path
    
    supplier = relationship("Supplier", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Invoice(number={self.number}, date={self.date}, total={self.total_amount})>"

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=True) # Codice Fornitore
    customer_code = Column(String, nullable=True) # Codice Cliente
    name = Column(String, nullable=False) # Normalized Name
    
    items = relationship("InvoiceItem", back_populates="product")

class InvoiceItem(Base):
    __tablename__ = 'invoice_items'
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True) # Linked Normalized Product
    
    code = Column(String, nullable=True) # Raw Code from invoice
    customer_code = Column(String, nullable=True) # Raw Customer Code
    description = Column(String, nullable=False) # Raw description
    quantity = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0)
    
    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", back_populates="items")

# Database Setup
engine = None
SessionLocal = None

def init_db(db_path='sqlite:///invoices.db'):
    global engine, SessionLocal
    engine = create_engine(db_path, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

def get_db_session():
    if SessionLocal is None:
        init_db()
    return SessionLocal()
