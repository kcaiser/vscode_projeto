from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = '123456'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')  # user ou admin


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(200))
    project_name = db.Column(db.String(200))
    status = db.Column(db.String(50), default='Pendente')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    user = db.relationship('User', backref='documents')


class DocumentHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))

    document = db.relationship('Document', backref='history_records')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        role = request.form.get('role', 'user')

        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('Usuário já existe!')
            return redirect(url_for('register'))

        user = User(username=username, password=password, role=role)
        db.session.add(user)
        db.session.commit()

        flash('Usuário cadastrado com sucesso!')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()

        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            flash('Login realizado com sucesso!')
            return redirect(url_for('dashboard'))

        flash('Login inválido')

    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Nenhum arquivo enviado!')
            return redirect(url_for('dashboard'))

        file = request.files['file']

        if file.filename == '':
            flash('Selecione um arquivo!')
            return redirect(url_for('dashboard'))

        if not file.filename.lower().endswith('.pdf'):
            flash('Só é permitido arquivo PDF!')
            return redirect(url_for('dashboard'))

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        description = request.form.get('description')
        project_name = request.form.get('project_name')

        doc = Document(
            filename=filename,
            description=description,
            project_name=project_name,
            user_id=current_user.id
        )
        db.session.add(doc)
        db.session.commit()

        history = DocumentHistory(
            action=f'Documento enviado por {current_user.username}',
            document_id=doc.id
        )
        db.session.add(history)
        db.session.commit()

        flash('PDF enviado com sucesso!')

    if current_user.role == 'admin':
        docs = Document.query.order_by(Document.created_at.desc()).all()
    else:
        docs = Document.query.filter_by(user_id=current_user.id).order_by(Document.created_at.desc()).all()

    return render_template('dashboard.html', docs=docs)


@app.route('/download/<filename>')
@login_required
def download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/delete/<int:id>')
@login_required
def delete(id):
    doc = Document.query.get_or_404(id)

    if current_user.role != 'admin' and doc.user_id != current_user.id:
        flash('Você não tem permissão para excluir este documento.')
        return redirect(url_for('dashboard'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc.filename)

    if os.path.exists(file_path):
        os.remove(file_path)

    history = DocumentHistory(
        action=f'Documento excluído por {current_user.username}',
        document_id=doc.id
    )
    db.session.add(history)
    db.session.commit()

    db.session.delete(doc)
    db.session.commit()

    flash('Documento excluído com sucesso!')
    return redirect(url_for('dashboard'))


@app.route('/update_status/<int:id>/<status>')
@login_required
def update_status(id, status):
    if current_user.role != 'admin':
        flash('Apenas administradores podem alterar o status.')
        return redirect(url_for('dashboard'))

    doc = Document.query.get_or_404(id)

    if status not in ['Pendente', 'Autenticado', 'Recusado']:
        flash('Status inválido.')
        return redirect(url_for('dashboard'))

    doc.status = status
    db.session.commit()

    history = DocumentHistory(
        action=f'Status alterado para {status} por {current_user.username}',
        document_id=doc.id
    )
    db.session.add(history)
    db.session.commit()

    flash('Status atualizado com sucesso!')
    return redirect(url_for('dashboard'))


@app.route('/history/<int:id>')
@login_required
def history(id):
    doc = Document.query.get_or_404(id)

    if current_user.role != 'admin' and doc.user_id != current_user.id:
        flash('Você não tem permissão para ver este histórico.')
        return redirect(url_for('dashboard'))

    records = DocumentHistory.query.filter_by(document_id=id).order_by(DocumentHistory.timestamp.desc()).all()
    return render_template('history.html', records=records, doc=doc)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.')
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)