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
    asset_id_qr = asset_id_qr.strip()
    far_df_qr = fetch_far()
    match = far_df_qr[far_df_qr["asset_id"] == asset_id_qr]

    st.sidebar.markdown("### 🧭 QR Redirect Active")
    if not match.empty:
        st.sidebar.success(f"Asset Found: {asset_id_qr}")
        st.title("🔍 Asset Info from QR")
        st.write("Here are the details for the scanned asset:")
        st.dataframe(match, use_container_width=True)
        st.stop()
    else:
        st.sidebar.error("Asset ID not found!")
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
elif tab == "FAR" and st.session_state.role in ["Admin", "Auditor"]:
    st.title("📋 Fixed Asset Register")
    is_editable = st.session_state.role == "Admin"
    far_df = fetch_far().fillna("")
    st.session_state.far_df = far_df

    edited_df = st.data_editor(
        st.session_state.far_df,
        use_container_width=True,
        num_rows="dynamic" if is_editable else "fixed",
        disabled=not is_editable
    )

    if st.button("💾 Save FAR") and is_editable:
        edited_df = edited_df.fillna("")
        original_df = fetch_far().fillna("")
        original_ids = set(original_df["asset_id"].astype(str))
        new_ids = set(edited_df["asset_id"].astype(str))

        for _, row in edited_df.iterrows():
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
                        "details": f"{col} = {new_val}",
                        "changed_by": st.session_state.username,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }).execute()

            supabase.table("assets").upsert(row.to_dict()).execute()

            if asset_id not in st.session_state.qr_codes:
                qr_img = qrcode.make(f"https://slugtries.onrender.com?asset_id={asset_id}")
                buffer = io.BytesIO()
                qr_img.save(buffer, format="PNG")
                buffer.seek(0)
                st.session_state.qr_codes[asset_id] = buffer.getvalue()
                os.makedirs("qr_folder", exist_ok=True)
                with open(os.path.join("qr_folder", f"{asset_id}.png"), "wb") as f:
                    f.write(st.session_state.qr_codes[asset_id])

        for asset_id in original_ids - new_ids:
            supabase.table("assets").delete().eq("asset_id", asset_id).execute()
            supabase.table("audit_log").insert({
                "asset_id": asset_id,
                "action": "delete",
                "details": "Asset deleted",
                "changed_by": st.session_state.username,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }).execute()
            if asset_id in st.session_state.qr_codes:
                del st.session_state.qr_codes[asset_id]
                try:
                    os.remove(os.path.join("qr_folder", f"{asset_id}.png"))
                except FileNotFoundError:
                    pass

        st.session_state.far_df = edited_df
        st.success("✅ FAR saved & audit log updated!")

    with st.expander("⬇️ Download FAR"):
        excel_io = io.BytesIO()
        st.session_state.far_df.to_excel(excel_io, index=False)
        excel_io.seek(0)
        st.download_button("Download FAR", excel_io, file_name="Fixed_Asset_Register.xlsx")

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
