from flask import Flask, jsonify, request, send_from_directory, render_template, redirect, url_for, flash
from flask_cors import CORS
import os
import requests
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from datetime import datetime, timedelta
import pymysql
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired
from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
import random
from openai import OpenAI, RateLimitError, APIError
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import session
import asyncio
from flask_caching import Cache
from functools import wraps
import time

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

socketio = SocketIO(app, cors_allowed_origins="*")

cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300  
})

waiting_players = []
active_games = {}

client = OpenAI(api_key='') 

FALLBACK_RESPONSES = [
    "That's interesting! How are you feeling while waiting?",
    "I understand waiting can be difficult. Would you like to talk about something else?",
    "That's a good point. Have you tried our entertainment section?",
    "I see. Is there anything specific you'd like to know about the hospital?",
    "Thanks for sharing. How long have you been waiting?",
    "That's quite interesting! What made you think about that?",
    "I understand. Would you like to know about our facilities?",
    "That's a valid concern. Have you checked our estimated wait times?",
]

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
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(100), nullable=False)
    id_number = db.Column(db.String(5), unique=True, nullable=False, default=lambda: str(random.randint(10000, 99999)))
    estimated_wait_time = db.Column(db.Integer)
    danger_level = db.Column(db.Integer)
    check_in_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    task_time = db.Column(db.DateTime)
    task_message = db.Column(db.String(255))
    task_status = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.Index('idx_patient_check_in', 'check_in_time'),
    )


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

def make_cache_key(*args, **kwargs):
    """Generate a cache key based on the current user"""
    if current_user.is_authenticated:
        return f'patient_info_{current_user.id}_{int(time.time() // 300)}'  # Changes every 5 minutes
    return 'no_user'

@app.route('/api/patient-info')
@login_required
def get_patient_info():
    try:
        if not current_user.is_authenticated:
            return jsonify({'error': 'Not authenticated'}), 401

        patient = Patients.query.filter_by(id=current_user.id).first()
        
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
            
        print(f"Fetching data for patient: {patient.id}")  
        response = {
            'waitTime': f'{patient.estimated_wait_time} minutes',
            'queuePosition': patient.id,  
            'triageLevel': f'Level {patient.danger_level}',
            'patientName': patient.last_name,
            'idNumber': patient.id_number,
            'activeTask': patient.task_message if (patient.task_message and not patient.task_status) else None
        }
        print(f"Response data: {response}") 
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"Error fetching patient info: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

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

@app.route('/add_task/<int:patient_id>', methods=['POST'])
def add_task(patient_id):
    try:
        patient = Patients.query.get(patient_id)
        if patient:
            task_message = request.form.get('task_message')
            if task_message:
                patient.task_message = task_message
                patient.task_time = datetime.utcnow()
                patient.task_status = False
                db.session.commit()
                
                notification = {
                    'type': 'task',
                    'message': f'New task assigned: {task_message}',
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                socketio.emit('notification', notification, room=f'patient_{patient_id}')
                
                flash('Task assigned successfully', 'success')
            else:
                flash('Task message cannot be empty', 'error')
        else:
            flash('Patient not found', 'error')
    except Exception as e:
        print(f"Error adding task: {str(e)}")
        flash('Error adding task', 'error')
    
    return redirect(url_for('add_patient'))

@app.route('/update_task_status', methods=['POST'])
@login_required
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

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated and isinstance(current_user, Patients):
        join_room(f'patient_{current_user.id}')

@socketio.on('join_game')
def handle_join_game():
    player = {
        'id': current_user.id,
        'socket_id': request.sid
    }
    
    if waiting_players and waiting_players[0]['id'] != current_user.id:
        
        opponent = waiting_players.pop(0)
        game_id = f"game_{random.randint(1000, 9999)}"
        
        active_games[game_id] = {
            'players': [player, opponent],
            'messages': [],
            'is_bot': False,
            'last_sender': None
        }
        
        join_room(game_id)
        emit('game_started', {
            'game_id': game_id,
            'opponent': 'Mystery Partner'
        })
        emit('game_started', {
            'game_id': game_id,
            'opponent': 'Mystery Partner'
        }, room=opponent['socket_id'])
    
    else:
        if random.random() < 0.5:  
            emit('searching_for_partner')  
            socketio.sleep(random.uniform(3, 6))
            
            game_id = f"game_{random.randint(1000, 9999)}"
            active_games[game_id] = {
                'players': [player],
                'messages': [],
                'is_bot': True,
                'last_sender': None
            }
            join_room(game_id)
            emit('game_started', {
                'game_id': game_id,
                'opponent': 'Mystery Partner'
            })
        else:
            waiting_players.append(player)
            emit('waiting_for_player')

@socketio.on('game_message')
def handle_game_message(data):
    game_id = data['game_id']
    message = data['message']
    game = active_games.get(game_id)
    
    if not game:
        return
        
    if game['last_sender'] == current_user.id:
        emit('error', {'message': "Please wait for your partner's response"}, room=request.sid)
        return
        
    game['messages'].append({
        'sender_id': current_user.id,
        'message': message
    })
    game['last_sender'] = current_user.id
    
    if game['is_bot']:
        emit('game_message', {
            'message': message,
            'isUser': True,
            'canRespond': False
        }, room=request.sid)
        
        emit('typing_indicator', {'isTyping': True}, room=game_id)
        socketio.sleep(random.uniform(2, 4))
        
        try:
            system_prompt = """You are participating in a game where users try to guess if they're talking to a human or AI.
        You should:
        1- U should sound as human like as possible
        2-be concise and try to be as human as possible always try to be as human as possible
        3- if the person is using jokes then you should pick up on it and make a joke back
        4- addapt to the user's tone and language
        6-if the person is sad Be positive and try to make the user feel better but don t sound too pushy
        7- if the person is talking with an accent then you should use an accent too
        8- Don t say how can I help you or anything like that , avoid a bit what'up or similar 
        9-use less punctuation , say no punctuation sometimes
        10- try ur best to not go beyond 1 to 1.5 lines"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=100,
                temperature=0.7
            )
            
            emit('typing_indicator', {'isTyping': False}, room=game_id)
            game['last_sender'] = None
            ai_response = response.choices[0].message.content
            emit('game_message', {
                'message': ai_response,
                'isUser': False,
                'canRespond': True
            }, room=game_id)
        except Exception as e:
            print(f"OpenAI API error: {e}")
            emit('typing_indicator', {'isTyping': False}, room=game_id)
            game['last_sender'] = None
            emit('game_message', {
                'message': "Sorry, I'm having trouble responding right now.",
                'isUser': False,
                'canRespond': True
            }, room=game_id)
    else:
        emit('game_message', {
            'message': message,
            'isUser': True,
            'canRespond': False
        }, room=request.sid)

        for player in game['players']:
            if player['id'] != current_user.id:
                emit('game_message', {
                    'message': message,
                    'isUser': False,
                    'canRespond': True
                }, room=player['socket_id'])

@socketio.on('make_guess')
def handle_guess(data):
    game_id = data['game_id']
    guess = data['guess']
    game = active_games.get(game_id)
    
    if not game:
        return
    
    is_correct = (guess == 'bot' and game['is_bot']) or (guess == 'human' and not game['is_bot'])
    emit('guess_result', {
        'correct': is_correct,
        'was_bot': game['is_bot']
    }, room=game_id)
    
    del active_games[game_id]
    
    socketio.sleep(3)
    emit('restart_game')

def get_gpt_response(message):
    try:
        system_prompt = """You are participating in a game where users try to guess if they're talking to a human or AI.
        You should:
        1- U should sound as human like as possible
        2-be concise and try to be as human as possible always try to be as human as possible
        3- if the person is using jokes then you should pick up on it and make a joke back
        5- there are user that would do weird things so be prepared for that, u can also do something weird too
        6-if the person is sad Be positive and try to make the user feel better but don t sound too pushy
        7- if the person is talking with an accent then you should use an accent too
        8- Don t say how can I help you or anything like that
        9-use less punctuation , say no punctuation sometimes
        10- try ur best to not go beyond 1 to 1.5 lines
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        return response.choices[0].message.content

    except Exception as e:
        return random.choice(FALLBACK_RESPONSES)

@socketio.on('user_typing')
def handle_typing(data):
    game_id = data['game_id']
    game = active_games.get(game_id)
    
    if not game or game['is_bot']:
        return
    
    for player in game['players']:
        if player['id'] != current_user.id:
            emit('typing_indicator', {
                'isTyping': data['isTyping']
            }, room=player['socket_id'])

def init_db():
    with app.app_context():
        db.create_all()
        if not any(idx.name == 'idx_patient_check_in' for idx in Patients.__table__.indexes):
            from sqlalchemy import Index
            Index('idx_patient_check_in', Patients.check_in_time)
def update_patient_cache(user_id):
    cache_key = f'patient_info_{user_id}_{int(time.time() // 300)}'
    cache.delete(cache_key)


with app.app_context():
    init_db()

@app.route('/entertainment')
def entertainment():
    return render_template('entertainment.html')

@app.route('/news')
def news():
    return render_template('news.html')

@app.route('/complete_task/<int:patient_id>', methods=['POST'])
def complete_task(patient_id):
    try:
        patient = Patients.query.get(patient_id)
        if patient:
            patient.task_status = True
            db.session.commit()
            flash('Task marked as completed', 'success')
        else:
            flash('Patient not found', 'error')
    except Exception as e:
        print(f"Error completing task: {str(e)}")
        flash('Error updating task status', 'error')
    
    return redirect(url_for('serve'))

@app.route('/clear_task/<int:patient_id>', methods=['POST'])
def clear_task(patient_id):
    try:
        patient = Patients.query.get(patient_id)
        if patient:
            patient.task_message = None
            patient.task_status = False
            patient.task_time = None
            db.session.commit()
            flash('Task cleared successfully', 'success')
        else:
            flash('Patient not found', 'error')
    except Exception as e:
        print(f"Error clearing task: {str(e)}")
        flash('Error clearing task', 'error')
    
    return redirect(url_for('add_patient'))

if __name__ == '__main__':
    socketio.run(app, debug=True)
