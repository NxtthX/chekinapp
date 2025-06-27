from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash,make_response
from werkzeug.security import generate_password_hash, check_password_hash
import zoneinfo
import pandas as pd
import os
import json
from datetime import datetime
import io
import qrcode

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATA_DIR = 'data'
USER_FILE = 'users.json'
EVENTS_FILE = 'events.json'

os.makedirs(DATA_DIR, exist_ok=True)

def load_events():
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # กรองเอาเฉพาะ dict ที่มี key name, start, end
            events = [e for e in data if isinstance(e, dict) and 'name' in e and 'start' in e and 'end' in e]
            return events
    return []

def save_events(events):
    with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
            return users
    return {}

def save_users(users):
    with open(USER_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def hash_password(password):
    return generate_password_hash(password)

def check_password(hashed_password, password):
    return check_password_hash(hashed_password, password)



@app.route('/')
def index():
    now = datetime.now(zoneinfo.ZoneInfo('Asia/Bangkok'))
    events = load_events()
    links = {}

    os.makedirs('static/qrcode', exist_ok=True)  # สร้างโฟลเดอร์ถ้ายังไม่มี

    for event in events:
        try:
            start = datetime.fromisoformat(event['start']).replace(tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))
            end = datetime.fromisoformat(event['end']).replace(tzinfo=zoneinfo.ZoneInfo('Asia/Bangkok'))
            if start <= now <= end:
                event_name = event['name']
                register_url = url_for('register_event', event=event_name, _external=True)

                qr_path = f'static/qrcode/{event_name}.png'
                
                # ลบไฟล์เก่าถ้ามี
                if os.path.exists(qr_path):
                    os.remove(qr_path)

                # สร้าง QR Code ใหม่เสมอ
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=6,
                    border=2,
                )
                qr.add_data(register_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                img.save(qr_path)

                links[event_name] = {
                    'url': register_url,
                    'start': event['start'],
                    'end': event['end'],
                    'qrcode_path': qr_path
                }
        except Exception as e:
            print(f"Error generating QR for {event}: {e}")
            continue

    return render_template('index.html', links=links)

@app.route('/qrcode/<event>')
def generate_qrcode(event):
    event_url = url_for('register_event', event=event, _external=True)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=6,
        border=2,
    )
    qr.add_data(event_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    response = make_response(img_io.read())
    response.headers.set('Content-Type', 'image/png')
    response.headers.set('Content-Disposition', 'inline', filename=f'{event}_qrcode.png')
    return response


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        student_id = request.form['student_id'].strip()
        password = request.form['password']

        users = load_users()
        user = users.get(student_id)

        if user and check_password(user['password'], password):
            session['student_id'] = student_id
            session['user'] = {
                'student_id': student_id,
                'Prefix': user.get('Prefix', ''),
                'name': f"{user.get('FirstName', '')} {user.get('LastName', '')}".strip(),
                'Email': user.get('Email', ''),
                'Position': user.get('Position', ''),
                'is_admin': user.get('is_admin', False)
            }
            return redirect('/dashboard') if user.get('is_admin') else redirect('/')

        flash('รหัสนักศึกษาหรือรหัสผ่านไม่ถูกต้อง', 'danger')
        return redirect(url_for('index'))

    return render_template('index.html')

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'student_id' not in session:
        return redirect('/')

    sid = session['student_id']
    users = load_users()
    user = users[sid]
    session['user'] = {
        'student_id': sid,
        'Prefix': user.get('Prefix', ''),
        'FirstName': user.get('FirstName', ''),
        'LastName': user.get('LastName', ''),
        'Email': user.get('Email', ''),
        'Position': user.get('Position', ''),
        'name': f"{user.get('FirstName', '')} {user.get('LastName', '')}".strip(),
        'is_admin': user.get('is_admin', False)
    }
    if sid not in users:
        return "ไม่พบผู้ใช้", 404

    if request.method == 'POST':
        old_pw = request.form.get('old_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        # ตรวจสอบรหัสผ่านเก่า
        if not check_password(users[sid]['password'], old_pw):
            flash('รหัสผ่านเก่าไม่ถูกต้อง', 'danger')
            return redirect(url_for('change_password'))

        if new_pw != confirm_pw:
            flash('รหัสผ่านใหม่กับยืนยันรหัสผ่านไม่ตรงกัน', 'danger')
            return redirect(url_for('change_password'))

        users[sid]['password'] = hash_password(new_pw)
        save_users(users)

        flash('เปลี่ยนรหัสผ่านเรียบร้อยแล้ว กรุณาเข้าสู่ระบบใหม่', 'success')
        return redirect(url_for('index'))

    return render_template('change_password.html')

# ปรับแก้ route download ให้ไม่ซ้ำกัน (เลือกแบบนี้)
@app.route('/download/<event>/<file_format>')
def download_file(event, file_format):
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')
    file_path = os.path.join(DATA_DIR, f'{event}.{file_format}')
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "ไม่พบไฟล์", 404

@app.route('/register/<event>', methods=['GET', 'POST'])
def register_event(event):
    if 'user' not in session:
        return redirect('/login')

    user = session['user']
    sid = session['student_id']

    if request.method == 'POST':
        path = os.path.join(DATA_DIR, f'{event}.xlsx')
        df = pd.read_excel(path) if os.path.exists(path) else pd.DataFrame(columns=['StudentID','Name','Email','Position','Time'])

        if str(sid) in df['StudentID'].astype(str).values:
            flash('คุณได้ลงทะเบียนกิจกรรมนี้แล้ว', 'warning')
        else:
            now = datetime.now(zoneinfo.ZoneInfo('Asia/Bangkok'))
            time_str = now.strftime('%Y-%m-%d %H:%M:%S')
            full_name = f"{user.get('Prefix','')} {user.get('FirstName','')} {user.get('LastName','')}".strip()
            new_entry = pd.DataFrame([{
                'StudentID': sid,
                'Name': full_name,
                'Email': user.get('Email', ''),
                'Position': user.get('Position', ''),
                'Time': time_str
            }])
            df = pd.concat([df, new_entry], ignore_index=True)
            df.to_excel(path, index=False)
            flash('ลงทะเบียนกิจกรรมสำเร็จ', 'success')

        return redirect('/activity')

    return render_template('confirm_register.html', event=event, user=user)

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
            session['user']['name'] = f"{users[sid].get('FirstName', '')} {users[sid].get('LastName', '')}".strip()
            save_users(users)
            session.pop('editing', None)
            return redirect(url_for('index'))

    user = users[sid]
    editing = session.get('editing', False)
    return render_template('profile.html', user=user, user_id=sid, editing=editing)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    # ตรวจสอบสิทธิ์ admin
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')

    if request.method == 'POST':
        # รับ POST จากฟอร์มเพิ่มกิจกรรม
        event_name = request.form.get('new_event', '').strip()
        start = request.form.get('start', '').strip()
        end = request.form.get('end', '').strip()

        if not event_name or not start or not end:
            flash('กรุณากรอกข้อมูลให้ครบถ้วน', 'danger')
            return redirect(url_for('dashboard'))

        events = load_events()
        if any(e.get('name') == event_name for e in events if isinstance(e, dict)):
            flash('มีกิจกรรมชื่อนี้แล้วในระบบ', 'warning')
            return redirect(url_for('dashboard'))

        new_event = {
            'name': event_name,
            'start': start,
            'end': end
        }
        events.append(new_event)
        save_events(events)

        flash('เพิ่มกิจกรรมเรียบร้อยแล้ว', 'success')
        return redirect(url_for('dashboard'))

    events = load_events()
    event_list = [e for e in events if isinstance(e, dict)]
    event_names = [e['name'] for e in event_list]

    users = load_users()
    event_data = {}

    for event in event_list:
        name = event['name']
        path_xlsx = os.path.join(DATA_DIR, f'{name}.xlsx')
        if os.path.exists(path_xlsx):
            df = pd.read_excel(path_xlsx)
            records = df.to_dict(orient='records')
            # เติมข้อมูลจาก users ถ้า fields เป็น nan หรือ ว่าง
            for r in records:
                sid = str(r.get('StudentID', ''))
                user_info = users.get(sid, {})
                # เติมชื่อ, email, position ถ้าไม่มีหรือเป็น nan
                for field in ['Name', 'Email', 'Position']:
                    if not r.get(field) or (isinstance(r.get(field), float) and pd.isna(r.get(field))):
                        if field == 'Name':
                            r[field] = f"{user_info.get('Prefix', '')} {user_info.get('FirstName', '')} {user_info.get('LastName', '')}".strip()
                        else:
                            r[field] = user_info.get(field, '') or ''
                # เติมเวลาลงทะเบียนเป็นข้อความว่างถ้าเป็น nan
                if 'Time' in r and (not r['Time'] or (isinstance(r['Time'], float) and pd.isna(r['Time']))):
                    r['Time'] = ''
        else:
            records = []

        event_data[name] = records

    selected_event = request.args.get('event', '')

    registered_ids = set()
    if selected_event and selected_event in event_data:
        registered_ids = set(str(p['StudentID']) for p in event_data[selected_event])

    return render_template('dashboard.html',
                           events=event_data,
                           event_list=event_list,
                           event_names=event_names,
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
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect('/login')

    event_name = request.form.get('event_name', '').strip()
    student_id = request.form.get('student_id', '').strip()

    if not event_name or not student_id:
        flash('ข้อมูลไม่ครบถ้วน', 'warning')
        return redirect('/dashboard')

    path = os.path.join(DATA_DIR, f'{event_name}.xlsx')
    if not os.path.exists(path):
        flash('ไม่พบไฟล์กิจกรรม', 'danger')
        return redirect('/dashboard')

    try:
        df = pd.read_excel(path)
        original_len = len(df)
        df = df[df['StudentID'].astype(str) != student_id]
        updated_len = len(df)

        if original_len == updated_len:
            flash('ไม่พบรหัสนักศึกษานี้ในรายการ', 'warning')
        else:
            df.to_excel(path, index=False)
            flash('ลบรายชื่อเรียบร้อยแล้ว', 'success')

    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')

    return redirect('/dashboard')


@app.route('/dashboard/add_event', methods=['GET', 'POST'])
def add_event():
    # ตรวจสอบสิทธิ์ admin
    if 'user' not in session or not session['user'].get('is_admin'):
        return redirect('/')

    if request.method == 'POST':
        event_name = request.form.get('name', '').strip()
        start = request.form.get('start', '').strip()
        end = request.form.get('end', '').strip()

        if not event_name or not start or not end:
            flash('กรุณากรอกข้อมูลให้ครบถ้วน', 'danger')
            return redirect(url_for('add_event'))

        events = load_events()

        # ตรวจสอบว่าชื่อกิจกรรมซ้ำหรือไม่
        if any(e.get('name') == event_name for e in events if isinstance(e, dict)):
            flash('มีกิจกรรมชื่อนี้แล้วในระบบ', 'warning')
            return redirect(url_for('add_event'))

        # เพิ่มกิจกรรมใหม่
        new_event = {
            'name': event_name,
            'start': start,
            'end': end
        }
        events.append(new_event)
        save_events(events)

        flash('เพิ่มกิจกรรมเรียบร้อยแล้ว', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_event.html')


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

@app.route('/register', methods=['POST'])
def register():
    student_id = request.form['student_id'].strip()
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    if password != confirm_password:
        error = 'รหัสผ่านกับยืนยันรหัสผ่านไม่ตรงกัน'
        return render_template('index.html', error=error)

    users = load_users()
    if student_id in users:
        error = 'รหัสนักศึกษานี้ถูกใช้แล้ว'
        return render_template('index.html', error=error)

    hashed_pw = hash_password(password)

    # สร้างข้อมูลผู้ใช้ใหม่ (ใส่ฟิลด์อื่นๆ เป็นค่าว่างหรือค่าพื้นฐานได้)
    users[student_id] = {
        'password': hashed_pw,
        'FirstName': '',
        'LastName': '',
        'Email': '',
        'Position': '',
        'is_admin': False
    }
    save_users(users)

    flash('สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ')
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('student_id', None)
    session.pop('user', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
