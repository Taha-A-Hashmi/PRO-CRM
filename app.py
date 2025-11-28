from flask import Flask, render_template, request, jsonify, send_file
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import os
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)

# --- DATABASE CONFIGURATION ---
# 1. On Local: It uses localhost (requires MongoDB installed).
# 2. On Vercel: You MUST set the 'MONGO_URI' environment variable in Vercel Settings.
#    If not set, it defaults to localhost and will FAIL on Vercel.
mongo_uri = os.environ.get("MONGO_URI", "mongodb+srv://taha-a-hashmi:123@cluster0.vxgxiip.mongodb.net/hospital_crm_db?retryWrites=true&w=majority&appName=Cluster0")
app.config["MONGO_URI"] = mongo_uri

try:
    mongo = PyMongo(app)
except Exception as e:
    print(f"Error initializing MongoDB: {e}")
    mongo = None

@app.route('/')
def index():
    return render_template('index.html')

# Helper to check DB connection
def check_db():
    if not mongo or not mongo.db:
        print("Database connection failed or not initialized.")
        return False
    return True

@app.route('/api/patients', methods=['GET'])
def get_patients():
    if not check_db(): return jsonify([])
    try:
        patients_cursor = mongo.db.patients.find()
        patients = []
        for p in patients_cursor:
            p['_id'] = str(p['_id'])
            patients.append(p)
        return jsonify(patients)
    except Exception as e:
        print(f"DB Fetch Error: {e}")
        return jsonify([])

@app.route('/api/patients', methods=['POST'])
def add_patient():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        data = request.json
        data['created_at'] = datetime.utcnow()
        data['notes'] = [] 
        result = mongo.db.patients.insert_one(data)
        return jsonify({"message": "Success", "id": str(result.inserted_id)}), 201
    except Exception as e:
        print(f"DB Insert Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/patients/<id>', methods=['PUT'])
def update_patient(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        data = request.json
        if '_id' in data: del data['_id']
        mongo.db.patients.update_one({'_id': ObjectId(id)}, {'$set': data})
        return jsonify({"message": "Updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/patients/<id>/notes', methods=['POST'])
def add_note(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        note = request.json 
        mongo.db.patients.update_one({'_id': ObjectId(id)}, {'$push': {'notes': note}})
        return jsonify({"message": "Note added"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/patients/<id>', methods=['DELETE'])
def delete_patient(id):
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        mongo.db.patients.delete_one({'_id': ObjectId(id)})
        return jsonify({"message": "Deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/export', methods=['POST'])
def export_patients():
    if not check_db(): return jsonify({"error": "Database error"}), 500
    try:
        req_data = request.get_json() or {}
        selected_fields = req_data.get('fields', 'all')
        
        cursor = mongo.db.patients.find()
        patients_list = list(cursor)
        
        if not patients_list:
            return jsonify({"error": "No patients found"}), 404

        # Prepare Data
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
