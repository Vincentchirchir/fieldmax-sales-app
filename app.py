from flask import Flask, request, jsonify, render_template
import psycopg2

app = Flask(__name__)

# ✅ PostgreSQL connection settings
conn = psycopg2.connect(
    dbname="Fieldmax_db",
    user="postgres",           # Replace with your actual PostgreSQL username
    password="2952",  # Replace with your real password
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

# ✅ Route to show the HTML form
@app.route('/')
def home():
    return render_template('index.html')

# ✅ Route to receive submitted sale data and insert into DB
@app.route('/submit-sale', methods=['POST'])
def submit_sale():
    data = request.get_json()

    cursor.execute("""
        INSERT INTO sales_log (item_code, item_name, buying_price, selling_price, profit)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        data['code'],
        data['name'],
        data['buying'],
        data['sale'],
        data['profit']
    ))

    conn.commit()
    return jsonify({'message': '✅ Sale recorded successfully!'})

# ✅ Start the Flask app
if __name__ == '__main__':
    app.run(debug=True)