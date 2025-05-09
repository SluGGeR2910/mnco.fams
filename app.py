import streamlit as st
from supabase import create_client, Client
import os
import io
import zipfile
from PIL import Image
import qrcode
from datetime import datetime
import psycopg2

# ----------------------------- CONFIG -----------------------------
import os
import streamlit as st

SUPABASE_URL = st.secrets.get("supabase", {}).get("url") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("supabase", {}).get("key") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase credentials not found. Check secrets or environment variables.")
    st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DB_CREDENTIALS = {
    "host": st.secrets["db_credentials"]["host"],
    "user": st.secrets["db_credentials"]["user"],
    "password": st.secrets["db_credentials"]["password"],
    "port": st.secrets["db_credentials"]["port"],
    "dbname": st.secrets["db_credentials"]["dbname"]
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

# ----------------------------- QR REDIRECT -----------------------------
import streamlit as st
import pandas as pd

# Load your Fixed Asset Register (FAR)
if "far_data" not in st.session_state:
    st.session_state["far_data"] = pd.read_excel("fixed_asset_register.xlsx")

df = st.session_state["far_data"]

# Official way to get query params
query_params = st.query_params
asset_id = query_params.get("asset_id", None)

if asset_id:
    st.title("🔍 Asset Information")
    asset_row = df[df["Asset ID"] == asset_id]

    if not asset_row.empty:
        st.success(f"Asset found for ID: {asset_id}")
        st.dataframe(asset_row)
    else:
        st.error(f"🚫 No asset found with ID: {asset_id}")
else:
    st.title("🏠 Welcome to Slugger's Digital Asset System")
    st.info("Scan a QR code to view asset information.")


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

        # Ensure net_block is treated as numeric manually
        numeric_cols = ["cost", "accumulated_dep", "net_block", "useful_life", "dep_rate"]
        for col in numeric_cols:
            edited_df[col] = pd.to_numeric(edited_df[col], errors="coerce")

        # Compare old and new asset values to detect changes
        if 'updated_ids' in locals():
            for asset_id in updated_ids:
                original = original_assets[asset_id]  # from session_state
                updated = updated_assets[asset_id]    # from edited table

                for field in original.keys():
                    old = str(original.get(field, ""))
                    new = str(updated.get(field, ""))

                    if old != new:
                        supabase.table("assets").update({field: new}).eq("asset_id", asset_id).execute()

                        # Audit log for each field change
                        def log_audit(asset_id, action, details, field=None, old_value=None, new_value=None):
                            supabase.table("audit_log").insert({
                                "asset_id": asset_id,
                                "action": action,
                                "field": field,
                                "old_value": old_value,
                                "new_value": new_value,
                                "changed_by": st.session_state.get("username", "Unknown"),
                                "user_role": st.session_state.get("role", "Unknown"),
                                "timestamp": datetime.now().isoformat(),
                                "details": details
                            }).execute()

            for _, row in edited_df.iterrows():
                asset_id = str(row["asset_id"]).strip()
                old_row = original_df[original_df["asset_id"] == asset_id]

                if not old_row.empty:
                    for col in edited_df.columns:

                        old = str(old_row.iloc[0][col]).strip()
                        new = row[col]

                        if col in numeric_cols:
                            new = pd.to_numeric(new, errors="coerce")
                            new = int(new) if pd.notna(new) and new.is_integer() else round(new, 2) if pd.notna(new) else 0

                        if old != str(new):
                            supabase.table("assets").update({col: new}).eq("asset_id", asset_id).execute()
                            log_audit(asset_id, "update", f"{col} changed from {old} to {new}", field=col, old_value=old, new_value=new)
                else:
                    insert_data = row.to_dict()
                    insert_data["useful_life"] = int(insert_data["useful_life"])
                    insert_data["dep_rate"] = float(insert_data["dep_rate"])
                    supabase.table("assets").insert(insert_data).execute()

                    for col in edited_df.columns:
                            log_audit(asset_id, "insert", f"{col} = {row[col]}", field=col, new_value=row[col])

                    # QR code generation and saving
                    asset_id = str(row["asset_id"])
                    qr_path = f"qr_codes/{asset_id}.png"
                    if asset_id not in st.session_state.qr_codes or not os.path.exists(qr_path):
                        qr_url = f"https://maheshwariandcofams.onrender.com/?asset_id={asset_id}"
                        qr_img = qrcode.make(qr_url)
                        buffer = io.BytesIO()
                        qr_img.save(buffer, format="PNG")
                        buffer.seek(0)

                        # Save to session_state and disk
                        st.session_state.qr_codes[asset_id] = buffer.getvalue()
                        os.makedirs("qr_codes", exist_ok=True)
                        with open(qr_path, "wb") as f:
                            f.write(buffer.getvalue())

        # Handle deletions
        deleted_ids = original_ids - updated_ids
        for asset_id in deleted_ids:
            log_audit(asset_id, "delete", "Asset deleted")
            try:
                supabase.table("audit_log").insert({
                    "asset_id": asset_id,
                    "action": "delete",
                    "details": "Asset deleted",
                    "changed_by": st.session_state.get("username", "unknown"),
                    "user_role": st.session_state.get("role", "unknown"),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }).execute()

            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.stop()

        st.success("✅ Changes saved and QR codes updated!")

    with st.expander("⬇️ Download FAR"):
        excel_buf = io.BytesIO()
        edited_df.to_excel(excel_buf, index=False)
        excel_buf.seek(0)
        st.download_button("Download FAR", excel_buf, file_name="Fixed_Asset_Register.xlsx")

# ----------------------------- QR CODES -----------------------------
elif tab == "QR Codes" and st.session_state.role == "Admin":
    st.title("🔗 QR Codes")
    
    qr_codes_dir = "qr_codes"
    if not os.path.exists(qr_codes_dir):
        st.warning("QR codes directory not found. No QR codes to show.")
    else:
        qr_files = [f for f in os.listdir(qr_codes_dir) if f.endswith(".png")]
        if not qr_files:
            st.info("No QR codes generated yet.")
        else:
            cols = st.columns(4)
            for idx, file in enumerate(qr_files):
                with open(os.path.join(qr_codes_dir, file), "rb") as f:
                    img_bytes = f.read()
                    asset_id = file.replace(".png", "")
                    with cols[idx % 4]:
                        st.image(img_bytes, caption=f"Asset ID: {asset_id}", use_column_width=True)
                        st.download_button(f"Download {asset_id}", img_bytes, file_name=file)

# ----------------------------- AUDIT TRAIL -----------------------------
elif tab == "Audit Trail":
    if st.session_state.role != "Admin":
        st.error("🚫 You do not have permission to view the Audit Trail.")
        st.stop()

    st.title("📜 Audit Trail")
    df = fetch_audit_log()
    st.dataframe(df)

# ----------------------------- END -----------------------------
