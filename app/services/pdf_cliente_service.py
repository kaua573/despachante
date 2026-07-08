"""
Serviço de geração do PDF de relatório individual do cliente.
Extraído do app.py original para separar responsabilidade.
"""
from __future__ import annotations

import io
import os
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.veiculo import Veiculo
from app.services.configuracao_service import (
    ConfiguracaoService, FONTES_PDF, TAMANHOS_PDF, resolver_cor
)


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
            TableStyle, HRFlowable,
        )
        from reportlab.platypus import Image as RLImage

        # Carrega configurações de apresentação
        cfg_fonte = FONTES_PDF.get(self._cfg.get("pdf_fonte", "moderna"), FONTES_PDF["moderna"])
        cfg_tam   = TAMANHOS_PDF.get(self._cfg.get("pdf_tamanho", "medio"), TAMANHOS_PDF["medio"])
        cfg_cor   = resolver_cor(self._cfg.get("pdf_cor", "azul"))
        mostrar_data  = self._cfg.get("pdf_mostrar_data_geracao", "1") == "1"
        espacamento   = self._cfg.get("pdf_espacamento", "espacada")
        ordem_blocos  = self._cfg.get("pdf_ordem_blocos", "dados_primeiro")
        nome_escrit   = self._cfg.get("pdf_nome_escritorio", "") or self._cfg.get("escritorio_nome", "")
        logo_arquivo  = self._cfg.get("escritorio_logo", "")
        cor_texto_cfg = self._cfg.get("pdf_cor_texto", "escuro")

        FONTE_BASE = cfg_fonte["base"]
        FONTE_BOLD = cfg_fonte["bold"]
        PAD = 5 if espacamento == "compacta" else 8

        COR_PRINCIPAL = colors.HexColor(cfg_cor["principal"])
        COR_SECUND    = colors.HexColor(cfg_cor["secundaria"])
        CINZA1 = colors.HexColor("#f4f6fa")
        CINZA2 = colors.HexColor("#e8ecf2")
        VERDE  = colors.HexColor("#065f46")
        VERM   = colors.HexColor("#991b1b")
        AMAR   = colors.HexColor("#92400e")
        BRANCO = colors.white
        # Texto do cabeçalho das tabelas (fundo = COR_PRINCIPAL): branco ou escuro,
        # o que garantir leitura, já que a cor principal pode ser clara ou escura.
        TEXTO_HEADER = colors.HexColor(cfg_cor["contraste"])

        _mapa_texto = {"escuro": "#1c2333", "cinza": "#4a5568", "claro": "#ffffff"}
        TEXTO = colors.HexColor(_mapa_texto.get(cor_texto_cfg, "#1c2333"))

        sTitulo = ParagraphStyle("titulo", fontName=FONTE_BOLD, fontSize=cfg_tam["titulo"], textColor=COR_PRINCIPAL, spaceAfter=4)
        sSub    = ParagraphStyle("sub",    fontName=FONTE_BASE, fontSize=cfg_tam["mini"] + 2, textColor=colors.HexColor("#5a6680"), spaceAfter=12)
        sSecao  = ParagraphStyle("secao",  fontName=FONTE_BOLD, fontSize=cfg_tam["secao"],   textColor=COR_SECUND, spaceBefore=14, spaceAfter=6)
        sLabel  = ParagraphStyle("label",  fontName=FONTE_BOLD, fontSize=cfg_tam["mini"] + 1, textColor=colors.HexColor("#5a6680"))
        sThead  = ParagraphStyle("thead",  fontName=FONTE_BOLD, fontSize=cfg_tam["mini"] + 1, textColor=TEXTO_HEADER)
        sValor  = ParagraphStyle("valor",  fontName=FONTE_BASE, fontSize=cfg_tam["texto"],   textColor=TEXTO)
        sPlaca  = ParagraphStyle("placa",  fontName=FONTE_BOLD, fontSize=cfg_tam["secao"] + 1, textColor=COR_PRINCIPAL)
        sMini   = ParagraphStyle("mini",   fontName=FONTE_BASE, fontSize=cfg_tam["mini"],    textColor=colors.HexColor("#5a6680"))
        sEscrit = ParagraphStyle("escrit", fontName=FONTE_BOLD, fontSize=cfg_tam["mini"] + 3, textColor=COR_SECUND, spaceAfter=2)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        story = []

        # Logo
        logo_path = os.path.join(self._logo_dir, logo_arquivo) if logo_arquivo else ""
        if logo_path and os.path.exists(logo_path):
            try:
                img = RLImage(logo_path, width=4*cm, height=2*cm)
                img.hAlign = "LEFT"
                story.append(img)
                story.append(Spacer(1, 4))
            except Exception:
                pass

        if nome_escrit:
            story.append(Paragraph(nome_escrit, sEscrit))
        story.append(Paragraph("Relatório do Cliente", sTitulo))
        if mostrar_data:
            story.append(Paragraph(f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}", sSub))
        story.append(HRFlowable(width="100%", thickness=2, color=COR_PRINCIPAL, spaceAfter=14))

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

        SITUACAO_LABEL = {"ativo": "Ativo", "desativado": "Desativado", "vendido": "Vendido"}
        ESPECIE_LABEL  = {"passeio": "Passeio", "carga": "Carga", "reboque": "Reboque"}

        def bloco_dados():
            bloco = []
            if "dados" in incluir:
                bloco.append(Paragraph("Dados do Cliente", sSecao))
                campos = [
                    ("Nome", cliente.nome),
                    ("CPF", cliente.cpf or "—"),
                    ("Telefone", cliente.telefone or "—"),
                    ("E-mail", cliente.email or "—"),
                    ("Observação", cliente.observacao or "—"),
                ]
                tdata = [[Paragraph(l, sLabel), Paragraph(str(v), sValor)] for l, v in campos]
                t = Table(tdata, colWidths=["30%", "70%"])
                t.setStyle(TableStyle([
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [CINZA1, CINZA2]),
                    ("BOX", (0, 0), (-1, -1), 0.5, CINZA2),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, CINZA2),
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
                bloco.append(Spacer(1, 8))
                bloco.append(HRFlowable(width="100%", thickness=1, color=CINZA2, spaceAfter=8))
                especie_txt = ESPECIE_LABEL.get(v.especie or "", v.especie or "")
                situacao_txt = SITUACAO_LABEL.get(v.situacao or "", v.situacao or "")
                bloco.append(Paragraph(f"Placa: {v.placa}  —  {especie_txt}  —  {situacao_txt}", sPlaca))

                if "veiculos" in incluir:
                    tdata2 = [
                        [Paragraph("Marca/Modelo", sLabel), Paragraph(v.marca_modelo or "—", sValor)],
                        [Paragraph("Proprietário", sLabel),  Paragraph(v.proprietario or "—", sValor)],
                        [Paragraph("RENAVAM", sLabel),       Paragraph(v.renavam or "—", sValor)],
                        [Paragraph("Observação", sLabel),    Paragraph(v.observacao or "—", sValor)],
                    ]
                    t2 = Table(tdata2, colWidths=["30%", "70%"])
                    t2.setStyle(TableStyle([
                        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [CINZA1, CINZA2]),
                        ("BOX", (0, 0), (-1, -1), 0.5, CINZA2),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, CINZA2),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("PADDING", (0, 0), (-1, -1), PAD - 1),
                    ]))
                    bloco.append(Spacer(1, 4))
                    bloco.append(t2)

                def tabela_registros(titulo, registros, campos_cabecalho, extrair_linha):
                    bloco.append(Spacer(1, 8))
                    bloco.append(Paragraph(titulo, sSecao))
                    thead = [Paragraph(h, sThead) for h in campos_cabecalho]
                    trows = [thead] + [extrair_linha(r) for r in registros]
                    col_w = [f"{100 / len(campos_cabecalho):.1f}%"] * len(campos_cabecalho)
                    ti = Table(trows, colWidths=col_w)
                    ti.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), COR_PRINCIPAL),
                        ("TEXTCOLOR", (0, 0), (-1, 0), TEXTO_HEADER),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CINZA1]),
                        ("BOX", (0, 0), (-1, -1), 0.5, CINZA2),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, CINZA2),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("PADDING", (0, 0), (-1, -1), PAD - 1),
                    ]))
                    bloco.append(ti)

                if "ipva" in incluir and item["ipva_list"]:
                    def linha_ipva(r):
                        label, tc = status_badge(r.vencimento, r.pago)
                        return [
                            Paragraph(str(r.ano_referencia), sValor),
                            Paragraph(fmt_moeda(r.valor), sValor),
                            Paragraph(fmt_data(r.vencimento), sValor),
                            Paragraph(label, ParagraphStyle("s", fontName=FONTE_BOLD, fontSize=cfg_tam["mini"], textColor=tc)),
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
                            Paragraph(label, ParagraphStyle("s2", fontName=FONTE_BOLD, fontSize=cfg_tam["mini"], textColor=tc)),
                            Paragraph(fmt_data(r.data_pagamento), sValor),
                            Paragraph(r.observacao or "—", sMini),
                        ]
                    tabela_registros("Licenciamento", item["lic_list"], ["Ano", "Valor", "Vencimento", "Status", "Dt. Pagamento", "Obs."], linha_lic)

            return bloco

        if ordem_blocos == "veiculos_primeiro":
            story.extend(bloco_veiculos())
            story.extend(bloco_dados())
        else:
            story.extend(bloco_dados())
            story.extend(bloco_veiculos())

        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=1, color=CINZA2))
        story.append(Paragraph(nome_escrit or "Sistema de Despachante", sMini))

        doc.build(story)
        buf.seek(0)
        return buf.read()
