"""
Popula o banco com dados fictícios para teste.
⚠️  Apaga todos os dados existentes antes de inserir.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta
from run import app, db, init_db
from app.models import Cliente, Veiculo, Ipva, Licenciamento, Multa, Documento


def hoje_mais(dias: int) -> str:
    return (date.today() + timedelta(days=dias)).isoformat()


def seed():
    init_db()
    with app.app_context():
        # Limpa tudo
        for modelo in [Multa, Ipva, Licenciamento, Documento, Veiculo, Cliente]:
            db.session.query(modelo).delete()
        db.session.commit()

        # Clientes
        clientes_data = [
            ("João Carlos Silva",        "123.456.789-00", "(18) 99111-2233", "joao@email.com",       "Cliente antigo."),
            ("Maria Fernanda Oliveira",  "234.567.890-11", "(18) 99222-3344", "maria@email.com",      ""),
            ("Transportes Rápido Ltda",  "12.345.678/0001-99", "(18) 3222-4455", "contato@tr.com.br", "Frota de caminhões."),
            ("Pedro Henrique Souza",     "345.678.901-22", "(18) 99333-4455", "pedro@email.com",      "Transferência pendente."),
            ("Ana Beatriz Costa",        "456.789.012-33", "(18) 99444-5566", "ana@email.com",        "Prefere WhatsApp."),
            ("Carlos Eduardo Martins",   "567.890.123-44", "(18) 99555-6677", "carlos@email.com",     ""),
            ("Distribuidora Bom Preço",  "23.456.789/0001-10", "(18) 3233-5566", "fin@bompreco.com",  "Múltiplos veículos."),
            ("Juliana Aparecida Lima",   "678.901.234-55", "(18) 99666-7788", "juliana@email.com",    "Vendeu o carro."),
        ]
        clientes = {}
        for nome, cpf, tel, email, obs in clientes_data:
            c = Cliente(nome=nome, cpf=cpf, telefone=tel, email=email, observacao=obs)
            db.session.add(c)
            db.session.flush()
            clientes[nome] = c.id
        db.session.commit()

        # Veículos
        veiculos_data = [
            ("João Carlos Silva",       "ABC1D23", "12345678901", "João Carlos Silva",     "Chevrolet Onix LT", "ativo",      "passeio", ""),
            ("João Carlos Silva",       "DEF4G56", "23456789012", "Maria Silva (esposa)",  "Fiat Strada",        "ativo",      "carga",   "Usado no comércio."),
            ("Maria Fernanda Oliveira", "GHI7J89", "34567890123", "Maria Fernanda Oliveira","Hyundai HB20",      "ativo",      "passeio", ""),
            ("Transportes Rápido Ltda", "JKL1M23", "45678901234", "Transportes Rápido Ltda","Volvo FH 540",      "ativo",      "carga",   "Caminhão principal."),
            ("Transportes Rápido Ltda", "NOP4Q56", "56789012345", "Transportes Rápido Ltda","Scania R450",       "ativo",      "carga",   ""),
            ("Transportes Rápido Ltda", "RST7U89", "67890123456", "Transportes Rápido Ltda","Carreta Randon SR", "ativo",      "reboque", "Acoplada ao Volvo."),
            ("Transportes Rápido Ltda", "VWX1Y23", "78901234567", "Transportes Rápido Ltda","Mercedes Atego",   "desativado", "carga",   "Em manutenção."),
            ("Pedro Henrique Souza",    "ZAB4C56", "89012345678", "José Souza (pai, falecido)","Volkswagen Gol", "ativo",      "passeio", "Transferência pendente."),
            ("Ana Beatriz Costa",       "DEF7G89", "90123456789", "Ana Beatriz Costa",     "Honda CG 160",      "ativo",      "passeio", "Motocicleta."),
            ("Carlos Eduardo Martins",  "HIJ1K23", "01234567890", "Carlos Eduardo Martins","Toyota Corolla",    "ativo",      "passeio", ""),
            ("Distribuidora Bom Preço", "LMN4O56", "11234567890", "Distribuidora Bom Preço","Iveco Daily",      "ativo",      "carga",   ""),
            ("Distribuidora Bom Preço", "PQR7S89", "21234567890", "Distribuidora Bom Preço","Carreta Facchini", "ativo",      "reboque", ""),
            ("Distribuidora Bom Preço", "TUV1W23", "31234567890", "Distribuidora Bom Preço","Ford Cargo 1719",  "desativado", "carga",   "Reserva."),
            ("Juliana Aparecida Lima",  "XYZ4A56", "41234567890", "Juliana Aparecida Lima","Renault Kwid",      "vendido",    "passeio", "Vendido em 02/2026."),
        ]
        veiculos = {}
        for cliente_nome, placa, renavam, prop, marca, situ, esp, obs in veiculos_data:
            v = Veiculo(cliente_id=clientes[cliente_nome], placa=placa, renavam=renavam,
                        proprietario=prop, marca_modelo=marca, situacao=situ, especie=esp, observacao=obs)
            db.session.add(v)
            db.session.flush()
            veiculos[placa] = v.id
        db.session.commit()

        # IPVA
        for placa, ano, valor, venc_delta, pago, pag_delta, obs in [
            ("ABC1D23", 2025, 780.50,  -200, True,  -205, ""),
            ("ABC1D23", 2026, 820.00,    15, False,  None, ""),
            ("DEF4G56", 2026, 650.30,   -10, False,  None, "Aguardando pagamento."),
            ("GHI7J89", 2026, 540.00,    25, False,  None, ""),
            ("JKL1M23", 2026, 3450.00,    5, False,  None, "Caminhão categoria especial."),
            ("NOP4Q56", 2026, 3200.00,   -3, False,  None, "Vencido recentemente."),
            ("RST7U89", 2026, 980.00,    40, False,  None, ""),
            ("VWX1Y23", 2026, 2100.00,  -90, False,  None, "Veículo desativado."),
            ("ZAB4C56", 2026, 410.00,   -15, False,  None, "Pendência na transferência."),
            ("DEF7G89", 2026, 180.00,     8, False,  None, ""),
            ("HIJ1K23", 2025, 920.00,  -400, True,  -410, ""),
            ("HIJ1K23", 2026, 960.00,    60, False,  None, ""),
            ("LMN4O56", 2026, 1450.00,   -1, False,  None, "Prioridade alta."),
            ("PQR7S89", 2026, 870.00,    20, False,  None, ""),
            ("TUV1W23", 2026, 1320.00,  -60, False,  None, "Veículo desativado."),
            ("XYZ4A56", 2025, 480.00,  -300, True,  -305, "Pago antes da venda."),
        ]:
            db.session.add(Ipva(
                veiculo_id=veiculos[placa], ano_referencia=ano, valor=valor,
                vencimento=hoje_mais(venc_delta), pago=pago,
                data_pagamento=hoje_mais(pag_delta) if pag_delta else None, observacao=obs
            ))

        # Licenciamento
        for placa, ano, valor, venc_delta, pago, pag_delta, obs in [
            ("ABC1D23", 2025, 130.00, -180, True,  -185, ""),
            ("ABC1D23", 2026, 145.00,   28, False,  None, ""),
            ("DEF4G56", 2026, 145.00,   -5, False,  None, "Atrasado."),
            ("GHI7J89", 2026, 145.00,   12, False,  None, ""),
            ("JKL1M23", 2026, 310.00,   18, False,  None, ""),
            ("NOP4Q56", 2026, 310.00,   -7, False,  None, ""),
            ("ZAB4C56", 2026, 145.00,  -20, False,  None, ""),
            ("HIJ1K23", 2025, 145.00, -350, True,  -355, ""),
            ("HIJ1K23", 2026, 150.00,   45, False,  None, ""),
            ("LMN4O56", 2026, 310.00,    3, False,  None, "Vencimento próximo."),
            ("XYZ4A56", 2025, 130.00, -280, True,  -285, "Pago antes da venda."),
        ]:
            db.session.add(Licenciamento(
                veiculo_id=veiculos[placa], ano_referencia=ano, valor=valor,
                vencimento=hoje_mais(venc_delta), pago=pago,
                data_pagamento=hoje_mais(pag_delta) if pag_delta else None, observacao=obs
            ))

        # Multas
        for placa, auto, dias_inf, desc, valor, dias_venc, pago, dias_pag, obs in [
            ("ABC1D23", "AIT-000123456", -40, "Excesso de velocidade até 20%", 130.16, -10, True,  -12, ""),
            ("DEF4G56", "AIT-000234567", -15, "Estacionar em local proibido",  195.23,  10, False, None, "Recurso em análise."),
            ("JKL1M23", "AIT-000345678", -60, "Avançar sinal vermelho",        293.47, -25, False, None, "Vencida."),
            ("NOP4Q56", "AIT-000456789",  -5, "Excesso de velocidade acima de 50%", 880.41, 40, False, None, ""),
            ("HIJ1K23", "AIT-000567890", -100,"Uso de celular ao volante",     293.47, -70, True,  -72, ""),
            ("LMN4O56", "AIT-000678901",  -8, "Transitar com excesso de peso", 130.16,  15, False, None, "Notificar motorista."),
        ]:
            db.session.add(Multa(
                veiculo_id=veiculos[placa], auto_infracao=auto,
                data_infracao=hoje_mais(dias_inf), descricao=desc, valor=valor,
                vencimento=hoje_mais(dias_venc), pago=pago,
                data_pagamento=hoje_mais(dias_pag) if dias_pag else None, observacao=obs
            ))

        # Documentos
        for cliente_nome, nome_doc, dias_doc, categoria, obs in [
            ("João Carlos Silva",       "RG e CPF",                  -500, "documento_pessoal",      "Cópia simples."),
            ("João Carlos Silva",       "Comprovante de Residência",   -30, "comprovante_residencia", "Conta de luz."),
            ("Maria Fernanda Oliveira", "CNH",                        -600, "documento_pessoal",      ""),
            ("Transportes Rápido Ltda", "Contrato Social",            -800, "contrato",               "Última alteração registrada."),
            ("Transportes Rápido Ltda", "Procuração — Setor Financeiro", -90, "procuracao",           "Autoriza retirada de documentos."),
            ("Pedro Henrique Souza",    "Certidão de Óbito do Pai",  -120, "outro",                   "Necessário para transferência."),
            ("Juliana Aparecida Lima",  "Recibo de Venda do Veículo",  -25, "outro",                  "Aguardando comunicação Detran."),
        ]:
            db.session.add(Documento(
                cliente_id=clientes[cliente_nome], nome=nome_doc,
                data_documento=hoje_mais(dias_doc), categoria=categoria,
                observacao=obs, arquivo=None
            ))

        db.session.commit()
        print("✅  Banco populado com dados de simulação!")
        print(f"   {len(clientes_data)} clientes · {len(veiculos_data)} veículos · {16} IPVA · 11 licenciamentos · 6 multas · 7 documentos")


if __name__ == "__main__":
    seed()
