from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db_session, Product, InvoiceItem, Invoice, Supplier
import pandas as pd

class AnalysisEngine:
    def __init__(self):
        self.session: Session = get_db_session()
        
    def get_price_trends(self):
        """
        Restituisce un DataFrame con:
        Product Name | Supplier | Last Price | Previous Price | Change % | Classification (Inc/Dec/Stable)
        """
        # Estraiamo tutti gli items con i dettagli necessari
        query = self.session.query(
            Product.name,
            Product.code,
            Product.customer_code,
            Supplier.name,
            Invoice.date,
            InvoiceItem.unit_price,
            InvoiceItem.description # Aggiunto per recupero descrizione
        ).join(Product.items) \
         .join(Invoice, InvoiceItem.invoice_id == Invoice.id) \
         .join(Supplier, Invoice.supplier_id == Supplier.id) \
         .order_by(Product.name, Supplier.name, Invoice.date)
         
        data = query.all()
        
        if not data:
            return []

        df = pd.DataFrame(data, columns=['Prodotto', 'Codice', 'CodiceCliente', 'Fornitore', 'Data', 'Prezzo', 'Descrizione'])
        
        # Converti data
        df['Data'] = pd.to_datetime(df['Data'])
        
        results = []
        
        # Raggruppa per Prodotto e Fornitore
        grouped = df.groupby(['Prodotto', 'Fornitore'])
        
        for (prod, supp), group in grouped:
            # Ordina per data
            group = group.sort_values('Data')
            
            # Se abbiamo almeno 2 prezzi, calcoliamo trend
            if len(group) >= 1:
                # Prendiamo l'ultimo prezzo
                last_row = group.iloc[-1]
                last_price = last_row['Prezzo']
                last_date = last_row['Data']
                last_desc = last_row['Descrizione']
                last_customer_code = last_row['CodiceCliente']
                
                # Statistiche Globali (tutti i mesi)
                min_price = group['Prezzo'].min()
                max_price = group['Prezzo'].max()
                avg_price = group['Prezzo'].mean()
                
                # Variazione vs Max Storico (per evidenziare i cali importanti come visto nello screenshot)
                var_vs_max_pct = 0.0
                if max_price > 0:
                    var_vs_max_pct = ((last_price - max_price) / max_price) * 100

                prev_price = None
                change_pct = 0.0
                change_abs = 0.0
                status = "Stabile"
                
                # Cerca all'indietro una riga con DATA diversa dall'ultima per il trend RECENTE
                for i in range(len(group) - 2, -1, -1):
                    row = group.iloc[i]
                    if row['Data'] != last_date or abs(row['Prezzo'] - last_price) > 0.0001:
                         prev_price = row['Prezzo']
                         break
                
                if prev_price is not None:
                    change_abs = last_price - prev_price
                    if prev_price > 0:
                        change_pct = (change_abs / prev_price) * 100
                    
                # Definizione Stato basata sia su trend recente che su contesto globale
                if change_pct > 0.1: # Aumento recente > 0.1%
                    status = "Aumento"
                elif change_pct < -0.1: # Diminuzione recente < -0.1%
                    status = "Diminuzione"
                elif var_vs_max_pct < -5.0: # Significativamente sotto il massimo storico
                    status = "Prezzo Basso"
                elif var_vs_max_pct > -1.0 and len(group) > 2: # Vicino al massimo storico
                    status = "Prezzo Alto"
                else:
                    status = "Stabile"
                
                results.append({
                    'Prodotto': prod,
                    'CodiceCliente': last_customer_code,
                    'Fornitore': supp,
                    'Ultimo Prezzo': last_price,
                    'Data Ultimo': last_date.strftime('%Y-%m-%d'),
                    'Descrizione': last_desc,
                    'Prezzo Prec.': prev_price if prev_price is not None else 0.0,
                    'Var. %': change_pct,
                    'Var. Ass.': change_abs,
                    'Min': min_price,
                    'Max': max_price,
                    'Media': avg_price,
                    'Var vs Max %': var_vs_max_pct,
                    'Stato': status
                })
                
        return results

    def get_product_history(self, product_name: str, supplier_name: str):
        """
        Recupera lo storico completo di un prodotto per un fornitore.
        Restituisce: lista di dict {Data, Numero Fattura, Prezzo Unitario, Quantità}
        """
        query = self.session.query(
            Invoice.date,
            Invoice.number,
            InvoiceItem.unit_price,
            InvoiceItem.quantity,
            InvoiceItem.description,
            Invoice.file_path,
            Product.customer_code
        ).join(InvoiceItem.invoice) \
         .join(InvoiceItem.product) \
         .join(Invoice.supplier) \
         .filter(Product.name == product_name) \
         .filter(Supplier.name == supplier_name) \
         .order_by(Invoice.date.desc())
         
        data = query.all()
        
        history = []
        for row in data:
            history.append({
                'Data': row.date.strftime('%Y-%m-%d'),
                'Numero Fattura': row.number,
                'Prezzo': row.unit_price,
                'Quantità': row.quantity,
                'Descrizione': row.description,
                'File': row.file_path,
                'CodiceCliente': row.customer_code
            })
        return history

    def get_supplier_reports(self):
        """
        Restituisce dati aggregati per Fornitore e Anno.
        Include sia il Netto (somma articoli) che il Lordo (totale fatture).
        Compatibile sia con PostgreSQL che con SQLite.
        """
        from sqlalchemy import cast, String

        anno_expr = cast(func.extract('year', Invoice.date), String).label('Anno')

        # 1. Calcolo Netto (da InvoiceItem)
        net_query = self.session.query(
            Supplier.name.label('Fornitore'),
            anno_expr,
            func.sum(InvoiceItem.total_price).label('TotaleNetto')
        ).join(Invoice, Supplier.id == Invoice.supplier_id) \
         .join(InvoiceItem, Invoice.id == InvoiceItem.invoice_id) \
         .group_by(Supplier.name, anno_expr).subquery()

        # 2. Calcolo Lordo e Conteggio (da Invoice)
        gross_query = self.session.query(
            Supplier.name.label('Fornitore'),
            anno_expr,
            func.sum(Invoice.total_amount).label('TotaleLordo'),
            func.count(Invoice.id).label('NumFatture')
        ).join(Supplier, Supplier.id == Invoice.supplier_id) \
         .group_by(Supplier.name, anno_expr).subquery()

        # Join dei risultati
        final_query = self.session.query(
            gross_query.c.Fornitore,
            gross_query.c.Anno,
            gross_query.c.NumFatture,
            net_query.c.TotaleNetto,
            gross_query.c.TotaleLordo
        ).join(net_query, (gross_query.c.Fornitore == net_query.c.Fornitore) & (gross_query.c.Anno == net_query.c.Anno)) \
         .order_by(gross_query.c.Fornitore, gross_query.c.Anno)
        
        results = final_query.all()
        return [dict(row._asdict()) for row in results]

