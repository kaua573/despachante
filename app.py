from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, send_from_directory
from markupsafe import Markup
import sqlite3, os, io, uuid
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
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    conn.commit()
    conn.close()

# ─── ÍCONES ──────────────────────────────────────────────────
@app.route('/static/icons/<nome>')
def icone(nome):
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'icons'), nome)

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

    AZUL=colors.HexColor('#1a4f8a'); AZUL2=colors.HexColor('#2563ae')
    CINZA=colors.HexColor('#f4f6fa'); CINZA2=colors.HexColor('#e8ecf2')
    VERDE=colors.HexColor('#065f46'); VERM=colors.HexColor('#991b1b')
    AMAR=colors.HexColor('#92400e'); BRANCO=colors.white
    TEXTO=colors.HexColor('#1c2333')

    sTitulo = ParagraphStyle('titulo', fontName='Helvetica-Bold', fontSize=18, textColor=AZUL, spaceAfter=4)
    sSub    = ParagraphStyle('sub', fontName='Helvetica', fontSize=10, textColor=colors.HexColor('#5a6680'), spaceAfter=12)
    sSecao  = ParagraphStyle('secao', fontName='Helvetica-Bold', fontSize=12, textColor=AZUL2, spaceBefore=14, spaceAfter=6)
    sLabel  = ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#5a6680'))
    sValor  = ParagraphStyle('valor', fontName='Helvetica', fontSize=10, textColor=TEXTO)
    sPlaca  = ParagraphStyle('placa', fontName='Helvetica-Bold', fontSize=13, textColor=AZUL)
    sMini   = ParagraphStyle('mini', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#5a6680'))

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

    story.append(Paragraph('Relatório do Cliente', sTitulo))
    story.append(Paragraph(f'Gerado em {datetime.now().strftime("%d/%m/%Y às %H:%M")}', sSub))
    story.append(HRFlowable(width='100%', thickness=2, color=AZUL, spaceAfter=14))

    if 'dados' in incluir:
        story.append(Paragraph('Dados do Cliente', sSecao))
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
            ('PADDING',(0,0),(-1,-1),8),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    if 'veiculos' in incluir or 'ipva' in incluir or 'licenciamento' in incluir:
        for v in veics:
            story.append(Spacer(1, 8))
            story.append(HRFlowable(width='100%', thickness=1, color=CINZA2, spaceAfter=8))

            especie_txt = ESPECIE_LABEL.get(v.get('especie',''), v.get('especie',''))
            situacao_txt = SITUACAO_LABEL.get(v.get('situacao',''), v.get('situacao',''))
            story.append(Paragraph(f"Placa: {v['placa']}  —  {especie_txt}  —  {situacao_txt}", sPlaca))

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
                    ('PADDING',(0,0),(-1,-1),7),
                ]))
                story.append(Spacer(1,4))
                story.append(t2)

            if 'ipva' in incluir and v['ipva_list']:
                story.append(Spacer(1,8))
                story.append(Paragraph('IPVA', sSecao))
                thead = [Paragraph(h, sLabel) for h in ['Ano','Valor','Vencimento','Status','Dt. Pagamento','Obs.']]
                trows = [thead]
                for r in v['ipva_list']:
                    label, tc = status_badge(r.get('vencimento'), r.get('pago'))
                    trows.append([
                        Paragraph(str(r['ano_referencia']), sValor),
                        Paragraph(fmt_moeda(r.get('valor')), sValor),
                        Paragraph(fmt_data(r.get('vencimento')), sValor),
                        Paragraph(label, ParagraphStyle('s', fontName='Helvetica-Bold', fontSize=8, textColor=tc)),
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
                    ('PADDING',(0,0),(-1,-1),5),
                ]))
                story.append(ti)

            if 'licenciamento' in incluir and v['lic_list']:
                story.append(Spacer(1,8))
                story.append(Paragraph('Licenciamento', sSecao))
                thead2 = [Paragraph(h, sLabel) for h in ['Ano','Valor','Vencimento','Status','Dt. Pagamento','Obs.']]
                trows2 = [thead2]
                for r in v['lic_list']:
                    label, tc = status_badge(r.get('vencimento'), r.get('pago'))
                    trows2.append([
                        Paragraph(str(r['ano_referencia']), sValor),
                        Paragraph(fmt_moeda(r.get('valor')), sValor),
                        Paragraph(fmt_data(r.get('vencimento')), sValor),
                        Paragraph(label, ParagraphStyle('s2', fontName='Helvetica-Bold', fontSize=8, textColor=tc)),
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
                    ('PADDING',(0,0),(-1,-1),5),
                ]))
                story.append(tl)

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=1, color=CINZA2))
    story.append(Paragraph('Sistema de Despachante', sMini))

    doc.build(story)
    buf.seek(0)
    nome_arquivo = f"relatorio_{cliente['nome'].replace(' ','_')}.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=nome_arquivo)

if __name__ == '__main__':
    init_db()
    print("\n✅ Sistema Despachante iniciado!")
    print("🌐 Abra no navegador: http://localhost:5000\n")
    app.run(debug=True, port=5000)
