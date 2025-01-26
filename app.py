from flask import Flask, jsonify, request, send_from_directory, render_template, redirect, url_for, flash
from flask_cors import CORS
import os
import requests
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from datetime import datetime
import pymysql
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired
from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
import random

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

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class Nurses(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

class Patients(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(100), nullable=False)
    id_number = db.Column(db.String(5), unique=True, nullable=False, default=lambda: str(random.randint(10000, 99999)))
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
            'id_number': self.id_number,
            'wait_time': self.estimated_wait_time,
            'danger_level': self.danger_level,
            'check_in_time': self.check_in_time.isoformat(),
            'task_time': self.task_time.isoformat() if self.task_time else None,
            'task_message': self.task_message,
            'task_status': self.task_status
        }

    def get_id(self):
        return str(self.id)

class LoginForm(FlaskForm):
    user_type = SelectField('Login as', choices=[('nurse', 'Nurse'), ('patient', 'Patient')])
    username = StringField('Username/Last Name', validators=[DataRequired()])
    password = PasswordField('Password/ID Number', validators=[DataRequired()])
    submit = SubmitField('Login')

class PatientForm(FlaskForm):
    last_name = StringField('Last Name', validators=[DataRequired()])
    estimated_wait_time = IntegerField('Estimated Wait Time', validators=[DataRequired()])
    danger_level = IntegerField('Danger Level', validators=[DataRequired()])

@login_manager.user_loader
def load_user(user_id):
    try:
        nurse = Nurses.query.get(int(user_id))
        if nurse:
            return nurse
        return Patients.query.get(int(user_id))
    except:
        return None

@app.route('/index')
def serve():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
        
    if isinstance(current_user, Nurses):
        return redirect(url_for('add_patient'))
    return render_template('index.html')

@app.route('/add-patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    if not isinstance(current_user, Nurses):
        return redirect(url_for('serve'))
    
    form = PatientForm()
    if form.validate_on_submit():
        new_patient = Patients(
            last_name=form.last_name.data,
            estimated_wait_time=form.estimated_wait_time.data,
            danger_level=form.danger_level.data
        )
        db.session.add(new_patient)
        db.session.commit()
        
    patients = Patients.query.order_by(Patients.check_in_time.desc())
    return render_template('patients_add.html', form=form, our_patient=patients)

@app.route('/delete_patient/<int:patient_id>', methods=['POST'])
def delete_patient(patient_id):
    patient = Patients.query.get(patient_id)
    if patient:
        try:
            Task.query.filter_by(patient_id=patient.id).delete()
            db.session.delete(patient)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error deleting patient: {e}")
    return redirect(url_for('add_patient'))

@app.route('/api/patient-info')
@login_required
def get_patient_info():
    if not isinstance(current_user, Patients):
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'waitTime': f'{current_user.estimated_wait_time} minutes',
        'queuePosition': current_user.id,  
        'triageLevel': f'Level {current_user.danger_level}',
        'patientName': current_user.last_name,
        'idNumber': current_user.id_number
    })

@app.route('/api/notifications')
@login_required
def get_notifications():
    if not isinstance(current_user, Patients):
        return jsonify({'error': 'Unauthorized'}), 403
    
    notifications = []
    for task in current_user.tasks:
        status = "Completed" if task.completed else "Pending"
        notifications.append({
            'id': task.id,
            'message': f"{task.description} - {status}",
            'created_at': task.created_at.strftime('%H:%M')
        })
    
    return jsonify(notifications)

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if isinstance(current_user, Nurses):
            return redirect(url_for('add_patient'))
        return redirect(url_for('serve'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user_type = form.user_type.data
        username = form.username.data
        password = form.password.data

        if user_type == 'nurse':
            user = Nurses.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('add_patient'))
        else:
            user = Patients.query.filter_by(last_name=username, id_number=password).first()
            if user:
                login_user(user)
                return redirect(url_for('serve'))

        flash('Invalid credentials')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
