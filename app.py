import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
import io
import zipfile
from PIL import Image
import qrcode
from datetime import datetime

# ----------------------------- CONFIG -----------------------------
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------- SESSION DEFAULTS -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "qr_codes" not in st.session_state:
    st.session_state.qr_codes = {}
if "far_df" not in st.session_state:
    st.session_state.far_df = pd.DataFrame()

# ----------------------------- USER AUTH -----------------------------
users = {
    "Slugger": {"password": "dam2910", "role": "Admin"},
    "Gautam": {"password": "mnco", "role": "Admin"},
    "Client": {"password": "client321", "role": "Admin"},
    "Auditor": {"password": "Auditor321", "role": "Auditor"},
    "Scan": {"password": "scan123", "role": "Asset Viewer"}
}

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
asset_id_qr = st.query_params.get("asset_id", None)

if asset_id_qr:
    # QR redirect → skip full login, only need passcode
    asset_id_qr = asset_id_qr.strip()
    far_df_qr = fetch_far()

    # Load passcode from settings table
    import psycopg2
    conn = psycopg2.connect(**st.secrets["db_credentials"])
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = 'qr_viewer_passcode'")
    stored_passcode = cur.fetchone()[0]
    cur.close()
    conn.close()

    st.sidebar.markdown("### 🧭 QR Redirect Active")
    st.sidebar.info(f"Scanned Asset ID: `{asset_id_qr}`")

    if "qr_passcode_ok" not in st.session_state or st.session_state.get("last_qr") != asset_id_qr:
        st.session_state.qr_passcode_ok = False
        st.session_state.last_qr = asset_id_qr

    if not st.session_state.qr_passcode_ok:
        entered_passcode = st.text_input("🔑 Enter QR Viewer Passcode", type="password")
        if entered_passcode:
            if entered_passcode == stored_passcode:
                st.session_state.qr_passcode_ok = True
                st.success("✅ Passcode correct!")
            else:
                st.error("❌ Incorrect passcode. Try again.")
                st.stop()

    # Passcode validated → show asset
    match = far_df_qr[far_df_qr["asset_id"] == asset_id_qr]
    if not match.empty:
        st.title("🔍 Asset Info from QR")
        st.write("Here are the details for the scanned asset:")
        st.dataframe(match, use_container_width=True)
    else:
        st.title("❌ Asset Not Found")
        st.warning("No matching asset found for this QR.")

    st.stop()  # Stop app here to prevent loading login etc

# ----------------------------- NORMAL LOGIN -----------------------------
# (rest of your app here → normal username/password login logic)


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
# ----------------------------- FAR -----------------------------
elif tab == "FAR":
    st.title("📋 Fixed Asset Register (Editable)")

    # Only Admins can edit
    is_admin = st.session_state.role == "Admin"
    original_df = fetch_far().fillna("")

    # Save in session
    st.session_state.far_df = original_df

    # Editable table
    st.markdown("🔧 Edit the asset data below:")
    edited_df = st.data_editor(
        original_df,
        use_container_width=True,
        num_rows="dynamic" if is_admin else "fixed",
        disabled=not is_admin
    )

    # Save button for Admins
    if is_admin and st.button("💾 Save Changes"):
        # Indent everything below this line to be inside the if block
        edited_df = edited_df.fillna("")
        original_ids = set(original_df["asset_id"].astype(str))
        updated_ids = set(edited_df["asset_id"].astype(str))

        # Loop through edited rows
        for _, row in edited_df.iterrows():
            asset_id = str(row["asset_id"]).strip()
            old_row = original_df[original_df["asset_id"] == asset_id]

            # Update or Insert
            if not old_row.empty:
            for col in edited_df.columns:
                old = str(old_row.iloc[0][col]).strip()
                new = str(row[col]).strip()
                if old != new:
                    supabase.table("audit_log").insert({
                        "asset_id": asset_id,
                        "action": "update",
                        "details": f"{col} changed from {old} to {new}",
                        "changed_by": st.session_state.username,
                        "user_role": st.session_state.role,  # Add this line to fix the error
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }).execute()
            else:
                for col in edited_df.columns:
                    new_val = str(row[col]).strip()
                    supabase.table("audit_log").insert({
                        "asset_id": asset_id,
                        "action": "insert",
                        "details": f"{col} = {new_val}",
                        "changed_by": st.session_state.username,
                        "user_role": st.session_state.role,  # Add this line to fix the error
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }).execute()

            # Save to Supabase
            supabase.table("assets").upsert(row.to_dict()).execute()

            # Auto-generate QR code
            if asset_id not in st.session_state.qr_codes:
                qr_url = f"https://maheshwariandcofams.onrender.com?asset_id={asset_id}" 
                qr_img = qrcode.make(qr_url)
                buffer = io.BytesIO()
                qr_img.save(buffer, format="PNG")
                buffer.seek(0)
                st.session_state.qr_codes[asset_id] = buffer.getvalue()

        # Handle deletions
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
            st.session_state.qr_codes.pop(asset_id, None)

        st.success("✅ Changes saved and QR codes updated!")

    # Excel download
    with st.expander("⬇️ Download FAR"):
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
