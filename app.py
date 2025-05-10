import streamlit as st
import pandas as pd
import os
import logging
import logging.config
from datetime import datetime, timedelta
import json
import re
import glob
import hashlib
from getpass import getpass
import plotly.express as px

# -------- Configuration --------
APP_NAME = "Pallet Tracker Pro"
VERSION = "2.0"

# -------- Constants --------
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, 'pallet_data.csv')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# -------- Security --------
# Set these in your environment variables in production
USERNAME = os.getenv("APP_USERNAME", "admin")
PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH", 
                         hashlib.sha256(getpass("Set admin password:").encode()).hexdigest())

# -------- Logging Setup --------
LOG_CONFIG = {
    'version': 1,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'fmt': '%(asctime)s %(levelname)s %(message)s %(name)s %(lineno)d'
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(DATA_DIR, 'app.log'),
            'formatter': 'json',
            'maxBytes': 1048576,
            'backupCount': 3
        }
    },
    'root': {
        'handlers': ['file'],
        'level': 'INFO'
    }
}

logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger(__name__)

# -------- Helper Functions --------
def validate_pallet_number(pallet_no):
    """Validate pallet number format (e.g., P001, ABC123)"""
    return bool(re.match(r'^[A-Za-z]+\d+$', str(pallet_no)))

def generate_sequence(start_pallet, num_pallets):
    """Generate sequential pallet numbers"""
    if not validate_pallet_number(start_pallet):
        raise ValueError("Invalid format. Expected format like 'P001'")
    
    prefix = re.sub(r'\d+$', '', start_pallet).upper()
    number_str = re.sub(r'^[A-Za-z]+', '', start_pallet)
    
    try:
        number = int(number_str)
    except ValueError:
        raise ValueError("Invalid number portion")
    
    return [f"{prefix}{str(number + i).zfill(len(number_str))}" 
            for i in range(num_pallets)]

def load_data():
    """Load pallet data with validation"""
    required_cols = ["Pallet_No", "Location", "Status", "Date"]
    try:
        if os.path.exists(DATA_FILE):
            df = pd.read_csv(DATA_FILE)
            
            # Validate structure
            if not all(col in df.columns for col in required_cols):
                raise ValueError("Missing required columns in data file")
                
            # Clean data
            df = df.dropna(how='all')
            df["Pallet_No"] = df["Pallet_No"].astype(str).str.strip().str.upper()
            df["Date"] = pd.to_datetime(df["Date"], format=DATE_FORMAT, errors='coerce')
            df = df.dropna(subset=["Date"])
            
            return df
        
        return pd.DataFrame(columns=required_cols)
    except Exception as e:
        logger.error(f"Data loading error: {str(e)}", exc_info=True)
        st.error(f"Failed to load data: {str(e)}")
        return pd.DataFrame(columns=required_cols)

def save_data(df):
    """Save data with atomic write"""
    try:
        # Validate before saving
        required_cols = ["Pallet_No", "Location", "Status", "Date"]
        if not all(col in df.columns for col in required_cols):
            raise ValueError("Data missing required columns")
            
        # Create temp file
        temp_file = DATA_FILE + ".tmp"
        df.to_csv(temp_file, index=False)
        
        # Replace original file
        if os.path.exists(DATA_FILE):
            os.replace(temp_file, DATA_FILE)
        else:
            os.rename(temp_file, DATA_FILE)
            
        logger.info(f"Data saved successfully with {len(df)} records")
        return True
    except Exception as e:
        logger.error(f"Data save failed: {str(e)}", exc_info=True)
        st.error(f"Failed to save data: {str(e)}")
        return False

def create_backup(df):
    """Create timestamped backup with rotation"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(BACKUP_DIR, f"pallet_backup_{timestamp}.json")
        
        with open(backup_file, 'w') as f:
            json.dump({
                "metadata": {
                    "app": APP_NAME,
                    "version": VERSION,
                    "created_at": timestamp,
                    "records": len(df)
                },
                "data": df.to_dict(orient='records')
            }, f, indent=2)
        
        # Keep only last 5 backups
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "pallet_backup_*.json")))
        for old_backup in backups[:-5]:
            os.remove(old_backup)
            
        logger.info(f"Backup created: {backup_file}")
        return True
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}", exc_info=True)
        return False

def restore_backup(backup_file=None):
    """Restore from backup"""
    try:
        if not backup_file:
            backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "pallet_backup_*.json")), reverse=True)
            if not backups:
                st.error("No backup files found!")
                return None
            backup_file = backups[0]
            
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
            
        df = pd.DataFrame(backup_data['data'])
        
        # Validate restored data
        required_cols = ["Pallet_No", "Location", "Status", "Date"]
        if not all(col in df.columns for col in required_cols):
            raise ValueError("Backup missing required columns")
            
        logger.info(f"Restored backup: {backup_file} with {len(df)} records")
        return df
    except Exception as e:
        logger.error(f"Restore failed: {str(e)}", exc_info=True)
        st.error(f"Failed to restore backup: {str(e)}")
        return None

# -------- Authentication --------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.login_attempts = 0
    st.session_state.last_attempt = None

def login():
    """Login page with attempt limiting"""
    st.title("🔐 Secure Login")
    
    # Check if temporarily locked out
    if (st.session_state.login_attempts >= 3 and 
        st.session_state.last_attempt and 
        (datetime.now() - st.session_state.last_attempt).seconds < 300):
        st.error("Too many failed attempts. Please wait 5 minutes.")
        return
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            st.session_state.last_attempt = datetime.now()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            if username == USERNAME and password_hash == PASSWORD_HASH:
                st.session_state.authenticated = True
                st.session_state.login_attempts = 0
                logger.info("Successful login", extra={"user": username})
                st.success("Login successful!")
                st.experimental_rerun()
            else:
                st.session_state.login_attempts += 1
                logger.warning("Failed login attempt", 
                              extra={"user": username, "attempts": st.session_state.login_attempts})
                st.error("Invalid credentials")
                
                if st.session_state.login_attempts >= 3:
                    st.error("Too many failed attempts. Please wait 5 minutes.")

def logout():
    """Logout handler"""
    logger.info("User logged out")
    st.session_state.authenticated = False
    st.success("Logged out successfully")
    st.experimental_rerun()

# -------- Main Application --------
if not st.session_state.authenticated:
    login()
    st.stop()

# -------- App Layout --------
st.title(f"📦 {APP_NAME}")
st.caption(f"Version {VERSION}")

# Load data
pallets = load_data()

# Sidebar for quick actions
with st.sidebar:
    st.header("Quick Actions")
    
    if st.button("🔄 Refresh Data"):
        pallets = load_data()
        st.success("Data refreshed")
    
    if st.button("💾 Create Backup"):
        if create_backup(pallets):
            st.success("Backup created successfully")
    
    if st.button("⏮️ Restore Latest Backup"):
        restored = restore_backup()
        if restored is not None:
            pallets = restored
            if save_data(pallets):
                st.success("Data restored from backup")
    
    if st.button("🚪 Logout"):
        logout()

# Main tabs
tab1, tab2, tab3, tab4 = st.tabs(["📦 Pallet Operations", "🔍 Search & View", "📊 Analytics", "⚙️ Settings"])

with tab1:
    # Add Pallets
    with st.expander("➕ Add Pallets", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            start_pallet = st.text_input("Starting Pallet No (e.g., P001)", key="add_start")
            num_pallets = st.number_input("Number of Pallets", min_value=1, max_value=1000, value=1)
        with col2:
            location = st.selectbox("Location", ["SGT", "DKP", "OFC", "End Customer"], key="add_loc")
            status = st.selectbox("Status", ["Received At", "In Transit To", "Delivered", "Discarded"], key="add_stat")
        
        if st.button("Add Pallets", key="add_btn"):
            try:
                new_pallets = generate_sequence(start_pallet, num_pallets)
                added = []
                skipped = []
                
                for pallet in new_pallets:
                    if pallet in pallets["Pallet_No"].values:
                        skipped.append(pallet)
                    else:
                        added.append(pallet)
                
                if added:
                    new_data = pd.DataFrame([{
                        "Pallet_No": p,
                        "Location": location,
                        "Status": status,
                        "Date": datetime.now().strftime(DATE_FORMAT)
                    } for p in added])
                    
                    pallets = pd.concat([pallets, new_data], ignore_index=True)
                    if save_data(pallets):
                        create_backup(pallets)
                        st.success(f"Added {len(added)} pallets: {', '.join(added[:5])}{'...' if len(added) > 5 else ''}")
                
                if skipped:
                    st.warning(f"Skipped {len(skipped)} existing pallets")
                
            except ValueError as e:
                st.error(str(e))
    
    # Update Pallets
    with st.expander("🔄 Update Pallets"):
        col1, col2 = st.columns(2)
        with col1:
            update_start = st.text_input("Starting Pallet No to Update", key="update_start")
            update_count = st.number_input("Number to Update", min_value=1, max_value=1000, value=1, key="update_count")
        with col2:
            new_location = st.selectbox("New Location", ["SGT", "DKP", "OFC", "End Customer"], key="update_loc")
            new_status = st.selectbox("New Status", ["Received At", "In Transit To", "Delivered", "Discarded"], key="update_stat")
        
        if st.button("Update Pallets", key="update_btn"):
            try:
                pallets_to_update = generate_sequence(update_start, update_count)
                updated = 0
                
                for pallet in pallets_to_update:
                    if pallet in pallets["Pallet_No"].values:
                        pallets.loc[pallets["Pallet_No"] == pallet, ["Location", "Status", "Date"]] = [
                            new_location, new_status, datetime.now().strftime(DATE_FORMAT)
                        ]
                        updated += 1
                
                if updated:
                    if save_data(pallets):
                        st.success(f"Updated {updated} pallets")
                else:
                    st.warning("No matching pallets found")
                    
            except ValueError as e:
                st.error(str(e))
    
    # Discard Pallets
    with st.expander("🗑️ Discard Pallets"):
        discard_start = st.text_input("Starting Pallet No to Discard", key="discard_start")
        discard_count = st.number_input("Number to Discard", min_value=1, max_value=1000, value=1, key="discard_count")
        
        if st.button("Discard Pallets", key="discard_btn"):
            try:
                pallets_to_discard = generate_sequence(discard_start, discard_count)
                discarded = 0
                
                for pallet in pallets_to_discard:
                    if pallet in pallets["Pallet_No"].values:
                        pallets.loc[pallets["Pallet_No"] == pallet, ["Status", "Date"]] = [
                            "Discarded", datetime.now().strftime(DATE_FORMAT)
                        ]
                        discarded += 1
                
                if discarded:
                    if save_data(pallets):
                        st.success(f"Discarded {discarded} pallets")
                else:
                    st.warning("No matching pallets found")
                    
            except ValueError as e:
                st.error(str(e))

with tab2:
    # Search Functionality
    with st.expander("🔍 Search Pallets"):
        search_term = st.text_input("Search by Pallet No or Location")
        if search_term:
            search_results = pallets[
                pallets["Pallet_No"].str.contains(search_term, case=False) | 
                pallets["Location"].str.contains(search_term, case=False)
            ]
            st.dataframe(search_results)
        else:
            st.info("Enter search term to filter pallets")
    
    # View All with Pagination
    with st.expander("📋 All Pallets"):
        page_size = st.selectbox("Rows per page", [10, 25, 50, 100], key="page_size")
        total_pages = max(1, len(pallets) // page_size + (1 if len(pallets) % page_size else 0))
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, len(pallets))
        
        st.dataframe(pallets.iloc[start_idx:end_idx])
        st.caption(f"Showing {start_idx + 1}-{end_idx} of {len(pallets)} pallets")

with tab3:
    # Analytics Dashboard
    st.header("📊 Pallet Analytics")
    
    col1, col2 = st.columns(2)
    with col1:
        group_by = st.selectbox("Group By", ["Location", "Status", "Date"], key="group_by")
    with col2:
        time_filter = st.selectbox("Time Period", 
                                 ["All Time", "Today", "Last 7 Days", "Last 30 Days", "Last 90 Days"],
                                 key="time_filter")
    
    # Apply filters
    filtered = pallets.copy()
    if time_filter != "All Time":
        now = datetime.now()
        if time_filter == "Today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif "7" in time_filter:
            cutoff = now - timedelta(days=7)
        elif "30" in time_filter:
            cutoff = now - timedelta(days=30)
        else:
            cutoff = now - timedelta(days=90)
        
        filtered = filtered[pd.to_datetime(filtered["Date"]) >= cutoff]
    
    # Summary stats
    st.metric("Total Pallets", len(filtered))
    st.metric("Active Pallets", len(filtered[filtered["Status"] != "Discarded"]))
    
    # Charts
    fig1 = px.bar(
        filtered.groupby(group_by).size().reset_index(name='Count'),
        x=group_by,
        y='Count',
        title=f"Pallets by {group_by}",
        color=group_by
    )
    st.plotly_chart(fig1, use_container_width=True)
    
    # Status over time
    if time_filter != "All Time":
        fig2 = px.line(
            filtered.groupby([pd.to_datetime(filtered["Date"]).dt.date, "Status"])
                .size().unstack().fillna(0),
            title="Status Changes Over Time",
            labels={'value': 'Count', 'variable': 'Status'}
        )
        st.plotly_chart(fig2, use_container_width=True)

with tab4:
    # Settings
    st.header("⚙️ Application Settings")
    
    with st.expander("Data Management"):
        if st.button("Export to CSV"):
            csv = pallets.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="pallet_export.csv",
                mime="text/csv"
            )
        
        if st.button("Export to Excel"):
            excel_file = "pallet_export.xlsx"
            pallets.to_excel(excel_file, index=False)
            with open(excel_file, "rb") as f:
                st.download_button(
                    label="Download Excel",
                    data=f,
                    file_name=excel_file,
                    mime="application/vnd.ms-excel"
                )
    
    with st.expander("Backup Management"):
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "pallet_backup_*.json")), reverse=True)
        selected_backup = st.selectbox("Select Backup", backups)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("View Backup"):
                with open(selected_backup, 'r') as f:
                    backup_data = json.load(f)
                    st.json(backup_data["metadata"])
                    st.write(f"Contains {len(backup_data['data'])} records")
        with col2:
            if st.button("Restore Selected Backup"):
                restored = restore_backup(selected_backup)
                if restored is not None:
                    pallets = restored
                    if save_data(pallets):
                        st.success("Data restored from selected backup")
    
    with st.expander("System Information"):
        st.write(f"**App Name:** {APP_NAME}")
        st.write(f"**Version:** {VERSION}")
        st.write(f"**Data File:** {DATA_FILE}")
        st.write(f"**Last Updated:** {datetime.fromtimestamp(os.path.getmtime(DATA_FILE)).strftime(DATE_FORMAT) if os.path.exists(DATA_FILE) else 'Never'}")
        st.write(f"**Records:** {len(pallets)}")
        st.write(f"**Backups Available:** {len(backups)}")