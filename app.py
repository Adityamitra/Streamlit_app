import streamlit as st
import pandas as pd
import os
import logging
from datetime import datetime
import json
import plotly.express as px

# -------- Logging Setup --------
logging.basicConfig(filename='app.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# -------- Constants --------
DATA_FILE = 'pallet_data.csv'
BACKUP_FILE = 'pallet_data_backup.json'
USERNAME = "admin"
PASSWORD = "1234"

# -------- Helper Functions --------
def load_data():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame(columns=["Pallet_No", "Location", "Status", "Date"])
    try:
        return pd.read_csv(DATA_FILE)
    except Exception as e:
        logging.error(f"Error loading CSV: {e}")
        st.error("Failed to load data. Check CSV format.")
        return pd.DataFrame(columns=["Pallet_No", "Location", "Status", "Date"])

def save_data(df):
    try:
        df.to_csv(DATA_FILE, index=False)
        logging.info("Data saved to CSV.")
    except Exception as e:
        logging.error(f"Error saving CSV: {e}")
        st.error("Failed to save data.")

def create_backup(df):
    try:
        pallets_dict = df.to_dict(orient='records')
        with open(BACKUP_FILE, 'w') as backup_file:
            json.dump(pallets_dict, backup_file)
        logging.info("Backup created.")
    except Exception as e:
        logging.error(f"Error creating backup: {e}")
        st.error("Failed to create backup.")

def restore_backup():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, 'r') as backup_file:
                pallet_data = json.load(backup_file)
                return pd.DataFrame(pallet_data)
        except Exception as e:
            logging.error(f"Error restoring backup: {e}")
            st.error("Failed to restore backup.")
            return pd.DataFrame(columns=["Pallet_No", "Location", "Status", "Date"])
    else:
        st.error("Backup file not found!")
        return pd.DataFrame(columns=["Pallet_No", "Location", "Status", "Date"])

def check_duplicate(pallet_no, df):
    return pallet_no in df["Pallet_No"].values

# -------- Session Auth --------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def login():
    st.title("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == USERNAME and password == PASSWORD:
            st.session_state.authenticated = True
            logging.info("User logged in.")
            st.experimental_rerun()
        else:
            st.error("Invalid credentials.")
            logging.warning("Failed login attempt.")
        if username == USERNAME and password == PASSWORD:
            st.session_state.authenticated = True
            st.success("Login successful!")
            logging.info("User logged in.")
        else:
            st.error("Invalid credentials.")
            logging.warning("Failed login attempt.")

def logout():
    st.session_state.authenticated = False
    logging.info("User logged out.")
    st.experimental_rerun()
    st.session_state.authenticated = False
    st.success("Logged out.")
    logging.info("User logged out.")

# -------- Main App --------
if not st.session_state.authenticated:
    login()
    st.stop()

st.title("📦 Pallet Tracker Dashboard")

# -------- Load Data --------
pallets = load_data()

# -------- Data Entry --------
with st.expander("➕ Add Multiple Pallets"):
    start_pallet = st.text_input("Enter Starting Pallet No (e.g., P001)", key="start_pallet")
    num_pallets = st.number_input("How many pallets to add?", min_value=1, step=1, key="num_pallets")
    location = st.selectbox("Location", ["SGT", "DKP", "OFC", "End Customer"], key="add_loc")
    status = st.selectbox("Status", ["Received At", "In Transit To", "Delivered", "Discarded"], key="add_stat")

    if st.button("Add Pallets"):
        if not start_pallet:
            st.error("Please enter a starting pallet number.")
        else:
            prefix = ''.join(filter(str.isalpha, start_pallet))
            number = ''.join(filter(str.isdigit, start_pallet))
            try:
                number = int(number)
                added = []
                skipped = []

                for i in range(num_pallets):
                    new_pallet = f"{prefix}{str(number + i).zfill(len(str(number)))}"
                    if not check_duplicate(new_pallet, pallets):
                        new_row = pd.DataFrame([{
                            "Pallet_No": new_pallet,
                            "Location": location,
                            "Status": status,
                            "Date": datetime.now().strftime("%Y-%m-%d")
                        }])
                        pallets = pd.concat([pallets, new_row], ignore_index=True)
                        added.append(new_pallet)
                    else:
                        skipped.append(new_pallet)

                save_data(pallets)
                create_backup(pallets)
                st.success(f"Added Pallets: {', '.join(added)}")
                if skipped:
                    st.warning(f"Skipped (already exists): {', '.join(skipped)}")


                # Clear form fields after successful addition
                st.session_state["start_pallet"] = ""
                st.session_state["num_pallets"] = 1
                st.session_state["add_loc"] = "SGT"
                st.session_state["add_stat"] = "Received At"
                    except ValueError:
                st.error("Invalid pallet number format. Must end with digits (e.g., P001).")


# -------- Update Data --------
with st.expander("🔄 Update Multiple Pallets"):
    start_pallet = st.text_input("Enter Starting Pallet No (e.g., P001)", key="start_pallet")
    num_pallets = st.number_input("How many pallets to update?", min_value=1, step=1, key="update_count")
    new_location = st.selectbox("New Location", ["SGT", "DKP", "OFC", "End Customer"], key="update_loc")
    new_status = st.selectbox("New Status", ["Received At", "In Transit To", "Delivered", "Discarded"], key="update_stat")

    if st.button("Update Pallets"):
        prefix = ''.join(filter(str.isalpha, start_pallet))
        number = ''.join(filter(str.isdigit, start_pallet))

        try:
            number = int(number)
            updated = []
            not_found = []

            for i in range(num_pallets):
                pallet_id = f"{prefix}{str(number + i).zfill(len(str(number)))}"
                if pallet_id in pallets["Pallet_No"].values:
                    pallets.loc[pallets["Pallet_No"] == pallet_id, ["Location", "Status", "Date"]] = [new_location, new_status, datetime.now().strftime("%Y-%m-%d")]
                    updated.append(pallet_id)
                else:
                    not_found.append(pallet_id)

            save_data(pallets)
            create_backup(pallets)
            st.success(f"Updated: {', '.join(updated)}")
            if not_found:
                st.warning(f"Not Found: {', '.join(not_found)}")

        except ValueError:
            st.error("Invalid starting pallet number format.")
# -------- Discard Data --------
with st.expander("🗑️ Discard Multiple Pallets"):
    start_pallet = st.text_input("Enter Starting Pallet No (e.g., P001)", key="start_pallet")
    num_pallets = st.number_input("How many pallets to discard?", min_value=1, step=1, key="discard_count")

    if st.button("Discard Pallets"):
        prefix = ''.join(filter(str.isalpha, start_pallet))
        number = ''.join(filter(str.isdigit, start_pallet))

        try:
            number = int(number)
            discarded = []
            not_found = []

            for i in range(num_pallets):
                pallet_id = f"{prefix}{str(number + i).zfill(len(str(number)))}"
                if pallet_id in pallets["Pallet_No"].values:
                    pallets.loc[pallets["Pallet_No"] == pallet_id, ["Status", "Date"]] = ["Discarded", datetime.now().strftime("%Y-%m-%d")]
                    discarded.append(pallet_id)
                else:
                    not_found.append(pallet_id)

            save_data(pallets)
            create_backup(pallets)
            st.success(f"Discarded: {', '.join(discarded)}")
            if not_found:
                st.warning(f"Not Found: {', '.join(not_found)}")

        except ValueError:
            st.error("Invalid starting pallet number format.")

# -------- View All Pallets --------
with st.expander("📋 View All Pallets"):
    st.dataframe(pallets)

# -------- Search Pallet --------
with st.expander("🔍 Search Pallet"):
    pallet_no = st.text_input("Enter Pallet Number to Search")
    if st.button("Search Pallet"):
        found = pallets[pallets["Pallet_No"] == pallet_no]
        if not found.empty:
            st.write(found)
        else:
            st.error(f"Pallet {pallet_no} not found!")
with st.expander("📍 Show Pallet Status"):
    st.subheader("📊 Pallet Distribution by Location and Status")

    # Count pallets grouped by location and status
    loc_status_counts = pallets.groupby(['Location', 'Status']).size().reset_index(name='Count')

    # Custom color mapping
    color_map = {
        "In Transit": "royalblue",
        "Delivered": "green",
        "Discarded": "red"
    }

    fig = px.bar(
        loc_status_counts,
        x="Location",
        y="Count",
        color="Status",
        barmode="group",
        color_discrete_map=color_map,
        text="Count"
    )

    fig.update_layout(
        xaxis_title="Location",
        yaxis_title="Number of Pallets",
        legend_title="Pallet Status",
        title="Live Pallet Status by Location"
    )

    st.plotly_chart(fig, use_container_width=True)

# -------- Export to Excel --------
with st.expander("💾 Export to Excel"):
    if st.button("Export to Excel"):
        export_path = st.text_input("Enter file path to save")
        if export_path:
            pallets.to_excel(export_path, index=False)
            st.success(f"Data exported to {export_path}")

# -------- Backup and Restore --------
with st.expander("🔙 Restore Backup"):
    if st.button("Restore Backup"):
        pallets = restore_backup()
        st.dataframe(pallets)

# -------- Logout --------
if st.button("Logout"):
    logout()
    st.stop()
