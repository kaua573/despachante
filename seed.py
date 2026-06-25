# Uso: python seed.py
# ⚠️  Apaga todos os dados existentes antes de inserir.

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


def dias(n: int) -> str:
    """Retorna data ISO relativa a hoje. Positivo = futuro, negativo = passado."""
    return (date.today() + timedelta(days=n)).isoformat()


def seed():
    init_db()
    with app.app_context():
        # ── Limpa tabelas na ordem correta para respeitar FKs ──────────────
        for modelo in [IpvaParcela, Multa, Ipva, Licenciamento, Documento, Veiculo, Cliente]:
            db.session.query(modelo).delete()
        db.session.commit()
        print("🗑️   Banco limpo.\n")

        # ── Clientes ───────────────────────────────────────────────────────
        # Cobre: pessoa física, pessoa jurídica, cliente sem veículos,
        # cliente com múltiplos veículos e proprietários diferentes.
        clientes_data = [
            # nome, cpf/cnpj, telefone, email, observacao
            ("João Carlos Silva",         "123.456.789-09", "(18) 99111-2233", "joao@email.com",        "Cliente antigo, prefere WhatsApp."),
            ("Maria Fernanda Oliveira",   "234.567.890-97", "(18) 99222-3344", "maria@email.com",       ""),
            ("Transportes Rápido Ltda",   "12.345.678/0001-95", "(18) 3222-4455", "contato@tr.com.br", "Frota com 4 veículos. Pagamento via boleto."),
            ("Pedro Henrique Souza",      "345.678.901-82", "(18) 99333-4455", "pedro@email.com",       "Transferência de titularidade pendente."),
            ("Ana Beatriz Costa",         "456.789.012-68", "(18) 99444-5566", "ana@email.com",         ""),
            ("Carlos Eduardo Martins",    "567.890.123-91", "(18) 99555-6677", "carlos@email.com",      ""),
            ("Distribuidora Bom Preço",   "23.456.789/0001-77", "(18) 3233-5566", "fin@bompreco.com",  "Múltiplos veículos. Contato: Financeiro."),
            # Cliente sem veículos — testa edge case na listagem e PDF
            ("Renata Lopes Ferreira",     "678.901.234-00", "(11) 98888-7766", "renata@email.com",      "Cadastro recente, sem veículos ainda."),
            # Pessoa física com muitas multas
            ("Roberto Alves Pereira",     "789.012.345-10", "(14) 99666-7788", "roberto@email.com",     "Histórico de infrações frequentes."),
            # Pessoa jurídica pequena com 1 veículo
            ("Agropecuária São Lucas Ltda","34.567.890/0001-11","(18) 3244-6677","fiscal@saolucas.com.br","Produtor rural — veículos agrícolas."),
            # Cliente com e-mail incomum / sem arroba (testa validação)
            ("Luciana Moreira Santos",    "890.123.456-21", "(11) 94444-3322", "",                      "Sem e-mail cadastrado. Contato apenas por telefone."),
            # Cliente com nome longo e caracteres especiais
            ("Sebastião D'Ávila Gonçalves Neto", "901.234.567-35", "(17) 99777-8899", "sebastiao@email.com", ""),
            # Segunda pessoa jurídica grande
            ("Logística Pantanal S/A",    "45.678.901/0001-33","(67) 3333-9900","operacoes@pantanal.com","Frota com veículos em vários estados. MS/SP."),
        ]

        clientes = {}
        for nome, cpf, tel, email, obs in clientes_data:
            c = Cliente(nome=nome, cpf=cpf, telefone=tel, email=email, observacao=obs)
            db.session.add(c)
            db.session.flush()
            clientes[nome] = c.id
        db.session.commit()
        print(f"✅  {len(clientes_data)} clientes inseridos.")

        # ── Veículos ───────────────────────────────────────────────────────
        # Cobre: placa Mercosul, placa antiga, passeio, carga, reboque,
        # situações ativo/desativado/vendido, proprietário diferente do cliente.
        veiculos_data = [
            # cliente, placa, renavam, proprietario, marca_modelo, situacao, especie, obs
            ("João Carlos Silva",       "ABC1D23", "12345678901", "João Carlos Silva",          "Chevrolet Onix LT 2021",   "ativo",      "passeio", ""),
            ("João Carlos Silva",       "DEF-4567","23456789012", "Maria Silva (esposa)",        "Fiat Strada 2020",          "ativo",      "carga",   "Usado no comércio familiar."),
            ("Maria Fernanda Oliveira", "GHI5J67", "34567890123", "Maria Fernanda Oliveira",    "Hyundai HB20 2022",         "ativo",      "passeio", ""),
            ("Transportes Rápido Ltda", "JKL8M90", "45678901234", "Transportes Rápido Ltda",   "Volvo FH 540 2019",         "ativo",      "carga",   "Caminhão principal da frota."),
            ("Transportes Rápido Ltda", "NOP2Q34", "56789012345", "Transportes Rápido Ltda",   "Scania R450 2020",          "ativo",      "carga",   ""),
            ("Transportes Rápido Ltda", "RST6U78", "67890123456", "Transportes Rápido Ltda",   "Carreta Randon SR 2018",    "ativo",      "reboque", "Acoplada ao Volvo FH."),
            ("Transportes Rápido Ltda", "VWX-1234","78901234567", "Transportes Rápido Ltda",   "Mercedes Atego 1719 2017",  "desativado", "carga",   "Em manutenção prolongada."),
            ("Pedro Henrique Souza",    "ZAB9C01", "89012345678", "José Souza (pai, falecido)", "Volkswagen Gol G5 2010",    "ativo",      "passeio", "Transferência pendente por inventário."),
            ("Ana Beatriz Costa",       "DEF2G34", "90123456789", "Ana Beatriz Costa",          "Honda CG 160 2023",         "ativo",      "passeio", "Motocicleta."),
            ("Carlos Eduardo Martins",  "HIJ5K67", "01234567890", "Carlos Eduardo Martins",    "Toyota Corolla XEi 2022",   "ativo",      "passeio", ""),
            ("Distribuidora Bom Preço", "LMN8O90", "11234567890", "Distribuidora Bom Preço",   "Iveco Daily 70-170 2021",   "ativo",      "carga",   ""),
            ("Distribuidora Bom Preço", "PQR-5678","21234567890", "Distribuidora Bom Preço",   "Carreta Facchini 2019",     "ativo",      "reboque", ""),
            ("Distribuidora Bom Preço", "TUV3W45", "31234567890", "Distribuidora Bom Preço",   "Ford Cargo 1719 2016",      "desativado", "carga",   "Reserva — sem uso desde 2024."),
            # Veículo vendido — testa a situação 'vendido' no painel
            ("João Carlos Silva",       "XYZ-9012","41234567890", "João Carlos Silva",          "Renault Kwid 2019",         "vendido",    "passeio", "Vendido em 03/2026."),
            # ── Novos cenários ────────────────────────────────────────────────
            # Moto de frota (cliente PJ)
            ("Distribuidora Bom Preço", "EFG4H56", "51234567890", "Distribuidora Bom Preço",   "Honda CG 160 Cargo 2023",   "ativo",      "passeio", "Moto de entrega."),
            # Veículo com placa de outro estado (MS) — cliente Logística Pantanal
            ("Logística Pantanal S/A",  "MSA1B23", "61234567890", "Logística Pantanal S/A",    "Scania R500 2022",          "ativo",      "carga",   "Emplacado em MS."),
            ("Logística Pantanal S/A",  "MSC4D56", "71234567890", "Logística Pantanal S/A",    "Carreta Guerra 2021",       "ativo",      "reboque", "Acoplada ao Scania R500."),
            ("Logística Pantanal S/A",  "IJK7L89", "81234567890", "Logística Pantanal S/A",    "Volkswagen Constellation 2020","ativo",   "carga",   "Base em SP."),
            # Veículo agrícola / trator (especie diferente)
            ("Agropecuária São Lucas Ltda","OPQ2R34","91234567890","Agropecuária São Lucas Ltda","John Deere 5075E 2021",     "ativo",      "especial","Trator agrícola."),
            # Veículo com proprietário diferente do cliente (arrendamento)
            ("Roberto Alves Pereira",   "STU5V67", "02234567890", "Banco Itaú S/A (financiado)","Chevrolet S10 LS 2023",    "ativo",      "passeio", "Financiado — alienação fiduciária Banco Itaú."),
            # Caminhonete do cliente com multas
            ("Roberto Alves Pereira",   "WXY8Z01", "03234567890", "Roberto Alves Pereira",     "Fiat Toro Freedom 2021",    "ativo",      "passeio", ""),
            # Veículo antigo com placa modelo antigo
            ("Luciana Moreira Santos",  "BCD-3456","04234567890", "Luciana Moreira Santos",    "Volkswagen Parati 1.6 2004","ativo",      "passeio", "Veículo antigo, IPVA reduzido."),
            # Ônibus (tipo diferente)
            ("Logística Pantanal S/A",  "EFG-7890","05234567890", "Logística Pantanal S/A",    "Marcopolo Paradiso 1200 2019","ativo",    "passeio", "Ônibus fretamento."),
            # Veículo em nome de terceiro (Sebastião)
            ("Sebastião D'Ávila Gonçalves Neto","HIJ1K23","06234567890","Sebastião D'Ávila Gonçalves Neto","Toyota Hilux SRX 2024","ativo","passeio","Veículo novo, 1º licenciamento em 2026."),
        ]

        veiculos = {}
        for cliente_nome, placa, renavam, prop, marca, situ, esp, obs in veiculos_data:
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
            veiculos[placa.replace("-", "")] = v.id
        db.session.commit()
        print(f"✅  {len(veiculos_data)} veículos inseridos.")

        # ── IPVA ───────────────────────────────────────────────────────────
        # Cobre: à vista pago, à vista pendente, à vista vencido,
        # parcelado (2×) todas pagas, parcelado (3×) parcialmente pago,
        # parcelado (5×) com vencidas, parcelado (4×) todas pendentes.
        ipva_service = IpvaService(db.session)

        ipva_data = [
            # placa, ano, valor, venc_delta, tipo, pago, pag_delta, obs
            # ── À vista: pago ──────────────────────────────────────────────
            ("ABC1D23",  2025, 780.50,  -200, "avista", True,  -195, "Pago em cota única."),
            ("GHI5J67",  2025, 540.00,  -300, "avista", True,  -295, ""),
            ("HIJ5K67",  2025, 960.00,  -400, "avista", True,  -392, ""),
            ("XYZ9012",  2025, 480.00,  -300, "avista", True,  -298, "Pago antes da venda."),
            # ── À vista: pendente (vencimento futuro) ──────────────────────
            ("ABC1D23",  2026, 820.00,   15,  "avista", False, None, ""),
            ("GHI5J67",  2026, 565.00,   25,  "avista", False, None, ""),
            ("DEF2G34",  2026, 185.00,    8,  "avista", False, None, "Motocicleta, valor reduzido."),
            ("RST6U78",  2026, 980.00,   40,  "avista", False, None, ""),
            # ── À vista: vencido (vencimento passado, não pago) ───────────
            ("DEF4567",  2026, 650.30,  -10,  "avista", False, None, "Aguardando regularização."),
            ("NOP2Q34",  2026, 3200.00,  -3,  "avista", False, None, "Vencido recentemente."),
            ("VWX1234",  2026, 2100.00, -90,  "avista", False, None, "Veículo desativado."),
            ("ZAB9C01",  2026, 415.00,  -15,  "avista", False, None, "Pendência de transferência."),
            ("TUV3W45",  2026, 1320.00, -60,  "avista", False, None, "Veículo desativado."),
            # ── Parcelado: configurados depois via IpvaService ────────────
            # (marcados com tipo='parcelado' e num_parcelas definido abaixo)
            ("JKL8M90",  2026, 3450.00,   5,  "parcelado", False, None, "2× — ambas pendentes."),
            ("NOP2Q34",  2025, 3100.00, -300, "parcelado", True,  None, "3× — todas pagas."),
            ("LMN8O90",  2026, 1450.00,  -1,  "parcelado", False, None, "5× — 1 vencida, 4 pendentes."),
            ("HIJ5K67",  2026, 960.00,   60,  "parcelado", False, None, "4× — todas pendentes, 2 vencidas não."),
            # ── Novos registros de IPVA ───────────────────────────────────────
            # Moto de entrega — à vista pago 2025
            ("EFG4H56",  2025, 210.00,  -180, "avista", True,  -175, ""),
            # Moto de entrega — 2026 pendente
            ("EFG4H56",  2026, 225.00,   20,  "avista", False, None, ""),
            # Caminhão MS — à vista vencido
            ("MSA1B23",  2026, 4100.00,  -8,  "avista", False, None, "IPVA de MS — em atraso."),
            # Caminhão SP — à vista pendente futuro
            ("IJK7L89",  2026, 3750.00,  30,  "avista", False, None, ""),
            # Trator agrícola — isento/valor simbólico (testa valor zero ou mínimo)
            ("OPQ2R34",  2026,  80.00,   45,  "avista", False, None, "IPVA rural com isenção parcial."),
            # S10 financiada — paga 2025
            ("STU5V67",  2025, 820.00,  -200, "avista", True,  -195, ""),
            # S10 financiada — parcelado 2026 (3× — 2 pagas, 1 pendente)
            ("STU5V67",  2026, 860.00,  -40,  "parcelado", False, None, "3× — 2 pagas, 1 pendente."),
            # Toro 2021 — pago 2025
            ("WXY8Z01",  2025, 750.00,  -160, "avista", True,  -155, ""),
            # Toro 2021 — vencido não pago 2026
            ("WXY8Z01",  2026, 785.00,  -25,  "avista", False, None, "Proprietário com multas — checar débitos."),
            # Parati 2004 — valor bem reduzido (veículo antigo)
            ("BCD3456",  2025,  60.00,  -360, "avista", True,  -355, "IPVA reduzido — veículo com mais de 20 anos."),
            ("BCD3456",  2026,  65.00,   10,  "avista", False, None, ""),
            # Ônibus — parcelado 2026 (4× — todas pendentes)
            ("EFG7890",  2026, 5200.00,  15,  "parcelado", False, None, "4× — ônibus, valor alto."),
            # Hilux nova — à vista pendente 2026 (1º IPVA)
            ("HIJ1K23",  2026, 1250.00,  35,  "avista", False, None, "1º IPVA do veículo, emplacado em 2025."),
        ]

        ipvas = {}  # (placa, ano) → id
        for placa, ano, valor, venc_delta, tipo, pago, pag_delta, obs in ipva_data:
            i = Ipva(
                veiculo_id=veiculos[placa],
                ano_referencia=ano,
                valor=valor,
                vencimento=dias(venc_delta),
                tipo_pagamento=tipo,
                pago=pago,
                data_pagamento=dias(pag_delta) if pag_delta else None,
                observacao=obs,
            )
            db.session.add(i)
            db.session.flush()
            ipvas[(placa, ano)] = i.id
        db.session.commit()

        # ── Parcelamento: gera as parcelas para os 4 IPVAs parcelados ─────
        # Cenário A — JKL8M90 2026 — 2× — ambas pendentes (vencimento futuro)
        ipva_service.gerar_parcelas(
            ipvas[("JKL8M90", 2026)],
            num_parcelas=2,
            valor_total=3450.00,
            data_primeira=dias(5),
        )

        # Cenário B — NOP2Q34 2025 — 3× — todas pagas
        ok, _ = ipva_service.gerar_parcelas(
            ipvas[("NOP2Q34", 2025)],
            num_parcelas=3,
            valor_total=3100.00,
            data_primeira=dias(-300),
        )
        if ok:
            parcelas_b = db.session.query(IpvaParcela).filter_by(
                ipva_id=ipvas[("NOP2Q34", 2025)]
            ).all()
            for p in parcelas_b:
                p.status = "pago"
                p.pago_em = dias(-290 + parcelas_b.index(p) * 30)
            # Sincroniza ipva.pago = True
            ipva_b = db.session.get(Ipva, ipvas[("NOP2Q34", 2025)])
            ipva_b.pago = True
            ipva_b.data_pagamento = dias(-240)
            db.session.commit()

        # Cenário C — LMN8O90 2026 — 5× — 1ª vencida não paga, 4 pendentes futuras
        ipva_service.gerar_parcelas(
            ipvas[("LMN8O90", 2026)],
            num_parcelas=5,
            valor_total=1450.00,
            data_primeira=dias(-35),  # 1ª já vencida
        )
        parc_c = db.session.query(IpvaParcela).filter_by(
            ipva_id=ipvas[("LMN8O90", 2026)]
        ).order_by(IpvaParcela.numero).first()
        if parc_c:
            parc_c.status = "vencido"
            db.session.commit()

        # Cenário D — HIJ5K67 2026 — 4× — parcialmente pago: 1ª paga, demais pendentes
        ipva_service.gerar_parcelas(
            ipvas[("HIJ5K67", 2026)],
            num_parcelas=4,
            valor_total=960.00,
            data_primeira=dias(-60),
        )
        parc_d = db.session.query(IpvaParcela).filter_by(
            ipva_id=ipvas[("HIJ5K67", 2026)]
        ).order_by(IpvaParcela.numero).all()
        if parc_d:
            parc_d[0].status = "pago"
            parc_d[0].pago_em = dias(-58)
            # 2ª parcela vencida e não paga
            if len(parc_d) > 1:
                parc_d[1].status = "vencido"
            db.session.commit()

        # Cenário E — STU5V67 2026 — 3× — 2 pagas, 1 pendente
        ipva_service.gerar_parcelas(
            ipvas[("STU5V67", 2026)],
            num_parcelas=3,
            valor_total=860.00,
            data_primeira=dias(-70),
        )
        parc_e = db.session.query(IpvaParcela).filter_by(
            ipva_id=ipvas[("STU5V67", 2026)]
        ).order_by(IpvaParcela.numero).all()
        if len(parc_e) >= 2:
            parc_e[0].status = "pago"
            parc_e[0].pago_em = dias(-68)
            parc_e[1].status = "pago"
            parc_e[1].pago_em = dias(-38)
            db.session.commit()

        # Cenário F — EFG7890 2026 — 4× — todas pendentes (ônibus)
        ipva_service.gerar_parcelas(
            ipvas[("EFG7890", 2026)],
            num_parcelas=4,
            valor_total=5200.00,
            data_primeira=dias(15),
        )

        total_ipva = len(ipva_data)
        print(f"✅  {total_ipva} registros de IPVA inseridos (4 parcelados com parcelas configuradas).")

        # ── Licenciamento ──────────────────────────────────────────────────
        # Cobre: pago válido, vencido não pago, próximo do vencimento,
        # emitido recentemente, veículo de carga (valor diferente).
        lic_data = [
            # placa, ano, valor, venc_delta, pago, pag_delta, obs
            ("ABC1D23",  2025, 130.00, -180, True,  -175, ""),
            ("ABC1D23",  2026, 145.00,   28, False,  None, ""),
            ("DEF4567",  2026, 145.00,   -5, False,  None, "Vencido — cliente notificado."),
            ("GHI5J67",  2026, 145.00,   12, False,  None, ""),
            ("JKL8M90",  2026, 310.00,   18, False,  None, "Caminhão — taxa diferenciada."),
            ("NOP2Q34",  2026, 310.00,   -7, False,  None, ""),
            ("ZAB9C01",  2026, 145.00,  -20, False,  None, "Bloqueado por transferência."),
            ("HIJ5K67",  2025, 145.00, -350, True,  -345, ""),
            ("HIJ5K67",  2026, 150.00,   45, False,  None, ""),
            ("LMN8O90",  2026, 310.00,    3, False,  None, "Vencimento em 3 dias — urgente."),
            ("PQR5678",  2026, 310.00,   22, False,  None, ""),
            ("XYZ9012",  2025, 130.00, -280, True,  -275, "Pago antes da venda."),
            # ── Novos licenciamentos ──────────────────────────────────────────
            ("EFG4H56",  2025, 100.00, -170, True,  -165, "Moto — taxa reduzida."),
            ("EFG4H56",  2026, 110.00,   18, False,  None, ""),
            ("MSA1B23",  2026, 310.00,   -6, False,  None, "Caminhão MS — vencido."),
            ("IJK7L89",  2026, 310.00,   25, False,  None, ""),
            ("OPQ2R34",  2026, 200.00,   50, False,  None, "Trator — licenciamento especial."),
            ("STU5V67",  2025, 145.00, -200, True,  -195, ""),
            ("STU5V67",  2026, 150.00,   14, False,  None, ""),
            ("WXY8Z01",  2026, 145.00,  -18, False,  None, "Vencido — mesmo perfil de IPVA atrasado."),
            ("BCD3456",  2026, 145.00,   30, False,  None, ""),
            ("EFG7890",  2026, 680.00,   20, False,  None, "Ônibus — taxa mais alta."),
            ("HIJ1K23",  2026, 155.00,   40, False,  None, "1º licenciamento, veículo novo."),
            ("MSC4D56",  2026, 310.00,   -2, False,  None, "Carreta — vencimento iminente."),
        ]

        for placa, ano, valor, venc_delta, pago, pag_delta, obs in lic_data:
            db.session.add(Licenciamento(
                veiculo_id=veiculos[placa],
                ano_referencia=ano,
                valor=valor,
                vencimento=dias(venc_delta),
                pago=pago,
                data_pagamento=dias(pag_delta) if pag_delta else None,
                observacao=obs,
            ))
        db.session.commit()
        print(f"✅  {len(lic_data)} registros de licenciamento inseridos.")

        # ── Multas ─────────────────────────────────────────────────────────
        # Cobre: paga com desconto, paga sem desconto (recurso negado),
        # pendente dentro do prazo de desconto, pendente fora do prazo,
        # vencida sem pagamento; órgãos: DETRAN-SP, PRF, CET, DER, SENATRAN.
        multa_data = [
            # placa, auto, dias_inf, descricao, valor, dias_venc, pago, dias_pag, obs
            ("ABC1D23", "DETRAN-000123", -40,
             "Excesso de velocidade até 20% — Art. 218, I CTB",
             130.16, -10, True, -12, "Pago com 20% de desconto por adesão ao REFIS."),

            ("DEF4567", "CET-000234",   -15,
             "Estacionamento em local proibido — Art. 181, I CTB",
             195.23,  10, False, None, "Recurso em 1ª instância — prazo: 10 dias."),

            ("JKL8M90", "PRF-000345",   -60,
             "Avanço de sinal vermelho — Art. 208 CTB",
             293.47, -25, False, None, "Vencida. Enviar para protesto."),

            ("NOP2Q34", "PRF-000456",    -5,
             "Excesso de velocidade acima de 50% — Art. 218, III CTB",
             880.41,  40, False, None, "Dentro do prazo de desconto de 20%."),

            ("HIJ5K67", "DETRAN-000567",-100,
             "Uso de celular ao volante — Art. 252, V CTB",
             293.47, -70, True, -68, "Pago no prazo, sem desconto."),

            ("LMN8O90", "DER-000678",    -8,
             "Transitar com excesso de carga — Art. 230, V CTB",
             1302.66,  15, False, None, "Notificar motorista responsável."),

            ("ABC1D23", "SENATRAN-000789", -200,
             "Dirigir com CNH vencida — Art. 162, I CTB",
             293.47, -165, True, -168, "Pago com desconto via parcelamento do DETRAN."),

            ("ZAB9C01", "DETRAN-000890",  -12,
             "Falta de equipamento obrigatório (extintor) — Art. 230, I CTB",
             195.23,   18, False, None, "Pendente dentro do prazo de desconto."),

            ("NOP2Q34", "PRF-000901",   -180,
             "Trafegar em faixa exclusiva de ônibus — Art. 193 CTB",
             130.16, -145, True, -143, ""),

            ("GHI5J67", "CET-001012",    -3,
             "Parar sobre a faixa de pedestres — Art. 170 CTB",
             195.23,   27, False, None, "Infração recente, prazo de recurso vigente."),
            # ── Novas multas ──────────────────────────────────────────────────
            # Roberto — histórico de infrações
            ("WXY8Z01", "DETRAN-001100",  -5,
             "Velocidade acima de 20% até 50% — Art. 218, II CTB",
             195.23,   25, False, None, "Dentro do prazo de desconto."),
            ("WXY8Z01", "PRF-001101",    -60,
             "Ultrapassagem indevida — Art. 220 CTB",
             293.47,  -30, False, None, "Vencida. Encaminhar para protesto."),
            ("STU5V67", "DETRAN-001200", -90,
             "Circular sem o CRLV — Art. 232 CTB",
             293.47,  -60, True, -62, "Pago com 20% de desconto dentro do prazo."),
            # Caminhão MS — multa de peso em balança federal
            ("MSA1B23", "PRF-001300",   -20,
             "Excesso de peso — Art. 99 CTB",
             2934.70,   10, False, None, "Valor elevado — excesso acima de 5%."),
            # Ônibus — infração em faixa exclusiva
            ("EFG7890", "CET-001400",    -8,
             "Circular em faixa exclusiva de ônibus sem autorização — Art. 193 CTB",
             130.16,   22, False, None, "Irônico: ônibus em faixa de ônibus errada."),
            # Hilux nova — sem cinto (infração leve)
            ("HIJ1K23", "DETRAN-001500",  -2,
             "Deixar de usar cinto de segurança — Art. 167 CTB",
             195.23,   28, False, None, "Infração recentíssima."),
            # Moto entrega — sem capacete passageiro
            ("EFG4H56", "DETRAN-001600", -30,
             "Transportar passageiro sem capacete — Art. 244, V CTB",
             293.47,    0, False, None, "Vencimento hoje — urgente."),
            # Toro — reincidência (segunda multa mesma placa)
            ("WXY8Z01", "SENATRAN-001700",-180,
             "Conduzir veículo com CNH suspensa — Art. 162, II CTB",
             293.47, -145, True, -147, "Pago com recurso parcialmente aceito."),
        ]

        for placa, auto, dias_inf, desc, valor, dias_venc, pago, dias_pag, obs in multa_data:
            db.session.add(Multa(
                veiculo_id=veiculos[placa],
                auto_infracao=auto,
                data_infracao=dias(dias_inf),
                descricao=desc,
                valor=valor,
                vencimento=dias(dias_venc),
                pago=pago,
                data_pagamento=dias(dias_pag) if dias_pag else None,
                observacao=obs,
            ))
        db.session.commit()
        print(f"✅  {len(multa_data)} multas inseridas.")

        # ── Documentos ─────────────────────────────────────────────────────
        doc_data = [
            # cliente, nome_doc, dias_doc, categoria, obs
            ("João Carlos Silva",        "RG e CPF",                      -500, "documento_pessoal",      "Cópia simples autenticada."),
            ("João Carlos Silva",        "Comprovante de Residência",       -30, "comprovante_residencia", "Conta de luz — Elektro."),
            ("Maria Fernanda Oliveira",  "CNH — categoria B",              -600, "documento_pessoal",      "Válida até 2028."),
            ("Transportes Rápido Ltda",  "Contrato Social",                -800, "contrato",               "Última alteração: 2023."),
            ("Transportes Rápido Ltda",  "Procuração — Setor Financeiro",   -90, "procuracao",             "Autoriza retirada de documentos no DETRAN."),
            ("Pedro Henrique Souza",     "Certidão de Óbito do Pai",       -120, "outro",                  "Necessário para inventário e transferência."),
            ("Pedro Henrique Souza",     "Alvará Judicial",                 -45, "outro",                  "Autoriza transferência antes do inventário."),
            ("Carlos Eduardo Martins",   "Comprovante de Residência",       -10, "comprovante_residencia", ""),
            ("Distribuidora Bom Preço",  "CRLV Digital 2026 — LMN8O90",    -5,  "outro",                  ""),
            # Cliente sem veículos também pode ter documentos
            ("Renata Lopes Ferreira",    "CPF e RG",                       -20, "documento_pessoal",      "Pré-cadastro."),
            # ── Novos documentos ──────────────────────────────────────────────
            # Logística Pantanal — empresa com vários documentos
            ("Logística Pantanal S/A",   "Contrato Social",                -730, "contrato",              "Constituição de 2020, objeto: transporte rodoviário."),
            ("Logística Pantanal S/A",   "Procuração — Gerente de Frota",   -60, "procuracao",            "Habilita Marcos Ribeiro a assinar documentos de veículos."),
            ("Logística Pantanal S/A",   "CRLV Digital 2026 — MSA1B23",     -3, "outro",                 ""),
            ("Logística Pantanal S/A",   "CRLV Digital 2026 — IJK7L89",    -10, "outro",                 ""),
            # Agropecuária
            ("Agropecuária São Lucas Ltda","Contrato Social",              -400, "contrato",              ""),
            ("Agropecuária São Lucas Ltda","Nota Fiscal do Trator",         -200, "outro",                "NF-e de aquisição — John Deere 5075E."),
            # Roberto — documentos de CNH e processo
            ("Roberto Alves Pereira",    "CNH — categoria B/C",            -730, "documento_pessoal",     "Válida até 2027. Categoria C adquirida em 2022."),
            ("Roberto Alves Pereira",    "Notificação DETRAN — suspensão",   -5, "outro",                 "1ª notificação de suspensão por pontuação."),
            # Sebastião — comprovante de residência e nota do veículo novo
            ("Sebastião D'Ávila Gonçalves Neto","Comprovante de Residência",  -7, "comprovante_residencia","Conta de água — SABESP."),
            ("Sebastião D'Ávila Gonçalves Neto","Nota Fiscal Hilux SRX 2024",-180, "outro",               "NF-e de aquisição na concessionária."),
            # Luciana — documento vencido (testa filtro de vencidos)
            ("Luciana Moreira Santos",   "CNH — categoria B",             -1500, "documento_pessoal",     "CNH VENCIDA — emitida em 2020, expirou em 2025."),
            # Carlos — procuração p/ despachante
            ("Carlos Eduardo Martins",   "Procuração ao Despachante",       -15, "procuracao",            "Autoriza despachante a tratar de todos os documentos."),
        ]

        for cliente_nome, nome_doc, dias_doc, categoria, obs in doc_data:
            db.session.add(Documento(
                cliente_id=clientes[cliente_nome],
                nome=nome_doc,
                data_documento=dias(dias_doc),
                categoria=categoria,
                observacao=obs,
                arquivo=None,
            ))
        db.session.commit()
        print(f"✅  {len(doc_data)} documentos inseridos.")

        # ── Resumo final ───────────────────────────────────────────────────
        print("\n" + "─" * 50)
        print("🏁  Seed concluído com sucesso!")
        print(f"   {len(clientes_data):>3} clientes  (2 sem veículos, 2 PJ frota, 1 PJ pequena, PF com multas)")
        print(f"   {len(veiculos_data):>3} veículos  (Mercosul + placa antiga, passeio/carga/reboque/especial, ativo/desativado/vendido, trator/ônibus/moto frota)")
        print(f"   {total_ipva:>3} IPVA      (à vista pago/pendente/vencido + 6 cenários de parcelamento)")
        print(f"   {len(lic_data):>3} licenciamentos  (pago, pendente, vencido, urgente, ônibus, trator)")
        print(f"   {len(multa_data):>3} multas    (5 órgãos, paga com/sem desconto, pendente, vencida, reincidência)")
        print(f"   {len(doc_data):>3} documentos (pessoal, contrato, procuração, NF, CNH vencida)")
        print("─" * 50)


if __name__ == "__main__":
    seed()