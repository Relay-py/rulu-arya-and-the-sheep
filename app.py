from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS
import os
import requests
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pymysql
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from urllib.parse import quote_plus
pymysql.install_as_MySQLdb()

app = Flask(__name__, 
    static_folder='templates',  
    static_url_path=''
)
CORS(app)

app.config['SECRET_KEY'] = 'your-secret-key-here'

password = quote_plus("password@2005")
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:{password}@localhost/my_hospital'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Patients(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(100), nullable=False)
    id_number = db.Column(db.String(20), unique=True, nullable=False)
    estimated_wait_time = db.Column(db.Integer) 
    danger_level = db.Column(db.Integer)
    check_in_time = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'last_name': self.last_name,
            'wait_time': self.estimated_wait_time,
            'danger_level': self.danger_level,
            'check_in_time': self.check_in_time.isoformat()
        }

class PatientForm(FlaskForm):
    last_name = StringField('Last Name')
    id_number = StringField('ID Number')
    estimated_wait_time = IntegerField('Estimated Wait Time')
    danger_level = IntegerField('Danger Level')

@app.route('/')
def serve():
    try:
        return app.send_static_file('index.html')
    except Exception as e:
        print(f"Error serving index.html: {e}")
        return "Error loading page", 500
@app.route('/add-patient', methods=['GET','POST'])
def add_patient():
    form = PatientForm()
    if form.validate_on_submit():
        new_patient = Patients(last_name=form.last_name.data, id_number=form.id_number.data, estimated_wait_time=form.estimated_wait_time.data, danger_level=form.danger_level.data)
        db.session.add(new_patient)
        db.session.commit()
    our_patient = Patients.query.order_by(Patients.check_in_time.desc())
    return render_template('patients_add.html', form=form, our_patient=our_patient)


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
