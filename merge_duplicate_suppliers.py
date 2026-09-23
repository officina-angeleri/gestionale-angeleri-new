import os
import shutil
import sqlite3
from datetime import datetime

KNOWN_PIVAS = {
    'COMEL SRL': '01057080184',
    'SACCHI GIUSEPPE S.P.A.': '00689730133',
    'I.M.B.G. S.r.l.': '01758620189',
    'CARPANELLI MOTORI ELETTRICI S.p.A.': '00662271204',
    'ALUSIC S.r.l.': '03105350049',
    'ALUSIC S.p.a.': '03105350049',
    'MATTI SRL OFFICINE MECCANICHE': '00278630181',
    'VIPETROL SPA': '00315600189',
    'Omega s.n.c. di Giorgio Crocco & C.': '01006810186',
    'I.C.S. FIRPO S.R.L.': '00835890187',
    'I.C.S. FIRPO S.P.A.': '00835890187',
    'T.G.P. s.r.l.': '00457810182',
    "BARATE' SPA": '00837850189',
    "BARATE' S.P.A.": '00837850189',
    'PROMETAL SAS DI SANTANDREA C., SANTANDRE': '00257000182',
    'ELVINOX   S.r.l.': '03946440157',
    'ELVINOX    S.r.l.': '03946440157',
    'ELVINOX S.r.l.': '03946440157',
}

def backup_db(db_path: str) -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dir_name = os.path.dirname(db_path)
    base_name = os.path.basename(db_path)
    name, ext = os.path.splitext(base_name)
    backup_path = os.path.join(dir_name, f"{name}_backup_{timestamp}{ext}")
    print(f"Creating backup of {db_path} -> {backup_path}...")
    shutil.copy2(db_path, backup_path)
    print("Backup created successfully.")
    return backup_path

def merge_suppliers_in_db(db_path: str):
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}, skipping.")
        return

    print(f"\n==================================================")
    print(f"Processing Database: {db_path}")
    print(f"==================================================")

    # 1. Backup
    backup_path = backup_db(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA foreign_keys = OFF")

    cur.execute("SELECT id, name, piva FROM suppliers")
    suppliers = {row[0]: {'name': row[1], 'piva': row[2]} for row in cur.fetchall()}

    print("Current suppliers:")
    for sid, info in suppliers.items():
        cur.execute("SELECT COUNT(*) FROM invoices WHERE supplier_id = ?", (sid,))
        cnt = cur.fetchone()[0]
        print(f"  ID {sid:2d} | Invoices: {cnt:3d} | PIVA: {str(info['piva']):12s} | Name: {repr(info['name'])}")

    with conn:
        # Check for Elvinox duplicates
        elvinox_suppliers = [sid for sid, info in suppliers.items() if 'ELVINOX' in info['name'].upper()]
        if len(elvinox_suppliers) > 1:
            target_id = elvinox_suppliers[0]
            canonical_name = 'ELVINOX S.r.l.'
            print(f"\nMerging Elvinox suppliers: keeping ID {target_id}, merging {elvinox_suppliers[1:]}...")
            for dup_id in elvinox_suppliers[1:]:
                cur.execute("UPDATE invoices SET supplier_id = ? WHERE supplier_id = ?", (target_id, dup_id))
                cur.execute("DELETE FROM suppliers WHERE id = ?", (dup_id,))
                print(f"  Merged ID {dup_id} into {target_id}")
            cur.execute("UPDATE suppliers SET name = ?, piva = ? WHERE id = ?", (canonical_name, '03946440157', target_id))

        elif len(elvinox_suppliers) == 1:
            cur.execute("UPDATE suppliers SET name = ?, piva = ? WHERE id = ?", ('ELVINOX S.r.l.', '03946440157', elvinox_suppliers[0]))

        # Check for Barate duplicates
        barate_suppliers = [sid for sid, info in suppliers.items() if 'BARATE' in info['name'].upper()]
        if len(barate_suppliers) > 1:
            target_id = next((sid for sid in barate_suppliers if "S.P.A." in suppliers[sid]['name']), barate_suppliers[0])
            dup_ids = [sid for sid in barate_suppliers if sid != target_id]
            canonical_name = "BARATE' S.P.A."
            print(f"\nMerging Barate suppliers: keeping ID {target_id}, merging {dup_ids}...")
            for dup_id in dup_ids:
                cur.execute("UPDATE invoices SET supplier_id = ? WHERE supplier_id = ?", (target_id, dup_id))
                cur.execute("DELETE FROM suppliers WHERE id = ?", (dup_id,))
                print(f"  Merged ID {dup_id} into {target_id}")
            cur.execute("UPDATE suppliers SET name = ?, piva = ? WHERE id = ?", (canonical_name, '00837850189', target_id))
        elif len(barate_suppliers) == 1:
            cur.execute("UPDATE suppliers SET piva = ? WHERE id = ?", ('00837850189', barate_suppliers[0]))

        # Check for Alusic duplicates
        alusic_suppliers = [sid for sid, info in suppliers.items() if 'ALUSIC' in info['name'].upper()]
        if len(alusic_suppliers) > 1:
            target_id = alusic_suppliers[0]
            dup_ids = alusic_suppliers[1:]
            canonical_name = "ALUSIC S.r.l."
            print(f"\nMerging Alusic suppliers: keeping ID {target_id}, merging {dup_ids}...")
            for dup_id in dup_ids:
                cur.execute("UPDATE invoices SET supplier_id = ? WHERE supplier_id = ?", (target_id, dup_id))
                cur.execute("DELETE FROM suppliers WHERE id = ?", (dup_id,))
                print(f"  Merged ID {dup_id} into {target_id}")
            cur.execute("UPDATE suppliers SET name = ?, piva = ? WHERE id = ?", (canonical_name, '03105350049', target_id))
        elif len(alusic_suppliers) == 1:
            cur.execute("UPDATE suppliers SET piva = ? WHERE id = ?", ('03105350049', alusic_suppliers[0]))

        # Clean spaces in all supplier names and populate known P.IVA
        cur.execute("SELECT id, name, piva FROM suppliers")
        for sid, sname, spiva in cur.fetchall():
            clean_name = " ".join(sname.split())
            if clean_name != sname:
                cur.execute("UPDATE suppliers SET name = ? WHERE id = ?", (clean_name, sid))
                sname = clean_name
            if not spiva:
                piva_val = KNOWN_PIVAS.get(sname)
                if piva_val:
                    cur.execute("UPDATE suppliers SET piva = ? WHERE id = ?", (piva_val, sid))
                    print(f"  Populated P.IVA for ID {sid} ({sname}) -> {piva_val}")

    print("\nUpdated suppliers after merge and normalization:")
    cur.execute("SELECT id, name, piva FROM suppliers ORDER BY name")
    for row in cur.fetchall():
        cur.execute("SELECT COUNT(*) FROM invoices WHERE supplier_id = ?", (row[0],))
        cnt = cur.fetchone()[0]
        print(f"  ID {row[0]:2d} | Invoices: {cnt:3d} | PIVA: {str(row[2]):12s} | Name: {repr(row[1])}")

    # Integrity verification
    cur.execute("SELECT COUNT(*) FROM invoices WHERE supplier_id NOT IN (SELECT id FROM suppliers)")
    orphans = cur.fetchone()[0]
    if orphans > 0:
        raise RuntimeError(f"Integrity check failed: {orphans} orphan invoices found!")
    print("\nIntegrity check PASSED: 0 orphan invoices.")

    conn.close()
    print(f"Done processing {db_path}.\n")

if __name__ == '__main__':
    # 1. Process server NAS DB
    server_db = r"\\angeleri_new\Pubblica\Database\Fornitori\invoices.db"
    merge_suppliers_in_db(server_db)

    # 2. Process local DBs if present
    local_dbs = [
        r"invoices.db",
        r"Fornitori\invoices.db"
    ]
    for ldb in local_dbs:
        if os.path.exists(ldb):
            merge_suppliers_in_db(os.path.abspath(ldb))
