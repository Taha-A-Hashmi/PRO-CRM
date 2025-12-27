from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pandas as pd
import io
from dotenv import load_dotenv  # 1. Add this import

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

def clean_input_data(data):
    """Strip trailing and leading spaces from string values in a dictionary."""
    if not isinstance(data, dict):
        return data
    
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned[key] = value.strip()
        elif isinstance(value, dict):
            cleaned[key] = clean_input_data(value)
        elif isinstance(value, list):
            cleaned[key] = [clean_input_data(item) if isinstance(item, dict) else item.strip() if isinstance(item, str) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned

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
    data = clean_input_data(request.json)
    user = mongo.db.users.find_one({"username": data['username']})
    
    if user and check_password_hash(user['password'], data['password']):
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({
            "message": "Login successful",
            "username": user['username'],
            "role": user['role'],
            "name": user.get('name', user['username']),
            "user_id": str(user['_id'])
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
            "user_id": session.get('user_id')
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
    data = clean_input_data(request.json)
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

# @app.route('/api/patients/<id>', methods=['DELETE'])
# @role_required(['Admin'])
# def delete_patient(id):
#     if not check_db(): return jsonify({"error": "Database error"}), 500
#     try:
#         mongo.db.patients.delete_one({'_id': ObjectId(id)})
#         return jsonify({"message": "Patient deleted"})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


@app.route('/api/users/change_password', methods=['POST'])
@login_required
def change_password():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = clean_input_data(request.json)
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
    
    if today.month == 12:
        end_of_month = today.replace(year=today.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        end_of_month = today.replace(month=today.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    try:
        # 1. Basic Counts
        total_patients = mongo.db.patients.count_documents({})
        admissions_this_month = mongo.db.patients.count_documents({
            'created_at': {'$gte': start_of_month, '$lt': end_of_month}
        })
        discharges_this_month = mongo.db.patients.count_documents({
            'isDischarged': True,
            'dischargeDate': {'$gte': start_of_month.isoformat(), '$lt': end_of_month.isoformat()}
        })
        
        # 2. Total Expected Incoming (Remaining Balance Calculation)
        # Fetch ALL canteen sales first to create a map
        # Note: We group by patient_id. We convert ObjectId to string for easy matching.
        all_canteen_sales = list(mongo.db.canteen_sales.find())
        canteen_map = {}
        
        for sale in all_canteen_sales:
            # Handle patient_id whether it's ObjectId or String
            pid = str(sale.get('patient_id', ''))
            amount = int(sale.get('amount', 0))
            if pid:
                canteen_map[pid] = canteen_map.get(pid, 0) + amount

        # Fetch Active Patients
        active_patients = list(mongo.db.patients.find({'isDischarged': {'$ne': True}}))
        
        total_income_this_month = 0
        
        print("\n--- DEBUGGING OVERHEAD CALCULATION ---")
        for p in active_patients:
            try:
                pid = str(p['_id'])
                name = p.get('name', 'Unknown')
                
                # Helper to safely parse currency strings like "15,000" or ints like 15000
                def safe_int(val):
                    if val is None: return 0
                    return int(str(val).replace(',', '').strip() or 0)

                fee = safe_int(p.get('monthlyFee'))
                laundry = safe_int(p.get('laundryAmount'))
                received = safe_int(p.get('receivedAmount'))
                canteen = canteen_map.get(pid, 0)
                
                total_bill = fee + laundry + canteen
                balance = total_bill - received
                
                # Only count positive balances (money they owe us)
                if balance > 0:
                    total_income_this_month += balance
                    print(f"Patient: {name} | Fee: {fee} + Lnd: {laundry} + Cant: {canteen} - Rec: {received} = Bal: {balance}")
                else:
                    print(f"Patient: {name} | Balance is 0 or negative ({balance}) - Ignoring")

            except Exception as e:
                print(f"Error calculating for {p.get('name')}: {e}")
        
        print(f"TOTAL EXPECTED INCOMING: {total_income_this_month}")
        print("--------------------------------------\n")

        # 3. Canteen Sales This Month (KPI Card)
        pipeline_month = [
            {'$match': {'date': {'$gte': start_of_month, '$lt': end_of_month}}},
            {'$group': {'_id': None, 'total_sales': {'$sum': '$amount'}}}
        ]
        canteen_month_res = list(mongo.db.canteen_sales.aggregate(pipeline_month))
        total_canteen_sales_this_month = canteen_month_res[0]['total_sales'] if canteen_month_res else 0
        
        return jsonify({
            'totalPatients': total_patients,
            'admissionsThisMonth': admissions_this_month,
            'dischargesThisMonth': discharges_this_month,
            'totalIncomeThisMonth': total_income_this_month,
            'totalCanteenSalesThisMonth': total_canteen_sales_this_month
        })
    except Exception as e:
        print(f"DB Metric Error: {e}")
        return jsonify({"error": str(e)}), 500


# DEBUG endpoint to inspect database
@app.route('/api/debug/dashboard', methods=['GET'])
@login_required
def debug_dashboard():
    """Debug endpoint to show raw data used in dashboard calculations"""
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    today = datetime.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    try:
        # Get all patients with fees
        patients = list(mongo.db.patients.find())
        patient_data = []
        for p in patients:
            try:
                fee = int(p.get('monthlyFee', '0').replace(',', ''))
                patient_data.append({
                    'name': p.get('name'),
                    'monthlyFee_raw': p.get('monthlyFee'),
                    'monthlyFee_parsed': fee
                })
            except ValueError:
                patient_data.append({
                    'name': p.get('name'),
                    'monthlyFee_raw': p.get('monthlyFee'),
                    'monthlyFee_parsed': 'ERROR'
                })
        
        # Get canteen sales this month
        canteen_pipeline = [
            {'$match': {'date': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
        ]
        canteen_data = list(mongo.db.canteen_sales.aggregate(canteen_pipeline))
        
        # Get all canteen sales for context
        all_canteen = list(mongo.db.canteen_sales.find().sort('date', -1).limit(5))
        canteen_sample = [{
            'date': str(c.get('date')),
            'amount': c.get('amount'),
            'item': c.get('item')
        } for c in all_canteen]
        
        return jsonify({
            'currentMonth': f"{today.year}-{today.month:02d}",
            'startOfMonth': str(start_of_month),
            'totalPatients': len(patients),
            'patientsWithFees': patient_data,
            'canteenThisMonth': canteen_data,
            'canteenSample': canteen_sample
        })
    except Exception as e:
        print(f"Debug error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/dashboard/admissions', methods=['GET'])
@login_required
def get_month_admissions():
    """Return detailed admissions for the current month."""
    if not check_db():
        return jsonify({"error": "Database error"}), 500

    today = datetime.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        cursor = mongo.db.patients.find({'created_at': {'$gte': start_of_month}})
        admissions = []
        for p in cursor:
            admissions.append({
                'id': str(p.get('_id')),
                'name': p.get('name', ''),
                'admissionDate': p.get('admissionDate', ''),
                'created_at': p.get('created_at').isoformat() if p.get('created_at') else ''
            })
        return jsonify(admissions)
    except Exception as e:
        print(f"Admissions list error: {e}")
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
            p['photo1'] = p.get('photo1', '')
            p['photo2'] = p.get('photo2', '')
            p['photo3'] = p.get('photo3', '')
            p['isDischarged'] = p.get('isDischarged', False)
            p['dischargeDate'] = p.get('dischargeDate')
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
        data = clean_input_data(request.json)
        data['created_at'] = datetime.now()
        data['notes'] = [] # General Notes (Legacy)
        data['monthlyFee'] = data.get('monthlyFee', '0')
        data['monthlyAllowance'] = data.get('monthlyAllowance', '3000') # Default allowance
        data['receivedAmount'] = data.get('receivedAmount', '0')  # New field
        data['drug'] = data.get('drug', '')  # New field
        data['photo1'] = data.get('photo1', '')
        data['photo2'] = data.get('photo2', '')
        data['photo3'] = data.get('photo3', '')
        data['isDischarged'] = data.get('isDischarged', False)
        data['dischargeDate'] = data.get('dischargeDate')
        
        # Laundry fields
        data['laundryStatus'] = data.get('laundryStatus', False)  # Boolean: whether laundry service is enabled
        if data['laundryStatus']:
            data['laundryAmount'] = int(data.get('laundryAmount', 3500))  # Default 3500 if enabled
        else:
            data['laundryAmount'] = 0  # 0 if not enabled
        
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
        data = clean_input_data(request.json)
        if '_id' in data: del data['_id']
        
        # Only Admin can modify sensitive/financial fields
        current_role = session.get('role')
        if current_role != 'Admin':
            # Remove sensitive fields for non-admin users
            sensitive_fields = ['monthlyFee', 'monthlyAllowance', 'laundryStatus', 
                              'laundryAmount', 'cnic', 'contactNo', 'guardianName', 
                              'relation', 'address']
            for field in sensitive_fields:
                if field in data:
                    del data[field]
        
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
        data = clean_input_data(request.json)
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
        data = clean_input_data(request.json)
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
    data = clean_input_data(request.json)
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
        # 1. Fetch all patients with ID, Name, Allowance AND isDischarged
        patients_cursor = mongo.db.patients.find({}, {
            'name': 1, 'monthlyAllowance': 1, 'isDischarged': 1
        })
        
        patients_map = {
            str(p['_id']): {
                'name': p['name'], 
                'allowance': p.get('monthlyAllowance', '0'), 
                'sales': 0,
                'isDischarged': p.get('isDischarged', False) # <--- NEW
            } 
            for p in patients_cursor
        }
        
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
                'remainingBalance': balance,
                'isDischarged': data['isDischarged'] # <--- NEW
            })
            
        return jsonify(breakdown_list)
    except Exception as e:
        print(f"Canteen Breakdown Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- EXPENSES APIs ---

@app.route('/api/expenses', methods=['GET'])
@login_required
def list_expenses():
    if not check_db():
        return jsonify({"error": "Database error"}), 500
    try:
        cursor = mongo.db.expenses.find().sort('date', -1)
        expenses = []
        for e in cursor:
            expenses.append({
                'id': str(e.get('_id')),
                'type': e.get('type', 'outgoing'),
                'amount': e.get('amount', 0),
                'category': e.get('category', ''),
                'note': e.get('note', ''),
                'date': e.get('date').isoformat() if e.get('date') else '',
                'recorded_by': e.get('recorded_by', ''),
                'auto': False
            })

        # Automated income entries (not stored, just surfaced)
        try:
            # Monthly fees sum (all patients)
            patients = mongo.db.patients.find()
            total_fees = 0
            for p in patients:
                try:
                    total_fees += int(str(p.get('monthlyFee', '0')).replace(',', ''))
                except ValueError:
                    pass

            # Canteen sales sum (all time or could be month? align with summary -> month)
            today = datetime.now()
            start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            pipeline = [
                {'$match': {'date': {'$gte': start_of_month}}},
                {'$group': {'_id': None, 'total_sales': {'$sum': '$amount'}}}
            ]
            sales_result = list(mongo.db.canteen_sales.aggregate(pipeline))
            total_canteen = sales_result[0]['total_sales'] if sales_result else 0

            today_iso = datetime.now().date().isoformat()
            expenses.insert(0, {
                'id': 'auto-canteen',
                'type': 'incoming',
                'amount': total_canteen,
                'category': 'Canteen Sales (auto)',
                'note': 'Automatically calculated from canteen sales this month',
                'date': today_iso,
                'recorded_by': 'system',
                'auto': True
            })
            expenses.insert(0, {
                'id': 'auto-fees',
                'type': 'incoming',
                'amount': total_fees,
                'category': 'Monthly Fees (auto)',
                'note': 'Automatically calculated from patient monthly fees',
                'date': today_iso,
                'recorded_by': 'system',
                'auto': True
            })
        except Exception as e:
            print(f"Auto income calc error: {e}")

        return jsonify(expenses)
    except Exception as e:
        print(f"Expenses list error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/expenses', methods=['POST'])
@role_required(['Admin'])
def add_expense():
    if not check_db():
        return jsonify({"error": "Database error"}), 500
    data = clean_input_data(request.json or {})
    required = ['type', 'amount', 'category']
    if not all(k in data for k in required):
        return jsonify({"error": "Missing fields"}), 400
    try:
        amount = int(str(data.get('amount', 0)).replace(',', ''))
    except ValueError:
        return jsonify({"error": "Amount must be a number"}), 400

    expense = {
        'type': data.get('type', 'outgoing'),
        'amount': amount,
        'category': data.get('category', ''),
        'note': data.get('note', ''),
        'date': datetime.fromisoformat(data.get('date')) if data.get('date') else datetime.now(),
        'recorded_by': session.get('username', 'System'),
        'created_at': datetime.now()
    }
    try:
        result = mongo.db.expenses.insert_one(expense)
        return jsonify({"message": "Expense saved", "id": str(result.inserted_id)}), 201
    except Exception as e:
        print(f"Add expense error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/expenses/<id>', methods=['DELETE'])
@role_required(['Admin'])
def delete_expense(id):
    if not check_db():
        return jsonify({"error": "Database error"}), 500
    try:
        result = mongo.db.expenses.delete_one({'_id': ObjectId(id)})
        if result.deleted_count:
            return jsonify({"message": "Expense deleted"})
        return jsonify({"error": "Expense not found"}), 404
    except Exception as e:
        print(f"Delete expense error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/expenses/summary', methods=['GET'])
@login_required
def expenses_summary():
    if not check_db():
        return jsonify({"error": "Database error"}), 500

    today = datetime.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    try:
        pipeline = [
            {'$match': {'date': {'$gte': start_of_month}}},
            {'$group': {'_id': '$type', 'total': {'$sum': '$amount'}}}
        ]
        summary_data = list(mongo.db.expenses.aggregate(pipeline))
        incoming = 0
        outgoing = 0
        for item in summary_data:
            if item['_id'] == 'incoming':
                incoming = item['total']
            elif item['_id'] == 'outgoing':
                outgoing = item['total']

        # Add automated incoming: monthly fees + canteen sales (month)
        # Monthly fees
        patients = mongo.db.patients.find()
        auto_fees = 0
        for p in patients:
            try:
                auto_fees += int(str(p.get('monthlyFee', '0')).replace(',', ''))
            except ValueError:
                pass
        # Canteen sales this month
        pipeline_sales = [
            {'$match': {'date': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total_sales': {'$sum': '$amount'}}}
        ]
        sales_result = list(mongo.db.canteen_sales.aggregate(pipeline_sales))
        auto_canteen = sales_result[0]['total_sales'] if sales_result else 0

        incoming += auto_fees + auto_canteen

        return jsonify({
            'incoming': incoming,
            'outgoing': outgoing,
            'net': incoming - outgoing,
            'autoFees': auto_fees,
            'autoCanteen': auto_canteen
        })
    except Exception as e:
        print(f"Expenses summary error: {e}")
        return jsonify({"error": str(e)}), 500

# --- EXPORT ROUTE (No change, retained for functionality) ---

@app.route('/api/export', methods=['POST'])
@role_required(['Admin', 'Doctor', 'Psychologist'])
def export_patients():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        req_data = request.get_json() or {}
        selected_fields = req_data.get('fields', 'all')
        current_user = session.get('user') or {}
        is_admin = current_user.get('role') == 'Admin'
        print(f"Export request from user: {current_user.get('username')}, is_admin: {is_admin}")
        
        cursor = mongo.db.patients.find()
        patients_list = list(cursor)
        print(f"Found {len(patients_list)} patients")
        
        if not patients_list:
            return jsonify({"error": "No patients found"}), 404

        # Prepare Data (Ensure new fields are included)
        export_data = []
        for p in patients_list:
            # Convert ObjectId to string
            patient_id = str(p.get('_id', '')) if '_id' in p else ''
            
            row = {
                'name': p.get('name', ''),
                'fatherName': p.get('fatherName', ''),
                'admissionDate': p.get('admissionDate', ''),
                'idNo': p.get('idNo', '') if is_admin else '',
                'age': p.get('age', ''),
                'cnic': p.get('cnic', '') if is_admin else '',
                'contactNo': p.get('contactNo', '') if is_admin else '',
                'address': p.get('address', '') if is_admin else '',
                'complaint': p.get('complaint', ''),
                'guardianName': p.get('guardianName', '') if is_admin else '',
                'relation': p.get('relation', '') if is_admin else '',
                'drugProblem': p.get('drugProblem', ''),
                'maritalStatus': p.get('maritalStatus', ''),
                'prevAdmissions': p.get('prevAdmissions', ''),
                'monthlyFee': p.get('monthlyFee', '') if is_admin else '',
                'monthlyAllowance': p.get('monthlyAllowance', '') if is_admin else '',
                'created_at': p.get('created_at', '')
            }
            export_data.append(row)

        print(f"Prepared {len(export_data)} rows for export")
        df = pd.DataFrame(export_data)
        print(f"Created DataFrame with columns: {list(df.columns)}")

        if isinstance(selected_fields, list) and len(selected_fields) > 0:
            valid_fields = [f for f in selected_fields if f in df.columns]
            if valid_fields:
                df = df[valid_fields]

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Patients')
        
        output.seek(0)
        print("Excel file created successfully")
        
        return send_file(
            output, 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='patients_export.xlsx'
        )
    except ImportError as ie:
        print(f"ImportError in export: {ie}")
        return jsonify({"error": "Missing 'openpyxl' library"}), 500
    except Exception as e:
        print(f"Error in export: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 500


# --- NEW ACCOUNTS ROUTE (ADMIN ONLY) ---

@app.route('/api/accounts/summary', methods=['GET'])
@role_required(['Admin'])
def get_accounts_summary():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # Get all patients - Added 'isDischarged' to projection
        patients = list(mongo.db.patients.find({}, {
            'name': 1, 'fatherName': 1, 'admissionDate': 1, 
            'monthlyFee': 1, 'address': 1, 'age': 1,
            'laundryStatus': 1, 'laundryAmount': 1, 'receivedAmount': 1,
            'isDischarged': 1
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
                'area': p.get('address', ''), 
                'admissionDate': p.get('admissionDate', ''),
                'monthlyFee': p.get('monthlyFee', '0'),
                'canteenTotal': sales_map.get(pid, 0),
                'laundryStatus': p.get('laundryStatus', False),
                'laundryAmount': p.get('laundryAmount', 0),
                'receivedAmount': p.get('receivedAmount', '0'),
                'isDischarged': p.get('isDischarged', False) # <--- NEW: Return discharge status
            })
        
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- CALL & MEETING TRACKING APIs ---

@app.route('/api/call_meeting_tracker', methods=['GET'])
@login_required
def get_call_meeting_data():
    """Get all call and meeting data for the month"""
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    try:
        today = datetime.now()
        year = today.year
        month = today.month
        
        # Fetch all records for the current month
        records_cursor = mongo.db.call_meeting_tracker.find({
            'year': year,
            'month': month
        }).sort('day', 1)
        
        records = []
        for r in records_cursor:
            r['_id'] = str(r['_id'])
            records.append(r)
        
        return jsonify(records)
    except Exception as e:
        print(f"Call/Meeting Fetch Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/call_meeting_tracker', methods=['POST'])
@role_required(['Admin'])
def add_call_meeting_entry():
    """Add or update a call/meeting entry"""
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    data = clean_input_data(request.json)
    if not all(k in data for k in ['name', 'day', 'month', 'year', 'type', 'date_of_admission']):
        return jsonify({"error": "Missing fields"}), 400
    
    try:
        entry = {
            'name': data['name'],
            'day': int(data['day']),
            'month': int(data['month']),
            'year': int(data['year']),
            'type': data['type'],  # 'Call', 'Meeting', or 'Text'
            'date_of_admission': data['date_of_admission'],
            'recorded_by': session.get('username', 'Admin'),
            'created_at': datetime.now()
        }
        
        # Check if entry already exists for this person on this day/month/year
        existing = mongo.db.call_meeting_tracker.find_one({
            'name': data['name'],
            'day': int(data['day']),
            'month': int(data['month']),
            'year': int(data['year'])
        })
        
        if existing:
            # Update existing entry
            mongo.db.call_meeting_tracker.update_one({'_id': existing['_id']}, {'$set': entry})
            return jsonify({"message": "Entry updated", "id": str(existing['_id'])}), 200
        else:
            # Create new entry
            result = mongo.db.call_meeting_tracker.insert_one(entry)
            return jsonify({"message": "Entry added", "id": str(result.inserted_id)}), 201
    except Exception as e:
        print(f"Call/Meeting Add Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/call_meeting_tracker/<id>', methods=['DELETE'])
@role_required(['Admin'])
def delete_call_meeting_entry(id):
    """Delete a call/meeting entry"""
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    try:
        result = mongo.db.call_meeting_tracker.delete_one({'_id': ObjectId(id)})
        if result.deleted_count > 0:
            return jsonify({"message": "Entry deleted"}), 200
        else:
            return jsonify({"error": "Entry not found"}), 404
    except Exception as e:
        print(f"Call/Meeting Delete Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/call_meeting_tracker/summary/<int:month>/<int:year>', methods=['GET'])
@login_required
def get_call_meeting_summary(month, year):
    """Get summary of calls and meetings for the month"""
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    try:
        # Get all records for the month
        records_cursor = mongo.db.call_meeting_tracker.find({
            'year': year,
            'month': month
        })
        
        # Count by type and by person
        call_count = 0
        meeting_count = 0
        text_count = 0
        by_person = {}
        
        for r in records_cursor:
            record_type = r.get('type', 'Unknown')
            if record_type == 'Call':
                call_count += 1
            elif record_type == 'Meeting':
                meeting_count += 1
            elif record_type == 'Text':
                text_count += 1
            
            person = r.get('name', 'Unknown')
            if person not in by_person:
                by_person[person] = {'Call': 0, 'Meeting': 0, 'Text': 0}
            by_person[person][record_type] = by_person[person].get(record_type, 0) + 1
        
        return jsonify({
            'totalCalls': call_count,
            'totalMeetings': meeting_count,
            'totalTexts': text_count,
            'byPerson': by_person
        })
    except Exception as e:
        print(f"Call/Meeting Summary Error: {e}")
        return jsonify({"error": str(e)}), 500


# --- UTILITY BILLS ROUTES ---

@app.route('/api/utility_bills', methods=['GET'])
@role_required(['Admin'])
def get_utility_bills():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # Fetch all bills sorted by due date (soonest first)
        cursor = mongo.db.utility_bills.find().sort('due_date', 1)
        bills = []
        for b in cursor:
            bills.append({
                'id': str(b['_id']),
                'type': b.get('type', 'Other'),
                'provider': b.get('provider', ''),
                'amount': b.get('amount', 0),
                'due_date': b.get('due_date'),
                'ref_no': b.get('ref_no', ''),
                'status': 'Unpaid'
            })
        return jsonify(bills)
    except Exception as e:
        print(f"Bills Fetch Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/utility_bills', methods=['POST'])
@role_required(['Admin'])
def add_utility_bill():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = clean_input_data(request.json)
    try:
        bill = {
            'type': data.get('type', 'Other'), # Electricity, Gas, etc.
            'provider': data.get('provider', ''),
            'amount': int(data.get('amount', 0)),
            'due_date': data.get('due_date'),
            'ref_no': data.get('ref_no', ''),
            'created_at': datetime.now()
        }
        result = mongo.db.utility_bills.insert_one(bill)
        return jsonify({"message": "Bill added", "id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/utility_bills/<id>', methods=['DELETE'])
@role_required(['Admin'])
def pay_utility_bill(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # OPTIONAL: When deleting/paying, record it as an expense automatically
        bill = mongo.db.utility_bills.find_one({'_id': ObjectId(id)})
        if bill:
            # Add to expenses
            mongo.db.expenses.insert_one({
                'type': 'outgoing',
                'amount': bill['amount'],
                'category': 'Utility Bill',
                'note': f"Paid bill for {bill.get('type')} (Ref: {bill.get('ref_no')})",
                'date': datetime.now(),
                'recorded_by': session.get('username', 'Admin'),
                'created_at': datetime.now()
            })
            
        # Remove from bills collection
        mongo.db.utility_bills.delete_one({'_id': ObjectId(id)})
        return jsonify({"message": "Bill paid and removed"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- TEAM / EMPLOYEE MANAGEMENT ROUTES ---
@app.route('/api/employees', methods=['GET'])
@role_required(['Admin'])
def get_employees():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # Sort by name alphabetically
        cursor = mongo.db.employees.find().sort('name', 1)
        employees = []
        for e in cursor:
            employees.append({
                'id': str(e['_id']),
                'name': e.get('name', ''),
                'designation': e.get('designation', ''),
                'pay': e.get('pay', ''),
                'advance': e.get('advance', ''),
                'duty_timings': e.get('duty_timings', ''),
                'date_of_joining': e.get('date_of_joining', ''),
                'cnic': e.get('cnic', ''),
                'phone': e.get('phone', '')
            })
        return jsonify(employees)
    except Exception as e:
        print(f"Employee Fetch Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/employees', methods=['POST'])
@role_required(['Admin'])
def add_employee():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = clean_input_data(request.json)
    try:
        employee = {
            'name': data.get('name'),
            'designation': data.get('designation'),
            'pay': data.get('pay', ''),
            'advance': data.get('advance', ''),
            'duty_timings': data.get('duty_timings', ''),
            'date_of_joining': data.get('date_of_joining', ''),
            'cnic': data.get('cnic', ''),
            'phone': data.get('phone', ''),
            'created_at': datetime.now()
        }
        result = mongo.db.employees.insert_one(employee)
        return jsonify({"message": "Employee added", "id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/employees/<id>', methods=['PUT'])
@role_required(['Admin'])
def update_employee(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = clean_input_data(request.json)
    # Remove _id from data if present to avoid immutable field error
    if '_id' in data: del data['_id']
    try:
        mongo.db.employees.update_one({'_id': ObjectId(id)}, {'$set': data})
        return jsonify({"message": "Employee updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/employees/<id>', methods=['DELETE'])
@role_required(['Admin'])
def delete_employee(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        mongo.db.employees.delete_one({'_id': ObjectId(id)})
        return jsonify({"message": "Employee deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/payment-records', methods=['GET'])
@role_required(['Admin'])
def get_payment_records():
    """Fetch all payment records (receipts) from expenses collection."""
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        # Fetch all incoming payments from Patient Fee category
        payments = list(mongo.db.expenses.find({
            'type': 'incoming',
            'category': 'Patient Fee'
        }).sort('date', -1))  # Most recent first
        
        # Process and format the records
        records = []
        for p in payments:
            # Extract patient name from note
            note = p.get('note', '')
            patient_name = 'Unknown'
            if 'Partial payment from ' in note:
                patient_name = note.split('Partial payment from ')[1].split(' via ')[0]
            
            records.append({
                '_id': str(p['_id']),
                'patient_name': patient_name,
                'amount': p.get('amount', 0),
                'date': p.get('date').strftime('%Y-%m-%d') if p.get('date') else 'N/A',
                'payment_method': p.get('payment_method', 'Cash'),
                'recorded_by': p.get('recorded_by', 'Admin'),
                'screenshot': p.get('screenshot', '')
            })
        
        return jsonify(records)
    except Exception as e:
        print(f"Payment Records Error: {e}")
        return jsonify({"error": str(e)}), 500


def _month_start_n_months_ago(months_ago: int) -> datetime:
    today = datetime.now()
    # months_ago = 0 => current month start; 5 => 5 months back
    target_month = today.month - months_ago
    target_year = today.year
    while target_month <= 0:
        target_month += 12
        target_year -= 1
    return datetime(target_year, target_month, 1)


@app.route('/api/payment-records/export', methods=['GET'])
@role_required(['Admin'])
def export_payment_records():
    """Export payment records to Excel for a given range.
    range=current (default) or six_months.
    """
    if not check_db(): return jsonify({"error": "Database error"}), 500

    range_key = request.args.get('range', 'current')

    today = datetime.now()
    if range_key == 'six_months':
        start_date = _month_start_n_months_ago(5)  # includes current month (6 total)
    else:
        start_date = datetime(today.year, today.month, 1)

    # end date = first day of next month
    if today.month == 12:
        end_date = datetime(today.year + 1, 1, 1)
    else:
        end_date = datetime(today.year, today.month + 1, 1)

    try:
        payments = list(mongo.db.expenses.find({
            'type': 'incoming',
            'category': 'Patient Fee',
            'date': {'$gte': start_date, '$lt': end_date}
        }).sort('date', 1))

        rows = []

        def to_date(dt_val):
            if not dt_val:
                return ''
            if isinstance(dt_val, datetime):
                return dt_val
            try:
                return datetime.fromisoformat(str(dt_val))
            except Exception:
                return None

        for p in payments:
            note = p.get('note', '')
            patient_name = 'Unknown'
            if 'Partial payment from ' in note:
                patient_name = note.split('Partial payment from ')[1].split(' via ')[0]

            dt = to_date(p.get('date'))
            rows.append({
                'Patient Name': patient_name,
                'Amount (PKR)': p.get('amount', 0),
                'Date': dt.strftime('%Y-%m-%d') if dt else '',
                'Payment Mode': p.get('payment_method', 'Cash'),
                'Recorded By': p.get('recorded_by', 'Admin'),
                'Note': note
            })

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame([{'Message': 'No payment records for selected range'}])

        output = io.BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)

        filename = f"payment_records_{'six_months' if range_key == 'six_months' else 'current_month'}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        print(f"Payment Records Export Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/patients/<id>/payment', methods=['POST'])
@role_required(['Admin'])
def add_patient_payment(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        data = clean_input_data(request.json)
        amount_paid = int(data.get('amount', 0))
        payment_method = data.get('payment_method', 'Cash') # Cash or Online
        screenshot = data.get('screenshot', '') # Base64 string if Online
        
        patient = mongo.db.patients.find_one({'_id': ObjectId(id)})
        if not patient:
            return jsonify({"error": "Patient not found"}), 404

        # 1. Parse existing received amount
        current_received_str = str(patient.get('receivedAmount', '0')).replace(',', '')
        try:
            current_received = int(current_received_str)
        except ValueError:
            current_received = 0

        # 2. Add new payment
        new_total = current_received + amount_paid

        # 3. Update Patient Record
        mongo.db.patients.update_one(
            {'_id': ObjectId(id)}, 
            {'$set': {'receivedAmount': str(new_total)}}
        )

        # 4. Log as an Incoming Expense automatically
        expense_note = f"Partial payment from {patient.get('name')} via {payment_method}"
        mongo.db.expenses.insert_one({
            'type': 'incoming',
            'amount': amount_paid,
            'category': 'Patient Fee',
            'note': expense_note,
            'payment_method': payment_method,
            'screenshot': screenshot, # Store proof if available
            'date': datetime.now(),
            'recorded_by': session.get('username', 'Admin'),
            'auto': True
        })

        return jsonify({"message": "Payment recorded successfully", "new_total": new_total})
    except Exception as e:
        print(f"Payment Error: {e}")
        return jsonify({"error": str(e)}), 500


# --- DAILY REPORT APIS ---

@app.route('/api/reports', methods=['GET'])
@role_required(['Admin', 'General Staff', 'Doctor'])
def get_daily_report():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "Date required"}), 400
        
    try:
        # Fetch all report entries for this specific date
        reports = list(mongo.db.daily_reports.find({'date': date_str}))
        
        # Convert ObjectId to string
        for r in reports:
            r['_id'] = str(r['_id'])
            r['patient_id'] = str(r['patient_id'])
            
        return jsonify(reports)
    except Exception as e:
        print(f"Report Fetch Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/reports/update', methods=['POST'])
@role_required(['Admin', 'General Staff', 'Doctor'])
def update_daily_report():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    
    data = clean_input_data(request.json)
    # Expected: { date, patient_id, time_slot, status }
    # status enum: 'done', 'not_done', 'complaint', ''
    
    try:
        query = {
            'date': data['date'],
            'patient_id': ObjectId(data['patient_id'])
        }
        
        # Upsert: Update if exists, Insert if not
        update = {
            '$set': {
                f"schedule.{data['time_slot']}": data['status'],
                'updated_at': datetime.now(),
                'updated_by': session.get('username', 'System')
            }
        }
        
        mongo.db.daily_reports.update_one(query, update, upsert=True)
        return jsonify({"message": "Status updated"}), 200
        
    except Exception as e:
        print(f"Report Update Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- REPORT CONFIGURATION API ---
    
@app.route('/api/reports/config', methods=['GET'])
@login_required
def get_report_config():
    if not check_db(): return jsonify({})
    # Return saved config or empty (frontend handles defaults)
    config = mongo.db.report_config.find_one({'_id': 'main_config'})
    if config:
        return jsonify(config)
    return jsonify({})

@app.route('/api/reports/config', methods=['POST'])
@role_required(['Admin'])
def save_report_config():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    data = clean_input_data(request.json)
    try:
        # Save day_columns and night_columns
        mongo.db.report_config.update_one(
            {'_id': 'main_config'},
            {'$set': {
                'day_columns': data.get('day_columns'),
                'night_columns': data.get('night_columns')
            }},
            upsert=True
        )
        return jsonify({"message": "Layout saved"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- PSYCHOLOGIST SESSIONS ---

def _parse_iso_date(date_str):
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return None


@app.route('/api/psych-sessions', methods=['GET'])
@login_required
def list_psych_sessions():
    if not check_db():
        return jsonify({"error": "Database error"}), 500

    role = session.get('role')
    user_id = session.get('user_id')

    start_str = request.args.get('start')
    end_str = request.args.get('end')
    psychologist_id = request.args.get('psychologistId')

    start_date = _parse_iso_date(start_str) if start_str else None
    end_date = _parse_iso_date(end_str) if end_str else None

    if end_date:
        # make end exclusive by moving to next day start
        end_date = end_date + timedelta(days=1)

    query = {}
    if start_date and end_date:
        query['date'] = {'$gte': start_date, '$lt': end_date}
    elif start_date:
        query['date'] = {'$gte': start_date}

    if role == 'Psychologist':
        query['psychologist_id'] = user_id
    elif psychologist_id:
        query['psychologist_id'] = psychologist_id

    try:
        sessions_cursor = mongo.db.psych_sessions.find(query).sort('date', 1)
        sessions = list(sessions_cursor)

        # collect ids for enrichment
        patient_ids = set()
        psych_ids = set()
        for s in sessions:
            for pid in s.get('patient_ids', []):
                patient_ids.add(pid)
            if s.get('psychologist_id'):
                psych_ids.add(s.get('psychologist_id'))

        patient_map = {}
        if patient_ids:
            patients = mongo.db.patients.find({"_id": {"$in": [ObjectId(pid) for pid in patient_ids if ObjectId.is_valid(pid)]}})
            for p in patients:
                patient_map[str(p['_id'])] = p.get('name', 'Unknown')

        psych_map = {}
        if psych_ids:
            users = mongo.db.users.find({"_id": {"$in": [ObjectId(pid) for pid in psych_ids if ObjectId.is_valid(pid)]}})
            for u in users:
                psych_map[str(u['_id'])] = u.get('name', u.get('username', 'Psych'))

        result = []
        for s in sessions:
            result.append({
                '_id': str(s['_id']),
                'psychologist_id': s.get('psychologist_id'),
                'psychologist_name': psych_map.get(s.get('psychologist_id', ''), s.get('psychologist_id', '')),
                'date': s.get('date').strftime('%Y-%m-%d') if s.get('date') else '',
                'time_slot': s.get('time_slot', ''),
                'patient_ids': s.get('patient_ids', []),
                'patient_names': [patient_map.get(pid, 'Unknown') for pid in s.get('patient_ids', [])],
                'title': s.get('title', ''),
                'note': s.get('note', ''),
                'note_author': s.get('note_author', ''),
                'note_at': s.get('note_at').isoformat() if s.get('note_at') else None
            })

        return jsonify(result)
    except Exception as e:
        print(f"Psych sessions fetch error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/psych-sessions', methods=['POST'])
@role_required(['Admin'])
def create_psych_session():
    if not check_db():
        return jsonify({"error": "Database error"}), 500

    data = clean_input_data(request.json)
    date_str = data.get('date')
    time_slot = data.get('time_slot', '')
    psychologist_id = data.get('psychologist_id')
    patient_ids = data.get('patient_ids', []) or []
    title = data.get('title', '')

    if not (date_str and psychologist_id and patient_ids):
        return jsonify({"error": "Missing fields"}), 400

    date_val = _parse_iso_date(date_str)
    if not date_val:
        return jsonify({"error": "Invalid date"}), 400

    # normalize to date-only at midnight
    date_val = date_val.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        doc = {
            'psychologist_id': psychologist_id,
            'date': date_val,
            'time_slot': time_slot,
            'patient_ids': patient_ids,
            'title': title,
            'created_by': session.get('username'),
            'created_at': datetime.now()
        }

        res = mongo.db.psych_sessions.insert_one(doc)
        return jsonify({"message": "Session created", "id": str(res.inserted_id)})
    except Exception as e:
        print(f"Psych session create error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/psych-sessions/<session_id>/note', methods=['POST'])
@role_required(['Admin', 'Psychologist'])
def add_psych_session_note(session_id):
    if not check_db():
        return jsonify({"error": "Database error"}), 500

    data = clean_input_data(request.json)
    note_text = data.get('note', '').strip()
    if not note_text:
        return jsonify({"error": "Note is required"}), 400

    try:
        session_doc = mongo.db.psych_sessions.find_one({'_id': ObjectId(session_id)})
        if not session_doc:
            return jsonify({"error": "Session not found"}), 404

        if session_doc.get('note'):
            return jsonify({"error": "Note already saved"}), 409

        mongo.db.psych_sessions.update_one(
            {'_id': ObjectId(session_id)},
            {'$set': {
                'note': note_text,
                'note_author': session.get('username'),
                'note_at': datetime.now()
            }}
        )

        return jsonify({"message": "Note saved"})
    except Exception as e:
        print(f"Psych session note error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/attendance')
def get_attendance():
    year = int(request.args.get('year'))
    month = int(request.args.get('month'))

    records = mongo.db.attendance.find({
        "year": year,
        "month": month
    })

    result = {}
    for rec in records:
        emp_id = str(rec["employee_id"])
        result[emp_id] = rec.get("days", {})

    return jsonify(result)

@app.route('/api/attendance', methods=['POST'])
def save_attendance():
    data = request.json

    employee_id = data['empId']
    day = str(data['day'])
    year = int(data['year'])
    month = int(data['month'])
    mark = data['mark']  # 'P', 'A', or ''

    query = {
        "employee_id": employee_id,
        "year": year,
        "month": month
    }

    if mark == '':
        mongo.db.attendance.update_one(
            query,
            { "$unset": { f"days.{day}": "" } },
            upsert=True
        )
    else:
        mongo.db.attendance.update_one(
            query,
            { "$set": { f"days.{day}": mark } },
            upsert=True
        )

    return jsonify(success=True)


if __name__ == '__main__':
    app.run(debug=True, port=5000)