# ===================================================================================
# FINAL CODE FOR FAMILY BUDGET APP WITH GOOGLE SHEETS DATABASE (v4 - FORCED SYNC)
# ===================================================================================

import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- Page Configuration ---
st.set_page_config(page_title="Family Budget Tracker", layout="wide", initial_sidebar_state="expanded")

# --- Google Sheets Authentication ---
# Scope for the APIs to authorize
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Check for secrets before trying to connect
if "gcp_service_account" in st.secrets:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(creds)

    # --- CONSTANTS ---
    # Use the name of the Google Sheet you created
    SHEET_NAME = "Family Budget Data"

    # Open the spreadsheet and the first sheet
    try:
        spreadsheet = client.open(SHEET_NAME)
        worksheet = spreadsheet.sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet named '{SHEET_NAME}' not found. Please check the name and sharing permissions.")
        st.stop()
else:
    st.error("GCP service account credentials not found in Streamlit Secrets. Please check your app settings.")
    st.stop()


# --- Helper Functions ---
@st.cache_data(ttl=60)  # Cache data for 60 seconds
def load_data():
    """Load data from Google Sheet."""
    try:
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        # Handle case where sheet is empty
        if df.empty:
            return pd.DataFrame(columns=['Member', 'Amount', 'Category', 'Payment_Mode', 'Date', 'Deadline'])

        # Ensure 'Amount' is numeric and dates are parsed correctly
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        # Coerce errors will turn invalid date formats into NaT (Not a Time)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Deadline'] = pd.to_datetime(df['Deadline'], errors='coerce')
        return df.dropna(subset=['Date', 'Amount'])  # Drop rows with invalid date or amount
    except Exception as e:
        st.error(f"Failed to load data from Google Sheets: {e}")
        return pd.DataFrame()


def save_data(df_to_save):
    """Save the entire DataFrame back to Google Sheet, handling data types."""
    try:
        # Create a copy to avoid modifying the original DataFrame in session state
        df_for_gsheet = df_to_save.copy()

        # Convert date columns to string in a specific format for Google Sheets
        # This handles NaT (Not a Time) values gracefully by converting them to empty strings
        df_for_gsheet['Date'] = df_for_gsheet['Date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')
        df_for_gsheet['Deadline'] = df_for_gsheet['Deadline'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')

        # Replace any other NaN values with empty strings for clean saving
        df_for_gsheet = df_for_gsheet.fillna('')

        # Clear the sheet before writing to avoid appending and creating duplicates
        worksheet.clear()
        # --- THIS IS THE FIX ---
        # Removed the 'include_sheet_name' argument to support the library version on Streamlit Cloud
        # The line should look exactly like this:
        set_with_dataframe(worksheet, df_for_gsheet, include_index=False, resize=True)
        # ----------------------
        st.cache_data.clear()  # Clear the app's cache after saving new data
    except Exception as e:
        st.error(f"Failed to save data to Google Sheets: {e}")


# --- Load Data into Session State ---
if 'df_expenses' not in st.session_state:
    st.session_state.df_expenses = load_data()

# --- App Title ---
st.title("💸 Family Budget Tracker")
st.markdown("### A central place for our family to track and manage expenses.")

# --- Input Form in Sidebar ---
with st.sidebar.form("expense_form", clear_on_submit=True):
    st.header("➕ Add an Expense")
    date = st.date_input("Date", datetime.date.today())
    member = st.selectbox("Family Member", ["Husnain", "Brother", "Father", "Mother"])
    category = st.text_input("Category (e.g. Grocery, Fuel)")
    amount = st.number_input("Amount (Rs)", min_value=0.01, step=0.01, format="%.2f")
    payment_mode = st.selectbox("Payment Mode", ["Cash", "Credit Card", "Online"])
    deadline = st.date_input("Deadline (optional)", value=None)

    submitted = st.form_submit_button("Add Expense")

    if submitted:
        if not category or not member:
            st.warning("Please fill in both Member and Category.")
        else:
            new_entry_df = pd.DataFrame([{
                "Member": member,
                "Amount": amount,
                "Category": category.strip().title(),
                "Payment_Mode": payment_mode,
                "Date": pd.to_datetime(date),
                "Deadline": pd.to_datetime(deadline) if deadline else pd.NaT
            }])

            # Append new entry to the DataFrame in session state
            st.session_state.df_expenses = pd.concat([st.session_state.df_expenses, new_entry_df], ignore_index=True)
            save_data(st.session_state.df_expenses)
            st.sidebar.success("Expense added and saved permanently! 🎉")

# --- Main Page Display ---
if st.session_state.df_expenses.empty:
    st.warning("No expenses found. Add an expense using the form on the left to get started!")
else:
    # Use the DataFrame from session state for display
    display_df = st.session_state.df_expenses.copy()
    display_df['Month'] = display_df['Date'].dt.to_period("M").astype(str)

    # --- Filters ---
    st.sidebar.header("📆 Filter & View")
    sorted_months = sorted(display_df["Month"].unique(), reverse=True)
    selected_month = st.sidebar.selectbox("Month", sorted_months)

    # Filter by selected month
    filtered_df = display_df[display_df["Month"] == selected_month]

    # --- Dashboard ---
    st.header(f"📊 Dashboard for {selected_month}")
    total_spent = filtered_df["Amount"].sum()
    avg_transaction = filtered_df["Amount"].mean()

    col1, col2 = st.columns(2)
    col1.metric("Total Spent", f"Rs. {total_spent:,.2f}")
    col2.metric("Average Transaction", f"Rs. {avg_transaction:,.2f}")
    st.markdown("---")

    # --- Graphs ---
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Spending by Category")
        category_spending = filtered_df.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        fig_pie = px.pie(category_spending, values="Amount", names=category_spending.index,
                         title="Spending Distribution", hole=.3)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col2:
        st.subheader("Spending by Member")
        member_spending = filtered_df.groupby("Member")["Amount"].sum().sort_values(ascending=False)
        fig_bar = px.bar(member_spending, x=member_spending.index, y="Amount", title="Total Spending by Member",
                         color=member_spending.index)
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- Data Table ---
    st.header(f"🧾 All Expenses for {selected_month}")
    # Format columns for better display
    st.dataframe(filtered_df[['Date', 'Member', 'Category', 'Amount', 'Payment_Mode', 'Deadline']].style.format({
        "Amount": "Rs. {:,.2f}",
        "Date": lambda x: x.strftime('%d-%m-%Y') if pd.notna(x) else 'N/A',
        "Deadline": lambda x: x.strftime('%d-%m-%Y') if pd.notna(x) else 'N/A'
    }), use_container_width=True)
