# app.py

import streamlit as st
import pandas as pd
import os
from sqlalchemy import create_engine, text

# -----------------------------
# CONFIG: Database Connection
# -----------------------------

db_user = os.environ["DB_USER"]
db_password = os.environ["DB_PASSWORD"]
db_host = os.environ["DB_HOST"]
db_port = os.environ.get("DB_PORT", "5432")
db_name = os.environ["DB_NAME"]


engine = create_engine(f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

# -----------------------------
# HELPERS
# -----------------------------

def get_passcode():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT value FROM settings WHERE key = 'qr_viewer_passcode'"))
        return result.scalar()

def fetch_asset(asset_id):
    query = text("""
        SELECT asset_id, asset_name, description, purchase_date, location, status, cost
        FROM assets WHERE asset_id = :asset_id
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"asset_id": asset_id})
    return df

def fetch_far():
    query = "SELECT * FROM assets"
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

def fetch_audit_log():
    query = "SELECT * FROM audit_log ORDER BY timestamp DESC"
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

def update_asset(asset_id, field, value):
    with engine.connect() as conn:
        conn.execute(text(f"UPDATE assets SET {field} = :value WHERE asset_id = :asset_id"),
                     {"value": value, "asset_id": asset_id})
        conn.execute(text("INSERT INTO audit_log (asset_id, action, details) VALUES (:asset_id, 'update', :details)"),
                     {"asset_id": asset_id, "details": f"{field} updated to {value}"})
        conn.commit()

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
