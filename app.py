from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import re
import os
from werkzeug.utils import secure_filename
import os

# UPLOAD_FOLDER = 'static/profile_pics'
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # ✅ Ensure it exists before uploads

import pytz
from datetime import datetime

import pytz
from datetime import datetime

def get_greeting(name=None):
    kenya_time = datetime.now(pytz.timezone("Africa/Nairobi"))
    hour = kenya_time.hour
    day_name = kenya_time.strftime("%A")  # e.g., Monday, Tuesday...

    if hour < 12:
        greeting = "Good Morning"
    elif hour < 16:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    base = f"{greeting}, {name}" if name else greeting
    return f"{base} – Happy {day_name}!"


app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'static/profile_pics'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form['phone']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        try:
            # ✅ Check if password and confirm match
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return redirect(url_for('register'))

            # ✅ Password strength validation
            if (
                len(password) < 6 or
                not re.search(r'[A-Z]', password) or
                not re.search(r'[a-z]', password) or
                not re.search(r'\d', password) or
                not re.search(r'[^\w\s]', password)
            ):
                flash('Password must meet all requirements.', 'danger')
                return redirect(url_for('register'))

            password_hash = generate_password_hash(password)

            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email = %s OR phone = %s", (email, phone))
            existing_user = cur.fetchone()

            if existing_user:
                flash('Email or phone number already registered.', 'danger')
                cur.close()
                return redirect(url_for('register'))

            cur.execute("""
                INSERT INTO users (first_name, last_name, phone, email, password_hash)
                VALUES (%s, %s, %s, %s, %s)
            """, (first_name, last_name, phone, email, password_hash))  # ✅ Use hashed password
            conn.commit()
            cur.close()

            flash('Registration successful. You can now log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()  # 💥 Important if any failure occurs
            flash("Registration error: " + str(e), "danger")
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()

        try:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()

            if user and check_password_hash(user[2], password):  # Adjust index if password is not at index 2
                session['user_id'] = user[0]
                session['email'] = user[1]
                flash("Login successful", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid email or password", "danger")

        except Exception as e:
            conn.rollback()  # 💥 Critical to prevent transaction lock
            flash("Login error: " + str(e), "danger")

    return render_template('login.html', datetime=datetime)

@app.route('/logout')
def logout():
    session.clear()
    flash("You’ve been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/upload-product', methods=['POST'])
def upload_product():
    # ✅ Ensure only logged-in users can access this route
    if 'user_id' not in session:
        flash("Login required", "warning")
        return redirect(url_for('login'))

    try:
        # ✅ Get form inputs
        code = request.form['code'].strip()
        name = request.form['name'].strip()
        buying = float(request.form['buying'])
        selling = float(request.form['selling'])
        added_stock = int(request.form['added_stock'])

        # ✅ Get current time in Kenya for FIFO batch tracking
        kenya_time = datetime.now(pytz.timezone("Africa/Nairobi"))

        # ✅ Check if product already exists
        cursor.execute("SELECT * FROM products WHERE item_code = %s", (code,))
        existing = cursor.fetchone()

        if existing:
            # ✅ If product exists, update stock
            cursor.execute("""
                UPDATE products
                SET item_name = %s,
                    all_stock = all_stock + %s,
                    in_stock = in_stock + %s
                WHERE item_code = %s
            """, (name, added_stock, added_stock, code))
        else:
            # ✅ If new product, insert it into products table
            cursor.execute("""
                INSERT INTO products (item_code, item_name, buying_price, selling_price, all_stock, in_stock)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (code, name, buying, selling, added_stock, added_stock))

        # ✅ Record batch-wise stock for FIFO using Kenya time
        cursor.execute("""
            INSERT INTO stock_entries (item_code, buying_price, quantity, remaining_quantity, date_received)
            VALUES (%s, %s, %s, %s, %s)
        """, (code, buying, added_stock, added_stock, kenya_time))

        # ✅ Commit all database operations
        conn.commit()
        flash("Product uploaded and stock batch recorded", "success")

    except Exception as e:
        # 💥 Rollback in case of any failure
        conn.rollback()
        flash(f"Upload error: {str(e)}", "danger")

    finally:
        # ✅ Always redirect back to dashboard
        return redirect(url_for('dashboard'))
    

@app.route('/record-sale', methods=['POST'])
def record_sale():
    # ✅ Ensure the user is logged in
    if 'user_id' not in session:
        flash("Login required", "warning")
        return redirect(url_for('login'))

    try:
        # ✅ Extract form data
        item_code = request.form['item_code'].strip()
        sale_price = float(request.form['sale_price'])
        quantity_to_sell = int(request.form['quantity'])

        # ✅ Kenyan timezone timestamp
        kenya_time = datetime.now(pytz.timezone("Africa/Nairobi"))

        # ✅ Get item name from products table
        cursor.execute("SELECT item_name FROM products WHERE item_code = %s", (item_code,))
        result = cursor.fetchone()
        item_name = result[0] if result else "Unknown"

        # ✅ Get available stock batches (FIFO order)
        cursor.execute("""
            SELECT id, buying_price, remaining_quantity
            FROM stock_entries
            WHERE item_code = %s AND remaining_quantity > 0
            ORDER BY date_received ASC
        """, (item_code,))
        stock_batches = cursor.fetchall()

        sold = 0  # ✅ Counter to track how many items sold

        for batch in stock_batches:
            if sold >= quantity_to_sell:
                break  # ✅ Stop once desired quantity is sold

            stock_id, buying_price, available_qty = batch
            to_sell = min(quantity_to_sell - sold, available_qty)
            profit = (sale_price - float(buying_price)) * to_sell

            # ✅ Insert individual sale into sales table
            cursor.execute("""
                INSERT INTO sales (item_code, item_name, sale_price, buying_price, profit, quantity, sale_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (item_code, item_name, sale_price, buying_price, profit, to_sell, kenya_time))

            # ✅ Update the remaining quantity in the batch
            cursor.execute("""
                UPDATE stock_entries
                SET remaining_quantity = remaining_quantity - %s
                WHERE id = %s
            """, (to_sell, stock_id))

            sold += to_sell  # ✅ Increment sold counter

        # ✅ Update total stock in products table
        cursor.execute("""
            UPDATE products
            SET in_stock = in_stock - %s
            WHERE item_code = %s
        """, (quantity_to_sell, item_code))

        conn.commit()
        flash(f"{quantity_to_sell} items of {item_name} sold using FIFO", "success")

    except Exception as e:
        # 💥 Rollback if anything fails
        conn.rollback()
        flash("Sale error: " + str(e), "danger")

    finally:
        # ✅ Always return to dashboard
        return redirect(url_for('dashboard'))


@app.route('/get-product/<item_code>')
def get_product(item_code):
    cursor.execute("""
        SELECT item_name, buying_price, selling_price, in_stock
        FROM products
        WHERE item_code = %s
    """, (item_code,))
    product = cursor.fetchone()

    if product:
        item_name, buying_price, selling_price, in_stock = product
        return jsonify({
            'exists': True,
            'item_name': item_name,
            'buying_price': float(buying_price),
            'selling_price': float(selling_price),
            'in_stock': in_stock
        })
    else:
        return jsonify({'exists': False})

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

    user_id = session['user_id']
    cursor = conn.cursor()

    # 👤 Fetch user info
    cursor.execute("SELECT first_name, last_name, email, phone, profile_image FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    user_first_name = user[0] if user else "User"
    user_last_name = user[1] if user else ""

    # --- Total products
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]

    # --- Kenyan Time: Daily, Weekly (from Sunday), Monthly
    tz = pytz.timezone("Africa/Nairobi")
    now = datetime.now(tz)

    midnight_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    weekday = midnight_today.weekday()  # Monday is 0
    start_of_week = midnight_today - timedelta(days=(weekday + 1) % 7)  # Sunday is start of week
    start_of_month = midnight_today.replace(day=1)

    sales_data = {}

    # --- Daily
    cursor.execute("""
        SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(profit), 0)
        FROM sales WHERE sale_date >= %s
    """, (midnight_today,))
    sales_data['daily_sales'], sales_data['daily_profit'] = cursor.fetchone()

    # --- Weekly
    cursor.execute("""
        SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(profit), 0)
        FROM sales WHERE sale_date >= %s
    """, (start_of_week,))
    sales_data['weekly_sales'], sales_data['weekly_profit'] = cursor.fetchone()

    # --- Monthly
    cursor.execute("""
        SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(profit), 0)
        FROM sales WHERE sale_date >= %s
    """, (start_of_month,))
    sales_data['monthly_sales'], sales_data['monthly_profit'] = cursor.fetchone()

    # --- All-time stats
    cursor.execute("SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(profit), 0) FROM sales")
    all_sales, all_profit = cursor.fetchone()

    # --- Latest 5 sales
    cursor.execute("""
        SELECT item_code, item_name, quantity, sale_price, profit, sale_date
        FROM sales ORDER BY sale_date DESC LIMIT 5
    """)
    latest_sales = cursor.fetchall()

    # --- Top 5 selling items
    cursor.execute("""
        SELECT item_name, SUM(quantity) AS total_quantity
        FROM sales GROUP BY item_name ORDER BY total_quantity DESC LIMIT 5
    """)
    top_selling_items = cursor.fetchall()

    # --- Low stock
    cursor.execute("SELECT item_code, item_name, in_stock FROM products WHERE in_stock <= 5")
    low_stock_items = cursor.fetchall()

    # --- Latest uploaded products (based on stock_entries)
    cursor.execute("""
        SELECT 
            p.item_code, 
            p.item_name, 
            p.buying_price, 
            p.selling_price, 
            p.in_stock,
            s.quantity,
            s.date_received
        FROM stock_entries s
        JOIN products p ON s.item_code = p.item_code
        ORDER BY s.date_received DESC
        LIMIT 10
    """)
    latest_products = cursor.fetchall()

    # --- Greeting
    greeting = get_greeting(user_first_name)

    return render_template(
        "dashboard.html", 
        user_first_name=user_first_name,
        user_last_name=user_last_name,
        greeting=greeting,
        user=user,
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


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = conn.cursor()

    if request.method == 'POST':
        # Form values
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form['phone']
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # --- Profile Image Upload ---
        image_file = request.files.get('profile_image')
        image_path = None

        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(f"user_{user_id}_{image_file.filename}")
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(save_path)
            image_path = f"profile_pics/{filename}"

        # --- Update profile info ---
        if image_path:
            cur.execute("""
                UPDATE users SET first_name=%s, last_name=%s, phone=%s, profile_image=%s WHERE id=%s
            """, (first_name, last_name, phone, image_path, user_id))
        else:
            cur.execute("""
                UPDATE users SET first_name=%s, last_name=%s, phone=%s WHERE id=%s
            """, (first_name, last_name, phone, user_id))

        # --- Password Update ---
        if current_password and new_password and confirm_password:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
            user_pass = cur.fetchone()[0]

            if not check_password_hash(user_pass, current_password):
                flash("Current password is incorrect.", "danger")
                return redirect(url_for('profile'))

            if new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                return redirect(url_for('profile'))

            if len(new_password) < 6:
                flash("New password must be at least 6 characters.", "danger")
                return redirect(url_for('profile'))

            new_hash = generate_password_hash(new_password)
            cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, user_id))

        conn.commit()
        flash("Profile updated successfully", "success")
        return redirect(url_for('profile'))

    # --- Get user info ---
    cur.execute("SELECT first_name, last_name, phone, email, profile_image FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    return render_template("profile.html", user=user)

@app.route('/stock-warnings')
def stock_warnings():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = conn.cursor()

    cur.execute("SELECT first_name, last_name FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    user_first_name, user_last_name = user if user else ("User", "")

    cur.execute("SELECT item_code, item_name, in_stock FROM products WHERE in_stock <= 5")
    low_stock_items = cur.fetchall()

    greeting = get_greeting(user_first_name)

    return render_template(
        "stock_warnings.html",
        user_first_name=user_first_name,
        user_last_name=user_last_name,
        greeting=greeting,
        low_stock_items=low_stock_items
    )

@app.route('/stock-level')
def stock_level():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = conn.cursor()

    cur.execute("SELECT first_name, last_name FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    user_first_name, user_last_name = user if user else ("User", "")

    cur.execute("""
        SELECT item_code, item_name, buying_price, selling_price, all_stock, in_stock
        FROM products
        ORDER BY item_code ASC
    """)
    stock_items = cur.fetchall()

    greeting = get_greeting(user_first_name)

    return render_template(
        "stock_level.html",
        user_first_name=user_first_name,
        user_last_name=user_last_name,
        greeting=greeting,
        stock_items=stock_items
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
