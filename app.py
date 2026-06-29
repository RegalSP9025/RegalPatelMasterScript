import os
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load local environmental variables
load_dotenv()

# Page Title & Layout Configurations
st.set_page_config(page_title="Regal Calibration Registry", layout="wide")

# Title Banner
st.title(" ^‿^ Regal Calibration Audit System ^‿^")
st.markdown("### Search and verify asset calibration logs instantaneously.")
st.divider()

# 🧠 Secure & Optimized Database Connection Engine
@st.cache_resource
def init_connection():
    """Maintains a single persistent connection pool to CalTest."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "CalTest"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD")
    )

try:
    conn = init_connection()
except Exception as e:
    st.error(f"❌ Database Connection Failure: {e}")
    st.stop()

def get_all_calibration_tables():
    """Queries Postgres system logs to fetch all custom data tables automatically."""
    query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_name LIKE 'calibration%'
        ORDER BY table_name;
    """
    # Fallback to include your original test table if it doesn't match the calibration prefix
    with conn.cursor() as cur:
        cur.execute(query)
        tables = [row[0] for row in cur.fetchall()]
    
    # Ensure your original table is included in case it doesn't match the new naming rule yet
    if "RegalPatelTest" not in tables:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'RegalPatelTest');")
            if cur.fetchone()[0]:
                tables.append("RegalPatelTest")
                
    return sorted(tables)

# Fetch all available asset tables dynamically
available_tables = get_all_calibration_tables()

if not available_tables:
    st.warning("⚠️ No active asset tables found in the 'CalTest' public schema. Run your import script first.")
    st.stop()

# 🗂️ Interactive Table Selection Slicer (Now 100% Dynamic!)
target_table = st.selectbox(
    "Select Asset Category:",
    options=available_tables,
    format_func=lambda x: x.replace("calibration_", "").replace("_", " ").upper()
)

# 🔍 The Auditor Search Bar
search_serial = st.text_input(" ^_^ Enter Gauge Serial Number to Audit:", placeholder="e.g. 96017").strip()

if search_serial:
    # Safe SQL injection querying the targeted dynamic table selection
    query = f'SELECT * FROM public."{target_table}" WHERE serial_number = %s;'
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (search_serial,))
        result = cur.fetchone()
        
    if result:
        st.success(f"✅ Record Found for Serial Number: {search_serial} in Category: {target_table.upper()}")
        
        # Split screen into clean visual layout cards
        col1, col2 = st.columns(2)
        
        # Dynamically map keys regardless of capitalization styles
        data_dict = {k.lower(): v for k, v in result.items()}
        
        with col1:
            st.subheader("📋 Asset Identity Details")
            st.write(f"**Gage Type:** {data_dict.get('gage_type', 'N/A')}")
            st.write(f"**Manufacturer / Mfg:** {data_dict.get('manufacturer', data_dict.get('mfg', 'N/A'))}")
            st.write(f"**Model Number:** {data_dict.get('model_number', 'N/A')}")
            st.write(f"**Graduation/Size:** {data_dict.get('graduation', 'N/A')}")
            st.write(f"**Inspector / Calibrated By:** {data_dict.get('calibrated_by', data_dict.get('inspector', 'N/A'))}")
            st.write(f"**Date Calibrated:** {data_dict.get('date_calibrated', 'N/A')}")
            st.write(f"**Last Sync Updated:** {data_dict.get('updated_at', 'N/A')}")
            
        with col2:
            st.subheader("🔬 Calibration System Parameters")
            st.write(f"**Procedure Key:** {data_dict.get('procedure_name', data_dict.get('procedure_used', 'N/A'))}")
            if 'procedure_number' in data_dict and data_dict['procedure_number']:
                st.write(f"**Procedure ID:** {data_dict['procedure_number']}")
                
            st.write(f"**Master S/N Used:** {data_dict.get('sn_gage_used_to_cal', data_dict.get('sn_of_gage_used_to_calibrate', 'N/A'))}")
            
            # Displays the exact status or finding with color-coding
            status_val = str(data_dict.get('status', data_dict.get('finding', 'READY'))).upper()
            if any(word in status_val for word in ["READY", "PASS", "ACCEPT"]):
                st.metric(label="ASSET OPERATIONAL STATUS", value=status_val, delta="Passed Inspection")
            else:
                st.metric(label="ASSET OPERATIONAL STATUS", value=status_val, delta="Requires Attention", delta_color="inverse")
                
        # 📊 Dynamic Matrix Generation Conditional Block
        # Only renders the matrix table if checkpoint values exist in the current database row profile
        if 'checkpoint_a_value' in data_dict:
            st.divider()
            with st.expander("👁️ View Full Raw Trial Run Spreadsheet Matrix", expanded=True):
                matrix_data = {
                    "Checkpoint Nominal": [data_dict.get('checkpoint_a_value'), data_dict.get('checkpoint_b_value'), data_dict.get('checkpoint_c_value')],
                    "Trial 1 Reading": [data_dict.get('a_1'), data_dict.get('b_1'), data_dict.get('c_1')],
                    "Trial 2 Reading": [data_dict.get('a_2'), data_dict.get('b_2'), data_dict.get('c_2')],
                    "Trial 3 Reading": [data_dict.get('a_3'), data_dict.get('b_3'), data_dict.get('c_3')]
                }
                st.table(matrix_data)
            
        if data_dict.get('notes'):
            st.info(f"📝 **System Deployment Notes:** {data_dict['notes']}")
            
    else:
        st.warning(f"⚠️ No active calibration entries found within table '{target_table}' for Serial Number: '{search_serial}'")