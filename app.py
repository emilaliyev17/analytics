import streamlit as st
import psycopg2
import pandas as pd
import os
import hashlib
from datetime import datetime, timedelta

st.set_page_config(page_title="Sunco Analytics", layout="wide")

# Database connection - don't cache the connection itself
def get_connection():
    # Use DATABASE_URL from environment if available (for Render)
    # Otherwise use local connection (for development)
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Render uses 'postgres://' but psycopg2 needs 'postgresql://'
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return psycopg2.connect(database_url)
    else:
        # Local development
        return psycopg2.connect(
            dbname='sales_analytics',
            user='emil.aliyev',
            password='',
            host='localhost',
            port='5432'
        )

# Load data with fresh connection each time
@st.cache_data
def load_data(query):
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Authentication
def check_password():
    """Returns True if user has correct credentials from database."""
    
    def hash_password(password):
        """Create SHA-256 hash of the password."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_credentials(username, password):
        """Verify credentials against database."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Get user from database
            cursor.execute(
                "SELECT password_hash, role FROM users WHERE username = %s",
                (username,)
            )
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                stored_hash, role = result
                # Compare password hash
                if stored_hash == hash_password(password):
                    return True, role
            
            return False, None
            
        except Exception as e:
            return False, None
    
    def credentials_entered():
        """Check credentials when entered."""
        username = st.session_state["username"]
        password = st.session_state["password"]
        
        is_valid, role = verify_credentials(username, password)
        
        if is_valid:
            st.session_state["password_correct"] = True
            st.session_state["logged_in_user"] = username
            st.session_state["user_role"] = role
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False
    
    # Return True if already logged in
    if st.session_state.get("password_correct", False):
        return True
    
    # Show login form
    st.title("🔐 Login to Sunco Analytics")
    st.text_input("Username", on_change=credentials_entered, key="username")
    st.text_input("Password", type="password", on_change=credentials_entered, key="password")
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Incorrect username or password")
    
    return False

# Check authentication before showing the app
if not check_password():
    st.stop()

# Title
st.title("🚲 Sunco Analytics Dashboard")

# Sidebar filters
st.sidebar.header("Filters")

# Date range filter
date_range = st.sidebar.date_input(
    "Select Date Range",
    value=[datetime(2024, 1, 1), datetime(2025, 8, 31)],
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2025, 8, 31)
)

# Check if date_range has both dates
if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = date_range[0] if date_range else datetime(2024, 1, 1)
    end_date = datetime(2025, 8, 31)

# Report type selector
report_type = st.sidebar.selectbox(
    "Select Report",
    ["Overview", "Best Sellers", "Worst Sellers", "Sales Trend", "Seasonal Analysis", "Product Performance by Launch Date", "Launch Period Analysis"]
)

# Admin panel in sidebar (only for admin users)
if st.session_state.get("user_role") == "admin":
    st.sidebar.divider()
    st.sidebar.header("👤 User Management")
    
    # Add new user section
    with st.sidebar.expander("Add New User"):
        new_username = st.text_input("Username", key="new_user")
        new_password = st.text_input("Password", type="password", key="new_pass")
        new_role = st.selectbox("Role", ["user", "admin"], key="new_role")
        
        if st.button("Add User"):
            if new_username and new_password:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    
                    # Hash the password
                    import hashlib
                    password_hash = hashlib.sha256(new_password.encode()).hexdigest()
                    
                    # Insert new user
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        (new_username, password_hash, new_role)
                    )
                    conn.commit()
                    cursor.close()
                    conn.close()
                    
                    st.sidebar.success(f"✅ User {new_username} added!")
                except Exception as e:
                    st.sidebar.error(f"Error: {str(e)}")
            else:
                st.sidebar.error("Please fill all fields")
    
    # View existing users
    if st.sidebar.button("View All Users"):
        try:
            conn = get_connection()
            users_df = pd.read_sql_query(
                "SELECT username, role, created_at FROM users ORDER BY created_at DESC",
                conn
            )
            conn.close()
            st.subheader("System Users")
            st.dataframe(users_df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error loading users: {str(e)}")

# Main content
if report_type == "Overview":
    col1, col2, col3 = st.columns(3)
    
    # Get summary metrics
    query = f"""
    SELECT 
        COUNT(DISTINCT master_sku) as total_skus,
        SUM(quantity_ordered) as total_units,
        SUM(sales_ordered) as total_revenue
    FROM sales
    WHERE order_date BETWEEN '{start_date}' AND '{end_date}'
    """
    metrics = load_data(query)
    
    col1.metric("Total SKUs", f"{metrics['total_skus'][0]:,}")
    col2.metric("Units Sold", f"{metrics['total_units'][0]:,}")
    col3.metric("Total Revenue", f"${metrics['total_revenue'][0]:,.2f}")

elif report_type == "Best Sellers":
    st.subheader("Top 20 Best Selling Products")
    
    query = f"""
    SELECT 
        master_sku,
        SUM(quantity_ordered) as units_sold,
        SUM(sales_ordered) as revenue,
        AVG(avg_price) as avg_price
    FROM sales
    WHERE order_date BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY master_sku
    ORDER BY revenue DESC
    LIMIT 20
    """
    
    df = load_data(query)
    st.dataframe(df, use_container_width=True, hide_index=True)

elif report_type == "Product Performance by Launch Date":
    st.subheader("Product Performance by Launch Date")
    
    query = f"""
    SELECT 
        lp.sku,
        lp.created_at::date as launch_date,
        COALESCE(SUM(s.quantity_ordered), 0) as total_units_sold,
        COALESCE(SUM(s.sales_ordered), 0) as total_revenue,
        COALESCE(AVG(s.avg_price), 0) as average_price
    FROM launched_products lp
    LEFT JOIN sales s ON lp.sku = s.master_sku 
        AND s.order_date BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY lp.sku, lp.created_at
    ORDER BY lp.created_at ASC, lp.sku ASC
    """
    
    df = load_data(query)
    
    # Format the columns
    df['total_revenue'] = df['total_revenue'].apply(lambda x: f"${x:,.2f}")
    df['average_price'] = df['average_price'].apply(lambda x: f"${x:.2f}")
    df['total_units_sold'] = df['total_units_sold'].apply(lambda x: f"{x:,}")
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Show summary metrics
    st.subheader("Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Products", len(df))
    col2.metric("Products with Sales", (df['total_units_sold'] != '0').sum())
    col3.metric("Products without Sales", (df['total_units_sold'] == '0').sum())

elif report_type == "Launch Period Analysis":
    st.subheader("Launch Period Analysis")
    
    # Add a separate date filter for launch period
    col1, col2 = st.columns(2)
    with col1:
        launch_start = st.date_input(
            "Launch Period Start",
            value=datetime(2025, 1, 1),
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2025, 12, 31)
        )
    with col2:
        launch_end = st.date_input(
            "Launch Period End", 
            value=datetime(2025, 4, 30),
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2025, 12, 31)
        )
    
    query = f"""
    SELECT 
        lp.sku,
        lp.created_at::date as launch_date,
        COALESCE(SUM(s.quantity_ordered), 0) as units_sold,
        COALESCE(SUM(s.sales_ordered), 0) as revenue
    FROM launched_products lp
    LEFT JOIN sales s ON lp.sku = s.master_sku
    WHERE lp.created_at::date BETWEEN '{launch_start}' AND '{launch_end}'
    GROUP BY lp.sku, lp.created_at
    ORDER BY lp.created_at ASC
    """
    
    df = load_data(query)
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Products Launched", len(df))
    col2.metric("Total Units Sold", f"{df['units_sold'].sum():,}")
    col3.metric("Total Revenue", f"${df['revenue'].sum():,.2f}")
    col4.metric("Avg Revenue/Product", f"${df['revenue'].mean():,.2f}")
    
    # Detailed table
    st.subheader("Products Launched in Selected Period")
    df['revenue'] = df['revenue'].apply(lambda x: f"${x:,.2f}")
    df['units_sold'] = df['units_sold'].apply(lambda x: f"{x:,}")
    st.dataframe(df, use_container_width=True, hide_index=True)

# Add more report types later