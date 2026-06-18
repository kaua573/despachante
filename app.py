from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, send_from_directory
from markupsafe import Markup
import sqlite3, os, io, uuid, shutil, threading, time, glob
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT

app = Flask(__name__)
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'despachante.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads', 'documentos')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Helper Jinja para inserir ícones SVG inline
def icon_svg(nome, classe='icon'):
    caminho = os.path.join(BASE_DIR, 'static', 'icons', f'{nome}.svg')
    if not os.path.exists(caminho):
        return ''
    with open(caminho, 'r', encoding='utf-8') as f:
        svg = f.read()
    if 'class="' in svg.split('>', 1)[0]:
        # já existe atributo class na tag <svg>, substitui o valor
        import re
        svg = re.sub(r'class="[^"]*"', f'class="{classe}"', svg, count=1)
    else:
        svg = svg.replace('<svg ', f'<svg class="{classe}" ', 1)
    return Markup(svg)

app.jinja_env.globals['icon'] = icon_svg

@app.context_processor
def inject_tema():
    """Disponibiliza o tema atual (modo + cores) em todos os templates,
    para já renderizar com as variáveis CSS corretas (evita 'flash' de tema errado)."""
    try:
        modo = get_config('tema_modo', 'claro')
        cor_chave = get_config('tema_cor', 'azul')
    except Exception:
        modo, cor_chave = 'claro', 'azul'
    cor = PALETA_CORES.get(cor_chave, PALETA_CORES['azul'])
    return {'tema_modo': modo, 'tema_cor_chave': cor_chave, 'tema_cor': cor}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT,
            telefone TEXT,
            email TEXT,
            observacao TEXT,
            criado_em TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS veiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            placa TEXT NOT NULL,
            renavam TEXT,
            proprietario TEXT,
            marca_modelo TEXT,
            situacao TEXT DEFAULT 'ativo',
            especie TEXT DEFAULT 'passeio',
            observacao TEXT,
            criado_em TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        );

        CREATE TABLE IF NOT EXISTS ipva (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            veiculo_id INTEGER NOT NULL,
            ano_referencia INTEGER NOT NULL,
            valor REAL,
            vencimento TEXT,
            pago INTEGER DEFAULT 0,
            data_pagamento TEXT,
            observacao TEXT,
            FOREIGN KEY (veiculo_id) REFERENCES veiculos(id)
        );

        CREATE TABLE IF NOT EXISTS licenciamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            veiculo_id INTEGER NOT NULL,
            ano_referencia INTEGER NOT NULL,
            valor REAL,
            vencimento TEXT,
            pago INTEGER DEFAULT 0,
            data_pagamento TEXT,
            observacao TEXT,
            FOREIGN KEY (veiculo_id) REFERENCES veiculos(id)
        );

        CREATE TABLE IF NOT EXISTS multas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            veiculo_id INTEGER NOT NULL,
            auto_infracao TEXT,
            data_infracao TEXT,
            descricao TEXT,
            valor REAL,
            vencimento TEXT,
            pago INTEGER DEFAULT 0,
            data_pagamento TEXT,
            observacao TEXT,
            FOREIGN KEY (veiculo_id) REFERENCES veiculos(id)
        );

        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            data_documento TEXT NOT NULL,
            categoria TEXT NOT NULL,
            observacao TEXT,
            arquivo TEXT,
            criado_em TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        );

        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        );
    ''')
    # Migrações suaves para bases já existentes
    migrations = [
        "ALTER TABLE clientes ADD COLUMN cpf TEXT",
        "ALTER TABLE clientes ADD COLUMN observacao TEXT",
        "ALTER TABLE veiculos ADD COLUMN proprietario TEXT",
        "ALTER TABLE veiculos ADD COLUMN marca_modelo TEXT",
        "ALTER TABLE veiculos ADD COLUMN situacao TEXT DEFAULT 'ativo'",
        "ALTER TABLE veiculos ADD COLUMN especie TEXT DEFAULT 'passeio'",
        "ALTER TABLE veiculos ADD COLUMN observacao TEXT",
    ]
    for ddl in migrations:
        try: c.execute(ddl)
        except: pass

    # Valores padrão de configuração (só insere se ainda não existir)
    defaults = {
        'senha_exclusao': '0000',
        'backup_intervalo_min': '30',
        # Tema do app (interface web)
        'tema_modo': 'claro',           # claro | escuro
        'tema_cor': 'azul',             # azul | vermelho | verde | amarelo | roxo | laranja
        # Personalização do relatório PDF
        'pdf_fonte': 'moderna',         # moderna (Helvetica) | classica (Times) | tecnica (Courier)
        'pdf_tamanho': 'medio',         # pequeno | medio | grande
        'pdf_cor': 'azul',              # mesma paleta do tema
        'pdf_mostrar_data_geracao': '1',
        'pdf_espacamento': 'espacada',  # compacta | espacada
        'pdf_ordem_blocos': 'dados_primeiro',  # dados_primeiro | veiculos_primeiro
        'pdf_nome_escritorio': '',
    }
    for chave, valor in defaults.items():
        c.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?,?)", (chave, valor))

    conn.commit()
    conn.close()

def get_config(chave, padrao=None):
    conn = get_db()
    row = conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
    conn.close()
    return row['valor'] if row else padrao

def set_config(chave, valor):
    conn = get_db()
    conn.execute("INSERT INTO configuracoes (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=?",
                 (chave, str(valor), str(valor)))
    conn.commit()
    conn.close()

# ─── PALETA DE CORES (compartilhada entre tema web e PDF) ────
PALETA_CORES = {
    'azul':    {'nome': 'Azul',     'principal': '#1a4f8a', 'secundaria': '#2563ae'},
    'vermelho':{'nome': 'Vermelho', 'principal': '#9a2424', 'secundaria': '#c0392b'},
    'verde':   {'nome': 'Verde',    'principal': '#1a6b40', 'secundaria': '#218c52'},
    'amarelo': {'nome': 'Amarelo',  'principal': '#92650a', 'secundaria': '#b8860b'},
    'roxo':    {'nome': 'Roxo',     'principal': '#5b3a8a', 'secundaria': '#7448ad'},
    'laranja': {'nome': 'Laranja',  'principal': '#a04a14', 'secundaria': '#c8631e'},
}

FONTES_PDF = {
    'moderna': {'nome': 'Moderna (sem serifa)', 'base': 'Helvetica', 'bold': 'Helvetica-Bold'},
    'classica': {'nome': 'Clássica (serifada)', 'base': 'Times-Roman', 'bold': 'Times-Bold'},
    'tecnica': {'nome': 'Técnica (monoespaçada)', 'base': 'Courier', 'bold': 'Courier-Bold'},
}

TAMANHOS_PDF = {
    'pequeno': {'nome': 'Pequeno', 'titulo': 15, 'secao': 10, 'texto': 8, 'mini': 7},
    'medio':   {'nome': 'Médio',   'titulo': 18, 'secao': 12, 'texto': 10, 'mini': 8},
    'grande':  {'nome': 'Grande',  'titulo': 21, 'secao': 14, 'texto': 12, 'mini': 9},
}

# ─── BACKUP AUTOMÁTICO ───────────────────────────────────────
_backup_event = threading.Event()  # usado para "acordar" a thread quando o intervalo mudar
_backup_lock = threading.Lock()

def fazer_backup():
    """Copia o banco de dados atual para a pasta backups/ com timestamp no nome,
    e remove backups com mais de 5 dias."""
    with _backup_lock:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if os.path.exists(DB_PATH):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            destino = os.path.join(BACKUP_DIR, f'backup_{timestamp}.db')
            shutil.copy2(DB_PATH, destino)
        else:
            destino = None

        # Limpeza: remove backups com mais de 5 dias
        limite = time.time() - (5 * 24 * 60 * 60)
        for caminho in glob.glob(os.path.join(BACKUP_DIR, 'backup_*.db')):
            try:
                if os.path.getmtime(caminho) < limite:
                    os.remove(caminho)
            except OSError:
                pass
        return destino

def _loop_backup():
    while True:
        try:
            minutos = int(get_config('backup_intervalo_min', '30'))
        except (ValueError, TypeError):
            minutos = 30
        segundos = max(60, minutos * 60)  # nunca menos que 1 minuto, por segurança
        _backup_event.wait(timeout=segundos)
        _backup_event.clear()
        try:
            fazer_backup()
        except Exception as e:
            print(f'[backup] erro ao fazer backup automático: {e}')

def reagendar_backup():
    """Chamado quando o intervalo é alterado nas configurações, para a thread
    não esperar o intervalo antigo terminar antes de aplicar o novo valor."""
    _backup_event.set()

def iniciar_thread_backup():
    t = threading.Thread(target=_loop_backup, daemon=True)
    t.start()

# ─── ÍCONES ──────────────────────────────────────────────────
@app.route('/static/icons/<nome>')
def icone(nome):
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'icons'), nome)

# ─── CONFIGURAÇÕES ───────────────────────────────────────────
@app.route('/configuracoes')
def pagina_configuracoes():
    return render_template('configuracoes.html')

@app.route('/api/configuracoes', methods=['GET'])
def api_get_configuracoes():
    return jsonify({
        'backup_intervalo_min': get_config('backup_intervalo_min', '30'),
        'senha_configurada': get_config('senha_exclusao', '0000') != '0000',
    })

@app.route('/api/configuracoes/backup-intervalo', methods=['POST'])
def api_set_backup_intervalo():
    d = request.json
    try:
        minutos = int(d.get('minutos'))
        if minutos < 1: raise ValueError
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'erro': 'Informe um número de minutos válido (mínimo 1).'}), 400
    set_config('backup_intervalo_min', minutos)
    reagendar_backup()
    return jsonify({'ok': True})

@app.route('/api/configuracoes/senha', methods=['POST'])
def api_set_senha():
    d = request.json
    senha_atual = d.get('senha_atual', '')
    nova_senha = d.get('nova_senha', '')
    if senha_atual != get_config('senha_exclusao', '0000'):
        return jsonify({'ok': False, 'erro': 'Senha atual incorreta.'}), 403
    if not nova_senha or len(nova_senha) < 4:
        return jsonify({'ok': False, 'erro': 'A nova senha deve ter ao menos 4 caracteres.'}), 400
    set_config('senha_exclusao', nova_senha)
    return jsonify({'ok': True})

@app.route('/api/configuracoes/verificar-senha', methods=['POST'])
def api_verificar_senha():
    d = request.json
    senha = d.get('senha', '')
    if senha == get_config('senha_exclusao', '0000'):
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'erro': 'Senha incorreta.'}), 403

@app.route('/api/configuracoes/backups', methods=['GET'])
def api_listar_backups():
    arquivos = sorted(glob.glob(os.path.join(BACKUP_DIR, 'backup_*.db')), reverse=True)
    lista = []
    for caminho in arquivos:
        nome = os.path.basename(caminho)
        tamanho_kb = round(os.path.getsize(caminho) / 1024, 1)
        mtime = datetime.fromtimestamp(os.path.getmtime(caminho)).strftime('%d/%m/%Y %H:%M:%S')
        lista.append({'nome': nome, 'tamanho_kb': tamanho_kb, 'criado_em': mtime})
    return jsonify(lista)

@app.route('/api/configuracoes/backup-agora', methods=['POST'])
def api_backup_agora():
    caminho = fazer_backup()
    return jsonify({'ok': True, 'arquivo': os.path.basename(caminho)})

# ─── TEMA DO APP ──────────────────────────────────────────────
@app.route('/api/configuracoes/tema', methods=['GET'])
def api_get_tema():
    cor = get_config('tema_cor', 'azul')
    return jsonify({
        'modo': get_config('tema_modo', 'claro'),
        'cor': cor,
        'paleta': PALETA_CORES,
    })

@app.route('/api/configuracoes/tema', methods=['POST'])
def api_set_tema():
    d = request.json
    modo = d.get('modo')
    cor = d.get('cor')
    if modo not in ('claro', 'escuro'):
        return jsonify({'ok': False, 'erro': 'Modo inválido.'}), 400
    if cor not in PALETA_CORES:
        return jsonify({'ok': False, 'erro': 'Cor inválida.'}), 400
    set_config('tema_modo', modo)
    set_config('tema_cor', cor)
    return jsonify({'ok': True})

# ─── CONFIGURAÇÃO DO RELATÓRIO PDF ────────────────────────────
@app.route('/api/configuracoes/pdf', methods=['GET'])
def api_get_config_pdf():
    return jsonify({
        'fonte': get_config('pdf_fonte', 'moderna'),
        'tamanho': get_config('pdf_tamanho', 'medio'),
        'cor': get_config('pdf_cor', 'azul'),
        'mostrar_data_geracao': get_config('pdf_mostrar_data_geracao', '1') == '1',
        'espacamento': get_config('pdf_espacamento', 'espacada'),
        'ordem_blocos': get_config('pdf_ordem_blocos', 'dados_primeiro'),
        'nome_escritorio': get_config('pdf_nome_escritorio', ''),
        'opcoes_fonte': FONTES_PDF,
        'opcoes_tamanho': TAMANHOS_PDF,
        'opcoes_cor': PALETA_CORES,
    })

@app.route('/api/configuracoes/pdf', methods=['POST'])
def api_set_config_pdf():
    d = request.json
    if d.get('fonte') not in FONTES_PDF:
        return jsonify({'ok': False, 'erro': 'Fonte inválida.'}), 400
    if d.get('tamanho') not in TAMANHOS_PDF:
        return jsonify({'ok': False, 'erro': 'Tamanho inválido.'}), 400
    if d.get('cor') not in PALETA_CORES:
        return jsonify({'ok': False, 'erro': 'Cor inválida.'}), 400
    if d.get('espacamento') not in ('compacta', 'espacada'):
        return jsonify({'ok': False, 'erro': 'Espaçamento inválido.'}), 400
    if d.get('ordem_blocos') not in ('dados_primeiro', 'veiculos_primeiro'):
        return jsonify({'ok': False, 'erro': 'Ordem de blocos inválida.'}), 400

    set_config('pdf_fonte', d.get('fonte'))
    set_config('pdf_tamanho', d.get('tamanho'))
    set_config('pdf_cor', d.get('cor'))
    set_config('pdf_mostrar_data_geracao', '1' if d.get('mostrar_data_geracao') else '0')
    set_config('pdf_espacamento', d.get('espacamento'))
    set_config('pdf_ordem_blocos', d.get('ordem_blocos'))
    set_config('pdf_nome_escritorio', d.get('nome_escritorio', ''))
    return jsonify({'ok': True})

# ─── DASHBOARD ───────────────────────────────────────────────
@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/dashboard')
def api_dashboard():
    conn = get_db()
    hoje = date.today().isoformat()
    limite = (date.today() + timedelta(days=30)).isoformat()

    ipva_rows = conn.execute('''
        SELECT i.*, v.placa, v.especie, v.situacao, c.nome as cliente_nome, c.id as cliente_id, v.id as vid
        FROM ipva i
        JOIN veiculos v ON i.veiculo_id = v.id
        JOIN clientes c ON v.cliente_id = c.id
        WHERE i.pago = 0 AND i.vencimento IS NOT NULL AND i.vencimento <= ?
        ORDER BY i.vencimento ASC
    ''', (limite,)).fetchall()

    lic_rows = conn.execute('''
        SELECT l.*, v.placa, v.especie, v.situacao, c.nome as cliente_nome, c.id as cliente_id, v.id as vid
        FROM licenciamento l
        JOIN veiculos v ON l.veiculo_id = v.id
        JOIN clientes c ON v.cliente_id = c.id
        WHERE l.pago = 0 AND l.vencimento IS NOT NULL AND l.vencimento <= ?
        ORDER BY l.vencimento ASC
    ''', (limite,)).fetchall()

    totais = conn.execute('''
        SELECT
          (SELECT COUNT(*) FROM clientes) as total_clientes,
          (SELECT COUNT(*) FROM veiculos WHERE situacao='ativo') as total_veiculos,
          (SELECT COUNT(*) FROM ipva WHERE pago=0 AND vencimento < ?) as ipva_vencidos,
          (SELECT COUNT(*) FROM licenciamento WHERE pago=0 AND vencimento < ?) as lic_vencidos,
          (SELECT COUNT(*) FROM multas WHERE pago=0) as multas_pendentes
    ''', (hoje, hoje)).fetchone()

    conn.close()
    return jsonify({
        'ipva': [dict(r) for r in ipva_rows],
        'licenciamento': [dict(r) for r in lic_rows],
        'totais': dict(totais)
    })

# ─── CLIENTES ────────────────────────────────────────────────
@app.route('/clientes')
def clientes():
    return render_template('clientes.html')

@app.route('/api/clientes', methods=['GET'])
def api_clientes():
    busca = request.args.get('busca', '')
    conn = get_db()
    if busca:
        rows = conn.execute(
            "SELECT * FROM clientes WHERE nome LIKE ? OR cpf LIKE ? OR telefone LIKE ? ORDER BY nome",
            (f'%{busca}%', f'%{busca}%', f'%{busca}%')
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/clientes/<int:cid>', methods=['GET'])
def api_cliente_unico(cid):
    conn = get_db()
    row = conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not row: return jsonify({'erro':'não encontrado'}), 404
    return jsonify(dict(row))

@app.route('/api/clientes', methods=['POST'])
def api_criar_cliente():
    d = request.json
    conn = get_db()
    conn.execute(
        "INSERT INTO clientes (nome, cpf, telefone, email, observacao) VALUES (?,?,?,?,?)",
        (d.get('nome'), d.get('cpf'), d.get('telefone'), d.get('email'), d.get('observacao'))
    )
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/clientes/<int:cid>', methods=['PUT'])
def api_editar_cliente(cid):
    d = request.json
    conn = get_db()
    conn.execute(
        "UPDATE clientes SET nome=?, cpf=?, telefone=?, email=?, observacao=? WHERE id=?",
        (d.get('nome'), d.get('cpf'), d.get('telefone'), d.get('email'), d.get('observacao'), cid)
    )
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/clientes/<int:cid>', methods=['DELETE'])
def api_deletar_cliente(cid):
    conn = get_db()
    conn.execute("DELETE FROM multas WHERE veiculo_id IN (SELECT id FROM veiculos WHERE cliente_id=?)", (cid,))
    conn.execute("DELETE FROM ipva WHERE veiculo_id IN (SELECT id FROM veiculos WHERE cliente_id=?)", (cid,))
    conn.execute("DELETE FROM licenciamento WHERE veiculo_id IN (SELECT id FROM veiculos WHERE cliente_id=?)", (cid,))
    conn.execute("DELETE FROM veiculos WHERE cliente_id=?", (cid,))
    conn.execute("DELETE FROM documentos WHERE cliente_id=?", (cid,))
    conn.execute("DELETE FROM clientes WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ─── DOCUMENTOS DO CLIENTE ───────────────────────────────────
@app.route('/api/clientes/<int:cid>/documentos', methods=['GET'])
def api_documentos(cid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM documentos WHERE cliente_id=? ORDER BY data_documento DESC", (cid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/documentos', methods=['POST'])
def api_criar_documento():
    cliente_id = request.form.get('cliente_id')
    nome = request.form.get('nome')
    data_documento = request.form.get('data_documento')
    categoria = request.form.get('categoria')
    observacao = request.form.get('observacao', '')
    arquivo_nome = None

    if 'arquivo' in request.files:
        f = request.files['arquivo']
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1]
            arquivo_nome = f"{uuid.uuid4().hex}{ext}"
            f.save(os.path.join(UPLOAD_DIR, arquivo_nome))

    conn = get_db()
    conn.execute(
        "INSERT INTO documentos (cliente_id, nome, data_documento, categoria, observacao, arquivo) VALUES (?,?,?,?,?,?)",
        (cliente_id, nome, data_documento, categoria, observacao, arquivo_nome)
    )
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/documentos/<int:did>', methods=['PUT'])
def api_editar_documento(did):
    d = request.json
    conn = get_db()
    conn.execute(
        "UPDATE documentos SET nome=?, data_documento=?, categoria=?, observacao=? WHERE id=?",
        (d.get('nome'), d.get('data_documento'), d.get('categoria'), d.get('observacao'), did)
    )
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/documentos/<int:did>', methods=['DELETE'])
def api_deletar_documento(did):
    conn = get_db()
    row = conn.execute("SELECT arquivo FROM documentos WHERE id=?", (did,)).fetchone()
    if row and row['arquivo']:
        caminho = os.path.join(UPLOAD_DIR, row['arquivo'])
        if os.path.exists(caminho):
            os.remove(caminho)
    conn.execute("DELETE FROM documentos WHERE id=?", (did,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/static/uploads/documentos/<nome>')
def baixar_documento(nome):
    return send_from_directory(UPLOAD_DIR, nome, as_attachment=True)

# ─── VEÍCULOS ────────────────────────────────────────────────
@app.route('/clientes/<int:cid>/veiculos')
def veiculos(cid):
    conn = get_db()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not cliente:
        return redirect(url_for('clientes'))
    return render_template('veiculos.html', cliente=dict(cliente))

@app.route('/api/clientes/<int:cid>/veiculos', methods=['GET'])
def api_veiculos(cid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM veiculos WHERE cliente_id=? ORDER BY placa", (cid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/veiculos', methods=['POST'])
def api_criar_veiculo():
    d = request.json
    conn = get_db()
    conn.execute(
        "INSERT INTO veiculos (cliente_id, placa, renavam, proprietario, marca_modelo, situacao, especie, observacao) VALUES (?,?,?,?,?,?,?,?)",
        (d.get('cliente_id'), d.get('placa','').upper(), d.get('renavam'),
         d.get('proprietario'), d.get('marca_modelo'), d.get('situacao','ativo'),
         d.get('especie','passeio'), d.get('observacao'))
    )
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/veiculos/<int:vid>', methods=['PUT'])
def api_editar_veiculo(vid):
    d = request.json
    conn = get_db()
    conn.execute(
        "UPDATE veiculos SET placa=?, renavam=?, proprietario=?, marca_modelo=?, situacao=?, especie=?, observacao=? WHERE id=?",
        (d.get('placa','').upper(), d.get('renavam'), d.get('proprietario'),
         d.get('marca_modelo'), d.get('situacao','ativo'), d.get('especie','passeio'),
         d.get('observacao'), vid)
    )
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/veiculos/<int:vid>', methods=['DELETE'])
def api_deletar_veiculo(vid):
    conn = get_db()
    conn.execute("DELETE FROM multas WHERE veiculo_id=?", (vid,))
    conn.execute("DELETE FROM ipva WHERE veiculo_id=?", (vid,))
    conn.execute("DELETE FROM licenciamento WHERE veiculo_id=?", (vid,))
    conn.execute("DELETE FROM veiculos WHERE id=?", (vid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ─── PAINEL DO VEÍCULO ───────────────────────────────────────
@app.route('/veiculos/<int:vid>/painel')
def painel(vid):
    conn = get_db()
    v = conn.execute("""
        SELECT v.*, c.nome as cliente_nome, c.id as cliente_id
        FROM veiculos v JOIN clientes c ON v.cliente_id = c.id
        WHERE v.id=?""", (vid,)).fetchone()
    conn.close()
    if not v:
        return redirect(url_for('clientes'))
    return render_template('painel.html', veiculo=dict(v))

# ── IPVA ──
@app.route('/api/veiculos/<int:vid>/ipva')
def api_ipva(vid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM ipva WHERE veiculo_id=? ORDER BY ano_referencia DESC", (vid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/ipva', methods=['POST'])
def api_criar_ipva():
    d = request.json
    conn = get_db()
    conn.execute("INSERT INTO ipva (veiculo_id,ano_referencia,valor,vencimento,pago,data_pagamento,observacao) VALUES (?,?,?,?,?,?,?)",
        (d['veiculo_id'],d.get('ano_referencia'),d.get('valor'),d.get('vencimento'),d.get('pago',0),d.get('data_pagamento'),d.get('observacao')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/ipva/<int:iid>', methods=['PUT'])
def api_editar_ipva(iid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE ipva SET ano_referencia=?,valor=?,vencimento=?,pago=?,data_pagamento=?,observacao=? WHERE id=?",
        (d.get('ano_referencia'),d.get('valor'),d.get('vencimento'),d.get('pago',0),d.get('data_pagamento'),d.get('observacao'),iid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/ipva/<int:iid>', methods=['DELETE'])
def api_deletar_ipva(iid):
    conn = get_db()
    conn.execute("DELETE FROM ipva WHERE id=?", (iid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── LICENCIAMENTO ──
@app.route('/api/veiculos/<int:vid>/licenciamento')
def api_licenciamento(vid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM licenciamento WHERE veiculo_id=? ORDER BY ano_referencia DESC", (vid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/licenciamento', methods=['POST'])
def api_criar_licenciamento():
    d = request.json
    conn = get_db()
    conn.execute("INSERT INTO licenciamento (veiculo_id,ano_referencia,valor,vencimento,pago,data_pagamento,observacao) VALUES (?,?,?,?,?,?,?)",
        (d['veiculo_id'],d.get('ano_referencia'),d.get('valor'),d.get('vencimento'),d.get('pago',0),d.get('data_pagamento'),d.get('observacao')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/licenciamento/<int:lid>', methods=['PUT'])
def api_editar_licenciamento(lid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE licenciamento SET ano_referencia=?,valor=?,vencimento=?,pago=?,data_pagamento=?,observacao=? WHERE id=?",
        (d.get('ano_referencia'),d.get('valor'),d.get('vencimento'),d.get('pago',0),d.get('data_pagamento'),d.get('observacao'),lid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/licenciamento/<int:lid>', methods=['DELETE'])
def api_deletar_licenciamento(lid):
    conn = get_db()
    conn.execute("DELETE FROM licenciamento WHERE id=?", (lid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── MULTAS ──
@app.route('/api/veiculos/<int:vid>/multas')
def api_multas(vid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM multas WHERE veiculo_id=? ORDER BY data_infracao DESC", (vid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/multas', methods=['POST'])
def api_criar_multa():
    d = request.json
    conn = get_db()
    conn.execute("INSERT INTO multas (veiculo_id,auto_infracao,data_infracao,descricao,valor,vencimento,pago,data_pagamento,observacao) VALUES (?,?,?,?,?,?,?,?,?)",
        (d['veiculo_id'],d.get('auto_infracao'),d.get('data_infracao'),d.get('descricao'),d.get('valor'),d.get('vencimento'),d.get('pago',0),d.get('data_pagamento'),d.get('observacao')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/multas/<int:mid>', methods=['PUT'])
def api_editar_multa(mid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE multas SET auto_infracao=?,data_infracao=?,descricao=?,valor=?,vencimento=?,pago=?,data_pagamento=?,observacao=? WHERE id=?",
        (d.get('auto_infracao'),d.get('data_infracao'),d.get('descricao'),d.get('valor'),d.get('vencimento'),d.get('pago',0),d.get('data_pagamento'),d.get('observacao'),mid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/multas/<int:mid>', methods=['DELETE'])
def api_deletar_multa(mid):
    conn = get_db()
    conn.execute("DELETE FROM multas WHERE id=?", (mid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ─── RELATÓRIO PDF ───────────────────────────────────────────
@app.route('/api/clientes/<int:cid>/relatorio')
def relatorio_pdf(cid):
    incluir = request.args.getlist('incluir')

    conn = get_db()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone()
    if not cliente:
        conn.close()
        return "Cliente não encontrado", 404
    cliente = dict(cliente)

    veics = conn.execute("SELECT * FROM veiculos WHERE cliente_id=? ORDER BY placa", (cid,)).fetchall()
    veics = [dict(v) for v in veics]

    for v in veics:
        v['ipva_list'] = [dict(r) for r in conn.execute(
            "SELECT * FROM ipva WHERE veiculo_id=? ORDER BY ano_referencia DESC", (v['id'],)).fetchall()]
        v['lic_list'] = [dict(r) for r in conn.execute(
            "SELECT * FROM licenciamento WHERE veiculo_id=? ORDER BY ano_referencia DESC", (v['id'],)).fetchall()]
    conn.close()

    # ── Configurações de personalização do PDF ──
    cfg_fonte = FONTES_PDF.get(get_config('pdf_fonte', 'moderna'), FONTES_PDF['moderna'])
    cfg_tam   = TAMANHOS_PDF.get(get_config('pdf_tamanho', 'medio'), TAMANHOS_PDF['medio'])
    cfg_cor   = PALETA_CORES.get(get_config('pdf_cor', 'azul'), PALETA_CORES['azul'])
    mostrar_data_geracao = get_config('pdf_mostrar_data_geracao', '1') == '1'
    espacamento = get_config('pdf_espacamento', 'espacada')
    ordem_blocos = get_config('pdf_ordem_blocos', 'dados_primeiro')
    nome_escritorio = get_config('pdf_nome_escritorio', '')

    FONTE_BASE = cfg_fonte['base']
    FONTE_BOLD = cfg_fonte['bold']
    PAD_TABELA = 5 if espacamento == 'compacta' else 8
    PAD_TABELA_REGISTROS = 4 if espacamento == 'compacta' else 7

    AZUL=colors.HexColor(cfg_cor['principal']); AZUL2=colors.HexColor(cfg_cor['secundaria'])
    CINZA=colors.HexColor('#f4f6fa'); CINZA2=colors.HexColor('#e8ecf2')
    VERDE=colors.HexColor('#065f46'); VERM=colors.HexColor('#991b1b')
    AMAR=colors.HexColor('#92400e'); BRANCO=colors.white
    TEXTO=colors.HexColor('#1c2333')

    sTitulo = ParagraphStyle('titulo', fontName=FONTE_BOLD, fontSize=cfg_tam['titulo'], textColor=AZUL, spaceAfter=4)
    sSub    = ParagraphStyle('sub', fontName=FONTE_BASE, fontSize=cfg_tam['mini']+2, textColor=colors.HexColor('#5a6680'), spaceAfter=12)
    sSecao  = ParagraphStyle('secao', fontName=FONTE_BOLD, fontSize=cfg_tam['secao'], textColor=AZUL2, spaceBefore=14, spaceAfter=6)
    sLabel  = ParagraphStyle('label', fontName=FONTE_BOLD, fontSize=cfg_tam['mini']+1, textColor=colors.HexColor('#5a6680'))
    sValor  = ParagraphStyle('valor', fontName=FONTE_BASE, fontSize=cfg_tam['texto'], textColor=TEXTO)
    sPlaca  = ParagraphStyle('placa', fontName=FONTE_BOLD, fontSize=cfg_tam['secao']+1, textColor=AZUL)
    sMini   = ParagraphStyle('mini', fontName=FONTE_BASE, fontSize=cfg_tam['mini'], textColor=colors.HexColor('#5a6680'))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    story = []

    def fmt_data(d):
        if not d: return '—'
        try: y,m,dia = d.split('-'); return f'{dia}/{m}/{y}'
        except: return d

    def fmt_moeda(v):
        if v is None or v == '': return '—'
        return f'R$ {float(v):,.2f}'.replace(',','X').replace('.',',').replace('X','.')

    def status_badge(venc, pago):
        if pago: return ('PAGO', VERDE)
        if not venc: return ('PENDENTE', AMAR)
        hoje = date.today().isoformat()
        if venc < hoje: return ('VENCIDO', VERM)
        return ('PENDENTE', AMAR)

    SITUACAO_LABEL = {'ativo':'Ativo','desativado':'Desativado','vendido':'Vendido'}
    ESPECIE_LABEL  = {'passeio':'Passeio','carga':'Carga','reboque':'Reboque'}

    if nome_escritorio:
        sEscritorio = ParagraphStyle('escritorio', fontName=FONTE_BOLD, fontSize=cfg_tam['mini']+3, textColor=AZUL2, spaceAfter=2)
        story.append(Paragraph(nome_escritorio, sEscritorio))
    story.append(Paragraph('Relatório do Cliente', sTitulo))
    if mostrar_data_geracao:
        story.append(Paragraph(f'Gerado em {datetime.now().strftime("%d/%m/%Y às %H:%M")}', sSub))
    story.append(HRFlowable(width='100%', thickness=2, color=AZUL, spaceAfter=14))

    def montar_bloco_dados():
        bloco = []
        if 'dados' in incluir:
            bloco.append(Paragraph('Dados do Cliente', sSecao))
            campos = [
                ('Nome', cliente['nome']),
                ('CPF', cliente.get('cpf') or '—'),
                ('Telefone', cliente.get('telefone') or '—'),
                ('E-mail', cliente.get('email') or '—'),
                ('Observação', cliente.get('observacao') or '—'),
            ]
            tdata = [[Paragraph(l, sLabel), Paragraph(str(v), sValor)] for l, v in campos]
            t = Table(tdata, colWidths=['30%','70%'])
            t.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,-1),CINZA),
                ('ROWBACKGROUNDS',(0,0),(-1,-1),[CINZA,CINZA2]),
                ('BOX',(0,0),(-1,-1),0.5,CINZA2),
                ('INNERGRID',(0,0),(-1,-1),0.5,CINZA2),
                ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('PADDING',(0,0),(-1,-1),PAD_TABELA),
            ]))
            bloco.append(t)
            bloco.append(Spacer(1, 10))
        return bloco

    def montar_bloco_veiculos():
        bloco = []
        if 'veiculos' in incluir or 'ipva' in incluir or 'licenciamento' in incluir:
            for v in veics:
                bloco.append(Spacer(1, 8))
                bloco.append(HRFlowable(width='100%', thickness=1, color=CINZA2, spaceAfter=8))

                especie_txt = ESPECIE_LABEL.get(v.get('especie',''), v.get('especie',''))
                situacao_txt = SITUACAO_LABEL.get(v.get('situacao',''), v.get('situacao',''))
                bloco.append(Paragraph(f"Placa: {v['placa']}  —  {especie_txt}  —  {situacao_txt}", sPlaca))

                if 'veiculos' in incluir:
                    info_campos = [
                        ('Marca/Modelo', v.get('marca_modelo') or '—'),
                        ('Proprietário', v.get('proprietario') or '—'),
                        ('RENAVAM', v.get('renavam') or '—'),
                    ]
                    tdata2 = [[Paragraph(l, sLabel), Paragraph(val, sValor)] for l, val in info_campos]
                    tdata2.append([Paragraph('Observação', sLabel), Paragraph(v.get('observacao') or '—', sValor)])
                    t2 = Table(tdata2, colWidths=['30%','70%'])
                    t2.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,-1),CINZA),
                        ('ROWBACKGROUNDS',(0,0),(-1,-1),[CINZA,CINZA2]),
                        ('BOX',(0,0),(-1,-1),0.5,CINZA2),
                        ('INNERGRID',(0,0),(-1,-1),0.5,CINZA2),
                        ('VALIGN',(0,0),(-1,-1),'TOP'),
                        ('PADDING',(0,0),(-1,-1),PAD_TABELA_REGISTROS),
                    ]))
                    bloco.append(Spacer(1,4))
                    bloco.append(t2)

                if 'ipva' in incluir and v['ipva_list']:
                    bloco.append(Spacer(1,8))
                    bloco.append(Paragraph('IPVA', sSecao))
                    thead = [Paragraph(h, sLabel) for h in ['Ano','Valor','Vencimento','Status','Dt. Pagamento','Obs.']]
                    trows = [thead]
                    for r in v['ipva_list']:
                        label, tc = status_badge(r.get('vencimento'), r.get('pago'))
                        trows.append([
                            Paragraph(str(r['ano_referencia']), sValor),
                            Paragraph(fmt_moeda(r.get('valor')), sValor),
                            Paragraph(fmt_data(r.get('vencimento')), sValor),
                            Paragraph(label, ParagraphStyle('s', fontName=FONTE_BOLD, fontSize=cfg_tam['mini'], textColor=tc)),
                            Paragraph(fmt_data(r.get('data_pagamento')), sValor),
                            Paragraph(r.get('observacao') or '—', sMini),
                        ])
                    ti = Table(trows, colWidths=['12%','16%','18%','14%','18%','22%'])
                    ti.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,0),AZUL),
                        ('TEXTCOLOR',(0,0),(-1,0),BRANCO),
                        ('ROWBACKGROUNDS',(0,1),(-1,-1),[BRANCO,CINZA]),
                        ('BOX',(0,0),(-1,-1),0.5,CINZA2),
                        ('INNERGRID',(0,0),(-1,-1),0.3,CINZA2),
                        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                        ('PADDING',(0,0),(-1,-1),PAD_TABELA_REGISTROS),
                    ]))
                    bloco.append(ti)

                if 'licenciamento' in incluir and v['lic_list']:
                    bloco.append(Spacer(1,8))
                    bloco.append(Paragraph('Licenciamento', sSecao))
                    thead2 = [Paragraph(h, sLabel) for h in ['Ano','Valor','Vencimento','Status','Dt. Pagamento','Obs.']]
                    trows2 = [thead2]
                    for r in v['lic_list']:
                        label, tc = status_badge(r.get('vencimento'), r.get('pago'))
                        trows2.append([
                            Paragraph(str(r['ano_referencia']), sValor),
                            Paragraph(fmt_moeda(r.get('valor')), sValor),
                            Paragraph(fmt_data(r.get('vencimento')), sValor),
                            Paragraph(label, ParagraphStyle('s2', fontName=FONTE_BOLD, fontSize=cfg_tam['mini'], textColor=tc)),
                            Paragraph(fmt_data(r.get('data_pagamento')), sValor),
                            Paragraph(r.get('observacao') or '—', sMini),
                        ])
                    tl = Table(trows2, colWidths=['12%','16%','18%','14%','18%','22%'])
                    tl.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,0),AZUL),
                        ('TEXTCOLOR',(0,0),(-1,0),BRANCO),
                        ('ROWBACKGROUNDS',(0,1),(-1,-1),[BRANCO,CINZA]),
                        ('BOX',(0,0),(-1,-1),0.5,CINZA2),
                        ('INNERGRID',(0,0),(-1,-1),0.3,CINZA2),
                        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                        ('PADDING',(0,0),(-1,-1),PAD_TABELA_REGISTROS),
                    ]))
                    bloco.append(tl)
        return bloco

    if ordem_blocos == 'veiculos_primeiro':
        story.extend(montar_bloco_veiculos())
        story.extend(montar_bloco_dados())
    else:
        story.extend(montar_bloco_dados())
        story.extend(montar_bloco_veiculos())

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=1, color=CINZA2))
    rodape_txt = nome_escritorio if nome_escritorio else 'Sistema de Despachante'
    story.append(Paragraph(rodape_txt, sMini))

    doc.build(story)
    buf.seek(0)
    nome_arquivo = f"relatorio_{cliente['nome'].replace(' ','_')}.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=nome_arquivo)

if __name__ == '__main__':
    init_db()
    # Com debug=True o Flask usa um reloader que recarrega o processo;
    # WERKZEUG_RUN_MAIN só existe no processo "filho" (o que de fato atende requisições).
    # Assim a thread de backup não é duplicada.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        iniciar_thread_backup()
    print("\n✅ Sistema Despachante iniciado!")
    print("🌐 Abra no navegador: http://localhost:5000\n")
    print("💾 Backup automático ativo (rodando em segundo plano)\n")
    app.run(debug=True, port=5000)
