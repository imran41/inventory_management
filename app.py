import streamlit as st
import psycopg2
from psycopg2 import IntegrityError
import os
import pandas as pd
from datetime import datetime
import uuid
import plotly.express as px


# ==================== CONFIGURATION ====================
def configure_page():
    """Configure Streamlit page settings"""
    st.set_page_config(page_title="Inventory Management", page_icon="📦", layout="wide")
    st.title("📦 Inventory Management System")


def get_database_url():
    """Get database URL from environment or default"""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://neondb_owner:npg_StHOc3FBpN2M@ep-twilight-scene-adsg231w-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )


# ==================== DATABASE CONNECTION ====================
@st.cache_resource
def get_connection():
    """Establish and return database connection"""
    conn = psycopg2.connect(get_database_url())
    initialize_database(conn)
    return conn


def initialize_database(conn):
    """Initialize database tables with proper schema"""
    cursor = conn.cursor()
    try:
        drop_old_tables_if_exists(cursor)
        create_products_table(cursor)
        create_transactions_table(cursor)
        conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Error initializing database: {e}")


def drop_old_tables_if_exists(cursor):
    """Drop old tables for migration if they exist"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'products'
        )
    """)
    products_exists = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'transactions'
        )
    """)
    transactions_exists = cursor.fetchone()[0]
    
    if products_exists or transactions_exists:
        cursor.execute("DROP TABLE IF EXISTS transactions CASCADE")
        cursor.execute("DROP TABLE IF EXISTS products CASCADE")


def create_products_table(cursor):
    """Create products table with UUID primary key"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            stock INTEGER DEFAULT 0
        )
    """)


def create_transactions_table(cursor):
    """Create transactions table with UUID primary key"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date DATE,
            product_uuid UUID REFERENCES products(uuid) ON DELETE CASCADE ON UPDATE CASCADE,
            product_id TEXT,
            product_name TEXT,
            quantity_added INTEGER,
            quantity_sold INTEGER,
            remarks TEXT
        )
    """)


# ==================== DATA VALIDATION ====================
def validate_product_name(name):
    """Validate that product name is lowercase only"""
    if any(c.isupper() for c in name):
        return False, "Error: Product name must be lowercase only."
    return True, ""


def validate_stock_availability(current_stock, quantity_to_sell):
    """Validate if enough stock is available for sale"""
    new_stock = current_stock - quantity_to_sell
    if new_stock < 0:
        return False, "Error: Not enough stock to sell."
    return True, new_stock


# ==================== PRODUCT OPERATIONS ====================
def add_product(cursor, conn, pid, name, category):
    """Add a new product to the database"""
    pid = str(pid).strip()
    name = name.lower().strip()
    
    is_valid, error_msg = validate_product_name(name)
    if not is_valid:
        return False, error_msg
    
    try:
        cursor.execute(
            "INSERT INTO products (id, name, category, stock) VALUES (%s, %s, %s, %s)",
            (pid, name, category, 0)
        )
        conn.commit()
        return True, f"Product '{name}' with ID {pid} added successfully."
    except IntegrityError as e:
        conn.rollback()
        if "duplicate key" in str(e) and "products_id_key" in str(e):
            return False, "Error: Product ID already exists."
        else:
            return False, f"Error: {str(e)}"
    except Exception as e:
        conn.rollback()
        return False, str(e)


def get_product_by_uuid(cursor, product_uuid):
    """Fetch product details by UUID"""
    cursor.execute("SELECT uuid, id, name, stock FROM products WHERE uuid=%s", (product_uuid,))
    return cursor.fetchone()


def update_product_stock(cursor, product_uuid, new_stock):
    """Update the stock quantity for a product"""
    cursor.execute("UPDATE products SET stock=%s WHERE uuid=%s", (new_stock, product_uuid))


def get_all_products(cursor):
    """Retrieve all products from database"""
    try:
        cursor.execute("SELECT uuid, id, name, category, stock FROM products ORDER BY id")
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []


def get_products_with_stock_added(cursor):
    """Get only products that have had stock added (quantity_added > 0)"""
    try:
        cursor.execute("""
            SELECT DISTINCT p.uuid, p.id, p.name, p.category, p.stock 
            FROM products p
            INNER JOIN transactions t ON p.uuid = t.product_uuid
            WHERE t.quantity_added > 0
            ORDER BY p.id
        """)
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []


def update_product_details(cursor, conn, product_uuid, new_id=None, new_name=None, new_category=None, new_stock=None):
    """Update product details and related transactions"""
    try:
        updates = []
        params = []
        
        if new_id:
            updates.append("id=%s")
            params.append(new_id.strip())
            cursor.execute(
                "UPDATE transactions SET product_id=%s WHERE product_uuid=%s",
                (new_id.strip(), product_uuid)
            )
        
        if new_name:
            updates.append("name=%s")
            params.append(new_name.lower().strip())
            cursor.execute(
                "UPDATE transactions SET product_name=%s WHERE product_uuid=%s",
                (new_name.lower().strip(), product_uuid)
            )
        
        if new_category:
            updates.append("category=%s")
            params.append(new_category.strip())
        
        if new_stock is not None:
            updates.append("stock=%s")
            params.append(new_stock)

        if updates:
            sql = f"UPDATE products SET {', '.join(updates)} WHERE uuid=%s"
            params.append(product_uuid)
            cursor.execute(sql, tuple(params))
            conn.commit()
            return True, "✅ Product updated successfully."
        else:
            return False, "No changes made."
    except IntegrityError as e:
        conn.rollback()
        if "duplicate key" in str(e) and "products_id_key" in str(e):
            return False, "Error: Product ID already exists."
        else:
            return False, f"Update failed: {e}"
    except Exception as e:
        conn.rollback()
        return False, f"Update failed: {e}"


def delete_product(cursor, conn, product_uuid):
    """Delete a product and all related transactions"""
    try:
        cursor.execute("DELETE FROM products WHERE uuid=%s", (product_uuid,))
        conn.commit()
        return True, "Product deleted successfully."
    except Exception as e:
        conn.rollback()
        return False, f"Delete failed: {e}"


# ==================== TRANSACTION OPERATIONS ====================
def record_transaction(cursor, date, product_uuid, product_id, product_name, added, sold, remarks):
    """Record a stock transaction"""
    cursor.execute("""
        INSERT INTO transactions (date, product_uuid, product_id, product_name, quantity_added, quantity_sold, remarks)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (date, product_uuid, product_id, product_name, added, sold, remarks))


def update_stock(cursor, conn, product_uuid, date, added=0, sold=0, remarks=""):
    """Update stock and record transaction"""
    try:
        product = get_product_by_uuid(cursor, product_uuid)
        if not product:
            return False, "Product not found."
        
        prod_uuid, pid, name, current_stock = product
        new_stock = current_stock + added - sold
        
        if sold > 0:
            is_valid, result = validate_stock_availability(current_stock, sold)
            if not is_valid:
                return False, result
            new_stock = result
        
        update_product_stock(cursor, prod_uuid, new_stock)
        record_transaction(cursor, date, prod_uuid, pid, name, added, sold, remarks)
        conn.commit()
        
        return True, f"Stock updated for '{name}' (ID: {pid}) on {date}. Current stock: {new_stock}"
    except Exception as e:
        conn.rollback()
        return False, str(e)


def get_transactions(cursor):
    """Retrieve all transactions"""
    try:
        cursor.execute("""
            SELECT t.uuid, t.date, t.product_id, t.product_name, t.quantity_added, t.quantity_sold, t.remarks
            FROM transactions t
            ORDER BY t.date DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []


# ==================== SUMMARY REPORTS ====================
def get_stock_summary(cursor):
    """Get summary of all products with total stock added"""
    try:
        cursor.execute("""
            SELECT p.id, p.name, p.category, COALESCE(SUM(t.quantity_added), 0) as total_added, p.stock as current_stock
            FROM products p
            LEFT JOIN transactions t ON p.uuid = t.product_uuid
            WHERE t.quantity_added > 0
            GROUP BY p.id, p.name, p.category, p.stock
            ORDER BY total_added DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []


def get_sales_summary(cursor):
    """Get summary of all products with total sales"""
    try:
        cursor.execute("""
            SELECT p.id, p.name, p.category, COALESCE(SUM(t.quantity_sold), 0) as total_sold
            FROM products p
            LEFT JOIN transactions t ON p.uuid = t.product_uuid
            WHERE t.quantity_sold > 0
            GROUP BY p.id, p.name, p.category
            ORDER BY total_sold DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []


# ==================== DATA PROCESSING ====================
def filter_dataframe_by_category(df, categories):
    """Filter dataframe by categories"""
    if categories:
        return df[df["Category"].isin(categories)]
    return df


def filter_dataframe_by_products(df, products):
    """Filter dataframe by product names"""
    if products:
        return df[df["Product Name"].isin(products)]
    return df


def filter_dataframe_by_low_stock(df, show_low_stock, threshold=10):
    """Filter dataframe to show only low stock items"""
    if show_low_stock == "Yes":
        return df[df["Stock"] < threshold]
    return df


def filter_dataframe_by_date(df, date_filter):
    """Filter dataframe by date"""
    if date_filter:
        return df[df["Date"] == date_filter.strftime("%Y-%m-%d")]
    return df


def prepare_products_dataframe(products):
    """Convert products list to DataFrame"""
    df = pd.DataFrame(products, columns=["UUID", "ID", "Product Name", "Category", "Stock"])
    return df


def prepare_transactions_dataframe(transactions, products):
    """Convert transactions list to DataFrame with category"""
    df = pd.DataFrame(transactions, columns=["Transaction UUID", "Date", "Product ID", "Product Name", "Added", "Sold", "Remarks"])
    prod_df = pd.DataFrame(products, columns=["UUID", "ID", "Product Name", "Category", "Stock"])
    df = df.merge(prod_df[["Product Name", "Category"]], on="Product Name", how="left")
    return df


# ==================== CSV IMPORT ====================
def validate_csv_columns(df, required_cols):
    """Validate that CSV has required columns"""
    return required_cols.issubset(df.columns)


def clean_csv_data(df):
    """Clean and format CSV data"""
    df["id"] = df["id"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.lower().str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    return df


def generate_unique_product_id(cursor, original_pid):
    """Generate unique product ID if duplicate exists"""
    pid = original_pid
    counter = 1
    while True:
        cursor.execute("SELECT 1 FROM products WHERE id=%s", (pid,))
        if cursor.fetchone():
            pid = f"{original_pid}({counter})"
            counter += 1
        else:
            return pid


def process_csv_products(cursor, conn, df_csv):
    """Process and add products from CSV"""
    added_count = 0
    for idx, row in df_csv.iterrows():
        original_pid = row["id"]
        name = row["name"]
        category = row["category"]

        pid = generate_unique_product_id(cursor, original_pid)
        success, message = add_product(cursor, conn, pid, name, category)
        
        if success:
            added_count += 1
        else:
            st.warning(f"Row {idx+1} skipped: {message}")
    
    return added_count


# ==================== UI COMPONENTS ====================
def render_navigation_menu():
    """Render sidebar navigation menu"""
    return st.sidebar.selectbox(
        "Navigation",
        ["Dashboard", "Add Product", "Add Stock", "Record Sale", "Transactions", "Stock Summary", "Sales Summary", "Manage Products"]
    )


def render_filter_section(df, filter_title="🔍 Filter"):
    """Render common filter section for category and product"""
    with st.expander(filter_title):
        col1, col2 = st.columns(2)
        category_filter = col1.multiselect("Filter by Category", options=df["Category"].unique())
        
        filtered_df = df
        if category_filter:
            filtered_df = df[df["Category"].isin(category_filter)]
        
        product_filter = col2.multiselect("Filter by Product Name", options=filtered_df["Product Name"].unique())
    
    return category_filter, product_filter


def render_inventory_filters(df):
    """Render inventory-specific filters"""
    with st.expander("🔍 Filter Inventory"):
        col1, col2, col3 = st.columns(3)
        category_filter = col1.multiselect("Filter by Category", options=df["Category"].unique())
        
        filtered_df = df
        if category_filter:
            filtered_df = df[df["Category"].isin(category_filter)]
        
        product_filter = col2.multiselect("Filter by Product Name", options=filtered_df["Product Name"].unique())
        low_stock_filter = col3.selectbox("Show only low stock items?", options=["No", "Yes"])
    
    return category_filter, product_filter, low_stock_filter


def render_transaction_filters(df):
    """Render transaction-specific filters"""
    with st.expander("🔍 Filter Transactions"):
        col1, col2, col3 = st.columns(3)
        category_filter = col1.multiselect("Filter by Category", options=df["Category"].dropna().unique())
        
        filtered_df = df
        if category_filter:
            filtered_df = df[df["Category"].isin(category_filter)]
        
        product_filter = col2.multiselect("Filter by Product Name", options=filtered_df["Product Name"].unique())
        date_filter = col3.date_input("Filter by Date (optional)", value=None)
    
    return category_filter, product_filter, date_filter


def render_metrics(total_products, total_stock, low_stock_count):
    """Render dashboard metrics"""
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Products", total_products)
    col2.metric("Total Stock", total_stock)
    col3.metric("Low Stock Items", low_stock_count)


def render_stock_summary_metrics(df):
    """Render stock summary metrics"""
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Products", len(df))
    col2.metric("Total Stock Added", int(df["Total Stock Added"].sum()))
    col3.metric("Current Stock Available", int(df["Current Stock"].sum()))


def render_sales_summary_metrics(df):
    """Render sales summary metrics"""
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Products Sold", len(df))
    col2.metric("Total Units Sold", int(df["Total Sold"].sum()))
    col3.metric("Average Sales per Product", f"{df['Total Sold'].mean():.2f}")


def render_transaction_metrics(df):
    """Render transaction metrics"""
    col1, col2 = st.columns(2)
    col1.metric("Total Items Added", df["Added"].sum())
    col2.metric("Total Items Sold", df["Sold"].sum())


# ==================== VISUALIZATION ====================
def render_stock_by_category_pie(df):
    """Render pie chart for stock by category"""
    stock_by_cat = df.groupby("Category")["Stock"].sum().reset_index()
    st.subheader("Stock Distribution by Category")
    st.plotly_chart(px.pie(stock_by_cat, names="Category", values="Stock", title="Stock by Category"))


def render_low_stock_bar(df, threshold=10):
    """Render bar chart for low stock items"""
    low_stock_items = df[df["Stock"] < threshold]
    if not low_stock_items.empty:
        st.subheader(f"Low Stock Items (<{threshold} units)")
        st.bar_chart(low_stock_items.set_index("Product Name")["Stock"])


def render_top_products_bar(df, top_n=10):
    """Render bar chart for top products by stock"""
    st.subheader("Top Products by Stock")
    top_products = df.sort_values("Stock", ascending=False).head(top_n)
    st.bar_chart(top_products.set_index("Product Name")["Stock"])


def render_sales_trend(transactions):
    """Render sales trend for last 30 days"""
    if transactions:
        trans_df = pd.DataFrame(transactions, columns=["Transaction UUID", "Date", "Product ID", "Product Name", "Added", "Sold", "Remarks"])
        trans_df["Date"] = pd.to_datetime(trans_df["Date"])
        last_30 = trans_df[trans_df["Date"] >= pd.Timestamp.now() - pd.Timedelta(days=30)]
        sales_trend = last_30.groupby("Date")["Sold"].sum().reset_index()
        st.subheader("Sales Trend (Last 30 Days)")
        st.line_chart(sales_trend.set_index("Date")["Sold"])


def render_stock_analytics(df):
    """Render stock analytics visualizations"""
    st.markdown("### 📈 Stock Analytics")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Stock Added by Category")
        stock_by_cat = df.groupby("Category")["Total Stock Added"].sum().reset_index()
        st.plotly_chart(px.bar(stock_by_cat, x="Category", y="Total Stock Added", title="Total Stock Added by Category"))
    
    with col2:
        st.subheader("Current Stock by Category")
        current_by_cat = df.groupby("Category")["Current Stock"].sum().reset_index()
        st.plotly_chart(px.pie(current_by_cat, names="Category", values="Current Stock", title="Current Stock Distribution"))
    
    st.subheader("Top 10 Products by Stock Added")
    top_products = df.sort_values("Total Stock Added", ascending=False).head(10)
    st.bar_chart(top_products.set_index("Product Name")["Total Stock Added"])


def render_sales_analytics(df):
    """Render sales analytics visualizations"""
    st.markdown("### 📈 Sales Analytics")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Sales by Category")
        sales_by_cat = df.groupby("Category")["Total Sold"].sum().reset_index()
        st.plotly_chart(px.bar(sales_by_cat, x="Category", y="Total Sold", title="Total Sales by Category"))
    
    with col2:
        st.subheader("Sales Distribution by Category")
        st.plotly_chart(px.pie(sales_by_cat, names="Category", values="Total Sold", title="Sales Distribution"))
    
    st.subheader("Top 10 Best Selling Products")
    top_sellers = df.sort_values("Total Sold", ascending=False).head(10)
    st.bar_chart(top_sellers.set_index("Product Name")["Total Sold"])


# ==================== PAGE RENDERERS ====================
def render_dashboard_page(cursor):
    """Render dashboard page"""
    st.header("Current Inventory")
    products = get_all_products(cursor)
    
    if products:
        df = prepare_products_dataframe(products)
        display_df = df[["ID", "Product Name", "Category", "Stock"]]

        category_filter, product_filter, low_stock_filter = render_inventory_filters(display_df)

        display_df = filter_dataframe_by_category(display_df, category_filter)
        display_df = filter_dataframe_by_products(display_df, product_filter)
        display_df = filter_dataframe_by_low_stock(display_df, low_stock_filter)

        render_metrics(len(display_df), display_df["Stock"].sum(), len(display_df[display_df["Stock"] < 10]))
        st.dataframe(display_df, use_container_width=True)

        st.markdown("### 📊 Inventory Analytics")
        render_stock_by_category_pie(display_df)
        render_low_stock_bar(display_df)
        render_top_products_bar(display_df)
        render_sales_trend(get_transactions(cursor))
    else:
        st.info("No products in inventory yet. Add products to get started!")


def render_add_product_page(cursor, conn):
    """Render add product page"""
    st.header("Add New Product")

    st.subheader("Upload CSV to Add Multiple Products")
    st.info("CSV columns required: id, name, category (name must be lowercase).")
    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
    
    if uploaded_file:
        df_csv = pd.read_csv(uploaded_file)
        required_cols = {"id", "name", "category"}
        
        if not validate_csv_columns(df_csv, required_cols):
            st.error(f"CSV must have columns: {', '.join(required_cols)}")
        else:
            df_csv = clean_csv_data(df_csv)
            st.subheader("Preview CSV Products")
            st.dataframe(df_csv)

            if st.button("Confirm & Add Products"):
                added_count = process_csv_products(cursor, conn, df_csv)
                st.success(f"{added_count} products added successfully from CSV!")

    st.markdown("---")
    with st.form("add_product_form"):
        col1, col2, col3 = st.columns(3)
        pid = col1.text_input("Product ID (string)")
        name = col2.text_input("Product Name (lowercase only)")
        category = col3.text_input("Category")
        submitted = st.form_submit_button("Add Product")
        
        if submitted:
            if pid and name and category:
                success, message = add_product(cursor, conn, pid, name, category)
                if success:
                    st.success(message)
                else:
                    st.error(message)
            else:
                st.error("Please enter ID, name, and category.")


def render_stock_operation_form(cursor, conn, operation_type, products):
    """Render form for stock operations (add/sell)"""
    if not products:
        st.warning(f"No products available. Please {'add products' if operation_type == 'add' else 'add stock'} first.")
        return
    
    df_prod = prepare_products_dataframe(products)
    category_filter = st.selectbox(
        "Select Category", 
        ["All"] + list(df_prod["Category"].unique()), 
        key=f"{operation_type}_stock_category"
    )
    
    filtered_df = df_prod if category_filter == "All" else df_prod[df_prod["Category"] == category_filter]
    
    with st.form(f"{operation_type}_stock_form"):
        col1, col2 = st.columns(2)
        
        product_options = [f"{row['ID']} - {row['Product Name']}" for _, row in filtered_df.iterrows()]
        
        if not product_options:
            st.warning("No products available in this category.")
            st.form_submit_button("Submit", disabled=True)
        else:
            selected = col1.selectbox("Select Product (ID - Name)", product_options)
            selected_idx = product_options.index(selected)
            product_uuid = filtered_df.iloc[selected_idx]["UUID"]

            date = col2.date_input("Date").strftime("%Y-%m-%d")
            qty = st.number_input("Quantity", min_value=1, step=1)
            submitted = st.form_submit_button("Submit")

            if submitted:
                if operation_type == "add":
                    success, message = update_stock(cursor, conn, product_uuid, date, added=qty, remarks="New stock received")
                else:
                    success, message = update_stock(cursor, conn, product_uuid, date, sold=qty, remarks="Sold to customer")
                
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)


def render_add_stock_page(cursor, conn):
    """Render add stock page"""
    st.header("Add Stock")
    products = get_all_products(cursor)
    render_stock_operation_form(cursor, conn, "add", products)


def render_record_sale_page(cursor, conn):
    """Render record sale page"""
    st.header("Record Sale")
    products = get_products_with_stock_added(cursor)
    render_stock_operation_form(cursor, conn, "sell", products)


def render_transactions_page(cursor):
    """Render transactions page"""
    st.header("Transaction History")
    transactions = get_transactions(cursor)
    
    if transactions:
        products = get_all_products(cursor)
        df = prepare_transactions_dataframe(transactions, products)
        display_df = df[["Date", "Product ID", "Product Name", "Category", "Added", "Sold", "Remarks"]]

        category_filter, product_filter, date_filter = render_transaction_filters(display_df)

        display_df = filter_dataframe_by_category(display_df, category_filter)
        display_df = filter_dataframe_by_products(display_df, product_filter)
        display_df = filter_dataframe_by_date(display_df, date_filter)

        st.dataframe(display_df, use_container_width=True)
        render_transaction_metrics(display_df)
    else:
        st.info("No transactions recorded yet.")


def render_stock_summary_page(cursor):
    """Render stock summary page"""
    st.header("📊 Stock Summary Report")
    st.subheader("All Stock Items with Available Stock Count")
    
    stock_data = get_stock_summary(cursor)
    
    if stock_data:
        df = pd.DataFrame(stock_data, columns=["Product ID", "Product Name", "Category", "Total Stock Added", "Current Stock"])
        
        category_filter, product_filter = render_filter_section(df, "🔍 Filter Stock Summary")
        
        display_df = filter_dataframe_by_category(df, category_filter)
        display_df = filter_dataframe_by_products(display_df, product_filter)
        
        render_stock_summary_metrics(display_df)
        st.dataframe(display_df, use_container_width=True)
        render_stock_analytics(display_df)
    else:
        st.info("No stock has been added yet. Add stock to see the summary.")


def render_sales_summary_page(cursor):
    """Render sales summary page"""
    st.header("📊 Sales Summary Report")
    st.subheader("All Sale Items with Sale Count")
    
    sales_data = get_sales_summary(cursor)
    
    if sales_data:
        df = pd.DataFrame(sales_data, columns=["Product ID", "Product Name", "Category", "Total Sold"])
        
        category_filter, product_filter = render_filter_section(df, "🔍 Filter Sales Summary")
        
        display_df = filter_dataframe_by_category(df, category_filter)
        display_df = filter_dataframe_by_products(display_df, product_filter)
        
        render_sales_summary_metrics(display_df)
        st.dataframe(display_df, use_container_width=True)
        render_sales_analytics(display_df)
    else:
        st.info("No sales have been recorded yet. Record sales to see the summary.")


def render_manage_products_page(cursor, conn):
    """Render manage products page"""
    st.header("Manage Products")
    products = get_all_products(cursor)
    
    if not products:
        st.warning("No products available to manage.")
        return
    
    df = prepare_products_dataframe(products)
    display_df = df[["ID", "Product Name", "Category", "Stock"]]
    st.dataframe(display_df, use_container_width=True)

    st.markdown("### ✏️ Edit Product Details")
    with st.form("edit_product_form"):
        col1, col2, col3 = st.columns(3)
        
        product_options = [f"{row['ID']}" for _, row in df.iterrows()]
        selected_display = col1.selectbox("Select Product ID", product_options)
        selected_uuid = df[df["ID"] == selected_display]["UUID"].values[0]
        
        new_id = col2.text_input("New Product ID (optional)")
        new_name = col3.text_input("New Product Name (optional)")
        col4, col5 = st.columns(2)
        new_category = col4.text_input("New Category (optional)")
        new_stock = col5.number_input("Adjust Stock (optional)", min_value=0, step=1, value=None)
        update_btn = st.form_submit_button("Update Product")

        if update_btn:
            success, message = update_product_details(cursor, conn, selected_uuid, new_id, new_name, new_category, new_stock)
            if success:
                st.success(message)
                st.rerun()
            else:
                if "No changes" in message:
                    st.warning(message)
                else:
                    st.error(message)

    st.markdown("---")
    st.markdown("### 🗑️ Delete Product")
    with st.form("delete_product_form"):
        del_options = [f"{row['ID']}" for _, row in df.iterrows()]
        del_display = st.selectbox("Select Product ID to Delete", del_options)
        del_uuid = df[df["ID"] == del_display]["UUID"].values[0]
        confirm = st.checkbox("I confirm I want to delete this product and all related transactions.")
        delete_btn = st.form_submit_button("Delete Product")

        if delete_btn:
            if confirm:
                success, message = delete_product(cursor, conn, del_uuid)
                if success:
                    st.success(f"Product with ID '{del_display}' deleted successfully.")
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.warning("Please confirm deletion.")


def render_sidebar_info():
    """Render sidebar information"""
    st.sidebar.markdown("---")
    st.sidebar.info("💡 Tip: All product names must be in lowercase.")


# ==================== MAIN APPLICATION ====================
def main():
    """Main application entry point"""
    configure_page()
    conn = get_connection()
    cursor = conn.cursor()
    
    menu = render_navigation_menu()
    
    if menu == "Dashboard":
        render_dashboard_page(cursor)
    elif menu == "Add Product":
        render_add_product_page(cursor, conn)
    elif menu == "Add Stock":
        render_add_stock_page(cursor, conn)
    elif menu == "Record Sale":
        render_record_sale_page(cursor, conn)
    elif menu == "Transactions":
        render_transactions_page(cursor)
    elif menu == "Stock Summary":
        render_stock_summary_page(cursor)
    elif menu == "Sales Summary":
        render_sales_summary_page(cursor)
    elif menu == "Manage Products":
        render_manage_products_page(cursor, conn)
    
    render_sidebar_info()


if __name__ == "__main__":
    main()
