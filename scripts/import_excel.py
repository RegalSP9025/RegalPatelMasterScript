import os
import glob
from datetime import datetime

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    raise ImportError("psycopg2 is required. Run 'python -m pip install psycopg2-binary'")

try:
    import openpyxl
except ImportError:
    raise ImportError("openpyxl is required. Run 'python -m pip install openpyxl'")

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(): return None

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "CalTest"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD")
    )

def clean_header(header_val):
    """Converts rough Excel headers into clean, database-safe column names."""
    if header_val is None:
        return None
    # Lowercase, replace spaces/slashes with underscores, drop parentheses
    cleaned = str(header_val).strip().lower()
    cleaned = cleaned.replace(" ", "_").replace("/", "_").replace("-", "_")
    for char in ["(", ")", "[", "]"]:
        cleaned = cleaned.replace(char, "")
    return cleaned

def parse_date(val):
    if val is None:
        return None
    if hasattr(val, "date"):
        return val.date()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None

def process_file(filepath, conn):
    """Reads any calibration workbook, auto-creates its table, and UPSERTs data."""
    filename = os.path.basename(filepath)
    # Generate clean table name from the file name (e.g., thread_ring_gages)
    table_name = os.path.splitext(filename)[0].strip().lower().replace(" ", "_")
    
    wb = openpyxl.load_workbook(filepath, data_only=True)
    if "MAIN_INPUT" not in wb.sheetnames:
        print(f"  ✕ Skipped {filename}: Missing 'MAIN_INPUT' worksheet tab.")
        return
        
    ws = wb["MAIN_INPUT"]
    
    # 1. Dynamically read Row 1 headers
    raw_headers = [cell.value for cell in ws[1]]
    cleaned_headers = [clean_header(h) for h in raw_headers if h is not None]
    
    if "serial_number" not in cleaned_headers:
        print(f"  ✕ Skipped {filename}: Header row missing required 'serial_number' cell identifier.")
        return

    cur = conn.cursor()
    
    # 2. Dynamic DDL: Automatically build the table if it does not exist yet!
    column_definitions = []
    for header in cleaned_headers:
        if header == "serial_number":
            column_definitions.append(f'"{header}" VARCHAR(100) PRIMARY KEY')
        elif "date" in header:
            column_definitions.append(f'"{header}" DATE')
        elif header in ["a_1", "a_2", "a_3", "b_1", "b_2", "b_3", "c_1", "c_2", "c_3"]:
            column_definitions.append(f'"{header}" NUMERIC')
        else:
            column_definitions.append(f'"{header}" TEXT')
            
    column_definitions.append('"updated_at" TIMESTAMP DEFAULT NOW()')
    
    create_table_query = f"""
        CREATE TABLE IF NOT EXISTS public."{table_name}" (
            {", ".join(column_definitions)}
        );
    """
    cur.execute(create_table_query)
    conn.commit()

    # 3. Read and insert actual rows
    success_count = 0
    sn_index = cleaned_headers.index("serial_number")
    
    # Iterate through row data streams starting from Row 2
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        # Stop processing if row is structurally empty or missing a serial number
        if not row or len(row) <= sn_index or row[sn_index] is None or str(row[sn_index]).strip() == "":
            continue
            
        # Match data values to our headers length limit
        row_values = list(row[:len(cleaned_headers)])
        
        # Format types safely before data hits Postgres
        for idx, header in enumerate(cleaned_headers):
            val = row_values[idx]
            if "date" in header:
                row_values[idx] = parse_date(val)
            elif val is not None:
                row_values[idx] = str(val).strip()

        # Build dynamic overwrite UPSERT query
        insert_cols = ", ".join([f'"{h}"' for h in cleaned_headers])
        placeholders = ", ".join(["%s"] * len(cleaned_headers))
        
        update_assignments = ", ".join([f'"{h}" = EXCLUDED."{h}"' for h in cleaned_headers if h != "serial_number"])
        
        upsert_query = f"""
            INSERT INTO public."{table_name}" ({insert_cols}, updated_at)
            VALUES ({placeholders}, NOW())
            ON CONFLICT (serial_number) DO UPDATE SET
                {update_assignments},
                updated_at = NOW();
        """
        
        try:
            cur.execute(upsert_query, row_values)
            conn.commit()
            success_count += 1
        except Exception as row_error:
            conn.rollback()
            print(f"  ✕ Row {row_idx} Sync Failed in {table_name}: {row_error}")

    print(f"  ✓ Processed '{filename}' ➔ Table '{table_name}' updated with {success_count} records.")
    cur.close()

def main():
    print("--- ^-^ Starting Master Dynamic Data Warehousing Pipeline ^-^ ---")
    
    try:
        conn = get_db_connection()
    except Exception as e:
        print(f"[FATAL CONNECTION ERROR]: Verify local Postgres configurations.\nDetail: {e}")
        return

    # Automatically scans your template directory for ANY workbook matching calibration*.xlsx
    target_files = glob.glob(os.path.join(TEMPLATES_DIR, "calibration*.xlsx"))
    
    if not target_files:
        print(f"[WARNING] No templates found matching 'calibration*.xlsx' in {TEMPLATES_DIR}")
        conn.close()
        return

    print(f"Found {len(target_files)} target template matrices to synchronize...")
    for filepath in sorted(target_files):
        process_file(filepath, conn)

    conn.close()
    print("\n--- ^-^ Master Pipeline Executed Successfully! ^-^ ---")

if __name__ == "__main__":
    main()