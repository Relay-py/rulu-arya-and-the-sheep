from app import app, db, Nurses

def create_nurse(username, password):
    with app.app_context():
        nurse = Nurses(username=username)
        nurse.set_password(password)
        db.session.add(nurse)
        db.session.commit()
        print(f"Nurse account created with username: {username}")

if __name__ == "__main__":
    create_nurse("admin", "admin123") 