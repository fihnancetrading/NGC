# NGC License Server - Complete Flask Application
# Copy this entire file and save as: app.py

from flask import Flask, request, jsonify
import sqlite3
import hashlib
import secrets
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# Database file
DATABASE = 'licenses.db'

#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE FUNCTIONS
#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def init_db():
    """Initialize the database with necessary tables"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Create licenses table
    c.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            product TEXT NOT NULL,
            created_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            status TEXT NOT NULL,
            activations INTEGER DEFAULT 0,
            max_activations INTEGER DEFAULT 1,
            last_validated TEXT,
            account_number TEXT
        )
    ''')
    
    # Create validation logs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS validation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT,
            timestamp TEXT,
            ip_address TEXT,
            account_number TEXT,
            result TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

def generate_license_key():
    """Generate a unique license key"""
    # Format: NGC-XXXX-XXXX-XXXX-XXXX
    parts = []
    for i in range(4):
        part = secrets.token_hex(2).upper()
        parts.append(part)
    return f"NGC-{'-'.join(parts)}"

#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API ENDPOINTS
#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/')
def home():
    """Home page - shows server is running"""
    return """
    <html>
        <head>
            <title>NGC License Server</title>
            <style>
                body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }
                h1 { color: #1F4E78; }
                .status { color: green; font-weight: bold; }
                .endpoint { background: #f5f5f5; padding: 10px; margin: 10px 0; border-left: 3px solid #1F4E78; }
            </style>
        </head>
        <body>
            <h1>🚀 NGC License Server</h1>
            <p class="status">✅ Status: Online and Running</p>
            <h2>Available Endpoints:</h2>
            <div class="endpoint">
                <strong>POST /validate</strong> - Validate a license key
            </div>
            <div class="endpoint">
                <strong>POST /activate</strong> - Activate a new license
            </div>
            <div class="endpoint">
                <strong>POST /generate</strong> - Generate new license (admin)
            </div>
            <div class="endpoint">
                <strong>GET /check/:license_key</strong> - Check license status
            </div>
            <p><em>Next Generation Capital - License Management System</em></p>
        </body>
    </html>
    """

@app.route('/validate', methods=['POST'])
def validate_license():
    """
    Validate a license key from MT5 EA
    
    Expected JSON:
    {
        "license_key": "NGC-XXXX-XXXX-XXXX-XXXX",
        "account_number": "12345678"  (optional)
    }
    
    Returns:
    {
        "valid": true/false,
        "expires": "2025-12-31",
        "status": "active",
        "message": "License valid"
    }
    """
    try:
        data = request.json
        license_key = data.get('license_key', '').strip().upper()
        account_number = data.get('account_number', '')
        ip_address = request.remote_addr
        
        if not license_key:
            return jsonify({
                'valid': False,
                'message': 'License key is required'
            }), 400
        
        # Connect to database
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Get license info
        c.execute('''
            SELECT license_key, email, product, expiry_date, status, activations, max_activations 
            FROM licenses 
            WHERE license_key = ?
        ''', (license_key,))
        
        result = c.fetchone()
        
        if not result:
            # Log failed validation
            c.execute('''
                INSERT INTO validation_logs (license_key, timestamp, ip_address, result)
                VALUES (?, ?, ?, ?)
            ''', (license_key, datetime.now().isoformat(), ip_address, 'NOT_FOUND'))
            conn.commit()
            conn.close()
            
            return jsonify({
                'valid': False,
                'message': 'License key not found'
            })
        
        # Parse result
        key, email, product, expiry_date, status, activations, max_activations = result
        
        # Check if expired
        expiry = datetime.strptime(expiry_date, '%Y-%m-%d')
        if expiry < datetime.now():
            c.execute('''
                INSERT INTO validation_logs (license_key, timestamp, ip_address, result)
                VALUES (?, ?, ?, ?)
            ''', (license_key, datetime.now().isoformat(), ip_address, 'EXPIRED'))
            conn.commit()
            conn.close()
            
            return jsonify({
                'valid': False,
                'message': 'License has expired',
                'expires': expiry_date
            })
        
        # Check if active
        if status != 'active':
            c.execute('''
                INSERT INTO validation_logs (license_key, timestamp, ip_address, result)
                VALUES (?, ?, ?, ?)
            ''', (license_key, datetime.now().isoformat(), ip_address, 'INACTIVE'))
            conn.commit()
            conn.close()
            
            return jsonify({
                'valid': False,
                'message': f'License status: {status}'
            })
        
        # Check activation limit
        if activations >= max_activations:
            # Could allow validation even if max activations reached
            # This depends on your business logic
            pass
        
        # Update last validated time
        c.execute('''
            UPDATE licenses 
            SET last_validated = ? 
            WHERE license_key = ?
        ''', (datetime.now().isoformat(), license_key))
        
        # Log successful validation
        c.execute('''
            INSERT INTO validation_logs (license_key, timestamp, ip_address, result)
            VALUES (?, ?, ?, ?)
        ''', (license_key, datetime.now().isoformat(), ip_address, 'SUCCESS'))
        
        conn.commit()
        conn.close()
        
        # Return success
        return jsonify({
            'valid': True,
            'expires': expiry_date,
            'status': status,
            'product': product,
            'message': 'License valid',
            'days_remaining': (expiry - datetime.now()).days
        })
        
    except Exception as e:
        print(f"Error in validate: {str(e)}")
        return jsonify({
            'valid': False,
            'message': 'Server error during validation'
        }), 500

@app.route('/activate', methods=['POST'])
def activate_license():
    """
    Activate a license (increment activation counter)
    
    Expected JSON:
    {
        "license_key": "NGC-XXXX-XXXX-XXXX-XXXX",
        "account_number": "12345678"
    }
    """
    try:
        data = request.json
        license_key = data.get('license_key', '').strip().upper()
        account_number = data.get('account_number', '')
        
        if not license_key:
            return jsonify({
                'success': False,
                'message': 'License key is required'
            }), 400
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Get current activation count
        c.execute('''
            SELECT activations, max_activations, status 
            FROM licenses 
            WHERE license_key = ?
        ''', (license_key,))
        
        result = c.fetchone()
        
        if not result:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'License not found'
            })
        
        activations, max_activations, status = result
        
        if status != 'active':
            conn.close()
            return jsonify({
                'success': False,
                'message': f'License is {status}'
            })
        
        if activations >= max_activations:
            conn.close()
            return jsonify({
                'success': False,
                'message': f'Maximum activations ({max_activations}) reached'
            })
        
        # Increment activation counter
        c.execute('''
            UPDATE licenses 
            SET activations = activations + 1 
            WHERE license_key = ?
        ''', (license_key,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'activations_used': activations + 1,
            'activations_remaining': max_activations - (activations + 1)
        })
        
    except Exception as e:
        print(f"Error in activate: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error during activation'
        }), 500

@app.route('/generate', methods=['POST'])
def generate_license():
    """
    Generate a new license (admin function)
    
    Expected JSON:
    {
        "email": "customer@example.com",
        "product": "NGC_Scalping",
        "duration_days": 365,
        "max_activations": 1
    }
    
    Optional auth header: X-API-Key
    """
    try:
        # Simple API key protection (change this!)
        api_key = request.headers.get('X-API-Key')
        ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'change-me-in-production')
        
        if api_key != ADMIN_API_KEY:
            return jsonify({
                'success': False,
                'message': 'Unauthorized'
            }), 401
        
        data = request.json
        email = data.get('email', '').strip()
        product = data.get('product', 'NGC_EA')
        duration_days = data.get('duration_days', 365)
        max_activations = data.get('max_activations', 1)
        
        if not email:
            return jsonify({
                'success': False,
                'message': 'Email is required'
            }), 400
        
        # Generate license key
        license_key = generate_license_key()
        
        # Calculate expiry date
        created_date = datetime.now().strftime('%Y-%m-%d')
        expiry_date = (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d')
        
        # Insert into database
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO licenses 
            (license_key, email, product, created_date, expiry_date, status, activations, max_activations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (license_key, email, product, created_date, expiry_date, 'active', 0, max_activations))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'license_key': license_key,
            'email': email,
            'product': product,
            'created': created_date,
            'expires': expiry_date,
            'max_activations': max_activations
        })
        
    except Exception as e:
        print(f"Error in generate: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error during generation'
        }), 500

@app.route('/check/<license_key>', methods=['GET'])
def check_license(license_key):
    """
    Check license status (simple GET endpoint)
    """
    try:
        license_key = license_key.strip().upper()
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        c.execute('''
            SELECT email, product, created_date, expiry_date, status, activations, max_activations, last_validated
            FROM licenses 
            WHERE license_key = ?
        ''', (license_key,))
        
        result = c.fetchone()
        conn.close()
        
        if not result:
            return jsonify({
                'found': False,
                'message': 'License not found'
            })
        
        email, product, created, expiry, status, activations, max_activations, last_validated = result
        
        # Check if expired
        expiry_date = datetime.strptime(expiry, '%Y-%m-%d')
        is_expired = expiry_date < datetime.now()
        days_remaining = (expiry_date - datetime.now()).days
        
        return jsonify({
            'found': True,
            'license_key': license_key,
            'email': email,
            'product': product,
            'created': created,
            'expires': expiry,
            'status': 'expired' if is_expired else status,
            'activations': activations,
            'max_activations': max_activations,
            'days_remaining': max(0, days_remaining),
            'last_validated': last_validated
        })
        
    except Exception as e:
        print(f"Error in check: {str(e)}")
        return jsonify({
            'found': False,
            'message': 'Error checking license'
        }), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get basic statistics (admin function)"""
    try:
        api_key = request.headers.get('X-API-Key')
        ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'change-me-in-production')
        
        if api_key != ADMIN_API_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Total licenses
        c.execute('SELECT COUNT(*) FROM licenses')
        total_licenses = c.fetchone()[0]
        
        # Active licenses
        c.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active'")
        active_licenses = c.fetchone()[0]
        
        # Expired licenses
        c.execute("SELECT COUNT(*) FROM licenses WHERE expiry_date < date('now')")
        expired_licenses = c.fetchone()[0]
        
        # Total validations today
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute("SELECT COUNT(*) FROM validation_logs WHERE timestamp LIKE ?", (f'{today}%',))
        validations_today = c.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'total_licenses': total_licenses,
            'active_licenses': active_licenses,
            'expired_licenses': expired_licenses,
            'validations_today': validations_today
        })
        
    except Exception as e:
        print(f"Error in stats: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INITIALIZATION
#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Initialize database on startup
init_db()

#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUN SERVER
#━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 NGC License Server starting on port {port}")
    print(f"📊 Database: {DATABASE}")
    print(f"✅ Server ready!")
    app.run(host='0.0.0.0', port=port, debug=False)
