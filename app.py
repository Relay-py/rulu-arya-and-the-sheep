from flask import Flask, jsonify, request, send_from_directory, render_template , redirect, url_for
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
    task_time = db.Column(db.DateTime)
    task_message = db.Column(db.String(255))
    task_status = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'last_name': self.last_name,
            'wait_time': self.estimated_wait_time,
            'danger_level': self.danger_level,
            'check_in_time': self.check_in_time.isoformat(),
            'task_time': self.task_time.isoformat() if self.task_time else None,
            'task_message': self.task_message,
            'task_status': self.task_status
        }

class PatientForm(FlaskForm):
    last_name = StringField('Last Name')
    id_number = StringField('ID Number')
    estimated_wait_time = IntegerField('Estimated Wait Time')
    danger_level = IntegerField('Danger Level')
    notification_message = StringField('Notification Message')

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

@app.route('/delete_patient/<int:patient_id>', methods=['POST'])
def delete_patient(patient_id):
    patient = Patients.query.get(patient_id)
    if patient:
        try:
            # Delete all tasks associated with this patient first
            Task.query.filter_by(patient_id=patient.id).delete()
            db.session.delete(patient)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error deleting patient: {e}")
    return redirect(url_for('add_patient'))

@app.route('/send-notification/<int:patient_id>', methods=['POST'])
def send_notification(patient_id):
    form = PatientForm()
    patient = Patients.query.get(patient_id)
    if patient and form.notification_message.data:
        patient.task_message = form.notification_message.data
        patient.task_time = datetime.utcnow()
        patient.task_status = True
        db.session.commit()
    return jsonify({'status': 'Notification sent'})

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

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patients', backref=db.backref('tasks', lazy=True))

@app.route('/add_task', methods=['POST'])
def add_task():
    patient_id = request.form.get('patient_id')
    task_description = request.form.get('task_description')
    
    new_task = Task(
        patient_id=patient_id,
        description=task_description,
        completed=False
    )
    db.session.add(new_task)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'task_id': new_task.id,
        'description': new_task.description,
        'completed': new_task.completed
    })

@app.route('/update_task_status', methods=['POST'])
def update_task_status():
    task_id = request.form.get('task_id')
    completed = request.form.get('completed') == 'true'
    
    task = Task.query.get(task_id)
    task.completed = completed
    db.session.commit()
    
    return jsonify({'status': 'success'})

@app.errorhandler(404)
def not_found(e):
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True)
