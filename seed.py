# Uso: python seed.py
# ⚠️  Apaga TODOS os dados existentes antes de inserir.

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta

from run import app, db, init_db
from app.models import (
    Cliente, Veiculo, Ipva, IpvaParcela,
    Licenciamento, Multa, Documento,
)
from app.services.ipva_service import IpvaService


def d(n: int) -> str:
    """Data ISO relativa a hoje. Positivo = futuro, negativo = passado."""
    return (date.today() + timedelta(days=n)).isoformat()


def limpar():
    for modelo in [IpvaParcela, Multa, Ipva, Licenciamento, Documento, Veiculo, Cliente]:
        db.session.query(modelo).delete()
    db.session.commit()


# ── Clientes ──────────────────────────────────────────────────────────────────
# 2 clientes com frota ampla + 3 clientes simples + 1 sem veículos
CLIENTES = [
    # nome, cpf, telefone, email, obs
    ("Carlos Eduardo Martins",    "567.890.123-91", "(18) 99100-2233", "carlos@email.com",  "Cliente VIP — frota própria."),
    ("Transportes Rápido Ltda",   "12.345.678/0001-95", "(18) 3222-4455", "frota@tr.com", "PJ — pagamento via boleto mensal."),
    ("Ana Beatriz Costa",         "456.789.012-68", "(18) 99300-4455", "ana@email.com",    ""),
    ("Pedro Henrique Souza",      "345.678.901-82", "(18) 99400-5566", "pedro@email.com",  "Transferência de titularidade pendente."),
    ("Roberto Alves Pereira",     "789.012.345-10", "(14) 99500-6677", "roberto@email.com","Histórico de infrações frequentes."),
    ("Renata Lopes Ferreira",     "678.901.234-00", "(11) 98800-7766", "renata@email.com", "Cadastro recente, sem veículos ainda."),
]


# ── Veículos ──────────────────────────────────────────────────────────────────
# Cobre: Mercosul, placa antiga, passeio/carga/reboque, ativo/desativado/vendido,
# proprietário diferente do cliente.
VEICULOS = [
    # cliente, placa, renavam, proprietario, marca_modelo, situacao, especie, obs
    # Carlos — frota variada (5 veículos)
    ("Carlos Eduardo Martins", "ABC1D23", "12345678901", "Carlos Eduardo Martins",  "Toyota Corolla XEi 2022",    "ativo",      "passeio", ""),
    ("Carlos Eduardo Martins", "DEF4567", "23456789012", "Maria Martins (esposa)",  "Fiat Strada 2020",           "ativo",      "carga",   "Usado no negócio."),
    ("Carlos Eduardo Martins", "GHI5J67", "34567890123", "Carlos Eduardo Martins",  "Honda CB 500 2023",          "ativo",      "passeio", "Motocicleta."),
    ("Carlos Eduardo Martins", "JKL8901", "45678901234", "Carlos Eduardo Martins",  "Renault Kwid 2019",          "vendido",    "passeio", "Vendido em 01/2026."),
    ("Carlos Eduardo Martins", "MNO2345", "56789012345", "Carlos Eduardo Martins",  "Volkswagen Gol G6 2015",     "desativado", "passeio", "Em manutenção prolongada."),

    # Transportes Rápido — frota de carga (4 veículos)
    ("Transportes Rápido Ltda", "PQR6789", "67890123456", "Transportes Rápido Ltda", "Volvo FH 540 2021",         "ativo",      "carga",   "Caminhão principal."),
    ("Transportes Rápido Ltda", "STU0123", "78901234567", "Transportes Rápido Ltda", "Scania R450 2020",          "ativo",      "carga",   ""),
    ("Transportes Rápido Ltda", "VWX4567", "89012345678", "Transportes Rápido Ltda", "Carreta Randon SR 2019",    "ativo",      "reboque", "Acoplada ao Volvo FH."),
    ("Transportes Rápido Ltda", "YZA8901", "90123456789", "Transportes Rápido Ltda", "Mercedes Atego 1719 2017",  "desativado", "carga",   "Reserva."),

    # Ana — 1 veículo simples
    ("Ana Beatriz Costa",      "BCD2345", "01234567890", "Ana Beatriz Costa",       "Hyundai HB20 2022",          "ativo",      "passeio", ""),

    # Pedro — proprietário diferente (inventário)
    ("Pedro Henrique Souza",   "EFG6789", "11234567890", "José Souza (pai, falecido)", "Volkswagen Gol G5 2010", "ativo",      "passeio", "Transferência pendente por inventário."),

    # Roberto — 2 veículos com multas
    ("Roberto Alves Pereira",  "HIJ0123", "21234567890", "Banco Itaú S/A (financiado)", "Chevrolet S10 2023",    "ativo",      "passeio", "Alienação fiduciária."),
    ("Roberto Alves Pereira",  "KLM4567", "31234567890", "Roberto Alves Pereira",    "Fiat Toro Freedom 2021",   "ativo",      "passeio", ""),
]


def inserir_clientes():
    ids = {}
    for nome, cpf, tel, email, obs in CLIENTES:
        c = Cliente(nome=nome, cpf=cpf, telefone=tel, email=email, observacao=obs)
        db.session.add(c)
        db.session.flush()
        ids[nome] = c.id
    db.session.commit()
    return ids


def inserir_veiculos(clientes):
    ids = {}
    for cliente_nome, placa, renavam, prop, marca, situ, esp, obs in VEICULOS:
        v = Veiculo(
            cliente_id=clientes[cliente_nome],
            placa=placa.replace("-", ""),
            renavam=renavam,
            proprietario=prop,
            marca_modelo=marca,
            situacao=situ,
            especie=esp,
            observacao=obs,
        )
        db.session.add(v)
        db.session.flush()
        ids[placa.replace("-", "")] = v.id
    db.session.commit()
    return ids


def inserir_ipva(veiculos):
    svc = IpvaService(db.session)

    # (placa, ano, valor, venc_delta, tipo, pago, pag_delta, obs)
    registros = [
        # ── À vista: histórico pago ──────────────────────────────────────
        ("ABC1D23", 2024, 980.00,  -400, "avista", True,  -395, ""),
        ("ABC1D23", 2025, 960.00,  -180, "avista", True,  -175, ""),
        ("BCD2345", 2025, 540.00,  -200, "avista", True,  -195, ""),
        ("PQR6789", 2025, 3200.00, -180, "avista", True,  -175, ""),
        ("HIJ0123", 2025, 820.00,  -180, "avista", True,  -174, ""),

        # ── À vista: pendente (vencimento futuro) ────────────────────────
        ("ABC1D23", 2026, 1010.00,  20, "avista", False, None, ""),
        ("GHI5J67", 2026,  195.00,  35, "avista", False, None, "Moto — valor reduzido."),
        ("BCD2345", 2026,  565.00,  14, "avista", False, None, ""),
        ("EFG6789", 2026,  415.00,  10, "avista", False, None, ""),
        ("STU0123", 2026, 3100.00,  25, "avista", False, None, ""),

        # ── À vista: vencido não pago ────────────────────────────────────
        ("DEF4567", 2026,  650.00,  -8, "avista", False, None, "Aguardando regularização."),
        ("KLM4567", 2026,  785.00, -25, "avista", False, None, "Cliente notificado."),
        ("VWX4567", 2026,  980.00,  -3, "avista", False, None, "Reboque — vencido recentemente."),
        ("YZA8901", 2026, 2100.00, -90, "avista", False, None, "Veículo desativado."),
        ("MNO2345", 2026,  620.00, -60, "avista", False, None, "Veículo desativado."),

        # ── Parcelado: configurado abaixo via IpvaService ────────────────
        # 2× ambas pendentes
        ("PQR6789", 2026, 3450.00,  5, "parcelado", False, None, "2× — ambas pendentes."),
        # 3× todas pagas
        ("STU0123", 2025, 3100.00, -300, "parcelado", False, None, "3× — todas pagas."),
        # 5× 1 vencida 4 pendentes
        ("VWX4567", 2025, 1200.00, -35, "parcelado", False, None, "5× — 1ª vencida."),
        # 4× parcialmente pago (1 paga, 1 vencida, 2 futuras)
        ("ABC1D23", 2023, 890.00,  -60, "parcelado", False, None, "4× — parcialmente pago."),
        # 3× 2 pagas 1 pendente
        ("HIJ0123", 2026, 860.00,  -70, "parcelado", False, None, "3× — 2 pagas, 1 pendente."),
    ]

    ipvas = {}
    for placa, ano, valor, venc_delta, tipo, pago, pag_delta, obs in registros:
        i = Ipva(
            veiculo_id=veiculos[placa],
            ano_referencia=ano,
            valor=valor,
            vencimento=d(venc_delta),
            tipo_pagamento=tipo,
            pago=pago,
            data_pagamento=d(pag_delta) if pag_delta else None,
            observacao=obs,
        )
        db.session.add(i)
        db.session.flush()
        ipvas[(placa, ano)] = i.id
    db.session.commit()

    # Cenário A — PQR6789/2026 — 2× pendentes
    svc.gerar_parcelas(ipvas[("PQR6789", 2026)], 2, 3450.00, d(5))

    # Cenário B — STU0123/2025 — 3× todas pagas
    svc.gerar_parcelas(ipvas[("STU0123", 2025)], 3, 3100.00, d(-300))
    for p in db.session.query(IpvaParcela).filter_by(ipva_id=ipvas[("STU0123", 2025)]).all():
        p.status = "pago"
        p.pago_em = d(-290 + (p.numero - 1) * 30)
    ipva_b = db.session.get(Ipva, ipvas[("STU0123", 2025)])
    ipva_b.pago = True
    ipva_b.data_pagamento = d(-240)
    db.session.commit()

    # Cenário C — VWX4567/2025 — 5× 1ª vencida
    svc.gerar_parcelas(ipvas[("VWX4567", 2025)], 5, 1200.00, d(-35))
    p1 = db.session.query(IpvaParcela).filter_by(
        ipva_id=ipvas[("VWX4567", 2025)]
    ).order_by(IpvaParcela.numero).first()
    if p1:
        p1.status = "vencido"
    db.session.commit()

    # Cenário D — ABC1D23/2023 — 4× 1ª paga, 2ª vencida, 3ª/4ª pendentes
    svc.gerar_parcelas(ipvas[("ABC1D23", 2023)], 4, 890.00, d(-60))
    parc_d = db.session.query(IpvaParcela).filter_by(
        ipva_id=ipvas[("ABC1D23", 2023)]
    ).order_by(IpvaParcela.numero).all()
    if len(parc_d) >= 2:
        parc_d[0].status = "pago"
        parc_d[0].pago_em = d(-58)
        parc_d[1].status = "vencido"
    db.session.commit()

    # Cenário E — HIJ0123/2026 — 3× 2 pagas 1 pendente
    svc.gerar_parcelas(ipvas[("HIJ0123", 2026)], 3, 860.00, d(-70))
    parc_e = db.session.query(IpvaParcela).filter_by(
        ipva_id=ipvas[("HIJ0123", 2026)]
    ).order_by(IpvaParcela.numero).all()
    if len(parc_e) >= 2:
        parc_e[0].status = "pago"
        parc_e[0].pago_em = d(-68)
        parc_e[1].status = "pago"
        parc_e[1].pago_em = d(-38)
    db.session.commit()

    return len(registros)


def inserir_licenciamento(veiculos):
    # (placa, ano, valor, venc_delta, pago, pag_delta, obs)
    registros = [
        ("ABC1D23", 2025, 145.00, -180, True,  -175, ""),
        ("ABC1D23", 2026, 150.00,  28,  False, None,  ""),
        ("DEF4567", 2026, 145.00,  -5,  False, None,  "Vencido — cliente notificado."),
        ("GHI5J67", 2026, 100.00,  12,  False, None,  "Moto."),
        ("BCD2345", 2025, 145.00, -350, True,  -345,  ""),
        ("BCD2345", 2026, 150.00,  45,  False, None,  ""),
        ("EFG6789", 2026, 145.00,  -20, False, None,  "Bloqueado por transferência."),
        ("PQR6789", 2025, 310.00, -180, True,  -175,  ""),
        ("PQR6789", 2026, 310.00,  18,  False, None,  ""),
        ("STU0123", 2026, 310.00,  -7,  False, None,  "Vencido."),
        ("VWX4567", 2026, 310.00,   3,  False, None,  "Vencimento em 3 dias — urgente."),
        ("HIJ0123", 2025, 145.00, -200, True,  -195,  ""),
        ("HIJ0123", 2026, 150.00,  14,  False, None,  ""),
        ("KLM4567", 2026, 145.00, -18,  False, None,  "Vencido."),
    ]

    for placa, ano, valor, venc_delta, pago, pag_delta, obs in registros:
        db.session.add(Licenciamento(
            veiculo_id=veiculos[placa],
            ano_referencia=ano,
            valor=valor,
            vencimento=d(venc_delta),
            pago=pago,
            data_pagamento=d(pag_delta) if pag_delta else None,
            observacao=obs,
        ))
    db.session.commit()
    return len(registros)


def inserir_multas(veiculos):
    # (placa, auto, dias_inf, descricao, valor, dias_venc, pago, dias_pag, obs)
    registros = [
        ("ABC1D23", "DETRAN-001", -40, "Excesso de velocidade até 20% — Art. 218,I",   130.16,  -10, True,  -12, "Pago com desconto."),
        ("DEF4567", "CET-002",    -15, "Estacionamento proibido — Art. 181,I",          195.23,   10, False, None, "Recurso em andamento."),
        ("PQR6789", "PRF-003",    -60, "Avanço de sinal — Art. 208",                    293.47,  -25, False, None, "Vencida. Encaminhar protesto."),
        ("STU0123", "PRF-004",     -5, "Excesso de velocidade >50% — Art. 218,III",     880.41,   40, False, None, "Dentro do prazo de desconto."),
        ("BCD2345", "DETRAN-005",-100, "Uso de celular — Art. 252,V",                   293.47,  -70, True,  -68, "Pago no prazo."),
        ("VWX4567", "DER-006",     -8, "Excesso de carga — Art. 230,V",                1302.66,   15, False, None, "Notificar motorista."),
        ("ABC1D23", "DETRAN-007",-200, "CNH vencida — Art. 162,I",                      293.47, -165, True, -168, "Pago com desconto."),
        ("EFG6789", "DETRAN-008", -12, "Sem extintor — Art. 230,I",                     195.23,   18, False, None, "Dentro do prazo."),
        # Roberto — histórico pesado
        ("KLM4567", "DETRAN-009",  -5, "Velocidade 20–50% — Art. 218,II",              195.23,   25, False, None, "Dentro do prazo de desconto."),
        ("KLM4567", "PRF-010",    -60, "Ultrapassagem indevida — Art. 220",             293.47,  -30, False, None, "Vencida — protesto."),
        ("HIJ0123", "DETRAN-011", -90, "Sem CRLV — Art. 232",                           293.47,  -60, True,  -62, "Pago com desconto."),
        ("KLM4567", "SENATRAN-012",-180,"CNH suspensa — Art. 162,II",                   293.47, -145, True, -147, "Recurso parcialmente aceito."),
        # Multa com vencimento hoje (edge case)
        ("GHI5J67", "DETRAN-013", -30, "Passageiro sem capacete — Art. 244,V",         293.47,    0, False, None, "Vencimento hoje."),
        # Valor alto (caminhão)
        ("PQR6789", "PRF-014",    -20, "Excesso de peso — Art. 99",                   2934.70,   10, False, None, "Excesso acima de 5%."),
    ]

    for placa, auto, dias_inf, desc, valor, dias_venc, pago, dias_pag, obs in registros:
        db.session.add(Multa(
            veiculo_id=veiculos[placa],
            auto_infracao=auto,
            data_infracao=d(dias_inf),
            descricao=desc,
            valor=valor,
            vencimento=d(dias_venc),
            pago=pago,
            data_pagamento=d(dias_pag) if dias_pag else None,
            observacao=obs,
        ))
    db.session.commit()
    return len(registros)


def inserir_documentos(clientes):
    registros = [
        ("Carlos Eduardo Martins",  "RG e CPF",                   -500, "documento_pessoal",      "Cópia autenticada."),
        ("Carlos Eduardo Martins",  "Comprovante de Residência",    -30, "comprovante_residencia", "Conta de luz — Elektro."),
        ("Carlos Eduardo Martins",  "Procuração ao Despachante",    -15, "procuracao",             "Autoriza todos os trâmites."),
        ("Transportes Rápido Ltda", "Contrato Social",             -800, "contrato",               "Última alteração: 2023."),
        ("Transportes Rápido Ltda", "Procuração — Setor Financeiro", -90, "procuracao",            "Retirada de docs no DETRAN."),
        ("Ana Beatriz Costa",       "CNH — categoria B",           -600, "documento_pessoal",      "Válida até 2028."),
        ("Ana Beatriz Costa",       "Comprovante de Residência",    -10, "comprovante_residencia", ""),
        ("Pedro Henrique Souza",    "Certidão de Óbito do Pai",   -120, "outro",                  "Necessário para inventário."),
        ("Pedro Henrique Souza",    "Alvará Judicial",              -45, "outro",                  "Autoriza transferência."),
        ("Roberto Alves Pereira",   "CNH — categoria B/C",        -730, "documento_pessoal",      "Válida até 2027."),
        ("Roberto Alves Pereira",   "Notificação DETRAN — suspensão", -5, "outro",                "1ª notificação por pontuação."),
        # Cliente sem veículos também tem documento
        ("Renata Lopes Ferreira",   "CPF e RG",                    -20, "documento_pessoal",      "Pré-cadastro."),
    ]

    for cliente_nome, nome_doc, dias_doc, categoria, obs in registros:
        db.session.add(Documento(
            cliente_id=clientes[cliente_nome],
            nome=nome_doc,
            data_documento=d(dias_doc),
            categoria=categoria,
            observacao=obs,
            arquivo=None,
        ))
    db.session.commit()
    return len(registros)


def seed():
    init_db()
    with app.app_context():
        limpar()
        print("🗑️   Banco limpo.\n")

        clientes = inserir_clientes()
        print(f"✅  {len(CLIENTES)} clientes")

        veiculos = inserir_veiculos(clientes)
        print(f"✅  {len(VEICULOS)} veículos")

        n_ipva = inserir_ipva(veiculos)
        print(f"✅  {n_ipva} registros de IPVA (5 cenários de parcelamento)")

        n_lic = inserir_licenciamento(veiculos)
        print(f"✅  {n_lic} licenciamentos")

        n_multas = inserir_multas(veiculos)
        print(f"✅  {n_multas} multas")

        n_docs = inserir_documentos(clientes)
        print(f"✅  {n_docs} documentos")

        print("\n─── Seed concluído ──────────────────────────────")
        print("Login: admin / admin123")


if __name__ == "__main__":
    seed()