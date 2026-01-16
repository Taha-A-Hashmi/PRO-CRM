"""
Database Cleanup Script
-----------------------
This script removes all records from the database except the admin user 'ImranSaab'
and updates the admin email to psyimranhussain@gmail.com
"""

from flask import Flask
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app and MongoDB
app = Flask(__name__)
mongo_uri = os.environ.get("MONGO_URI", "mongodb+srv://taha_admin:hospital123@cluster0.ukoxtzf.mongodb.net/hospital_crm_db?retryWrites=true&w=majority&appName=Cluster0&authSource=admin")
app.config["MONGO_URI"] = mongo_uri

try:
    mongo = PyMongo(app)
    print("✓ Connected to MongoDB successfully")
except Exception as e:
    print(f"✗ Error connecting to MongoDB: {e}")
    exit(1)

def clean_database():
    """Remove all records except the admin user and update admin email"""
    
    try:
        # Find the admin user (ImranSaab)
        admin_user = mongo.db.users.find_one({"username": "ImranSaab"})
        
        if not admin_user:
            print("⚠ Admin user 'ImranSaab' not found. Creating new admin user...")
            # Create the admin user
            admin_user = {
                'username': 'ImranSaab',
                'password': generate_password_hash('password123'),
                'role': 'Admin',
                'name': 'Imran Khan (Admin)',
                'email': 'psyimranhussain@gmail.com',
                'created_at': datetime.now()
            }
            result = mongo.db.users.insert_one(admin_user)
            admin_user_id = result.inserted_id
            print(f"✓ Admin user created with email: psyimranhussain@gmail.com")
        else:
            admin_user_id = admin_user['_id']
            # Update admin email
            mongo.db.users.update_one(
                {'_id': admin_user_id},
                {'$set': {'email': 'psyimranhussain@gmail.com'}}
            )
            print(f"✓ Admin user 'ImranSaab' found and email updated to: psyimranhussain@gmail.com")
        
        # Delete all other users
        other_users_count = mongo.db.users.count_documents({'_id': {'$ne': admin_user_id}})
        if other_users_count > 0:
            result = mongo.db.users.delete_many({'_id': {'$ne': admin_user_id}})
            print(f"✓ Deleted {result.deleted_count} other users")
        else:
            print("✓ No other users to delete")
        
        # Delete all patients
        patients_count = mongo.db.patients.count_documents({})
        if patients_count > 0:
            result = mongo.db.patients.delete_many({})
            print(f"✓ Deleted {result.deleted_count} patients")
        else:
            print("✓ No patients to delete")
        
        # Delete all patient records
        patient_records_count = mongo.db.patient_records.count_documents({})
        if patient_records_count > 0:
            result = mongo.db.patient_records.delete_many({})
            print(f"✓ Deleted {result.deleted_count} patient records")
        else:
            print("✓ No patient records to delete")
        
        # Delete all canteen sales
        canteen_sales_count = mongo.db.canteen_sales.count_documents({})
        if canteen_sales_count > 0:
            result = mongo.db.canteen_sales.delete_many({})
            print(f"✓ Deleted {result.deleted_count} canteen sales records")
        else:
            print("✓ No canteen sales to delete")
        
        # Delete all expenses
        expenses_count = mongo.db.expenses.count_documents({})
        if expenses_count > 0:
            result = mongo.db.expenses.delete_many({})
            print(f"✓ Deleted {result.deleted_count} expenses")
        else:
            print("✓ No expenses to delete")
        
        # Delete all call/meeting tracker records
        tracker_count = mongo.db.call_meeting_tracker.count_documents({})
        if tracker_count > 0:
            result = mongo.db.call_meeting_tracker.delete_many({})
            print(f"✓ Deleted {result.deleted_count} call/meeting tracker records")
        else:
            print("✓ No call/meeting tracker records to delete")
        
        # Delete all assets
        assets_count = mongo.db.assets.count_documents({})
        if assets_count > 0:
            result = mongo.db.assets.delete_many({})
            print(f"✓ Deleted {result.deleted_count} assets")
        else:
            print("✓ No assets to delete")
        
        # Delete all attendance records
        attendance_count = mongo.db.attendance.count_documents({})
        if attendance_count > 0:
            result = mongo.db.attendance.delete_many({})
            print(f"✓ Deleted {result.deleted_count} attendance records")
        else:
            print("✓ No attendance records to delete")
        
        # Delete all daily reports
        daily_reports_count = mongo.db.daily_reports.count_documents({})
        if daily_reports_count > 0:
            result = mongo.db.daily_reports.delete_many({})
            print(f"✓ Deleted {result.deleted_count} daily reports")
        else:
            print("✓ No daily reports to delete")
        
        # Delete all emergency alerts
        alerts_count = mongo.db.emergency_alerts.count_documents({})
        if alerts_count > 0:
            result = mongo.db.emergency_alerts.delete_many({})
            print(f"✓ Deleted {result.deleted_count} emergency alerts")
        else:
            print("✓ No emergency alerts to delete")
        
        # Delete all employees
        employees_count = mongo.db.employees.count_documents({})
        if employees_count > 0:
            result = mongo.db.employees.delete_many({})
            print(f"✓ Deleted {result.deleted_count} employees")
        else:
            print("✓ No employees to delete")
        
        # Delete all old balances
        old_balances_count = mongo.db.old_balances.count_documents({})
        if old_balances_count > 0:
            result = mongo.db.old_balances.delete_many({})
            print(f"✓ Deleted {result.deleted_count} old balances")
        else:
            print("✓ No old balances to delete")
        
        # Delete all psych sessions
        psych_sessions_count = mongo.db.psych_sessions.count_documents({})
        if psych_sessions_count > 0:
            result = mongo.db.psych_sessions.delete_many({})
            print(f"✓ Deleted {result.deleted_count} psych sessions")
        else:
            print("✓ No psych sessions to delete")
        
        # Delete all report config
        report_config_count = mongo.db.report_config.count_documents({})
        if report_config_count > 0:
            result = mongo.db.report_config.delete_many({})
            print(f"✓ Deleted {result.deleted_count} report config")
        else:
            print("✓ No report config to delete")
        
        # Delete all utility bills
        utility_bills_count = mongo.db.utility_bills.count_documents({})
        if utility_bills_count > 0:
            result = mongo.db.utility_bills.delete_many({})
            print(f"✓ Deleted {result.deleted_count} utility bills")
        else:
            print("✓ No utility bills to delete")
        
        print("\n" + "="*60)
        print("DATABASE CLEANUP COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"Remaining user: ImranSaab (Admin)")
        print(f"Admin email: psyimranhussain@gmail.com")
        print(f"Admin password: password123")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Error during database cleanup: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("\n" + "="*60)
    print("DATABASE CLEANUP SCRIPT")
    print("="*60)
    print("This will remove ALL records except the admin user 'ImranSaab'")
    print("="*60 + "\n")
    
    # Ask for confirmation
    confirm = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        print("\nStarting database cleanup...\n")
        success = clean_database()
        if success:
            print("\n✓ Script completed successfully!")
        else:
            print("\n✗ Script completed with errors!")
    else:
        print("\n✗ Operation cancelled by user")
