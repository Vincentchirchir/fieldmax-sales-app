from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

def get_greeting():
    hour = datetime.now().hour
    if hour < 18:
        return "Good morning"
    elif hour < 12:
        return "Good afternoon"
    else:
        return "Good evening"

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# PostgreSQL connection setup
conn = psycopg2.connect(
    host='dpg-d1i10rili9vc73d54u5g-a.oregon-postgres.render.com',
    dbname='fieldmax_db_exx4',
    user='fieldmax_db_exx4_user',
    password='lAvVBkjMXyUrxGPBkAYWzYQNJKaOiN5j',
    port='5432'
)
cursor = conn.cursor()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()

        # Check if email already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email already in use", "warning")
            return redirect(url_for('register'))

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Save user to database
        cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", 
                       (email, hashed_password))
        conn.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html', datetime=datetime)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user[2], password):  # Assuming password is column index 2
            session['user_id'] = user[0]
            session['email'] = user[1]
            flash("Login successful", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password", "danger")

    return render_template('login.html', datetime=datetime)

@app.route('/logout')
def logout():
    session.clear()
    flash("You’ve been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/upload-product', methods=['POST'])
def upload_product():
    if 'user_id' not in session:
        flash("Login required", "warning")
        return redirect(url_for('login'))

    code = request.form['code'].strip()
    name = request.form['name'].strip()
    buying = float(request.form['buying'])
    selling = float(request.form['selling'])
    added_stock = int(request.form['added_stock'])

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE item_code = %s", (code,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE products
            SET item_name = %s,
                all_stock = all_stock + %s,
                in_stock = in_stock + %s
            WHERE item_code = %s
        """, (name, added_stock, added_stock, code))
    else:
        cursor.execute("""
            INSERT INTO products (item_code, item_name, buying_price, selling_price, all_stock, in_stock)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (code, name, buying, selling, added_stock, added_stock))

    cursor.execute("""
        INSERT INTO stock_entries (item_code, buying_price, quantity, remaining_quantity)
        VALUES (%s, %s, %s, %s)
    """, (code, buying, added_stock, added_stock))

    conn.commit()
    flash("Product uploaded and stock batch recorded", "success")
    return redirect(url_for('dashboard'))
    

@app.route('/record-sale', methods=['POST'])
def record_sale():
    if 'user_id' not in session:
        flash("Login required", "warning")
        return redirect(url_for('login'))

    item_code = request.form['item_code'].strip()
    sale_price = float(request.form['sale_price'])
    quantity_to_sell = int(request.form['quantity'])

    cursor = conn.cursor()

    # Get item name
    cursor.execute("SELECT item_name FROM products WHERE item_code = %s", (item_code,))
    result = cursor.fetchone()
    item_name = result[0] if result else "Unknown"

    # Get FIFO batches
    cursor.execute("""
        SELECT id, buying_price, remaining_quantity
        FROM stock_entries
        WHERE item_code = %s AND remaining_quantity > 0
        ORDER BY date_received ASC
    """, (item_code,))
    stock_batches = cursor.fetchall()

    sold = 0
    for batch in stock_batches:
        if sold >= quantity_to_sell:
            break

        stock_id, buying_price, available_qty = batch
        to_sell = min(quantity_to_sell - sold, available_qty)
        profit = (sale_price - float(buying_price)) * to_sell

        # Record sale
        cursor.execute("""
            INSERT INTO sales (item_code, item_name, sale_price, buying_price, profit, quantity)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (item_code, item_name, sale_price, buying_price, profit, to_sell))

        # Update remaining quantity in batch
        cursor.execute("""
            UPDATE stock_entries
            SET remaining_quantity = remaining_quantity - %s
            WHERE id = %s
        """, (to_sell, stock_id))

        sold += to_sell

    # Update main stock
    cursor.execute("""
        UPDATE products
        SET in_stock = in_stock - %s
        WHERE item_code = %s
    """, (quantity_to_sell, item_code))

    conn.commit()
    flash(f"{quantity_to_sell} items of {item_name} sold using FIFO", "success")
    return redirect(url_for('dashboard'))

@app.route('/get-product/<item_code>')
def get_product(item_code):
    cursor.execute("SELECT item_name, buying_price, in_stock FROM products WHERE item_code = %s", (item_code,))
    product = cursor.fetchone()

    if product:
        item_name, buying_price, in_stock = product
        return jsonify({
            'item_name': item_name,
            'buying_price': float(buying_price),
            'in_stock': in_stock
        })
    else:
        return jsonify({'error': 'Product not found'})

@app.route("/actions")
def actions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("actions.html")

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for('login'))

    cursor = conn.cursor()

    # --- Total products
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]

    # --- Sales and profits breakdown
    timeframes = {
        'daily': "CURRENT_DATE",
        'weekly': "CURRENT_DATE - INTERVAL '7 days'",
        'monthly': "CURRENT_DATE - INTERVAL '30 days'"
    }

    sales_data = {}
    for key, condition in timeframes.items():
        cursor.execute(f"""
            SELECT 
                COALESCE(SUM(quantity), 0), 
                COALESCE(SUM(profit), 0)
            FROM sales 
            WHERE sale_date >= {condition}
        """)
        quantity, profit = cursor.fetchone()
        sales_data[f"{key}_sales"] = quantity
        sales_data[f"{key}_profit"] = profit

    # --- All-time stats
    cursor.execute("SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(profit), 0) FROM sales")
    all_sales, all_profit = cursor.fetchone()

    # --- Latest 5 sales
    cursor.execute("""
        SELECT item_code, item_name, quantity, sale_price, profit, sale_date
        FROM sales 
        ORDER BY sale_date DESC 
        LIMIT 5
    """)
    latest_sales = cursor.fetchall()

    # --- Top 5 selling items
    cursor.execute("""
        SELECT item_name, SUM(quantity) AS total_quantity
        FROM sales 
        GROUP BY item_name 
        ORDER BY total_quantity DESC 
        LIMIT 5
    """)
    top_selling_items = cursor.fetchall()

    # --- Stock warnings (<= 5 in_stock)
    cursor.execute("""
        SELECT item_code, item_name, in_stock 
        FROM products 
        WHERE in_stock <= 5
    """)
    low_stock_items = cursor.fetchall()

    greeting = get_greeting()

    return render_template(
    "dashboard.html",
    greeting=greeting,
    total_products=total_products,
    total_sales=all_sales,
    total_profit=all_profit,
    daily_sales=sales_data['daily_sales'],
    weekly_sales=sales_data['weekly_sales'],
    monthly_sales=sales_data['monthly_sales'],
    daily_profit=sales_data['daily_profit'],
    weekly_profit=sales_data['weekly_profit'],
    monthly_profit=sales_data['monthly_profit'],
    latest_sales=latest_sales,
    top_selling_items=top_selling_items,
    low_stock_items=low_stock_items,
    datetime=datetime
)

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.context_processor
def inject_datetime():
    return {'datetime': datetime}

if __name__ == '__main__':
    app.run(debug=True)
