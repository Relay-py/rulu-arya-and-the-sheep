from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os

app = Flask(__name__, 
    static_folder='static',  # Change this to where your static files are
    static_url_path=''
)
CORS(app)

@app.route('/')
def serve():
    try:
        return app.send_static_file('index.html')
    except Exception as e:
        print(f"Error serving index.html: {e}")
        return "Error loading page", 500

@app.route('/api/patient-info')
def get_patient_info():
    return jsonify({
        'waitTime': '45 minutes',
        'queuePosition': 8,
        'triageLevel': 'Level 3 - Urgent',
        'patientName': 'John Doe'
    })

@app.route('/api/notifications')
def get_notifications():
    return jsonify([
        {'id': 1, 'message': 'Doctor will see you in 15 minutes'},
        {'id': 2, 'message': 'Please prepare your medical history'}
    ])

@app.route('/api/emergency', methods=['POST'])
def emergency_alert():
    data = request.json
    return jsonify({'status': 'Emergency alert received'})


@app.errorhandler(404)
def not_found(e):
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True)