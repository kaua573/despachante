"""
Script de população (seed) do banco de dados com dados fictícios
cobrindo todos os cenários possíveis do sistema, para teste e demonstração.
"""
import sqlite3
import os
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'despachante.db')

def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hoje_mais(dias):
    return (date.today() + timedelta(days=dias)).isoformat()

def limpar_tudo(conn):
    for t in ['multas', 'licenciamento', 'ipva', 'documentos', 'veiculos', 'clientes']:
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM sqlite_sequence")  # reseta autoincrement
    conn.commit()

def seed():
    conn = conectar()
    limpar_tudo(conn)
    c = conn.cursor()

    # ── CLIENTES (variados) ──
    clientes = [
        ("João Carlos Silva",        "123.456.789-00", "(18) 99111-2233", "joao.silva@email.com", "Cliente antigo, sempre pontual nos pagamentos."),
        ("Maria Fernanda Oliveira",  "234.567.890-11", "(18) 99222-3344", "maria.oliveira@email.com", ""),
        ("Transportes Rápido Ltda",  "12.345.678/0001-99", "(18) 3222-4455", "contato@transportesrapido.com.br", "Empresa com frota de caminhões. Contato preferencial: setor financeiro."),
        ("Pedro Henrique Souza",     "345.678.901-22", "(18) 99333-4455", "pedro.souza@email.com", "Veículo herdado do pai, documentação em transição."),
        ("Ana Beatriz Costa",        "456.789.012-33", "(18) 99444-5566", "ana.costa@email.com", "Prefere contato por WhatsApp."),
        ("Carlos Eduardo Martins",   "567.890.123-44", "(18) 99555-6677", "carlos.martins@email.com", ""),
        ("Distribuidora Bom Preço S/A", "23.456.789/0001-10", "(18) 3233-5566", "financeiro@bompreco.com.br", "Possui múltiplos veículos de carga e reboques."),
        ("Juliana Aparecida Lima",   "678.901.234-55", "(18) 99666-7788", "juliana.lima@email.com", "Vendeu o carro recentemente, aguardando baixa."),
    ]
    for nome, cpf, tel, email, obs in clientes:
        c.execute("INSERT INTO clientes (nome, cpf, telefone, email, observacao) VALUES (?,?,?,?,?)",
                   (nome, cpf, tel, email, obs))
    conn.commit()

    cliente_ids = {nome: cid for cid, nome in
                   c.execute("SELECT id, nome FROM clientes").fetchall()}

    # ── VEÍCULOS (cobrindo todas espécies x situações) ──
    veiculos = [
        # cliente, placa, renavam, proprietario, marca_modelo, situacao, especie, obs
        ("João Carlos Silva", "ABC1D23", "12345678901", "João Carlos Silva", "Chevrolet Onix LT", "ativo", "passeio", ""),
        ("João Carlos Silva", "DEF4G56", "23456789012", "Maria Silva (esposa)", "Fiat Strada", "ativo", "carga", "Veículo usado no comércio da família."),

        ("Maria Fernanda Oliveira", "GHI7J89", "34567890123", "Maria Fernanda Oliveira", "Hyundai HB20", "ativo", "passeio", ""),

        ("Transportes Rápido Ltda", "JKL1M23", "45678901234", "Transportes Rápido Ltda", "Volvo FH 540", "ativo", "carga", "Caminhão principal da frota."),
        ("Transportes Rápido Ltda", "NOP4Q56", "56789012345", "Transportes Rápido Ltda", "Scania R450", "ativo", "carga", ""),
        ("Transportes Rápido Ltda", "RST7U89", "67890123456", "Transportes Rápido Ltda", "Carreta Randon SR", "ativo", "reboque", "Reboque acoplado ao Volvo."),
        ("Transportes Rápido Ltda", "VWX1Y23", "78901234567", "Transportes Rápido Ltda", "Mercedes Atego", "desativado", "carga", "Em manutenção há 3 meses, sem previsão de retorno."),

        ("Pedro Henrique Souza", "ZAB4C56", "89012345678", "José Henrique Souza (pai, falecido)", "Volkswagen Gol", "ativo", "passeio", "Transferência de proprietário pendente no Detran."),

        ("Ana Beatriz Costa", "DEF7G89", "90123456789", "Ana Beatriz Costa", "Honda CG 160", "ativo", "passeio", "Motocicleta."),

        ("Carlos Eduardo Martins", "HIJ1K23", "01234567890", "Carlos Eduardo Martins", "Toyota Corolla", "ativo", "passeio", ""),

        ("Distribuidora Bom Preço S/A", "LMN4O56", "11234567890", "Distribuidora Bom Preço S/A", "Iveco Daily", "ativo", "carga", ""),
        ("Distribuidora Bom Preço S/A", "PQR7S89", "21234567890", "Distribuidora Bom Preço S/A", "Carreta Facchini", "ativo", "reboque", ""),
        ("Distribuidora Bom Preço S/A", "TUV1W23", "31234567890", "Distribuidora Bom Preço S/A", "Ford Cargo 1719", "desativado", "carga", "Veículo reserva, fora de operação."),

        ("Juliana Aparecida Lima", "XYZ4A56", "41234567890", "Juliana Aparecida Lima", "Renault Kwid", "vendido", "passeio", "Vendido em 02/2026 para terceiro. Aguardando comunicação de venda no Detran."),
    ]
    for nome_cliente, placa, renavam, prop, marca, situ, esp, obs in veiculos:
        c.execute("""INSERT INTO veiculos
            (cliente_id, placa, renavam, proprietario, marca_modelo, situacao, especie, observacao)
            VALUES (?,?,?,?,?,?,?,?)""",
            (cliente_ids[nome_cliente], placa, renavam, prop, marca, situ, esp, obs))
    conn.commit()

    veic_ids = {placa: vid for vid, placa in c.execute("SELECT id, placa FROM veiculos").fetchall()}

    # ── IPVA (variando: pago, pendente futuro, vencido) ──
    ipva_dados = [
        # placa, ano, valor, vencimento (dias relativos a hoje), pago, data_pagamento, obs
        ("ABC1D23", 2025, 780.50, hoje_mais(-200), 1, hoje_mais(-205), ""),
        ("ABC1D23", 2026, 820.00, hoje_mais(15),  0, None, ""),

        ("DEF4G56", 2026, 650.30, hoje_mais(-10), 0, None, "Cliente avisado, aguardando pagamento."),

        ("GHI7J89", 2026, 540.00, hoje_mais(25),  0, None, ""),

        ("JKL1M23", 2026, 3450.00, hoje_mais(5),   0, None, "Valor alto — caminhão categoria especial."),
        ("NOP4Q56", 2026, 3200.00, hoje_mais(-3),  0, None, "Vencido recentemente, contatar empresa."),
        ("RST7U89", 2026, 980.00,  hoje_mais(40),  0, None, ""),
        ("VWX1Y23", 2026, 2100.00, hoje_mais(-90), 0, None, "Veículo desativado, mas IPVA continua gerando até baixa formal."),

        ("ZAB4C56", 2026, 410.00, hoje_mais(-15), 0, None, "Pendência ligada à transferência de proprietário."),

        ("DEF7G89", 2026, 180.00, hoje_mais(8), 0, None, ""),

        ("HIJ1K23", 2025, 920.00, hoje_mais(-400), 1, hoje_mais(-410), ""),
        ("HIJ1K23", 2026, 960.00, hoje_mais(60),   0, None, ""),

        ("LMN4O56", 2026, 1450.00, hoje_mais(-1),  0, None, "Vence hoje/ontem — prioridade alta."),
        ("PQR7S89", 2026, 870.00,  hoje_mais(20),  0, None, ""),
        ("TUV1W23", 2026, 1320.00, hoje_mais(-60), 0, None, "Veículo desativado."),

        ("XYZ4A56", 2025, 480.00, hoje_mais(-300), 1, hoje_mais(-305), "Pago antes da venda."),
    ]
    for placa, ano, valor, venc, pago, dtpag, obs in ipva_dados:
        c.execute("""INSERT INTO ipva (veiculo_id, ano_referencia, valor, vencimento, pago, data_pagamento, observacao)
            VALUES (?,?,?,?,?,?,?)""", (veic_ids[placa], ano, valor, venc, pago, dtpag, obs))
    conn.commit()

    # ── LICENCIAMENTO ──
    lic_dados = [
        ("ABC1D23", 2025, 130.00, hoje_mais(-180), 1, hoje_mais(-185), ""),
        ("ABC1D23", 2026, 145.00, hoje_mais(28),   0, None, ""),

        ("DEF4G56", 2026, 145.00, hoje_mais(-5),   0, None, "Atrasado, multa por atraso pode incidir."),

        ("GHI7J89", 2026, 145.00, hoje_mais(12),   0, None, ""),

        ("JKL1M23", 2026, 310.00, hoje_mais(18),   0, None, ""),
        ("NOP4Q56", 2026, 310.00, hoje_mais(-7),   0, None, ""),
        ("RST7U89", 2026, 200.00, hoje_mais(30),   0, None, ""),
        ("VWX1Y23", 2026, 280.00, hoje_mais(-120), 0, None, "Veículo parado, sem previsão de licenciar."),

        ("ZAB4C56", 2026, 145.00, hoje_mais(-20),  0, None, ""),

        ("DEF7G89", 2026, 95.00,  hoje_mais(6),    0, None, ""),

        ("HIJ1K23", 2025, 145.00, hoje_mais(-350), 1, hoje_mais(-355), ""),
        ("HIJ1K23", 2026, 150.00, hoje_mais(45),   0, None, ""),

        ("LMN4O56", 2026, 310.00, hoje_mais(3),    0, None, "Vencimento próximo, agendar."),
        ("PQR7S89", 2026, 200.00, hoje_mais(22),   0, None, ""),
        ("TUV1W23", 2026, 280.00, hoje_mais(-45),  0, None, ""),

        ("XYZ4A56", 2025, 130.00, hoje_mais(-280), 1, hoje_mais(-285), "Pago antes da venda."),
    ]
    for placa, ano, valor, venc, pago, dtpag, obs in lic_dados:
        c.execute("""INSERT INTO licenciamento (veiculo_id, ano_referencia, valor, vencimento, pago, data_pagamento, observacao)
            VALUES (?,?,?,?,?,?,?)""", (veic_ids[placa], ano, valor, venc, pago, dtpag, obs))
    conn.commit()

    # ── MULTAS ──
    multas_dados = [
        # placa, auto, data_infracao, descricao, valor, vencimento, pago, dtpag, obs
        ("ABC1D23", "AIT-000123456", hoje_mais(-40), "Excesso de velocidade até 20%", 130.16, hoje_mais(-10), 1, hoje_mais(-12), ""),
        ("DEF4G56", "AIT-000234567", hoje_mais(-15), "Estacionar em local proibido", 195.23, hoje_mais(10), 0, None, "Recurso em análise."),
        ("JKL1M23", "AIT-000345678", hoje_mais(-60), "Avançar sinal vermelho", 293.47, hoje_mais(-25), 0, None, "Vencida, gerar boleto atualizado."),
        ("NOP4Q56", "AIT-000456789", hoje_mais(-5),  "Excesso de velocidade acima de 50%", 880.41, hoje_mais(40), 0, None, ""),
        ("HIJ1K23", "AIT-000567890", hoje_mais(-100),"Uso de celular ao volante", 293.47, hoje_mais(-70), 1, hoje_mais(-72), ""),
        ("LMN4O56", "AIT-000678901", hoje_mais(-8),  "Transitar com excesso de peso", 130.16, hoje_mais(15), 0, None, "Notificar motorista responsável."),
        ("ZAB4C56", "AIT-000789012", hoje_mais(-200),"Não uso do cinto de segurança", 195.23, hoje_mais(-170), 0, None, "Multa anterior à transferência — verificar responsável."),
    ]
    for placa, auto, dtinf, desc, valor, venc, pago, dtpag, obs in multas_dados:
        c.execute("""INSERT INTO multas (veiculo_id, auto_infracao, data_infracao, descricao, valor, vencimento, pago, data_pagamento, observacao)
            VALUES (?,?,?,?,?,?,?,?,?)""", (veic_ids[placa], auto, dtinf, desc, valor, venc, pago, dtpag, obs))
    conn.commit()

    # ── DOCUMENTOS ──
    documentos = [
        ("João Carlos Silva", "RG e CPF", hoje_mais(-500), "documento_pessoal", "Cópia simples."),
        ("João Carlos Silva", "Comprovante de Residência", hoje_mais(-30), "comprovante_residencia", "Conta de luz."),
        ("Maria Fernanda Oliveira", "CNH", hoje_mais(-600), "documento_pessoal", ""),
        ("Transportes Rápido Ltda", "Contrato Social", hoje_mais(-800), "contrato", "Última alteração contratual registrada."),
        ("Transportes Rápido Ltda", "Procuração - Setor Financeiro", hoje_mais(-90), "procuracao", "Autoriza retirada de documentos pelo financeiro."),
        ("Pedro Henrique Souza", "Certidão de Óbito do Pai", hoje_mais(-120), "outro", "Necessário para regularizar transferência do veículo."),
        ("Distribuidora Bom Preço S/A", "Contrato Social", hoje_mais(-1000), "contrato", ""),
        ("Juliana Aparecida Lima", "Recibo de Venda do Veículo", hoje_mais(-25), "outro", "Aguardando comunicação de venda no Detran."),
    ]
    for nome_cliente, nome_doc, data_doc, categoria, obs in documentos:
        c.execute("""INSERT INTO documentos (cliente_id, nome, data_documento, categoria, observacao, arquivo)
            VALUES (?,?,?,?,?,NULL)""", (cliente_ids[nome_cliente], nome_doc, data_doc, categoria, obs))
    conn.commit()

    conn.close()
    print("✅ Banco populado com dados de simulação!")
    print(f"   - {len(clientes)} clientes")
    print(f"   - {len(veiculos)} veículos (ativos, desativados e vendidos)")
    print(f"   - {len(ipva_dados)} registros de IPVA (pagos, pendentes e vencidos)")
    print(f"   - {len(lic_dados)} registros de licenciamento")
    print(f"   - {len(multas_dados)} multas")
    print(f"   - {len(documentos)} documentos anexados")

if __name__ == '__main__':
    seed()
