import streamlit as st
import pandas as pd
import os
import io
import zipfile
from PIL import Image
import qrcode
from datetime import datetime
import psycopg2
from supabase import create_client, Client

# ----------------------------- CONFIG -----------------------------
def get_secret(section, key):
    try:
        return st.secrets[section][key]
    except:
        return os.getenv(f"{section.upper()}_{key.upper()}")

SUPABASE_URL = get_secret("supabase", "url")
SUPABASE_KEY = get_secret("supabase", "key")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase credentials are not set. Please configure them in secrets or environment variables.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DB_CONFIG = {
    "host": get_secret("db_credentials", "host"),
    "port": get_secret("db_credentials", "port"),
    "user": get_secret("db_credentials", "user"),
    "password": get_secret("db_credentials", "password"),
    "database": get_secret("db_credentials", "database")
}

# ----------------------------- SESSION DEFAULTS -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "qr_codes" not in st.session_state:
    st.session_state.qr_codes = {}
if "far_df" not in st.session_state:
    st.session_state.far_df = pd.DataFrame()

# ----------------------------- USERS -----------------------------
users = {
    "Slugger": {"password": "dam2910", "role": "Admin"},
    "Gautam": {"password": "mnco", "role": "Admin"},
    "Client": {"password": "client321", "role": "Admin"},
    "Auditor": {"password": "Auditor321", "role": "Auditor"},
    "Scan": {"password": "scan123", "role": "Asset Viewer"}
}

# ----------------------------- LOGIN -----------------------------
def login():
    st.header("🔐 Login")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if user in users and users[user]["password"] == pwd:
            st.session_state.logged_in = True
            st.session_state.username = user
            st.session_state.role = users[user]["role"]
            st.success(f"✅ Welcome, {user}!")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")

if not st.session_state.logged_in:
    login()
    st.stop()

# ----------------------------- HELPERS -----------------------------
def fetch_far():
    result = supabase.table("assets").select("*").execute()
    return pd.DataFrame(result.data)

def fetch_audit_log():
    result = supabase.table("audit_log").select("*").order("timestamp", desc=True).execute()
    return pd.DataFrame(result.data)

def log_audit(asset_id, action, details, field=None, old_value=None, new_value=None):
    supabase.table("audit_log").insert({
        "asset_id": asset_id,
        "action": action,
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "changed_by": st.session_state.get("username", "unknown"),
        "user_role": st.session_state.get("role", "unknown"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "details": details
    }).execute()

# ----------------------------- QR REDIRECT -----------------------------
asset_id_qr = st.query_params.get("asset_id")

if asset_id_qr:
    asset_id_qr = asset_id_qr.strip()
    far_df_qr = fetch_far()

    # Fetch the passcode stored in your database
    conn = psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        dbname=DB_CONFIG["database"]
    )

    cur = conn.cursor()

    # Get the stored passcode from the database
    cur.execute("SELECT value FROM settings WHERE key = 'qr_viewer_passcode'")
    stored_passcode = cur.fetchone()[0]

    # Check if the passcode was previously entered successfully within the last hour
    cur.execute("""
        SELECT access_granted_at 
        FROM qr_access_log 
        WHERE asset_id = %s 
        AND access_granted_at > NOW() - INTERVAL '1 hour'
    """, (asset_id_qr,))
    row = cur.fetchone()

    cur.close()
    conn.close()

    st.sidebar.markdown("### 🧭 QR Redirect Active")
    st.sidebar.info(f"Scanned Asset ID: {asset_id_qr}")

    # If passcode validation is not successful yet or expired, prompt for passcode
    if not row:
        # If there's no validation record or it's expired, prompt for passcode
        if "qr_passcode_ok" not in st.session_state or st.session_state.get("last_qr") != asset_id_qr:
            st.session_state.qr_passcode_ok = False
            st.session_state.last_qr = asset_id_qr

        if not st.session_state.qr_passcode_ok:
            entered_passcode = st.text_input("🔑 Enter QR Viewer Passcode", type="password")
            if entered_passcode:
                if entered_passcode == stored_passcode:
                    st.session_state.qr_passcode_ok = True
                    st.success("✅ Passcode correct!")

                    # Insert or update the access time in the database
                    conn = psycopg2.connect(
                        host=DB_CONFIG["host"],
                        port=DB_CONFIG["port"],
                        user=DB_CONFIG["user"],
                        password=DB_CONFIG["password"],
                        dbname=DB_CONFIG["database"]
                    )

                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO qr_access_log (asset_id, access_granted_at) 
                        VALUES (%s, NOW()) 
                        ON CONFLICT (asset_id) DO UPDATE SET access_granted_at = NOW()
                    """, (asset_id_qr,))
                    conn.commit()
                    cur.close()
                    conn.close()

                else:
                    st.error("❌ Incorrect passcode.")
                    st.stop()

    # If passcode validation was successful, show asset info
    if st.session_state.qr_passcode_ok:
        match = far_df_qr[far_df_qr["asset_id"] == asset_id_qr]
        if not match.empty:
            st.title("🔍 Asset Info from QR")
            st.dataframe(match, use_container_width=True)
        else:
            st.title("❌ Asset Not Found")
            st.warning("No matching asset found for this QR.")

    st.stop()

# ----------------------------- NAVIGATION -----------------------------
tabs = ["Home", "QR Codes"]
if st.session_state.role in ["Admin", "Auditor"]:
    tabs += ["FAR", "Audit Trail"]

tab = st.sidebar.radio("🔽 Navigate", tabs)

# ----------------------------- HOME -----------------------------
if tab == "Home":
    st.title("🏠 Welcome to Slugger's Digital Asset Management System")
    st.write("Track, manage, and retrieve asset info in real-time via QR codes or the FAR.")

# ----------------------------- FAR -----------------------------
elif tab == "FAR":
    st.title("📋 Fixed Asset Register (Editable)")

    is_admin = st.session_state.role == "Admin"
    original_df = fetch_far().fillna("")

    st.session_state.far_df = original_df

    st.markdown("🔧 Edit the asset data below:")
    edited_df = st.data_editor(
        original_df,
        use_container_width=True,
        num_rows="dynamic" if is_admin else "fixed",
        disabled=not is_admin
    )

    if is_admin and st.button("💾 Save Changes"):
        edited_df = edited_df.fillna("")

        numeric_cols = ["cost", "accumulated_dep", "net_block", "useful_life", "dep_rate"]
        for col in numeric_cols:
            edited_df[col] = pd.to_numeric(edited_df[col], errors="coerce")

        original_dict = original_df.set_index("asset_id").to_dict(orient="index")
        edited_dict = edited_df.set_index("asset_id").to_dict(orient="index")

        original_ids = set(original_dict.keys())
        updated_ids = set(edited_dict.keys())

        # Handle updates and inserts
        for asset_id in edited_dict:
            if asset_id in original_dict:
                for field in edited_dict[asset_id]:
                    old = str(original_dict[asset_id].get(field, "")).strip()
                    new = edited_dict[asset_id][field]

                    if field in numeric_cols:
                        new = pd.to_numeric(new, errors="coerce")
                        new = int(new) if pd.notna(new) and float(new).is_integer() else round(new, 2) if pd.notna(new) else 0

                    if str(old) != str(new):
                        supabase.table("assets").update({field: new}).eq("asset_id", asset_id).execute()
                        log_audit(asset_id, "update", f"{field} changed from '{old}' to '{new}'", field=field, old_value=old, new_value=new)
            else:
                insert_data = edited_dict[asset_id]
                insert_data["useful_life"] = int(insert_data["useful_life"])
                insert_data["dep_rate"] = float(insert_data["dep_rate"])
                supabase.table("assets").insert(insert_data).execute()

                for field, value in insert_data.items():
                    log_audit(asset_id, "insert", f"{field} = {value}", field=field, new_value=value)

                # Generate QR code
                qr_url = f"https://maheshwariandcofams.onrender.com?asset_id={asset_id}"
                qr_img = qrcode.make(qr_url)
                buffer = io
::contentReference[oaicite:17]{index=17}
 
elif tab == "QR Codes":
    st.title("🏷️ QR Codes for Assets")

    st.info("QRs are auto-generated for each asset. Click to download, or download all in one go.")

    # Regenerate all QR codes from FAR
    df = fetch_far()
    qr_dict = {}

    for _, row in df.iterrows():
        asset_id = row["asset_id"]
        qr_url = f"https://maheshwariandcofams.onrender.com?asset_id={asset_id}"
        qr = qrcode.make(qr_url)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        qr_bytes = buf.getvalue()
        qr_dict[asset_id] = qr_bytes

    # Store in session state
    st.session_state.qr_codes = qr_dict

    # Display 4-column layout
    cols = st.columns(4)
    for idx, (asset_id, qr_data) in enumerate(qr_dict.items()):
        col = cols[idx % 4]
        with col:
            st.image(qr_data, caption=f"ID: {asset_id}", use_column_width=True)
            st.download_button(
                label="⬇️ Download",
                data=qr_data,
                file_name=f"{asset_id}.png",
                mime="image/png",
                key=f"download_{asset_id}"
            )

    # Download all button
    if st.button("📦 Download All as ZIP"):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for asset_id, img_data in qr_dict.items():
                zip_file.writestr(f"{asset_id}.png", img_data)
        st.download_button(
            label="⬇️ Download ZIP",
            data=zip_buffer.getvalue(),
            file_name="All_QR_Codes.zip",
            mime="application/zip"
        )


elif tab == "Audit Trail":
    st.title("🧾 Audit Trail")

    audit_df = fetch_audit_log()

    if audit_df.empty:
        st.warning("No audit records found.")
    else:
        audit_df["timestamp"] = pd.to_datetime(audit_df["timestamp"])
        audit_df = audit_df.sort_values(by="timestamp", ascending=False)

        st.dataframe(
            audit_df[[
                "timestamp", "asset_id", "action", "field",
                "old_value", "new_value", "changed_by", "user_role", "details"
            ]],
            use_container_width=True
        )

        # Download as Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            audit_df.to_excel(writer, index=False, sheet_name="Audit Log")
        st.download_button(
            label="⬇️ Download Audit Trail",
            data=excel_buffer.getvalue(),
            file_name="Audit_Trail.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
