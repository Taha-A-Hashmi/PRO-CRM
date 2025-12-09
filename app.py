from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pandas as pd
import io

app = Flask(__name__)

# --- CONFIGURATION ---
mongo_uri = os.environ.get("MONGO_URI", "mongodb+srv://taha_admin:hospital123@cluster0.ukoxtzf.mongodb.net/hospital_crm_db?retryWrites=true&w=majority&appName=Cluster0&authSource=admin")
app.config["MONGO_URI"] = mongo_uri
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "a_very_secret_key_for_hms_pro")

try:
    mongo = PyMongo(app)
except Exception as e:
    print(f"Error initializing MongoDB: {e}")
    mongo = None

# --- HELPER: DATABASE CHECK & INITIAL SETUP ---
def check_db():
    if mongo is None or mongo.db is None:
        print("Database connection failed or not initialized.")
        return False
    return True

def ensure_initial_admin():
    """Checks for and creates the default admin user 'ImranSaab' on first run."""
    if check_db():
        if mongo.db.users.count_documents({}) == 0:
            # Create ImranSaab as the Admin
            admin_user = {
                'username': 'ImranSaab',
                'password': generate_password_hash('password123'),
                'role': 'Admin',
                'name': 'Imran Khan (Admin)',
                'created_at': datetime.now()
            }
            mongo.db.users.insert_one(admin_user)
            print("Initial Admin user 'ImranSaab' created.")

# Run initial setup outside of request context
with app.app_context():
    ensure_initial_admin()


# --- AUTHENTICATION ROUTES ---

def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def role_required(roles):
    def decorator(f):
        @login_required
        def wrapper(*args, **kwargs):
            user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})
            if user and user.get('role') in roles:
                return f(*args, **kwargs)
            return jsonify({"error": "Access Denied"}), 403
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

@app.route('/')
def index():
    # Frontend handles redirection to login if session is missing.
    return render_template('index.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = request.json
    user = mongo.db.users.find_one({"username": data['username']})
    
    if user and check_password_hash(user['password'], data['password']):
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({
            "message": "Login successful",
            "username": user['username'],
            "role": user['role'],
            "name": user.get('name', user['username'])
        })
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None)
    return jsonify({"message": "Logged out"})

@app.route('/api/auth/session', methods=['GET'])
def check_session():
    if 'user_id' in session:
        return jsonify({
            "is_logged_in": True,
            "username": session.get('username'),
            "role": session.get('role'),
        })
    return jsonify({"is_logged_in": False})

# --- USER MANAGEMENT (ADMIN ONLY) ---
@app.route('/api/users', methods=['GET'])
@role_required(['Admin'])
def get_users():
    if not check_db(): return jsonify([])
    users_cursor = mongo.db.users.find({}, {'password': 0})
    users = [{**u, '_id': str(u['_id'])} for u in users_cursor]
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@role_required(['Admin'])
def create_user():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = request.json
    if not all(k in data for k in ['username', 'password', 'role', 'name']):
        return jsonify({"error": "Missing fields"}), 400
    
    if mongo.db.users.find_one({"username": data['username']}):
        return jsonify({"error": "Username already exists"}), 409

    data['password'] = generate_password_hash(data['password'])
    data['created_at'] = datetime.now()
    try:
        result = mongo.db.users.insert_one(data)
        return jsonify({"message": "User created", "id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<id>', methods=['DELETE'])
@role_required(['Admin'])
def delete_user(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # Prevent deleting the logged-in user or the primary admin by ID if necessary
        mongo.db.users.delete_one({'_id': ObjectId(id)})
        return jsonify({"message": "User deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/change_password', methods=['POST'])
@login_required
def change_password():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = request.json
    user_id = session['user_id']
    
    try:
        # User is changing their own password
        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if not user or not check_password_hash(user['password'], data['old_password']):
            return jsonify({"error": "Invalid old password"}), 401
        
        new_password_hash = generate_password_hash(data['new_password'])
        mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'password': new_password_hash}})
        return jsonify({"message": "Password updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- DASHBOARD METRICS ---
@app.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard_metrics():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    today = datetime.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    try:
        # 1. Total Patients
        total_patients = mongo.db.patients.count_documents({})

        # 2. Admissions This Month
        admissions_this_month = mongo.db.patients.count_documents({
            'created_at': {'$gte': start_of_month}
        })
        
        # 3. Total Income This Month (Mock: sum of Monthly Fees from active patients)
        # Assuming monthly fee is stored as 'monthlyFee' on patient record (string, e.g., "10000")
        active_patients = mongo.db.patients.find()
        total_income_this_month = 0
        for p in active_patients:
            try:
                fee = int(p.get('monthlyFee', '0').replace(',', ''))
                total_income_this_month += fee
            except ValueError:
                pass # Ignore invalid fees
        
        # 4. Total Canteen Sales This Month
        pipeline = [
            {'$match': {'date': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total_sales': {'$sum': '$amount'}}}
        ]
        canteen_sales_result = list(mongo.db.canteen_sales.aggregate(pipeline))
        total_canteen_sales_this_month = canteen_sales_result[0]['total_sales'] if canteen_sales_result else 0
        
        return jsonify({
            'totalPatients': total_patients,
            'admissionsThisMonth': admissions_this_month,
            'totalIncomeThisMonth': total_income_this_month,
            'totalCanteenSalesThisMonth': total_canteen_sales_this_month
        })
    except Exception as e:
        print(f"DB Metric Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- PATIENT API UPDATES ---

@app.route('/api/patients', methods=['GET'])
@login_required
def get_patients():
    if not check_db(): return jsonify([])
    try:
        patients_cursor = mongo.db.patients.find()
        patients = []
        for p in patients_cursor:
            p['_id'] = str(p['_id'])
            # Ensure monthlyFee is present for canteen view logic
            p['monthlyFee'] = p.get('monthlyFee', '0')
            patients.append(p)
        return jsonify(patients)
    except Exception as e:
        print(f"DB Fetch Error: {e}")
        return jsonify([])

@app.route('/api/patients', methods=['POST'])
@role_required(['Admin', 'Doctor']) # Only Admin/Doctor can admit
def add_patient():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        data = request.json
        data['created_at'] = datetime.now()
        data['notes'] = [] # General Notes (Legacy)
        data['monthlyFee'] = data.get('monthlyFee', '0')
        data['monthlyAllowance'] = data.get('monthlyAllowance', '3000') # Default allowance
        result = mongo.db.patients.insert_one(data)
        return jsonify({"message": "Success", "id": str(result.inserted_id)}), 201
    except Exception as e:
        print(f"DB Insert Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/patients/<id>', methods=['PUT'])
@role_required(['Admin', 'Doctor'])
def update_patient(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        data = request.json
        if '_id' in data: del data['_id']
        mongo.db.patients.update_one({'_id': ObjectId(id)}, {'$set': data})
        return jsonify({"message": "Updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/patients/<id>', methods=['DELETE'])
@role_required(['Admin'])
def delete_patient(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # Delete the patient
        result = mongo.db.patients.delete_one({'_id': ObjectId(id)})
        if result.deleted_count > 0:
            # Also delete associated records (session notes and medical records)
            mongo.db.patient_records.delete_many({'patient_id': id})
            return jsonify({"message": "Patient deleted successfully"}), 200
        else:
            return jsonify({"error": "Patient not found"}), 404
    except Exception as e:
        print(f"Delete Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- NEW PATIENT RECORD APIS (SESSION NOTES & MEDICAL RECORDS) ---

@app.route('/api/patients/<patient_id>/session_note', methods=['POST'])
@role_required(['Admin', 'Psychologist'])
def add_session_note(patient_id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        data = request.json
        note = {
            'text': data['text'],
            'type': 'session_note',
            'date': datetime.now(),
            'recorded_by': session.get('username', 'System'),
            'patient_id': ObjectId(patient_id)
        }
        result = mongo.db.patient_records.insert_one(note)
        return jsonify({"message": "Session note added", "id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/patients/<patient_id>/medical_record', methods=['POST'])
@role_required(['Admin', 'Doctor'])
def add_medical_record(patient_id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        data = request.json
        record = {
            'title': data['title'],
            'details': data['details'],
            'type': 'medical_record',
            'date': datetime.now(),
            'recorded_by': session.get('username', 'System'),
            'patient_id': ObjectId(patient_id)
        }
        result = mongo.db.patient_records.insert_one(record)
        return jsonify({"message": "Medical record added", "id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route('/api/patients/<patient_id>/records', methods=['GET'])
@login_required
def get_patient_records(patient_id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        records_cursor = mongo.db.patient_records.find({'patient_id': ObjectId(patient_id)}).sort('date', -1)
        records = []
        for r in records_cursor:
            r['_id'] = str(r['_id'])
            r['patient_id'] = str(r['patient_id'])
            r['date'] = r['date'].isoformat()
            records.append(r)
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- CANTEEN APIS ---

@app.route('/api/canteen/sales', methods=['POST'])
@role_required(['Admin', 'Canteen'])
def record_canteen_sale():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = request.json
    if not all(k in data for k in ['patient_id', 'amount', 'item']):
        return jsonify({"error": "Missing fields"}), 400
    
    try:
        # Convert amount to integer
        data['amount'] = int(data['amount'])
        
        sale = {
            'patient_id': ObjectId(data['patient_id']),
            'item': data['item'],
            'amount': data['amount'],
            'date': datetime.now(),
            'recorded_by': session.get('username', 'Canteen Staff')
        }
        result = mongo.db.canteen_sales.insert_one(sale)
        return jsonify({"message": "Sale recorded", "id": str(result.inserted_id)}), 201
    except ValueError:
        return jsonify({"error": "Amount must be a number"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/canteen/sales/breakdown', methods=['GET'])
@role_required(['Admin', 'Canteen'])
def get_canteen_breakdown():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    today = datetime.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    try:
        # 1. Fetch all patients with ID, Name, and Allowance
        patients_cursor = mongo.db.patients.find({}, {'name': 1, 'monthlyAllowance': 1})
        patients_map = {str(p['_id']): {'name': p['name'], 'allowance': p.get('monthlyAllowance', '0'), 'sales': 0} for p in patients_cursor}
        
        # 2. Calculate monthly sales per patient
        pipeline = [
            {'$match': {'date': {'$gte': start_of_month}}},
            {'$group': {'_id': '$patient_id', 'total_sales': {'$sum': '$amount'}}}
        ]
        sales_breakdown = list(mongo.db.canteen_sales.aggregate(pipeline))
        
        # 3. Merge data
        for sale in sales_breakdown:
            p_id = str(sale['_id'])
            if p_id in patients_map:
                patients_map[p_id]['sales'] = sale['total_sales']
        
        # Format output
        breakdown_list = []
        for p_id, data in patients_map.items():
            try:
                sales = data['sales']
                allowance = int(data['allowance'].replace(',', ''))
                balance = allowance - sales
            except ValueError:
                sales = data['sales']
                allowance = 0
                balance = -sales
                
            breakdown_list.append({
                'id': p_id,
                'name': data['name'],
                'monthlyAllowance': data['allowance'],
                'monthlySales': sales,
                'remainingBalance': balance
            })
            
        return jsonify(breakdown_list)
    except Exception as e:
        print(f"Canteen Breakdown Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- EXPORT ROUTE (No change, retained for functionality) ---

@app.route('/api/export', methods=['POST'])
@role_required(['Admin'])
def export_patients():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        req_data = request.get_json() or {}
        selected_fields = req_data.get('fields', 'all')
        
        cursor = mongo.db.patients.find()
        patients_list = list(cursor)
        
        if not patients_list:
            return jsonify({"error": "No patients found"}), 404

        # Prepare Data (Ensure new fields are included)
        export_data = []
        for p in patients_list:
            row = {
                'name': p.get('name', ''),
                'fatherName': p.get('fatherName', ''),
                'admissionDate': p.get('admissionDate', ''),
                'idNo': p.get('idNo', ''),
                'age': p.get('age', ''),
                'cnic': p.get('cnic', ''),
                'contactNo': p.get('contactNo', ''),
                'address': p.get('address', ''),
                'complaint': p.get('complaint', ''),
                'guardianName': p.get('guardianName', ''),
                'relation': p.get('relation', ''),
                'drugProblem': p.get('drugProblem', ''),
                'maritalStatus': p.get('maritalStatus', ''),
                'prevAdmissions': p.get('prevAdmissions', ''),
                'monthlyFee': p.get('monthlyFee', ''),
                'monthlyAllowance': p.get('monthlyAllowance', ''),
                'created_at': p.get('created_at', '')
            }
            export_data.append(row)

        df = pd.DataFrame(export_data)

        if isinstance(selected_fields, list) and len(selected_fields) > 0:
            valid_fields = [f for f in selected_fields if f in df.columns]
            if valid_fields:
                df = df[valid_fields]

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Patients')
        
        output.seek(0)
        
        return send_file(
            output, 
            download_name="patients_export.xlsx", 
            as_attachment=True, 
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except ImportError:
        return jsonify({"error": "Missing 'openpyxl' library"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- NEW ACCOUNTS ROUTE (ADMIN ONLY) ---

@app.route('/api/accounts/summary', methods=['GET'])
@role_required(['Admin'])
def get_accounts_summary():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # Get all patients
        patients = list(mongo.db.patients.find({}, {
            'name': 1, 'fatherName': 1, 'admissionDate': 1, 
            'monthlyFee': 1, 'address': 1, 'age': 1
        }))
        
        # Get total canteen sales per patient
        pipeline = [
            {'$group': {'_id': '$patient_id', 'total_sales': {'$sum': '$amount'}}}
        ]
        sales_data = list(mongo.db.canteen_sales.aggregate(pipeline))
        sales_map = {str(s['_id']): s['total_sales'] for s in sales_data}

        summary = []
        for p in patients:
            pid = str(p['_id'])
            summary.append({
                'id': pid,
                'name': p.get('name', ''),
                'fatherName': p.get('fatherName', ''),
                'age': p.get('age', ''),
                'area': p.get('address', ''), # Using address as "Area"
                'admissionDate': p.get('admissionDate', ''),
                'monthlyFee': p.get('monthlyFee', '0'),
                'canteenTotal': sales_map.get(pid, 0)
            })
        
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)