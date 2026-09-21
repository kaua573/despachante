"""
Serviço de geração do PDF de relatório individual do cliente.

Visual fixo (sem opções de cor/fonte/tamanho configuráveis) — mesma
linguagem visual do relatório geral: cabeçalho com identificação do
escritório, barras cinza de seção e tabelas com borda.
"""
from __future__ import annotations

import io
import os
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.veiculo import Veiculo
from app.services.configuracao_service import ConfiguracaoService
from app.services.validacao_service import formatar_cpf, formatar_cnpj


class PdfClienteService:
    def __init__(self, session: Session, logo_dir: str) -> None:
        self._session = session
        self._logo_dir = logo_dir
        self._cfg = ConfiguracaoService(session)

    def gerar(self, cliente_id: int, incluir: list[str]) -> tuple[Optional[bytes], str]:
        """
        Gera PDF do relatório do cliente.
        Retorna (bytes_pdf, nome_arquivo) ou (None, mensagem_erro).
        """
        cliente = self._session.get(Cliente, cliente_id)
        if not cliente:
            return None, "Cliente não encontrado."

        veics = (
            self._session.query(Veiculo)
            .filter_by(cliente_id=cliente_id)
            .order_by(Veiculo.placa)
            .all()
        )

        dados_veics = []
        for v in veics:
            dados_veics.append({
                "veiculo": v,
                "ipva_list": sorted(v.ipva_list, key=lambda x: x.ano_referencia, reverse=True),
                "lic_list": sorted(v.licenciamentos, key=lambda x: x.ano_referencia, reverse=True),
            })

        pdf_bytes = self._montar_pdf(cliente, dados_veics, incluir)
        nome_arquivo = f"relatorio_{cliente.nome.replace(' ', '_')}.pdf"
        return pdf_bytes, nome_arquivo

    def _montar_pdf(self, cliente: Cliente, dados_veics: list, incluir: list[str]) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, Image as RLImage,
        )

        nome_escrit  = self._cfg.get("escritorio_nome", "")
        logo_arquivo = self._cfg.get("escritorio_logo", "")

        FONTE_BASE = "Helvetica"
        FONTE_BOLD = "Helvetica-Bold"
        PAD = 6

        PRETO       = colors.HexColor("#16181C")
        CINZA_BARRA = colors.HexColor("#EDEAE1")
        CINZA_BORDA = colors.HexColor("#D8D4C8")
        CINZA_SUB   = colors.HexColor("#63697A")
        VERDE = colors.HexColor("#1F6F4A")
        VERM  = colors.HexColor("#A6291F")
        AMAR  = colors.HexColor("#8A5A0B")

        sEscrit  = ParagraphStyle("escrit", fontName=FONTE_BOLD, fontSize=13, textColor=PRETO, spaceAfter=1)
        sSecaoBarra = ParagraphStyle("secaobarra", fontName=FONTE_BOLD, fontSize=9, textColor=PRETO)
        sBarraData = ParagraphStyle("barradata", fontName=FONTE_BASE, fontSize=9.5, textColor=PRETO, alignment=2)
        sLabel  = ParagraphStyle("label",  fontName=FONTE_BOLD, fontSize=8.5, textColor=PRETO)
        sThead  = ParagraphStyle("thead",  fontName=FONTE_BOLD, fontSize=8,   textColor=PRETO)
        sValor  = ParagraphStyle("valor",  fontName=FONTE_BASE, fontSize=8.5, textColor=PRETO)
        sMini   = ParagraphStyle("mini",   fontName=FONTE_BASE, fontSize=8,   textColor=CINZA_SUB)
        sRodape = ParagraphStyle("rodape", fontName=FONTE_BASE, fontSize=7.5, textColor=CINZA_SUB)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        story = []

        def barra_secao(texto: str, texto_direita: str = "") -> Table:
            if texto_direita:
                t = Table(
                    [[Paragraph(texto.upper(), sSecaoBarra), Paragraph(texto_direita, sBarraData)]],
                    colWidths=["70%", "30%"],
                )
            else:
                t = Table([[Paragraph(texto.upper(), sSecaoBarra)]], colWidths=["100%"])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), CINZA_BARRA),
                ("BOX",        (0, 0), (-1, -1), 0.6, CINZA_BORDA),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING",    (0, 0), (-1, -1), 6),
            ]))
            return t

        # ── Cabeçalho: logo + nome do escritório ─────────────────────────
        logo_path = os.path.join(self._logo_dir, logo_arquivo) if logo_arquivo else ""
        if logo_path and os.path.exists(logo_path):
            try:
                img = RLImage(logo_path, width=3.4*cm, height=1.7*cm)
                img.hAlign = "LEFT"
                story.append(img)
                story.append(Spacer(1, 4))
            except Exception:
                pass
        if nome_escrit:
            story.append(Paragraph(nome_escrit, sEscrit))
        story.append(Spacer(1, 8))

        data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M")
        story.append(barra_secao("Relatório do Cliente", data_geracao))
        story.append(Spacer(1, 10))

        def fmt_data(d):
            if not d:
                return "—"
            try:
                y, m, dia = d.split("-")
                return f"{dia}/{m}/{y}"
            except Exception:
                return d

        def fmt_moeda(v):
            if v is None or v == "":
                return "—"
            return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        def status_badge(venc, pago):
            if pago:
                return ("PAGO", VERDE)
            if not venc:
                return ("PENDENTE", AMAR)
            return ("VENCIDO", VERM) if venc < date.today().isoformat() else ("PENDENTE", AMAR)

        SITUACAO_LABEL = {"ativo": "Ativo", "desativado": "Desativado", "vendido": "Vendido", "pendente": "Pendente"}
        ESPECIE_LABEL  = {"passeio": "Passeio", "carga": "Carga", "reboque": "Reboque"}

        def bloco_dados():
            bloco = []
            if "dados" in incluir:
                bloco.append(barra_secao("Dados do Cliente"))
                if cliente.tipo_pessoa == "PJ":
                    campos = [
                        ("Razão Social", cliente.nome),
                        ("CNPJ", formatar_cnpj(cliente.cnpj) if cliente.cnpj else "—"),
                    ]
                else:
                    campos = [
                        ("Nome", cliente.nome),
                        ("CPF", formatar_cpf(cliente.cpf) if cliente.cpf else "—"),
                    ]
                campos += [
                    ("Telefone", cliente.telefone or "—"),
                    ("E-mail", cliente.email or "—"),
                    ("Observação", cliente.observacao or "—"),
                ]
                tdata = [[Paragraph(l, sLabel), Paragraph(str(v), sValor)] for l, v in campos]
                t = Table(tdata, colWidths=["30%", "70%"])
                t.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.6, CINZA_BORDA),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, CINZA_BORDA),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), PAD),
                ]))
                bloco.append(t)
                bloco.append(Spacer(1, 10))
            return bloco

        def bloco_veiculos():
            bloco = []
            if not any(x in incluir for x in ("veiculos", "ipva", "licenciamento")):
                return bloco
            for item in dados_veics:
                v = item["veiculo"]
                especie_txt = ESPECIE_LABEL.get(v.especie or "", v.especie or "")
                situacao_txt = SITUACAO_LABEL.get(v.situacao or "", v.situacao or "")
                bloco.append(barra_secao(f"Veículo — {v.placa}", f"{especie_txt} · {situacao_txt}"))
                bloco.append(Spacer(1, 4))

                if "veiculos" in incluir:
                    tdata2 = [
                        [Paragraph("Marca/Modelo", sLabel), Paragraph(v.marca_modelo or "—", sValor)],
                        [Paragraph("Proprietário", sLabel),  Paragraph(v.proprietario or "—", sValor)],
                        [Paragraph("RENAVAM", sLabel),       Paragraph(v.renavam or "—", sValor)],
                        [Paragraph("Observação", sLabel),    Paragraph(v.observacao or "—", sValor)],
                    ]
                    t2 = Table(tdata2, colWidths=["30%", "70%"])
                    t2.setStyle(TableStyle([
                        ("BOX", (0, 0), (-1, -1), 0.6, CINZA_BORDA),
                        ("INNERGRID", (0, 0), (-1, -1), 0.4, CINZA_BORDA),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("PADDING", (0, 0), (-1, -1), PAD - 1),
                    ]))
                    bloco.append(t2)
                    bloco.append(Spacer(1, 6))

                def tabela_registros(titulo, registros, campos_cabecalho, extrair_linha):
                    bloco.append(Paragraph(titulo, ParagraphStyle("subtit", fontName=FONTE_BOLD, fontSize=9, textColor=PRETO, spaceBefore=4, spaceAfter=4)))
                    thead = [Paragraph(h, sThead) for h in campos_cabecalho]
                    trows = [thead] + [extrair_linha(r) for r in registros]
                    col_w = [f"{100 / len(campos_cabecalho):.1f}%"] * len(campos_cabecalho)
                    ti = Table(trows, colWidths=col_w)
                    ti.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), CINZA_BARRA),
                        ("BOX", (0, 0), (-1, -1), 0.6, CINZA_BORDA),
                        ("INNERGRID", (0, 0), (-1, -1), 0.4, CINZA_BORDA),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("PADDING", (0, 0), (-1, -1), PAD - 1),
                    ]))
                    bloco.append(ti)
                    bloco.append(Spacer(1, 8))

                if "ipva" in incluir and item["ipva_list"]:
                    def linha_ipva(r):
                        label, tc = status_badge(r.vencimento, r.pago)
                        return [
                            Paragraph(str(r.ano_referencia), sValor),
                            Paragraph(fmt_moeda(r.valor), sValor),
                            Paragraph(fmt_data(r.vencimento), sValor),
                            Paragraph(label, ParagraphStyle("s", fontName=FONTE_BOLD, fontSize=8, textColor=tc)),
                            Paragraph(fmt_data(r.data_pagamento), sValor),
                            Paragraph(r.observacao or "—", sMini),
                        ]
                    tabela_registros("IPVA", item["ipva_list"], ["Ano", "Valor", "Vencimento", "Status", "Dt. Pagamento", "Obs."], linha_ipva)

                if "licenciamento" in incluir and item["lic_list"]:
                    def linha_lic(r):
                        label, tc = status_badge(r.vencimento, r.pago)
                        return [
                            Paragraph(str(r.ano_referencia), sValor),
                            Paragraph(fmt_moeda(r.valor), sValor),
                            Paragraph(fmt_data(r.vencimento), sValor),
                            Paragraph(label, ParagraphStyle("s2", fontName=FONTE_BOLD, fontSize=8, textColor=tc)),
                            Paragraph(fmt_data(r.data_pagamento), sValor),
                            Paragraph(r.observacao or "—", sMini),
                        ]
                    tabela_registros("Licenciamento", item["lic_list"], ["Ano", "Valor", "Vencimento", "Status", "Dt. Pagamento", "Obs."], linha_lic)

                bloco.append(Spacer(1, 4))
            return bloco

        story.extend(bloco_dados())
        story.extend(bloco_veiculos())

        story.append(Spacer(1, 12))
        story.append(Paragraph(
            f"Relatório emitido pelo {nome_escrit or 'Sistema Despachante'} em {data_geracao}",
            sRodape,
        ))

        doc.build(story)
        buf.seek(0)
        return buf.read()
