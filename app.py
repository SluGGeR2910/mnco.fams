import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os

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
    supabase.table("assets").update({field: value}).eq("asset_id", asset_id).execute()
    supabase.table("audit_log").insert({
        "asset_id": asset_id,
        "action": "update",
        "details": f"{field} updated to {value}"
    }).execute()

# -----------------------------
# SIDEBAR NAV
# -----------------------------
tabs = ["Home", "Asset Intelligence", "Editable FAR", "Audit Trail"]
selected_tab = st.sidebar.selectbox("Select Tab", tabs)

st.sidebar.markdown("---")
st.sidebar.write("👤 Role-Based Access")
user_role = st.sidebar.selectbox("Role", ["Developer", "Client", "Auditor", "QR Viewer"])

# -----------------------------
# HOME TAB
# -----------------------------
if selected_tab == "Home":
    st.title("🏠 Fixed Asset Management System")
    st.write("Welcome to the dashboard.")

# -----------------------------
# ASSET INTELLIGENCE (QR Viewer)
# -----------------------------
elif selected_tab == "Asset Intelligence":
    asset_id = st.experimental_get_query_params().get("asset_id", [""])[0]
    if not asset_id:
        asset_id = st.text_input("Enter Asset ID from QR")

    entered_passcode = st.text_input("Enter Viewer Passcode", type="password")
    correct_passcode = get_passcode()

    if st.button("Access Asset"):
        if entered_passcode == correct_passcode:
            st.success("✅ Access granted")
            df = fetch_asset(asset_id)
            if not df.empty:
                st.table(df)
            else:
                st.warning("Asset not found.")
        else:
            st.error("❌ Invalid passcode.")

# -----------------------------
# EDITABLE FAR
# -----------------------------
elif selected_tab == "Editable FAR":
    if user_role in ["Developer", "Client"]:
        st.header("📋 Editable Fixed Asset Register")
        df = fetch_far()
        edited_df = st.data_editor(df, num_rows="dynamic")

        if st.button("Save Changes"):
            for idx, row in edited_df.iterrows():
                for col in ["asset_name", "description", "purchase_date", "location", "status", "cost"]:
                    update_asset(row["asset_id"], col, row[col])
            st.success("✅ Changes saved.")
    else:
        st.error("Unauthorized Access")

# -----------------------------
# AUDIT TRAIL
# -----------------------------
elif selected_tab == "Audit Trail":
    if user_role in ["Developer", "Client", "Auditor"]:
        st.header("🕵️ Audit Log")
        df_log = fetch_audit_log()
        st.dataframe(df_log)
        st.download_button("Download Audit Log (CSV)", df_log.to_csv(index=False), "audit_log.csv", "text/csv")
    else:
        st.error("Unauthorized Access")
