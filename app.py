import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
import io
import zipfile
from PIL import Image
import qrcode
from datetime import datetime
import psycopg2

# ----------------------------- CONFIG -----------------------------
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DB_CREDENTIALS = {
    "host": st.secrets["db_credentials"]["host"],
    "user": st.secrets["db_credentials"]["user"],
    "password": st.secrets["db_credentials"]["password"],
    "port": st.secrets["db_credentials"]["port"],
    "dbname": st.secrets["db_credentials"]["dbname"]
}


st.write("Available secrets keys:", list(st.secrets.keys()))


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
import psycopg2
import streamlit as st

# QR redirect logic
asset_id_qr = st.query_params.get("asset_id")

if asset_id_qr:
    asset_id_qr = asset_id_qr.strip()
    far_df_qr = fetch_far()

    # Fetch the passcode stored in your database
    conn = psycopg2.connect(**st.secrets["db_credentials"])
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
                    conn = psycopg2.connect(**st.secrets["db_credentials"])
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
    original_df["net_block"] = original_df["cost"] - original_df["accumulated_dep"]


    # Convert numeric columns to numeric types, coercing errors to NaN
    numeric_cols = ["cost", "useful_life", "dep_rate"]
    for col in numeric_cols:
        original_df[col] = pd.to_numeric(original_df[col], errors='coerce')

    st.session_state.far_df = original_df

    st.markdown("🔧 Edit the asset data below:")
    edited_df = st.data_editor(
        original_df,
        use_container_width=True,
        num_rows="dynamic" if is_admin else "fixed",
        disabled=not is_admin
    )

    if is_admin and st.button("💾 Save Changes"):
        edited_df = edited_df.fillna("")  # Replace NaN with empty strings for simplicity
        original_ids = set(original_df["asset_id"].astype(str))
        updated_ids = set(edited_df["asset_id"].astype(str))
        edited_df["net_block"] = edited_df["cost"] - edited_df["accumulated_dep"]
        st.session_state.far_df = edited_df

        for _, row in edited_df.iterrows():
            asset_id = str(row["asset_id"]).strip()
            old_row = original_df[original_df["asset_id"] == asset_id]

            if not old_row.empty:
                for col in edited_df.columns:
                    if col == "net_block":
                        continue  # Skip if it's a calculated column
                    old = str(old_row.iloc[0][col]).strip()
                    new = row[col]

                    # Handle numeric columns and ensure type conversion
                    if col in numeric_cols:
                        new = pd.to_numeric(new, errors='coerce')  # Convert to numeric, NaN if invalid
                        if pd.notna(new):
                            if new.is_integer():
                                new = int(new)  # Convert to integer if whole number
                            else:
                                new = round(new, 2)  # Round if it's a float
                        else:
                            new = 0  # Set to 0 if NaN

                    # Update the database if the value has changed
                    if old != str(new):
                        supabase.table("assets").update({col: new}).eq("asset_id", asset_id).execute()
                        supabase.table("audit_log").insert({
                            "asset_id": asset_id,
                            "action": "update",
                            "details": f"{col} changed from {old} to {new}",
                            "changed_by": st.session_state.username,
                            "user_role": st.session_state.role,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }).execute()
            else:
                # If asset doesn't exist, insert new data
                insert_data = row.drop("net_block").to_dict()
                
                insert_data["useful_life"] = int(insert_data["useful_life"])
                insert_data["dep_rate"] = float(insert_data["dep_rate"])  # keep float

                try:
                    supabase.table("assets").insert(insert_data).execute()
                except Exception as e:
                    st.error(f"Error inserting data: {e}")
                    st.write(f"Insert Data: {insert_data}")

                for col in edited_df.columns:
                    supabase.table("audit_log").insert({
                        "asset_id": asset_id,
                        "action": "insert",
                        "details": f"{col} = {str(row[col]).strip()}",
                        "changed_by": st.session_state.username,
                        "user_role": st.session_state.role,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }).execute()

                # QR code generation for new assets
                if asset_id not in st.session_state.qr_codes:
                    # Generate the QR code URL
                    qr_url = f"https://maheshwariandcofams.onrender.com?asset_id={asset_id}"
                
                    # Create the QR code image
                    qr_img = qrcode.make(qr_url)
                    buffer = io.BytesIO()
                    qr_img.save(buffer, format="PNG")
                    buffer.seek(0)
                
                    # Store the generated QR code in session state for later use (optional, for caching)
                    st.session_state.qr_codes[asset_id] = buffer.getvalue()
                    
                    # Ensure that the qr_codes directory exists
                    qr_codes_dir = "qr_codes"
                    if not os.path.exists(qr_codes_dir):
                        os.makedirs(qr_codes_dir)  # Create the directory if it doesn't exist
                    
                    # Now, save the QR code image to the directory
                    with open(f"{qr_codes_dir}/{asset_id}.png", "wb") as f:
                        f.write(buffer.getvalue())

                    
                
        # Handle asset deletions (assets removed from the table)
        deleted_ids = original_ids - updated_ids
        for asset_id in deleted_ids:
            supabase.table("assets").delete().eq("asset_id", asset_id).execute()
            supabase.table("audit_log").insert({
                "asset_id": asset_id,
                "action": "delete",
                "details": "Asset deleted",
                "changed_by": st.session_state.username,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }).execute()
            st.session_state.qr_codes.pop(asset_id, None)  # Remove QR code for deleted asset

        st.success("✅ Changes saved and QR codes updated!")

    with st.expander("⬇️ Download FAR"):
        # Provide option to download the updated FAR as an Excel file
        excel_buf = io.BytesIO()
        edited_df.to_excel(excel_buf, index=False)
        excel_buf.seek(0)
        st.download_button("Download FAR", excel_buf, file_name="Fixed_Asset_Register.xlsx")

# ----------------------------- QR CODES -----------------------------
elif tab == "QR Codes" and st.session_state.role == "Admin":
    st.title("🔗 QR Codes")
    qr_list = list(st.session_state.qr_codes.items())
    if qr_list:
        cols = st.columns(4)
        for i, (asset_id, img_data) in enumerate(qr_list):
            with cols[i % 4]:
                st.image(Image.open(io.BytesIO(img_data)), caption=asset_id, width=150)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for asset_id, img_data in qr_list:
                zipf.writestr(f"{asset_id}.png", img_data)
        zip_buffer.seek(0)
        st.download_button("⬇️ Download All QR Codes", zip_buffer, file_name="All_QR_Codes.zip")
    else:
        st.info("No QR codes yet. Save assets in FAR first.")

# ----------------------------- AUDIT TRAIL -----------------------------
elif tab == "Audit Trail" and st.session_state.role in ["Admin", "Auditor"]:
    st.title("🕵️ Audit Trail")
    audit_df = fetch_audit_log()
    if audit_df.empty:
        st.info("No changes logged yet.")
    else:
        st.dataframe(audit_df, use_container_width=True)
        with st.expander("🔍 Filter Logs"):
            asset_filter = st.text_input("Filter by Asset ID")
            user_filter = st.text_input("Filter by Changed By")
            filtered = audit_df.copy()
            if asset_filter:
                filtered = filtered[filtered["asset_id"].str.contains(asset_filter, case=False)]
            if user_filter:
                filtered = filtered[filtered["changed_by"].str.contains(user_filter, case=False)]
            st.dataframe(filtered, use_container_width=True)
