"""
Script per unificare i fornitori con prefisso [CODIFICARE] o [NON CODIFICATO]
e rimuovere eventuali testate fatture duplicate vuote.
"""
import sys
import re

sys.path.insert(0, '.')

from app.database import get_db_session, Supplier, Invoice, InvoiceItem, SupplierProduct

def main():
    session = get_db_session()
    try:
        codif = session.query(Supplier).filter(
            (Supplier.name.ilike('[CODIFICARE]%')) | (Supplier.name.ilike('[NON CODIFICATO]%'))
        ).all()
        print(f"Trovati {len(codif)} fornitori con prefisso da normalizzare.")

        merged_suppliers = 0
        renamed_suppliers = 0
        removed_duplicate_invoices = 0

        for s_old in codif:
            clean_name = re.sub(r'^\s*\[(CODIFICARE|NON CODIFICATO)\]\s*', '', s_old.name, flags=re.IGNORECASE).strip()
            if not clean_name:
                continue

            match = session.query(Supplier).filter(
                Supplier.id != s_old.id,
                Supplier.name.ilike(clean_name)
            ).first()

            if match:
                # Se il fornitore vecchio ha la P.IVA e match non ce l'ha, copiala
                if s_old.piva and not match.piva:
                    match.piva = s_old.piva

                # Controlla fatture di s_old
                old_invoices = session.query(Invoice).filter_by(supplier_id=s_old.id).all()
                for inv in old_invoices:
                    dup = session.query(Invoice).filter(
                        Invoice.id != inv.id,
                        Invoice.supplier_id == match.id,
                        Invoice.number == inv.number,
                        Invoice.date == inv.date
                    ).first()

                    if dup:
                        # Uno dei due è duplicato
                        dup_items_cnt = session.query(InvoiceItem).filter_by(invoice_id=dup.id).count()
                        inv_items_cnt = session.query(InvoiceItem).filter_by(invoice_id=inv.id).count()

                        if dup_items_cnt == 0 and inv_items_cnt > 0:
                            # Sposta articoli da inv a dup
                            session.query(InvoiceItem).filter_by(invoice_id=inv.id).update({"invoice_id": dup.id})
                            session.delete(inv)
                            removed_duplicate_invoices += 1
                        elif dup_items_cnt >= inv_items_cnt:
                            # Elimina inv che è vuoto o duplicato
                            if inv_items_cnt > 0:
                                session.query(InvoiceItem).filter_by(invoice_id=inv.id).delete()
                            session.delete(inv)
                            removed_duplicate_invoices += 1
                    else:
                        inv.supplier_id = match.id

                session.flush()

                # Sposta i codici articolo fornitore (SupplierProduct)
                for sp in session.query(SupplierProduct).filter_by(supplier_id=s_old.id).all():
                    existing_sp = session.query(SupplierProduct).filter_by(
                        supplier_id=match.id,
                        product_id=sp.product_id,
                        supplier_code=sp.supplier_code
                    ).first()
                    if not existing_sp:
                        sp.supplier_id = match.id
                    else:
                        session.delete(sp)

                session.flush()
                session.delete(s_old)
                merged_suppliers += 1
            else:
                s_old.name = clean_name
                renamed_suppliers += 1

            session.commit()

        print(f"\nCompletato con successo:")
        print(f"- Fornitori unificati ed eliminati: {merged_suppliers}")
        print(f"- Fornitori rinominati (pulito prefisso): {renamed_suppliers}")
        print(f"- Testate fatture duplicate rimosse: {removed_duplicate_invoices}")
    except Exception as e:
        session.rollback()
        print(f"Errore durante l'operazione: {e}")
        raise
    finally:
        session.close()

if __name__ == '__main__':
    main()
