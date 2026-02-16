import os
import re
from typing import List
from datetime import datetime
from bs4 import BeautifulSoup
from .base import InvoiceParser, ParsedInvoice, ParsedInvoiceItem

class HTMLInvoiceParser(InvoiceParser):
    def can_handle(self, file_path: str) -> bool:
        return file_path.lower().endswith(('.htm', '.html'))

    def clean_text(self, text):
        if not text:
            return ""
        return " ".join(text.split())

    def extract_value_from_ul(self, ul_element, label_text):
        """Cerca un li che contiene label_text e ritorna il contenuto dello span al suo interno."""
        if not ul_element:
            return ""
        
        items = ul_element.find_all('li', recursive=True)
        for item in items:
            if label_text in item.get_text():
                span = item.find('span')
                if span:
                    return self.clean_text(span.get_text())
        return ""

    def parse(self, file_path: str) -> List[ParsedInvoice]:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'lxml')
        
        # --- Fornitore ---
        supplier_block = soup.find('div', id='cedente')
        supplier_name = "Sconosciuto"
        if supplier_block:
            for li in supplier_block.find_all('li'):
                if "Denominazione" in li.get_text():
                    span = li.find('span')
                    if span:
                        supplier_name = self.clean_text(span.get_text())
                        break
        
        # --- Testata ---
        doc_general_block = soup.find('div', id='dati-generali-documento')
        doc_date_obj = datetime.now().date() # Default
        doc_number = "N/A"
        
        if doc_general_block:
            for li in doc_general_block.find_all('li'):
                text = li.get_text()
                if "Data documento" in text:
                    span = li.find('span')
                    if span:
                        date_str = self.clean_text(span.get_text())
                        # Tenta formati comuni
                        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                            try:
                                doc_date_obj = datetime.strptime(date_str, fmt).date()
                                break
                            except ValueError:
                                continue
                elif "Numero documento" in text:
                    span = li.find('span')
                    if span:
                        doc_number = self.clean_text(span.get_text())

        # --- Righe ---
        parsed_items = []
        rows_container = soup.find('div', id='righe')
        
        total_amount = 0.0
        
        if rows_container:
            row_uls = rows_container.select('div#righe > ul')
            
            for ul in row_uls:
                code = ''
                customer_code = None
                
                # Cerca blocco "Codifica articolo"
                codifica_li = None
                for li in ul.find_all('li', recursive=False):
                    if li.find('h5') and "Codifica articolo" in li.find('h5').get_text():
                        codifica_li = li
                        break
                
                if codifica_li:
                    # Estrai testo pulito del blocco codifica
                    # Prova ad estrarre mappando i li interni (più robusto per spazi)
                    sub_items = codifica_li.find_all('li')
                    current_tipo = ""
                    
                    # Etichette note
                    tech_labels = ['ART.', 'AswArtFor', 'Codice Art. fornitore']
                    customer_labels = ['ART.CLI.']

                    for si in sub_items:
                        txt = si.get_text(strip=True)
                        if "Tipo:" in txt:
                            current_tipo = self.clean_text(txt.replace("Tipo:", ""))
                        elif "Valore:" in txt and current_tipo:
                            current_val = self.clean_text(txt.replace("Valore:", ""))
                            if current_tipo in tech_labels:
                                code = current_val
                            elif current_tipo in customer_labels:
                                customer_code = current_val
                            # Non resettiamo current_tipo se ci sono più valori per lo stesso tipo, 
                            # ma qui lo facciamo per sicurezza se la struttura è Tipo-Valore-Tipo-Valore
                            current_tipo = ""

                desc = self.extract_value_from_ul(ul, "Descrizione bene/servizio")
                
                qty_str = self.extract_value_from_ul(ul, "Quantita")
                try:
                    qty = float(qty_str.replace(',', '.')) if qty_str else 0.0
                except:
                    qty = 0.0
                    
                price_str = self.extract_value_from_ul(ul, "Valore unitario")
                try:
                    unit_price = float(price_str.replace(',', '.')) if price_str else 0.0
                except:
                    unit_price = 0.0
                    
                total_str = self.extract_value_from_ul(ul, "Valore totale")
                try:
                    item_total = float(total_str.replace(',', '.')) if total_str else 0.0
                except:
                    item_total = 0.0
                
                total_amount += item_total
                
                # === FILTRO RIGHE TECNICHE === (stesso del parser XML)
                technical_noise_keywords = [
                    "riga ausiliaria",
                    "informazioni tecniche",
                    "sconto visualizzato",
                    "omaggio",
                    "ddt num",
                    "contributo conai",
                    "note:"
                ]
                
                # Verifica se la descrizione contiene parole chiave tecniche (case-insensitive)
                is_technical_noise = any(
                    keyword.upper() in desc.upper() 
                    for keyword in technical_noise_keywords
                )
                
                # CONDIZIONI DI SKIP:
                # 1. Se è rumore tecnico E ha prezzo zero -> SKIP
                # 2. Se ha prezzo zero E non ha né codice fornitore né codice cliente -> SKIP
                should_skip = False
                
                if abs(unit_price) < 0.001:  # Prezzo zero o quasi
                    if is_technical_noise:
                        should_skip = True
                    elif not code and not customer_code:
                        should_skip = True
                
                if should_skip:
                    continue  # Salta questa riga, passa alla prossima
                
                parsed_items.append(ParsedInvoiceItem(
                    code=code,
                    customer_code=customer_code,
                    description=desc,
                    quantity=qty,
                    unit_price=unit_price,
                    total_price=item_total
                ))

        return [ParsedInvoice(
            supplier_name=supplier_name,
            date=doc_date_obj,
            number=doc_number,
            total_amount=total_amount,
            items=parsed_items,
            original_file_path=file_path
        )]
