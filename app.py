from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import os
from datetime import datetime
import zoneinfo

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # ควรใช้ความยาวอย่างน้อย 16 ตัวอักษรแบบสุ่ม

app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://geniusmember_user:70O6AySjOd71NubGqzWp1ycYqinPzD0D@dpg-d1f5bl3e5dus73fiq8i0-a/geniusmember"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

# ======================== SQLAlchemy Models =========================
db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    student_id = db.Column(db.String, primary_key=True)
    prefix = db.Column(db.String)
    first_name = db.Column(db.String)
    last_name = db.Column(db.String)
    major = db.Column(db.String)
    position = db.Column(db.String)
    nickname = db.Column(db.String)
    phone = db.Column(db.String)
    email = db.Column(db.String)
    password = db.Column(db.String)
    is_admin = db.Column(db.Boolean, default=False)

class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    start = db.Column(db.String)
    end = db.Column(db.String)

class Participant(db.Model):
    __tablename__ = 'participants'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String, db.ForeignKey('users.student_id'))
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))
    time = db.Column(db.String)

    student = db.relationship('User', backref='participations')
    event = db.relationship('Event', backref='participants')

# ======================== Utility =========================
def hash_password(password):
    return generate_password_hash(password)

def check_password(hashed_password, password):
    return check_password_hash(hashed_password, password)

@app.route('/')
def index():
    now = datetime.now(zoneinfo.ZoneInfo('Asia/Bangkok'))
    events = Event.query.all()
    links = {}
    for event in events:
        try:
            start = datetime.fromisoformat(event.start).replace(tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))
            end = datetime.fromisoformat(event.end).replace(tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))
            if start <= now <= end:
                links[event.name] = {
                    'url': url_for('register_event', event=event.name),
                    'start': event.start,
                    'end': event.end
                }
        except:
            continue
    return render_template('index.html', links=links)


@app.route('/login', methods=['POST'])
def login():
    student_id = request.form['student_id']
    password = request.form['password']
    users = load_users()
    hashed_pw = hash_password(password)

    if student_id in users and users[student_id]['password'] == hashed_pw:
        session['student_id'] = student_id
        session['user'] = {
            'student_id': student_id,
            'name': users[student_id].get('FirstName', '') + ' ' + users[student_id].get('LastName', ''),
            'is_admin': users[student_id].get('is_admin', False)
        }
        return redirect(url_for('profile'))
    return "<h3 style='color:red;'>รหัสนักศึกษาหรือรหัสผ่านไม่ถูกต้อง</h3><a href='/'>กลับ</a>"

@app.route('/logout')
def logout():
    session.pop('student_id', None)
    session.pop('user', None)
    return redirect('/')

@app.route('/calendar')
def calendar():
    events = load_events()
    calendar_events = []

    for event in events:
        if not isinstance(event, dict):
            continue
        try:
            calendar_events.append({
                'title': event.get('name', 'กิจกรรม'),
                'start': event.get('start', ''),
                'end': event.get('end', '')
            })
        except Exception as e:
            continue

    return render_template('calendar.html', calendar_events=json.dumps(calendar_events, ensure_ascii=False))


@app.route('/dashboard/add_event', methods=['POST'])
def add_event():
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')

    new_event = request.form.get('new_event', '').strip()
    start = request.form.get('start', '').strip()
    end = request.form.get('end', '').strip()

    if not new_event:
        return redirect('/dashboard')

    events = load_events()
    if not any(e.get('name') == new_event for e in events if isinstance(e, dict)):
        events.append({'name': new_event, 'start': start, 'end': end})
        save_events(events)
        df = pd.DataFrame(columns=["StudentID", "Name", "Email", "Position", "Time"])
        df.to_excel(os.path.join(DATA_DIR, f'{new_event}.xlsx'), index=False)

    return redirect('/dashboard')

@app.route('/download/<event>.<format>')
def download_file(event, format):
    filename = os.path.join(DATA_DIR, f"{event}.xlsx")
    if not os.path.exists(filename):
        return "ไม่พบไฟล์", 404

    if format == 'csv':
        df = pd.read_excel(filename)
        csv_path = os.path.join(DATA_DIR, f"{event}.csv")
        df.to_csv(csv_path, index=False)
        return send_file(csv_path, as_attachment=True)
    else:
        return send_file(filename, as_attachment=True)

@app.route('/download/<event>/<format>')
def download_file_admin(event, format):
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')
    file_path = os.path.join(DATA_DIR, f'{event}.{format}')
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return 'ไม่พบไฟล์'

@app.route('/register/<event>', methods=['GET', 'POST'])
def register_event(event):
    if 'student_id' not in session:
        return redirect('/')

    users = load_users()
    sid = session['student_id']
    user = users.get(sid, {})

    events = load_events()
    now = datetime.now(zoneinfo.ZoneInfo('Asia/Bangkok'))
    matched = next((e for e in events if isinstance(e, dict) and e.get('name') == event), None)
    if not matched:
        flash("ไม่พบกิจกรรมนี้")
        return redirect('/')

    try:
        start = datetime.fromisoformat(matched.get('start')).replace(tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))
    except Exception:
        start = datetime(1900, 1, 1, tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))

    try:
        end = datetime.fromisoformat(matched.get('end')).replace(tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))
    except Exception:
        end = datetime(2100, 1, 1, tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))

    if request.method == 'POST':
        path = os.path.join(DATA_DIR, f'{event}.xlsx')
        if os.path.exists(path):
            df = pd.read_excel(path)
        else:
            df = pd.DataFrame(columns=["StudentID", "Name", "Email", "Position", "Time"])

        if sid in df['StudentID'].astype(str).values:
            return jsonify({'status': 'error', 'message': 'คุณได้ลงทะเบียนกิจกรรมนี้แล้ว'}), 400

        new_row = {
            "StudentID": sid,
            "Name": user.get('FirstName', '') + ' ' + user.get('LastName', ''),
            "Email": user.get('Email', ''),
            "Position": user.get('Position', ''),
            "Time": now.strftime("%Y-%m-%d %H:%M:%S")
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_excel(path, index=False)

        return jsonify({'status': 'success', 'message': 'ลงทะเบียนสำเร็จ'})

    return render_template('confirm_register.html', event=event, user=user, start=start.strftime('%Y-%m-%d %H:%M'), end=end.strftime('%Y-%m-%d %H:%M'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'student_id' not in session:
        return redirect('/')

    sid = session['student_id']
    users = load_users()
    if sid not in users:
        return "ไม่พบผู้ใช้"

    if request.method == 'POST':
        if 'edit' in request.form:
            session['editing'] = True
        elif session.get('editing'):
            users[sid]['Prefix'] = request.form.get('Prefix', '').strip()
            users[sid]['FirstName'] = request.form.get('FirstName', '').strip()
            users[sid]['LastName'] = request.form.get('LastName', '').strip()
            users[sid]['Major'] = request.form.get('Major', '').strip()
            users[sid]['Position'] = request.form.get('Position', '').strip()
            users[sid]['Nickname'] = request.form.get('Nickname', '').strip()
            users[sid]['Phone'] = request.form.get('Phone', '').strip()
            users[sid]['Email'] = request.form.get('Email', '').strip()
            save_users(users)
            session.pop('editing', None)
            return redirect(url_for('index'))

    user = users[sid]
    editing = session.get('editing', False)
    return render_template('profile.html', user=user, user_id=sid, editing=editing)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')

    events = load_events()
    event_list = [e for e in events if isinstance(e, dict)]
    
    event_data = {}
    events_metadata = {}
    for event in event_list:
        name = event['name']
        path = os.path.join(DATA_DIR, f'{name}.xlsx')
        if os.path.exists(path):
            df = pd.read_excel(path)
            records = df.to_dict(orient='records')
        else:
            records = []

        event_data[name] = records
        events_metadata[name] = {
            'start': event.get('start', ''),
            'end': event.get('end', '')
        }

    users = load_users()
    selected_event = request.args.get('event', '')

    registered_ids = set()
    if selected_event and selected_event in event_data:
        registered_ids = set(str(p['StudentID']) for p in event_data[selected_event])

    return render_template('dashboard.html',
                           events=event_data,
                           event_list=event_list,
                           users=users,
                           selected_event=selected_event,
                           registered_ids=registered_ids)

@app.route('/download/<event>/<format>')
def download(event, format):
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')
    file_path = os.path.join(DATA_DIR, f'{event}.{format}')
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return 'ไม่พบไฟล์'

@app.route('/dashboard/remove_participant', methods=['POST'])
def remove_participant():
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')

    event = request.form.get('event_name')
    student_id = request.form.get('student_id')
    path = os.path.join(DATA_DIR, f'{event}.xlsx')
    if os.path.exists(path):
        df = pd.read_excel(path)
        df = df[df['StudentID'].astype(str) != str(student_id)]
        df.to_excel(path, index=False)

    return redirect('/dashboard')

@app.route('/dashboard/delete_event', methods=['POST'])
def delete_event():
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')

    event_to_delete = request.form.get('delete_event')
    if not event_to_delete:
        return redirect('/dashboard')

    events = load_events()
    events = [e for e in events if not (isinstance(e, dict) and e.get('name') == event_to_delete)]
    save_events(events)

    for ext in ['xlsx', 'csv']:
        file_path = os.path.join(DATA_DIR, f'{event_to_delete}.{ext}')
        if os.path.exists(file_path):
            os.remove(file_path)

    return redirect('/dashboard')

@app.route('/activity')
def user_activity():
    if 'student_id' not in session:
        return redirect('/login')

    sid = session['student_id']
    users = load_users()
    user = users.get(sid, {})

    events = load_events()
    events = [e for e in events if isinstance(e, dict)]
    records = []

    for event in events:
        name = event['name']
        path = os.path.join(DATA_DIR, f'{name}.xlsx')
        if os.path.exists(path):
            df = pd.read_excel(path)
            if sid in df['StudentID'].astype(str).values:
                user_rows = df[df['StudentID'].astype(str) == str(sid)]
                for _, row in user_rows.iterrows():
                    records.append({
                        'Event': name,
                        'Name': row.get('Name', ''),
                        'Position': row.get('Position', ''),
                        'Time': row.get('Time', ''),
                        'Nickname': user.get('Nickname', ''),
                    })

    return render_template('activity.html', records=records, user=user)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'student_id' not in session:
        return redirect('/')

    sid = session['student_id']
    users = load_users()

    if sid not in users:
        return "ไม่พบผู้ใช้", 404

    if request.method == 'POST':
        old_pw = request.form.get('old_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if users[sid]['password'] != hash_password(old_pw):
            flash('รหัสผ่านเก่าไม่ถูกต้อง', 'danger')
            return redirect(url_for('change_password'))

        if new_pw != confirm_pw:
            flash('รหัสผ่านใหม่กับยืนยันรหัสผ่านไม่ตรงกัน', 'danger')
            return redirect(url_for('change_password'))

        users[sid]['password'] = hash_password(new_pw)
        save_users(users)

        session.pop('student_id', None)
        session.pop('user', None)

        flash('เปลี่ยนรหัสผ่านเรียบร้อยแล้ว กรุณาเข้าสู่ระบบใหม่', 'success')
        return redirect(url_for('index'))

    return render_template('change_password.html')

if __name__ == '__main__':
    app.run(debug=True)
