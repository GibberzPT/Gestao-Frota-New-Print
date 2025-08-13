import sqlite3
import os
import pandas as pd
import zipfile
import shutil
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, send_file, after_this_request
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Configuração da aplicação Flask
app = Flask(__name__)
app.secret_key = 't1rRS$^g8GZYYbWiADWoS'  # Mudar para uma chave segura em produção
app.config['VEHICLE_UPLOAD_FOLDER'] = 'static/fotos/veiculos'
app.config['INCIDENT_UPLOAD_FOLDER'] = 'static/fotos/incidencias'
app.config['ROUND_START_UPLOAD_FOLDER'] = 'static/fotos/saida'  # Pasta para fotos de saída
app.config['ROUND_END_UPLOAD_FOLDER'] = 'static/fotos/chegada'  # Pasta para fotos de chegada
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB de limite para o upload

DATABASE = 'gestao_frota.db'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """Inicializa a base de dados com todas as tabelas necessárias."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Tabela Utilizadores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Utilizadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                nivel_acesso INTEGER NOT NULL
            )
        ''')

        # Tabela Veiculos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Veiculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marca TEXT,
                modelo TEXT,
                nome TEXT NOT NULL,
                matricula TEXT NOT NULL UNIQUE,
                data_revisao TEXT,
                data_inspecao TEXT,
                foto_veiculo TEXT
            )
        ''')

        # Tabela Voltas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Voltas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_motorista INTEGER,
                id_veiculo INTEGER,
                destino TEXT NOT NULL,
                data_hora_saida DATETIME NOT NULL,
                kms_saida REAL NOT NULL,
                acompanhantes TEXT,
                fotos_saida TEXT,
                fotos_chegada TEXT,
                data_hora_chegada DATETIME,
                kms_chegada REAL,
                status INTEGER NOT NULL,
                FOREIGN KEY(id_motorista) REFERENCES Utilizadores(id),
                FOREIGN KEY(id_veiculo) REFERENCES Veiculos(id)
            )
        ''')

        # Tabela Incidencias
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Incidencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_utilizador INTEGER,
                id_veiculo INTEGER,
                descricao TEXT NOT NULL,
                data_reporte DATETIME NOT NULL,
                foto_incidencia TEXT,
                status INTEGER NOT NULL, -- 0: Em Aberto, 1: Em Resolucao, 2: Fechada
                FOREIGN KEY(id_utilizador) REFERENCES Utilizadores(id),
                FOREIGN KEY(id_veiculo) REFERENCES Veiculos(id)
            )
        ''')

        db.commit()


def update_db_schema():
    """
    Atualiza a estrutura da base de dados com colunas novas se necessário.
    Isto evita a perda de dados.
    """
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Verifica se a coluna 'id_veiculo' existe na tabela 'Incidencias'
        cursor.execute("PRAGMA table_info(Incidencias)")
        columns_incidencias = [col[1] for col in cursor.fetchall()]
        if 'id_veiculo' not in columns_incidencias:
            cursor.execute("ALTER TABLE Incidencias ADD COLUMN id_veiculo INTEGER")
            db.commit()
        if 'foto_incidencia' not in columns_incidencias:
            cursor.execute("ALTER TABLE Incidencias ADD COLUMN foto_incidencia TEXT")
            db.commit()

        # Verifica colunas em Veiculos
        cursor.execute("PRAGMA table_info(Veiculos)")
        columns_veiculos = [col[1] for col in cursor.fetchall()]
        if 'marca' not in columns_veiculos:
            cursor.execute("ALTER TABLE Veiculos ADD COLUMN marca TEXT")
            db.commit()
        if 'modelo' not in columns_veiculos:
            cursor.execute("ALTER TABLE Veiculos ADD COLUMN modelo TEXT")
            db.commit()
        cursor.execute("PRAGMA table_info(Voltas)")
        columns_voltas = [col[1] for col in cursor.fetchall()]
        if 'fotos_chegada' not in columns_voltas:
            cursor.execute("ALTER TABLE Voltas ADD COLUMN fotos_chegada TEXT")
            db.commit()


def add_initial_admin():
    """Adiciona um utilizador administrador se este não existir."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM Utilizadores WHERE nivel_acesso = 1")
        admin = cursor.fetchone()

        if not admin:
            password_hashed = generate_password_hash("admin123")
            cursor.execute(
                "INSERT INTO Utilizadores (nome, username, password, nivel_acesso) VALUES (?, ?, ?, ?)",
                ("Administrador", "admin", password_hashed, 1)
            )
            db.commit()


# --- ROTAS DA APLICAÇÃO ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM Utilizadores WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['nome']
            session['user_access_level'] = user['nivel_acesso']
            return redirect(url_for('dashboard'))
        else:
            flash("Nome de utilizador ou palavra-passe incorretos.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        cursor = db.cursor()

        try:
            password_hashed = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO Utilizadores (nome, username, password, nivel_acesso) VALUES (?, ?, ?, ?)",
                (name, username, password_hashed, 0)
            )
            db.commit()
            flash("Registo efetuado com sucesso! Por favor, faça login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Nome de utilizador já existe. Por favor, escolha outro.", "error")
            return redirect(url_for('register'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('user_access_level') == 1:
        return redirect(url_for('admin_vehicles'))
    else:
        return redirect(url_for('driver_dashboard'))


# ----------------- Rotas do Administrador -----------------

@app.route('/admin/vehicles', methods=['GET'])
def admin_vehicles():
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()

    # Lógica original para mostrar todos os veículos
    cursor.execute("""
            SELECT
                v.id, v.nome, v.matricula, v.data_revisao, v.data_inspecao, v.foto_veiculo,
                (SELECT kms_chegada FROM Voltas WHERE id_veiculo = v.id AND status = 1 ORDER BY data_hora_chegada DESC LIMIT 1) AS kms_atuais
            FROM Veiculos v
        """)
    vehicles = cursor.fetchall()
    # --- LÓGICA RESTAURADA PARA PROCESSAR AS FOTOS ---
    vehicles_with_urls = []
    for vehicle in vehicles:
        vehicle_dict = dict(vehicle)
        if vehicle_dict['foto_veiculo']:
            # Cria o URL completo para a foto
            vehicle_dict['foto_url'] = url_for('static', filename=vehicle_dict['foto_veiculo'])
        else:
            # Se não houver foto, usa uma imagem padrão
            vehicle_dict['foto_url'] = 'https://placehold.co/400x300?text=Sem+Foto'
        vehicles_with_urls.append(vehicle_dict)
    # --- FIM DA LÓGICA RESTAURADA ---

    # --- MODIFICAÇÃO INICIA ---
    # Adicionar a mesma lógica do painel do motorista aqui
    admin_user_id = session['user_id']

    # Buscar a volta atual do admin
    current_round = cursor.execute("""
        SELECT v.id, v.destino, v.kms_saida, veh.matricula AS veiculo_matricula
        FROM Voltas v
        JOIN Veiculos veh ON v.id_veiculo = veh.id
        WHERE v.id_motorista = ? AND v.status = 0
        LIMIT 1
    """, (admin_user_id,)).fetchone()

    # Buscar veículos que não estão em uso
    available_vehicles = cursor.execute("""
        SELECT id, nome, marca, modelo, matricula 
        FROM Veiculos 
        WHERE id NOT IN (SELECT id_veiculo FROM Voltas WHERE status = 0 AND id_veiculo IS NOT NULL)
    """).fetchall()
    # --- MODIFICAÇÃO TERMINA ---

    return render_template(
        'admin_dashboard.html',
        vehicles=vehicles_with_urls,
        active_tab='vehicles',
        current_round=current_round,  # Enviar a volta atual para o template
        available_vehicles=available_vehicles  # Enviar veículos disponíveis para o template
    )


@app.route('/admin/close_round/<int:round_id>', methods=['POST'])
def admin_close_round(round_id):
    """ Rota para o admin fechar uma volta. """
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()

    data_hora_chegada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        "UPDATE Voltas SET status = ?, data_hora_chegada = ? WHERE id = ?",
        (1, data_hora_chegada, round_id)
    )
    db.commit()
    flash("Volta fechada com sucesso pelo administrador!", "success")

    return redirect(url_for('admin_rounds'))


@app.route('/admin/delete_round/<int:round_id>', methods=['POST'])
def admin_delete_round(round_id):
    """ Rota para o admin eliminar uma volta e as suas fotos associadas. """
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()

    # 1. Vai buscar os caminhos de TODAS as fotos da volta ANTES de apagar
    cursor.execute("SELECT fotos_saida, fotos_chegada FROM Voltas WHERE id = ?", (round_id,))
    volta = cursor.fetchone()

    if volta:
        fotos_para_apagar = []
        # Adiciona fotos de saída à lista
        if volta['fotos_saida']:
            fotos_para_apagar.extend(volta['fotos_saida'].split(','))
        # Adiciona fotos de chegada à lista
        if volta['fotos_chegada']:
            fotos_para_apagar.extend(volta['fotos_chegada'].split(','))

        # 2. Itera sobre a lista e apaga cada ficheiro
        for foto_path in fotos_para_apagar:
            caminho_completo = os.path.join(app.root_path, 'static', foto_path)
            if os.path.exists(caminho_completo):
                os.remove(caminho_completo)

    # 3. Apaga o registo da volta da base de dados
    cursor.execute("DELETE FROM Voltas WHERE id = ?", (round_id,))
    db.commit()
    flash("Volta e fotos associadas eliminadas com sucesso!", "success")

    return redirect(url_for('admin_rounds'))


@app.route('/admin/add_vehicle', methods=['GET', 'POST'])
def add_vehicle():
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    if request.method == 'POST':
        nome = request.form['nome']
        matricula = request.form['matricula']
        data_revisao = request.form['data_revisao']
        data_inspecao = request.form['data_inspecao']
        foto = request.files['foto_veiculo']

        foto_path_db = None
        if foto and foto.filename != '':
            filename = secure_filename(foto.filename)
            foto_path_db = f'fotos/veiculos/{filename}'
            foto_path_fs = os.path.join(app.config['VEHICLE_UPLOAD_FOLDER'], filename)
            foto.save(foto_path_fs)

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO Veiculos (nome, matricula, data_revisao, data_inspecao, foto_veiculo) VALUES (?, ?, ?, ?, ?)",
                (nome, matricula, data_revisao, data_inspecao, foto_path_db)
            )
            db.commit()
            flash("Veículo adicionado com sucesso!", "success")
            return redirect(url_for('admin_vehicles'))
        except sqlite3.IntegrityError:
            flash("Matrícula já existe.", "error")
            return redirect(url_for('add_vehicle'))

    return render_template('manage_vehicle.html', title="Adicionar Veículo", vehicle=None)


@app.route('/admin/edit_vehicle/<int:vehicle_id>', methods=['GET', 'POST'])
def edit_vehicle(vehicle_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM Veiculos WHERE id = ?", (vehicle_id,))
    vehicle = cursor.fetchone()

    if not vehicle:
        return redirect(url_for('admin_vehicles'))

    if request.method == 'POST':
        nome = request.form['nome']
        matricula = request.form['matricula']
        data_revisao = request.form['data_revisao']
        data_inspecao = request.form['data_inspecao']
        foto = request.files.get('foto_veiculo')
        foto_path_db = vehicle['foto_veiculo']

        if foto and foto.filename != '':
            filename = secure_filename(foto.filename)
            foto_path_db = f'fotos/veiculos/{filename}'
            foto_path_fs = os.path.join(app.config['VEHICLE_UPLOAD_FOLDER'], filename)
            foto.save(foto_path_fs)

        try:
            cursor.execute(
                "UPDATE Veiculos SET nome = ?, matricula = ?, data_revisao = ?, data_inspecao = ?, foto_veiculo = ? WHERE id = ?",
                (nome, matricula, data_revisao, data_inspecao, foto_path_db, vehicle_id)
            )
            db.commit()
            flash("Veículo atualizado com sucesso!", "success")
            return redirect(url_for('admin_vehicles'))
        except sqlite3.IntegrityError:
            flash("Matrícula já existe.", "error")
            return redirect(url_for('edit_vehicle', vehicle_id=vehicle_id))

    return render_template('manage_vehicle.html', title="Editar Veículo", vehicle=vehicle)


@app.route('/admin/delete_vehicle/<int:vehicle_id>', methods=['POST'])
def delete_vehicle(vehicle_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT foto_veiculo FROM Veiculos WHERE id = ?", (vehicle_id,))
    vehicle = cursor.fetchone()

    if vehicle:
        foto_path_db = vehicle['foto_veiculo']
        cursor.execute("DELETE FROM Veiculos WHERE id = ?", (vehicle_id,))
        db.commit()
        if foto_path_db and os.path.exists(os.path.join(app.root_path, 'static', foto_path_db)):
            os.remove(os.path.join(app.root_path, 'static', foto_path_db))
        flash("Veículo removido com sucesso!", "success")

    return redirect(url_for('admin_vehicles'))


@app.route('/admin/users', methods=['GET'])
def admin_users():
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM Utilizadores")
    users = cursor.fetchall()
    return render_template('admin_dashboard.html', users=users, active_tab='users')


@app.route('/admin/add_user', methods=['GET', 'POST'])
def add_user():
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        access_level = int(request.form['access_level'])
        password_hashed = generate_password_hash(password)

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO Utilizadores (nome, username, password, nivel_acesso) VALUES (?, ?, ?, ?)",
                (name, username, password_hashed, access_level)
            )
            db.commit()
            flash("Utilizador adicionado com sucesso!", "success")
            return redirect(url_for('admin_users'))
        except sqlite3.IntegrityError:
            flash("Nome de utilizador já existe.", "error")
            return redirect(url_for('add_user'))

    return render_template('manage_user.html', title="Adicionar Utilizador", user=None)


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM Utilizadores WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        name = request.form['name']
        access_level = int(request.form['access_level'])
        cursor.execute("UPDATE Utilizadores SET nome = ?, nivel_acesso = ? WHERE id = ?", (name, access_level, user_id))
        db.commit()
        flash("Utilizador atualizado com sucesso!", "success")
        return redirect(url_for('admin_users'))

    return render_template('manage_user.html', title="Editar Utilizador", user=user)


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    if user_id == session.get('user_id'):
        flash("Não pode apagar a sua própria conta.", "error")
        return redirect(url_for('admin_users'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM Utilizadores WHERE id = ?", (user_id,))
    db.commit()
    flash("Utilizador removido com sucesso!", "success")
    return redirect(url_for('admin_users'))


@app.route('/admin/full_backup')
def full_backup():
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    backup_dir = tempfile.mkdtemp()

    try:
        db = get_db()

        # 1. GERAR O FICHEIRO EXCEL (sem alterações)
        excel_path = os.path.join(backup_dir, 'backup_dados.xlsx')
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            tabelas = ['Utilizadores', 'Veiculos', 'Voltas', 'Incidencias']
            for tabela in tabelas:
                df = pd.read_sql_query(f"SELECT * FROM {tabela}", db)
                df.to_excel(writer, sheet_name=tabela, index=False)

        # 2. COPIAR E RENOMEAR AS FOTOS
        fotos_dir = os.path.join(backup_dir, 'fotos_backup')
        veiculos_backup_dir = os.path.join(fotos_dir, 'veiculos')
        saida_backup_dir = os.path.join(fotos_dir, 'saida')
        chegada_backup_dir = os.path.join(fotos_dir, 'chegada')
        incidencias_backup_dir = os.path.join(fotos_dir, 'incidencias')

        for path in [veiculos_backup_dir, saida_backup_dir, chegada_backup_dir, incidencias_backup_dir]:
            os.makedirs(path)

        # Fotos dos Veículos (sem alterações)
        veiculos = db.execute(
            "SELECT id, nome, matricula, foto_veiculo FROM Veiculos WHERE foto_veiculo IS NOT NULL").fetchall()
        for veiculo in veiculos:
            if veiculo['foto_veiculo']:
                try:
                    extensao = veiculo['foto_veiculo'].split('.')[-1]
                    novo_nome = f"{veiculo['nome']}_{veiculo['matricula']}.{extensao}"
                    shutil.copy(os.path.join(app.root_path, 'static', veiculo['foto_veiculo']),
                                os.path.join(veiculos_backup_dir, novo_nome))
                except Exception as e:
                    print(f"Aviso: não foi possível copiar a foto do veículo {veiculo['matricula']}. Erro: {e}")

        # Fotos das Voltas (já atualizado)
        resultados = db.execute("""
            SELECT v.id as volta_id, v.destino, u.nome as motorista_nome, v.data_hora_saida, v.fotos_saida, v.fotos_chegada
            FROM Voltas v JOIN Utilizadores u ON v.id_motorista = u.id
        """).fetchall()
        for volta in resultados:
            motorista_safe = "".join(x for x in volta['motorista_nome'] if x.isalnum() or x in " _-").replace(" ", "_")
            destino_safe = "".join(x for x in volta['destino'] if x.isalnum() or x in " _-").replace(" ", "_")
            data_safe = datetime.strptime(volta['data_hora_saida'], '%Y-%m-%d %H:%M:%S').strftime('%Y%m%d_%H%M')
            if volta['fotos_saida']:
                for i, foto_path in enumerate(volta['fotos_saida'].split(',')):
                    try:
                        extensao = foto_path.split('.')[-1]
                        novo_nome = f"Volta_{destino_safe}_{motorista_safe}_{data_safe}_saida_{i + 1}.{extensao}"
                        shutil.copy(os.path.join(app.root_path, 'static', foto_path),
                                    os.path.join(saida_backup_dir, novo_nome))
                    except Exception as e:
                        print(f"Aviso: não foi possível copiar a foto de saída {foto_path}. Erro: {e}")
            if volta['fotos_chegada']:
                for i, foto_path in enumerate(volta['fotos_chegada'].split(',')):
                    try:
                        extensao = foto_path.split('.')[-1]
                        novo_nome = f"Volta_{destino_safe}_{motorista_safe}_{data_safe}_chegada_{i + 1}.{extensao}"
                        shutil.copy(os.path.join(app.root_path, 'static', foto_path),
                                    os.path.join(chegada_backup_dir, novo_nome))
                    except Exception as e:
                        print(f"Aviso: não foi possível copiar a foto de chegada {foto_path}. Erro: {e}")

        # --- MODIFICAÇÃO COMEÇA AQUI ---

        # Fotos das Incidências
        incidencias = db.execute("""
            SELECT i.id, i.descricao, u.nome, i.data_reporte, i.foto_incidencia 
            FROM Incidencias i 
            JOIN Utilizadores u ON i.id_utilizador = u.id 
            WHERE i.foto_incidencia IS NOT NULL AND i.foto_incidencia != ''
        """).fetchall()  # Adicionado i.descricao

        for inc in incidencias:
            # Prepara os nomes para serem seguros para nomes de ficheiro
            motorista_safe = "".join(x for x in inc['nome'] if x.isalnum() or x in " _-").replace(" ", "_")
            # Novo: Obter, limpar e encurtar a descrição para usar no nome do ficheiro
            descricao_safe = "".join(x for x in inc['descricao'] if x.isalnum() or x in " _-").replace(" ", "_")[
                :25]  # Limita aos primeiros 25 caracteres
            data_safe = datetime.strptime(inc['data_reporte'], '%Y-%m-%d %H:%M:%S').strftime('%Y%m%d_%H%M')

            if inc['foto_incidencia']:
                for i, foto_path in enumerate(inc['foto_incidencia'].split(',')):
                    try:
                        extensao = foto_path.split('.')[-1]
                        # Alterado: Usa a descrição em vez do ID da incidência
                        novo_nome = f"Incidencia_{descricao_safe}_{motorista_safe}_{data_safe}_{i + 1}.{extensao}"
                        shutil.copy(os.path.join(app.root_path, 'static', foto_path),
                                    os.path.join(incidencias_backup_dir, novo_nome))
                    except Exception as e:
                        print(f"Aviso: não foi possível copiar a foto da incidência {foto_path}. Erro: {e}")

        # --- MODIFICAÇÃO TERMINA AQUI ---

        # 3. CRIAR O FICHEIRO ZIP (sem alterações)
        zip_filename = f"backup_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(backup_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, backup_dir)
                    zipf.write(full_path, arcname)

        # 4. ENVIAR O ZIP E LIMPAR (sem alterações)
        @after_this_request
        def cleanup(response):
            try:
                os.remove(zip_path)
                shutil.rmtree(backup_dir)
            except Exception as e:
                print(f"Erro na limpeza do backup: {e}")
            return response

        return send_file(zip_path, as_attachment=True)

    except Exception as e:
        shutil.rmtree(backup_dir)
        flash(f"Ocorreu um erro ao gerar o backup: {e}", "error")
        return redirect(url_for('admin_vehicles'))

@app.route('/admin/incidents')
def admin_incidents():
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT i.id, i.descricao, i.data_reporte, i.foto_incidencia, i.status, u.nome AS motorista_nome, v.matricula AS veiculo_matricula
        FROM Incidencias i
        LEFT JOIN Utilizadores u ON i.id_utilizador = u.id
        LEFT JOIN Veiculos v ON i.id_veiculo = v.id
        ORDER BY i.data_reporte DESC
    """)
    incidents_raw = cursor.fetchall()
    incidents = [dict(inc) for inc in incidents_raw]

    # --- LÓGICA ADICIONADA PARA O MODAL ---
    # Buscar motoristas e veículos para o formulário de adição no pop-up
    motoristas = cursor.execute("SELECT id, nome FROM Utilizadores WHERE nivel_acesso = 0").fetchall()
    veiculos = cursor.execute("SELECT id, nome, matricula FROM Veiculos").fetchall()
    # --- FIM DA LÓGICA ADICIONADA ---

    status_map = {0: 'Em Aberto', 1: 'Em Resolução', 2: 'Fechada'}
    return render_template('admin_dashboard.html',
                           incidents=incidents,
                           status_map=status_map,
                           active_tab='incidents',
                           motoristas=motoristas,  # <-- Passa a lista de motoristas
                           veiculos=veiculos)  # <-- Passa a lista de veículos

@app.route('/admin/add_incident', methods=['GET', 'POST'])
def add_incident():
    """
    Rota para o admin adicionar uma nova incidência com múltiplas fotos.
    """
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome FROM Utilizadores")
    motoristas = cursor.fetchall()
    cursor.execute("SELECT id, nome, matricula FROM Veiculos")
    veiculos = cursor.fetchall()

    if request.method == 'POST':
        id_motorista = request.form['id_motorista']
        id_veiculo = request.form['id_veiculo']
        descricao = request.form['descricao']
        data_reporte = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = int(request.form.get('status', 0))

        # --- MODIFICAÇÃO INICIA ---
        fotos = request.files.getlist('foto_incidencia')
        photo_paths = []

        if fotos and fotos[0].filename != '':
            if not os.path.exists(app.config['INCIDENT_UPLOAD_FOLDER']):
                os.makedirs(app.config['INCIDENT_UPLOAD_FOLDER'])

            for foto in fotos:
                if foto and foto.filename != '':
                    filename = secure_filename(foto.filename)
                    unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                    foto_path_db = f'fotos/incidencias/{unique_filename}'
                    foto_path_fs = os.path.join(app.config['INCIDENT_UPLOAD_FOLDER'], unique_filename)
                    foto.save(foto_path_fs)
                    photo_paths.append(foto_path_db)

        fotos_str = ",".join(photo_paths)
        # --- MODIFICAÇÃO TERMINA ---

        cursor.execute(
            "INSERT INTO Incidencias (id_utilizador, id_veiculo, descricao, data_reporte, foto_incidencia, status) VALUES (?, ?, ?, ?, ?, ?)",
            (id_motorista, id_veiculo, descricao, data_reporte, fotos_str, status)
        )
        db.commit()
        flash("Incidência adicionada com sucesso!", "success")
        return redirect(url_for('admin_incidents'))

    return render_template('manage_incident.html', title="Adicionar Incidência", incident=None, motoristas=motoristas, veiculos=veiculos)


@app.route('/admin/edit_incident/<int:incident_id>', methods=['GET', 'POST'])
def edit_incident(incident_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    incident = cursor.execute("SELECT * FROM Incidencias WHERE id = ?", (incident_id,)).fetchone()

    if not incident:
        flash("Incidência não encontrada.", "error")
        return redirect(url_for('admin_incidents'))

    motoristas = cursor.execute("SELECT id, nome FROM Utilizadores").fetchall()
    veiculos = cursor.execute("SELECT id, nome, matricula FROM Veiculos").fetchall()

    if request.method == 'POST':
        id_motorista = request.form['id_motorista']
        id_veiculo = request.form['id_veiculo']
        descricao = request.form['descricao']
        status = int(request.form['status'])

        # --- MODIFICAÇÃO INICIA ---
        fotos = request.files.getlist('foto_incidencia')
        fotos_str = incident['foto_incidencia']

        if fotos and fotos[0].filename != '':
            photo_paths = []

            if incident['foto_incidencia']:
                old_photos = incident['foto_incidencia'].split(',')
                for old_photo in old_photos:
                    old_photo_path = os.path.join(app.root_path, 'static', old_photo)
                    if os.path.exists(old_photo_path):
                        os.remove(old_photo_path)

            for foto in fotos:
                if foto and foto.filename != '':
                    filename = secure_filename(foto.filename)
                    unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                    foto_path_db = f'fotos/incidencias/{unique_filename}'
                    foto_path_fs = os.path.join(app.config['INCIDENT_UPLOAD_FOLDER'], unique_filename)
                    foto.save(foto_path_fs)
                    photo_paths.append(foto_path_db)

            fotos_str = ",".join(photo_paths)
        # --- MODIFICAÇÃO TERMINA ---

        cursor.execute(
            "UPDATE Incidencias SET id_utilizador = ?, id_veiculo = ?, descricao = ?, status = ?, foto_incidencia = ? WHERE id = ?",
            (id_motorista, id_veiculo, descricao, status, fotos_str, incident_id)
        )
        db.commit()
        flash("Incidência atualizada com sucesso!", "success")
        return redirect(url_for('admin_incidents'))

    return render_template('manage_incident.html', title="Editar Incidência", incident=incident, motoristas=motoristas,
                           veiculos=veiculos)


@app.route('/admin/delete_incident/<int:incident_id>', methods=['POST'])
def delete_incident(incident_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    # 1. Vai buscar a string com os caminhos das fotos
    cursor.execute("SELECT foto_incidencia FROM Incidencias WHERE id = ?", (incident_id,))
    incident = cursor.fetchone()

    if incident:
        # --- MODIFICAÇÃO INICIA AQUI ---
        # 2. Separa a string numa lista de fotos e apaga cada uma
        if incident['foto_incidencia']:
            lista_fotos = incident['foto_incidencia'].split(',')
            for foto_path in lista_fotos:
                caminho_completo = os.path.join(app.root_path, 'static', foto_path)
                if os.path.exists(caminho_completo):
                    os.remove(caminho_completo)
        # --- MODIFICAÇÃO TERMINA AQUI ---

        # 3. Apaga o registo da base de dados
        cursor.execute("DELETE FROM Incidencias WHERE id = ?", (incident_id,))
        db.commit()
        flash("Incidência removida com sucesso!", "success")

    return redirect(url_for('admin_incidents'))


@app.route('/admin/close_incident/<int:incident_id>', methods=['POST'])
def close_incident(incident_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "UPDATE Incidencias SET status = ? WHERE id = ?",
        (2, incident_id)  # Status 2 = Fechada
    )
    db.commit()
    flash("Incidência fechada com sucesso!", "success")

    return redirect(url_for('admin_incidents'))


@app.route('/admin/rounds', methods=['GET'])
def admin_rounds():
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            v.id, v.destino, v.data_hora_saida, v.data_hora_chegada, v.status,
            v.kms_saida, v.kms_chegada, -- <-- CAMPOS ADICIONADOS AQUI
            u.nome AS motorista_nome, 
            veh.matricula AS veiculo_matricula
        FROM Voltas v
        LEFT JOIN Utilizadores u ON v.id_motorista = u.id
        LEFT JOIN Veiculos veh ON v.id_veiculo = veh.id
        ORDER BY v.data_hora_saida DESC
    """)
    rounds = cursor.fetchall()
    status_map = {0: 'Em Andamento', 1: 'Concluída'}
    return render_template('admin_dashboard.html', rounds=rounds, status_map=status_map, active_tab='rounds')


@app.route('/admin/edit_round/<int:round_id>', methods=['GET', 'POST'])
def admin_edit_round(round_id):
    if 'user_id' not in session or session.get('user_access_level') != 1:
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()

    round_to_edit = cursor.execute("SELECT * FROM Voltas WHERE id = ?", (round_id,)).fetchone()
    if not round_to_edit:
        flash("Volta não encontrada.", "error")
        return redirect(url_for('admin_rounds'))

    if request.method == 'POST':
        # Recolhe os dados do formulário
        id_motorista = request.form['id_motorista']
        id_veiculo = request.form['id_veiculo']
        destino = request.form['destino']
        kms_saida = request.form['kms_saida']
        kms_chegada = request.form['kms_chegada'] if request.form['kms_chegada'] else None
        data_hora_saida_form = request.form['data_hora_saida']
        data_hora_saida_db = data_hora_saida_form.replace('T', ' ') + ':00'
        data_hora_chegada_form = request.form['data_hora_chegada']
        data_hora_chegada_db = None
        if data_hora_chegada_form:
            data_hora_chegada_db = data_hora_chegada_form.replace('T', ' ') + ':00'

        # --- LÓGICA DE GESTÃO DE FOTOS ---

        # Processa Fotos de Saída
        fotos_saida_str = round_to_edit['fotos_saida']
        novas_fotos_saida = request.files.getlist('fotos_saida')
        if novas_fotos_saida and novas_fotos_saida[0].filename:
            if round_to_edit['fotos_saida']:  # Apaga fotos antigas
                for old_photo in round_to_edit['fotos_saida'].split(','):
                    if os.path.exists(os.path.join(app.root_path, 'static', old_photo)):
                        os.remove(os.path.join(app.root_path, 'static', old_photo))

            new_paths = []
            for foto in novas_fotos_saida:
                filename = secure_filename(foto.filename)
                unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                foto.save(os.path.join(app.config['ROUND_START_UPLOAD_FOLDER'], unique_filename))
                new_paths.append(f'fotos/saida/{unique_filename}')
            fotos_saida_str = ",".join(new_paths)

        # Processa Fotos de Chegada
        fotos_chegada_str = round_to_edit['fotos_chegada']
        novas_fotos_chegada = request.files.getlist('fotos_chegada')
        if novas_fotos_chegada and novas_fotos_chegada[0].filename:
            if round_to_edit['fotos_chegada']:  # Apaga fotos antigas
                for old_photo in round_to_edit['fotos_chegada'].split(','):
                    if os.path.exists(os.path.join(app.root_path, 'static', old_photo)):
                        os.remove(os.path.join(app.root_path, 'static', old_photo))

            new_paths = []
            for foto in novas_fotos_chegada:
                filename = secure_filename(foto.filename)
                unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                foto.save(os.path.join(app.config['ROUND_END_UPLOAD_FOLDER'], unique_filename))
                new_paths.append(f'fotos/chegada/{unique_filename}')
            fotos_chegada_str = ",".join(new_paths)

        # --- FIM DA LÓGICA DE FOTOS ---

        # Atualiza a base de dados com todos os campos, incluindo as fotos
        cursor.execute("""
            UPDATE Voltas 
            SET id_motorista = ?, id_veiculo = ?, destino = ?, 
                data_hora_saida = ?, data_hora_chegada = ?,
                kms_saida = ?, kms_chegada = ?,
                fotos_saida = ?, fotos_chegada = ?
            WHERE id = ?
        """, (id_motorista, id_veiculo, destino,
              data_hora_saida_db, data_hora_chegada_db,
              kms_saida, kms_chegada,
              fotos_saida_str, fotos_chegada_str,
              round_id))
        db.commit()

        flash("Volta atualizada com sucesso!", "success")
        return redirect(url_for('admin_rounds'))

    # Se for GET, busca dados para os dropdowns e mostra o formulário
    motoristas = cursor.execute("SELECT id, nome FROM Utilizadores").fetchall()
    veiculos = cursor.execute("SELECT id, nome, matricula FROM Veiculos").fetchall()

    return render_template('edit_round.html', round=round_to_edit, motoristas=motoristas, veiculos=veiculos)

# ----------------- Rotas do Motorista (ATUALIZADAS) -----------------
@app.route('/driver_dashboard')
def driver_dashboard():
    """
    Painel principal para o motorista.
    """
    if 'user_id' not in session or session.get('user_access_level') != 0:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    # 1. Obter a volta ATUAL do motorista
    current_round = cursor.execute("""
        SELECT v.id, v.destino, v.data_hora_saida, v.kms_saida, v.acompanhantes,
               veh.nome AS veiculo_nome, veh.matricula AS veiculo_matricula
        FROM Voltas v JOIN Veiculos veh ON v.id_veiculo = veh.id
        WHERE v.id_motorista = ? AND v.status = 0 LIMIT 1
    """, (user_id,)).fetchone()

    # 2. Obter TODAS as voltas em curso
    all_open_rounds_raw = cursor.execute("""
        SELECT v.id, v.destino, v.data_hora_saida, u.nome AS motorista_nome, 
               v.id_motorista, veh.matricula AS veiculo_matricula, 
               veh.foto_veiculo AS veiculo_foto, veh.nome as veiculo_nome
        FROM Voltas v JOIN Utilizadores u ON v.id_motorista = u.id
        JOIN Veiculos veh ON v.id_veiculo = veh.id WHERE v.status = 0 ORDER BY v.data_hora_saida DESC
    """).fetchall()
    all_open_rounds = [dict(r) for r in all_open_rounds_raw]
    for r in all_open_rounds:
        if r.get('data_hora_saida'):
            r['data_hora_saida'] = datetime.strptime(r['data_hora_saida'][:19], '%Y-%m-%d %H:%M:%S')

    # 3. Obter veículos disponíveis e todos os veículos
    available_vehicles = cursor.execute(
        "SELECT id, nome, matricula FROM Veiculos WHERE id NOT IN (SELECT id_veiculo FROM Voltas WHERE status = 0 AND id_veiculo IS NOT NULL)").fetchall()
    all_vehicles = cursor.execute("SELECT id, nome, matricula FROM Veiculos ORDER BY nome").fetchall()

    # --- CORREÇÃO NA FORMATAÇÃO DA DATA ---
    # 4. Obter as incidências do motorista
    driver_incidents_raw = cursor.execute("""
        SELECT i.id, i.descricao, i.data_reporte, i.status, i.foto_incidencia, v.matricula AS veiculo_matricula
        FROM Incidencias i JOIN Veiculos v ON i.id_veiculo = v.id WHERE i.id_utilizador = ? ORDER BY i.data_reporte DESC
    """, (user_id,)).fetchall()
    driver_incidents = []
    for incident in driver_incidents_raw:
        incident_dict = dict(incident)
        if incident_dict.get('data_reporte'):
            # Pega apenas os primeiros 19 caracteres (YYYY-MM-DD HH:MM:SS) para evitar erros
            date_string = incident_dict['data_reporte'][:19]
            try:
                incident_dict['data_reporte'] = datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S').strftime(
                    '%d/%m/%Y %H:%M')
            except ValueError:
                incident_dict['data_reporte'] = "Data Inválida"  # Caso a data esteja muito corrompida
        incident_dict['fotos'] = incident_dict['foto_incidencia'].split(',') if incident_dict.get(
            'foto_incidencia') else []
        driver_incidents.append(incident_dict)

    # 5. Obter as voltas fechadas do motorista
    closed_rounds = cursor.execute("""
        SELECT v.destino, v.data_hora_chegada, v.kms_saida, v.kms_chegada, 
               veh.matricula, veh.foto_veiculo, veh.nome as veiculo_nome
        FROM Voltas v JOIN Veiculos veh ON v.id_veiculo = veh.id
        WHERE v.id_motorista = ? AND v.status = 1 ORDER BY v.data_hora_chegada DESC
    """, (user_id,)).fetchall()

    return render_template('driver_dashboard.html', current_round=current_round, all_open_rounds=all_open_rounds,
                           available_vehicles=available_vehicles, all_vehicles=all_vehicles,
                           driver_incidents=driver_incidents, closed_rounds=closed_rounds)


# ... (outras rotas) ...

@app.route('/driver/edit_incident/<int:incident_id>', methods=['GET', 'POST'])
def editar_incidencia_motorista(incident_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = get_db()

    incident_to_edit = db.execute("SELECT * FROM Incidencias WHERE id = ? AND id_utilizador = ?",
                                  (incident_id, user_id)).fetchone()
    if not incident_to_edit:
        flash("Incidência não encontrada ou não tem permissão para a editar.", "error")
        return redirect(url_for('driver_dashboard'))

    if request.method == 'POST':
        descricao = request.form['descricao']
        data_reporte_form = request.form['data_reporte']
        # Garante que os segundos são adicionados corretamente
        data_reporte_db = data_reporte_form.replace('T', ' ') + ':00'

        fotos_str = incident_to_edit['foto_incidencia']
        novas_fotos = request.files.getlist('fotos_incidencia')
        if novas_fotos and novas_fotos[0].filename:
            if incident_to_edit['foto_incidencia']:
                for old_photo in incident_to_edit['foto_incidencia'].split(','):
                    if os.path.exists(os.path.join(app.root_path, 'static', old_photo)):
                        os.remove(os.path.join(app.root_path, 'static', old_photo))

            new_paths = []
            for foto in novas_fotos:
                filename = secure_filename(foto.filename)
                unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                foto.save(os.path.join(app.config['INCIDENT_UPLOAD_FOLDER'], unique_filename))
                new_paths.append(f'fotos/incidencias/{unique_filename}')
            fotos_str = ",".join(new_paths)

        novo_status = 0

        db.execute(
            "UPDATE Incidencias SET descricao = ?, data_reporte = ?, foto_incidencia = ?, status = ? WHERE id = ?",
            (descricao, data_reporte_db, fotos_str, novo_status, incident_id))
        db.commit()

        flash("Incidência atualizada com sucesso! O estado foi alterado para 'Em Aberto' para revisão.", "success")
        return redirect(url_for('driver_dashboard'))

    return render_template('edit_incident_driver.html', incident=incident_to_edit)

@app.route('/iniciar_volta', methods=['POST'])
def iniciar_volta():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    id_veiculo = request.form['id_veiculo']
    destino = request.form['destino']
    kms_saida = float(request.form['kms_saida'])
    # --- NOVA LINHA ---
    acompanhantes = request.form.get('acompanhantes', '')  # Recolhe as observações

    data_hora_saida_form = request.form['data_hora_saida']
    data_hora_saida_db = data_hora_saida_form.replace('T', ' ') + ':00'

    db = get_db()
    cursor = db.cursor()
    if cursor.execute("SELECT 1 FROM Voltas WHERE id_motorista = ? AND status = 0", (user_id,)).fetchone():
        flash("Já tem uma volta em andamento. Feche a volta atual primeiro.", "error")
        return redirect(
            url_for('driver_dashboard') if session.get('user_access_level') == 0 else url_for('admin_vehicles'))

    fotos = request.files.getlist('fotos_saida')
    photo_paths = []
    if fotos and fotos[0].filename:
        for foto in fotos:
            filename = secure_filename(foto.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
            foto.save(os.path.join(app.config['ROUND_START_UPLOAD_FOLDER'], unique_filename))
            photo_paths.append(f'fotos/saida/{unique_filename}')
    fotos_str = ",".join(photo_paths)

    cursor.execute(
        # --- ALTERAÇÃO AQUI ---
        "INSERT INTO Voltas (id_motorista, id_veiculo, destino, data_hora_saida, kms_saida, fotos_saida, acompanhantes, status) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
        (user_id, id_veiculo, destino, data_hora_saida_db, kms_saida, fotos_str, acompanhantes)
    )
    db.commit()
    flash("Volta iniciada com sucesso!", "success")

    return redirect(url_for('driver_dashboard') if session.get('user_access_level') == 0 else url_for('admin_vehicles'))


@app.route('/fechar_volta/<int:round_id>', methods=['POST'])
def fechar_volta(round_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    kms_chegada = float(request.form['kms_chegada'])

    db = get_db()
    cursor = db.cursor()

    # --- NOVA VALIDAÇÃO ---
    # 1. Buscar os KMs de saída da volta que está a ser fechada
    volta_db = cursor.execute("SELECT kms_saida FROM Voltas WHERE id = ? AND id_motorista = ?",
                              (round_id, user_id)).fetchone()

    if not volta_db:
        flash("Volta não encontrada ou não tem permissão para a fechar.", "error")
        return redirect(
            url_for('driver_dashboard') if session.get('user_access_level') == 0 else url_for('admin_rounds'))

    kms_saida = volta_db['kms_saida']

    # 2. Comparar os KMs
    if kms_chegada < kms_saida:
        flash(f"Erro: Os KMs de chegada ({kms_chegada}) não podem ser inferiores aos KMs de saída ({kms_saida}).",
              "error")
        # Redireciona para o painel correto
        if session.get('user_access_level') == 1:
            return redirect(url_for('admin_rounds'))
        else:
            return redirect(url_for('driver_dashboard'))
    # --- FIM DA VALIDAÇÃO ---

    data_hora_chegada_form = request.form['data_hora_chegada']
    data_hora_chegada_db = data_hora_chegada_form.replace('T', ' ') + ':00'

    fotos = request.files.getlist('fotos_chegada')
    photo_paths = []
    if fotos and fotos[0].filename:
        for foto in fotos:
            filename = secure_filename(foto.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
            foto.save(os.path.join(app.config['ROUND_END_UPLOAD_FOLDER'], unique_filename))
            photo_paths.append(f'fotos/chegada/{unique_filename}')
    fotos_str = ",".join(photo_paths)

    cursor.execute(
        "UPDATE Voltas SET data_hora_chegada = ?, kms_chegada = ?, status = ?, fotos_chegada = ? WHERE id = ? AND id_motorista = ?",
        (data_hora_chegada_db, kms_chegada, 1, fotos_str, round_id, user_id)
    )
    db.commit()
    flash("Volta fechada com sucesso!", "success")

    if session.get('user_access_level') == 1:
        return redirect(url_for('admin_rounds'))
    else:
        return redirect(url_for('driver_dashboard'))

@app.route('/editar_volta/<int:round_id>', methods=['GET'])
def editar_volta(round_id):
    flash("Funcionalidade de edição ainda não implementada.", "info")
    return redirect(url_for('driver_dashboard'))


@app.route('/driver/edit_round/<int:round_id>', methods=['GET', 'POST'])
def editar_volta_motorista(round_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = get_db()

    # Garante que a volta a editar pertence ao motorista e está aberta
    round_to_edit = db.execute("SELECT * FROM Voltas WHERE id = ? AND id_motorista = ? AND status = 0",
                               (round_id, user_id)).fetchone()
    if not round_to_edit:
        flash("Volta não encontrada ou não tem permissão para a editar.", "error")
        return redirect(url_for('driver_dashboard'))

    if request.method == 'POST':
        destino = request.form['destino']
        kms_saida = request.form['kms_saida']
        acompanhantes = request.form.get('acompanhantes', '')

        # --- LÓGICA DE DATA/HORA ADICIONADA ---
        data_hora_saida_form = request.form['data_hora_saida']
        data_hora_saida_db = data_hora_saida_form.replace('T', ' ') + ':00'

        # --- LÓGICA DE GESTÃO DE FOTOS ADICIONADA ---
        fotos_saida_str = round_to_edit['fotos_saida']
        novas_fotos_saida = request.files.getlist('fotos_saida')
        if novas_fotos_saida and novas_fotos_saida[0].filename:
            # Apaga as fotos antigas do disco
            if round_to_edit['fotos_saida']:
                for old_photo in round_to_edit['fotos_saida'].split(','):
                    if os.path.exists(os.path.join(app.root_path, 'static', old_photo)):
                        os.remove(os.path.join(app.root_path, 'static', old_photo))

            # Guarda as novas fotos
            new_paths = []
            for foto in novas_fotos_saida:
                filename = secure_filename(foto.filename)
                unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                foto.save(os.path.join(app.config['ROUND_START_UPLOAD_FOLDER'], unique_filename))
                new_paths.append(f'fotos/saida/{unique_filename}')
            fotos_saida_str = ",".join(new_paths)

        # Atualiza a base de dados com todos os campos
        db.execute("""
            UPDATE Voltas 
            SET destino = ?, kms_saida = ?, acompanhantes = ?, data_hora_saida = ?, fotos_saida = ? 
            WHERE id = ?
        """, (destino, kms_saida, acompanhantes, data_hora_saida_db, fotos_saida_str, round_id))
        db.commit()
        flash("Volta atualizada com sucesso!", "success")
        return redirect(url_for('driver_dashboard'))

    return render_template('edit_round_driver.html', round=round_to_edit)

@app.route('/reportar_incidencia', methods=['POST'])
def reportar_incidencia():
    # --- MODIFICAÇÃO 1: Permitir acesso a qualquer utilizador logado ---
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    id_veiculo = request.form['id_veiculo_incidencia']
    descricao = request.form['descricao_incidencia']
    data_reporte = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fotos = request.files.getlist('fotos_incidencia')
    photo_paths = []

    if fotos and fotos[0].filename != '':
        if not os.path.exists(app.config['INCIDENT_UPLOAD_FOLDER']):
            os.makedirs(app.config['INCIDENT_UPLOAD_FOLDER'])

        for foto in fotos:
            if foto and foto.filename != '':
                filename = secure_filename(foto.filename)
                unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
                foto_path_db = f'fotos/incidencias/{unique_filename}'
                foto_path_fs = os.path.join(app.config['INCIDENT_UPLOAD_FOLDER'], unique_filename)
                foto.save(foto_path_fs)
                photo_paths.append(foto_path_db)

    fotos_str = ",".join(photo_paths)

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO Incidencias (id_utilizador, id_veiculo, descricao, data_reporte, foto_incidencia, status) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, id_veiculo, descricao, data_reporte, fotos_str, 0)
    )
    db.commit()
    flash("Incidência reportada com sucesso!", "success")

    # --- MODIFICAÇÃO 2: Redirecionar para o painel correto ---
    if session.get('user_access_level') == 1:
        return redirect(url_for('admin_incidents'))
    else:
        return redirect(url_for('driver_dashboard'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
        update_db_schema()
        add_initial_admin()

    for folder in ['veiculos', 'incidencias', 'saida', 'chegada']:
        os.makedirs(os.path.join('static', 'fotos', folder), exist_ok=True)

    app.run(debug=True)