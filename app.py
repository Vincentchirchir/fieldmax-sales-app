from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

from datetime import datetime

def get_greeting():
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Needed for flashing messages

# PostgreSQL connection setup

# Establish database connection
#conn = psycopg2.connect(
    #host="localhost",
    #database="Fieldmax_db",
    #user="postgres",
    #password="2952"
#)

conn = psycopg2.connect(
    host='dpg-d1i10rili9vc73d54u5g-a.oregon-postgres.render.com',
    dbname='fieldmax_db_exx4',
    user='fieldmax_db_exx4_user',
    password='lAvVBkjMXyUrxGPBkAYWzYQNJKaOiN5j',
    port='5432'
)
cursor = conn.cursor()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()

        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))


@app.route('/upload-product', methods=['POST'])
def upload_product():
    code = request.form['code'].strip()
    name = request.form['name'].strip()
    buying = float(request.form['buying'])
    selling = float(request.form['selling'])
    added_stock = int(request.form['added_stock'])

    # Check if product already exists
    cursor.execute("SELECT * FROM products WHERE item_code = %s", (code,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE products
            SET item_name = %s,
                buying_price = %s,
                selling_price = %s,
                all_stock = all_stock + %s,
                in_stock = in_stock + %s
            WHERE item_code = %s
        """, (name, buying, selling, added_stock, added_stock, code))
        flash("Product updated successfully!", "info")
    else:
        cursor.execute("""
            INSERT INTO products (item_code, item_name, buying_price, selling_price, all_stock, in_stock)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (code, name, buying, selling, added_stock, added_stock))
        flash("New product uploaded successfully!", "success")

    conn.commit()
    return redirect(url_for('dashboard'))

@app.route('/record-sale', methods=['POST'])
def record_sale():
    item_code = request.form['item_code'].strip()
    sale_price = float(request.form['sale_price'])
    quantity = int(request.form['quantity'])

    # Fetch product info from database
    cursor.execute(
        "SELECT item_name, buying_price, in_stock FROM products WHERE item_code = %s",
        (item_code,)
    )
    product = cursor.fetchone()

    if not product:
        flash("Product not found in database.", "danger")
        return redirect(url_for('dashboard'))

    item_name, buying_price, current_stock = product

    # Validate stock
    if current_stock < quantity:
        flash("Not enough stock to complete the sale.", "warning")
        return redirect(url_for('dashboard'))

    # Calculate profit per item
    profit = sale_price - float(buying_price)

    # Update stock
    cursor.execute(
        "UPDATE products SET in_stock = in_stock - %s WHERE item_code = %s",
        (quantity, item_code)
    )

    # Insert individual sale records
    for _ in range(quantity):
        cursor.execute("""
            INSERT INTO sales (item_code, item_name, sale_price, buying_price, profit, quantity, sale_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (item_code, item_name, sale_price, buying_price, profit, 1, datetime.now()))

    conn.commit()
    flash("Sale recorded successfully!", "success")
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

@app.route("/login")
def actions():
    return render_template("login.html")

#@app.route('/dashboard')
#def dashboard():
    # Total Products
    #cursor.execute("SELECT COUNT(*) FROM products")
    #total_products = cursor.fetchone()[0]

    # Total Sales
    #cursor.execute("SELECT COUNT(*) FROM sales")
    #total_sales = cursor.fetchone()[0]

    # Total Revenue
    #cursor.execute("SELECT COALESCE(SUM(sale_price), 0) FROM sales")
    #total_revenue = float(cursor.fetchone()[0])

    # Total Profit
    #cursor.execute("SELECT COALESCE(SUM(profit), 0) FROM sales")
    #total_profit = float(cursor.fetchone()[0])

    # Low Stock Items (<= 5)
    #cursor.execute("""
        #SELECT item_code, item_name, in_stock
        #FROM products
        #WHERE in_stock <= 5
    #""")
    #low_stock_items = cursor.fetchall()

    #return render_template(
        #'dashboard.html',
        #total_products=total_products,
        #total_sales=total_sales,
        #total_revenue=total_revenue,
        #total_profit=total_profit,
        #low_stock_items=low_stock_items
    #)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sales")
    total_sales = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(profit) FROM sales")
    total_profit = cursor.fetchone()[0] or 0

    greeting = get_greeting()

    return render_template("dashboard.html", total_products=total_products,
                           total_sales=total_sales, total_profit=total_profit,
                           greeting=greeting)

@app.route('/')
def home():
    return redirect(url_for('login'))

def ensure_default_user():
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", ('Admin',))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            ('Admin', 'A12345')
        )
        conn.commit()
        print("✅ Default user created: Admin / A12345")
    cur.close()

if __name__ == '__main__':
    ensure_default_user()  # Create Admin user if not exists
    app.run(debug=True)
