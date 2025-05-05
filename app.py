import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
import io
import zipfile
from PIL import Image
from datetime import datetime

# -----------------------------
# CONFIG: Supabase Connection
# -----------------------------
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# HELPERS
# -----------------------------

def get_passcode():
    result = supabase.table("settings").select("value").eq("key", "qr_viewer_passcode").execute()
    if result.data:
        return result.data[0]["value"]
    return None

def fetch_asset(asset_id):
    result = supabase.table("assets").select("*").eq("asset_id", asset_id).execute()
    return pd.DataFrame(result.data)

def fetch_far():
    result = supabase.table("assets").select("*").execute()
    return pd.DataFrame(result.data)

def fetch_audit_log():
    result = supabase.table("audit_log").select("*").order("timestamp", desc=True).execute()
    return pd.DataFrame(result.data)

def update_asset(asset_id, field, value):
    # Update the asset in the "assets" table and log the action in the "audit_log"
    supabase.table("assets").update({field: value}).eq("asset_id", asset_id).execute()
    supabase.table("audit_log").insert({
        "asset_id": asset_id,
        "action": "update",
        "details": f"{field} updated to {value}"
    }).execute()

# -----------------------------
# USER AUTH
# -----------------------------

users = {
    "Slugger": {"password": "dam2910", "role": "Admin"},
    "Gautam": {"password": "mnco", "role": "Admin"},  # Treat as admin/editor combo
    "Client": {"password": "client321", "role": "Admin"},
    "Auditor": {"password": "Auditor321", "role": "Auditor"},
    "Scan": {"password": "scan123", "role": "Asset Viewer"}
}

def login():
    st.header("🔐 Login")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if user in users and users[user]['password'] == pwd:
            st.session_state.logged_in = True
            st.session_state.role = users[user]['role']
            st.session_state.username = user
            st.success(f"Welcome {user}!")
        else:
            st.error("Access Revoked")

if not st.session_state.logged_in:
    login()
    st.stop()

# -----------------------------
# ASSET REDIRECT FROM QR
# -----------------------------

asset_id_qr = st.query_params.get("asset_id", None)

if asset_id_qr:
    asset_id_qr = asset_id_qr.strip()
    asset_row = st.session_state.far_df[st.session_state.far_df["asset_id"] == asset_id_qr]

    st.sidebar.markdown("### 🧭 QR Redirect Active")

    if not asset_row.empty:
        st.sidebar.success(f"Asset Found: {asset_id_qr}")
        st.title("🔍 Asset Info from QR")
        st.write("Here are the details for the scanned asset:")
        st.dataframe(asset_row, use_container_width=True)
        st.stop()
    else:
        st.sidebar.error("Asset ID not found in FAR!")
        st.title("❌ Asset Not Found")
        st.warning("No matching asset found for this QR.")
        st.stop()

# -----------------------------
# NAVIGATION
# -----------------------------

tabs = ["Home", "QR Codes"]
if st.session_state.role == "Admin":
    tabs += ["FAR", "Audit Trail"]
tab = st.sidebar.radio("Navigate", tabs)

# -----------------------------
# HOME
# -----------------------------

if tab == "Home":
    st.title("🏠 Welcome to Slugger's Digital Asset Management System")
    st.write("Your centralized platform to seamlessly track, manage, and retrieve asset information — all in real time. Whether you're scanning a QR code or exploring the FAR, this tool ensures transparency, efficiency, and control over your organization’s valuable assets.!")

# -----------------------------
# FAR
# -----------------------------

elif tab == "FAR" and st.session_state.role in ["Admin", "Auditor"]:
    st.title("📋 Fixed Asset Register")

    is_editable = st.session_state.role == "Admin"

    far_df = fetch_far()  # Fetch data from Supabase
    st.session_state.far_df = far_df.fillna("")

    edited_df = st.data_editor(
        st.session_state.far_df,
        use_container_width=True,
        num_rows="dynamic" if is_editable else "fixed",
        disabled=not is_editable
    )

    if st.button("💾 Save FAR") and is_editable:
        edited_df = edited_df.fillna("")
        original_df = fetch_far().fillna("")  # Fetch data from Supabase
        original_ids = set(original_df["asset_id"].astype(str))
        new_ids = set(edited_df["asset_id"].astype(str))

        for idx, row in edited_df.iterrows():
            asset_id = str(row["asset_id"]).strip()
            existing_row = original_df[original_df["asset_id"] == asset_id]

            if not existing_row.empty:
                for col in edited_df.columns:
                    old_val = str(existing_row.iloc[0][col]).strip()
                    new_val = str(row[col]).strip()
                    if old_val != new_val:
                        supabase.table("audit_log").insert({
                            "asset_id": asset_id,
                            "action": "update",
                            "details": f"{col} updated from {old_val} to {new_val}",
                            "changed_by": st.session_state.username,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }).execute()
            else:
                for col in edited_df.columns:
                    new_val = str(row[col]).strip()
                    supabase.table("audit_log").insert({
                        "asset_id": asset_id,
                        "action": "insert",
                        "details": f"New asset added: {col} = {new_val}",
                        "changed_by": st.session_state.username,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }).execute()

            # Update the asset
            supabase.table("assets").upsert(dict(row.to_dict())).execute()

            # Handle QR codes
            if asset_id not in st.session_state.qr_codes:
                qr_img = qrcode.make(f"https://slugtries.onrender.com?asset_id={asset_id}")
                buffer = io.BytesIO()
                qr_img.save(buffer, format="PNG")
                buffer.seek(0)
                st.session_state.qr_codes[asset_id] = buffer.getvalue()
                with open(os.path.join("qr_folder", f"{asset_id}.png"), "wb") as f:
                    f.write(st.session_state.qr_codes[asset_id])

        removed_ids = original_ids - new_ids
        for asset_id in removed_ids:
            if asset_id in st.session_state.qr_codes:
                del st.session_state.qr_codes[asset_id]
                try:
                    os.remove(os.path.join("qr_folder", f"{asset_id}.png"))
                except FileNotFoundError:
                    pass

            supabase.table("assets").delete().eq("asset_id", asset_id).execute()
            supabase.table("audit_log").insert({
                "asset_id": asset_id,
                "action": "delete",
                "details": "Asset deleted",
                "changed_by": st.session_state.username,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }).execute()

        st.session_state.far_df = edited_df
        st.success("✅ FAR saved and audit trail updated!")

    with st.expander("⬇️ Download FAR as Excel"):
        excel_buffer = io.BytesIO()
        st.session_state.far_df.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)
        st.download_button("Download FAR", excel_buffer, file_name="Fixed_Asset_Register.xlsx")

# -----------------------------
# QR CODES
# -----------------------------

elif tab == "QR Codes" and st.session_state.role == "Admin":
    st.title("🔗 QR Codes")

    qr_list = list(st.session_state.qr_codes.items())
    if qr_list:
        col_count = 4
        cols = st.columns(col_count)
        for i, (asset_id, img_data) in enumerate(qr_list):
            with cols[i % col_count]:
                st.image(Image.open(io.BytesIO(img_data)), caption=asset_id, width=150)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for asset_id, img_data in qr_list:
                zipf.writestr(f"{asset_id}.png", img_data)
        zip_buffer.seek(0)
        st.download_button("⬇️ Download All QR Codes", zip_buffer, file_name="All_QR_Codes.zip")
    else:
        st.info("No QR codes available yet. Go to FAR tab and save some assets.")

# -----------------------------
# AUDIT TRAIL
# -----------------------------

elif tab == "Audit Trail" and st.session_state.role in ["Admin", "Auditor"]:
    st.title("🕵️ Audit Trail")

    audit_df = fetch_audit_log()  # Fetch data from Supabase

    if audit_df.empty:
        st.info("No changes logged yet.")
    else:
        st.dataframe(audit_df, use_container_width=True)

        with st.expander("🔍 Filter Logs"):
            asset_filter = st.text_input("Search by Asset ID")
            user_filter = st.text_input("Search by Changed By")
            field_filter = st.text_input("Search by Field")

            filtered_df = audit_df.copy()
            if asset_filter:
                filtered_df = filtered_df[filtered_df["asset_id"].str.contains(asset_filter, case=False)]
            if user_filter:
                filtered_df = filtered_df[filtered_df["changed_by"].str.contains(user_filter, case=False)]
            if field_filter:
                filtered_df = filtered_df[filtered_df["field_changed"].str.contains(field_filter, case=False)]

            st.dataframe(filtered_df, use_container_width=True)

        download_buffer = io.BytesIO()
        audit_df.to_excel(download_buffer, index=False)
        download_buffer.seek(0)
        st.download_button("⬇️ Download Full Audit Trail (Excel)", download_buffer, file_name="Audit_Trail.xlsx")
