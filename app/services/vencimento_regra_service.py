"""
Serviço das regras de vencimento por final de placa + espécie (item 3, set/2026).

Fluxo:
  1) CRUD das regras (`RegraVencimento`): para cada combinação de final de
     placa (0-9) e espécie, define em que mês/dia o licenciamento costuma
     vencer.
  2) `previsao()`: cruza as regras com os veículos reais e calcula, pra cada
     um, a data de vencimento prevista no ano escolhido — e sinaliza se o
     licenciamento daquele ano já foi lançado ou não.
  3) `lancar_lote()`: recebe a lista de veículos escolhidos manualmente (com
     supervisão do usuário) e cria o registro de Licenciamento de cada um
     com a data prevista (ou a data ajustada manualmente na tela).
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.licenciamento import Licenciamento
from app.models.regra_vencimento import RegraVencimento
from app.models.veiculo import Veiculo

FINAIS_VALIDOS = {str(n) for n in range(10)}
ESPECIES_VALIDAS = ("carga", "passeio", "reboque")


def final_da_placa(placa: str) -> Optional[str]:
    """Extrai o último dígito de uma placa (Mercosul ou antiga). Retorna None se não achar dígito."""
    for ch in reversed(placa or ""):
        if ch.isdigit():
            return ch
    return None


class VencimentoRegraService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ── CRUD das regras ──────────────────────────────────────────────────────

    def listar_regras(self) -> list[RegraVencimento]:
        return (
            self._session.query(RegraVencimento)
            .order_by(RegraVencimento.final_placa, RegraVencimento.especie)
            .all()
        )

    def salvar_regra(self, dados: dict) -> tuple[Optional[RegraVencimento], str]:
        final_placa = str(dados.get("final_placa", "")).strip()
        especie = (dados.get("especie") or "").strip()
        mes = dados.get("mes_vencimento")
        dia = dados.get("dia_vencimento") or None

        if final_placa not in FINAIS_VALIDOS:
            return None, "Final de placa inválido (use 0 a 9)."
        if especie not in ESPECIES_VALIDAS:
            return None, "Espécie inválida."
        try:
            mes = int(mes)
            if not (1 <= mes <= 12):
                raise ValueError
        except (TypeError, ValueError):
            return None, "Mês de vencimento inválido."
        if dia is not None:
            try:
                dia = int(dia)
                if not (1 <= dia <= 31):
                    raise ValueError
            except (TypeError, ValueError):
                return None, "Dia de vencimento inválido."

        regra_id = dados.get("id")
        if regra_id:
            regra = self._session.get(RegraVencimento, regra_id)
            if not regra:
                return None, "Regra não encontrada."
        else:
            regra = (
                self._session.query(RegraVencimento)
                .filter_by(final_placa=final_placa, especie=especie)
                .first()
            )
            if not regra:
                regra = RegraVencimento(final_placa=final_placa, especie=especie)
                self._session.add(regra)

        regra.final_placa = final_placa
        regra.especie = especie
        regra.mes_vencimento = mes
        regra.dia_vencimento = dia
        regra.ativo = bool(dados.get("ativo", True))
        self._session.commit()
        return regra, ""

    def excluir_regra(self, regra_id: int) -> tuple[bool, str]:
        regra = self._session.get(RegraVencimento, regra_id)
        if not regra:
            return False, "Regra não encontrada."
        self._session.delete(regra)
        self._session.commit()
        return True, ""

    def salvar_regras_lote(
        self, finais: list[str], especies: list[str],
        mes_vencimento, dia_vencimento, ativo: bool = True,
    ) -> tuple[list[RegraVencimento], list[str]]:
        """
        Cria/atualiza uma regra para CADA combinação de final de placa x
        espécie selecionada (ex.: finais=['0','1'], especies=['carga','passeio']
        gera 4 regras). Cada combinação é salva de forma independente — se uma
        falhar (ex.: dado inválido), as outras continuam sendo salvas.
        """
        salvas: list[RegraVencimento] = []
        erros: list[str] = []
        for final in finais:
            for especie in especies:
                regra, erro = self.salvar_regra({
                    "final_placa": final,
                    "especie": especie,
                    "mes_vencimento": mes_vencimento,
                    "dia_vencimento": dia_vencimento,
                    "ativo": ativo,
                })
                if regra:
                    salvas.append(regra)
                else:
                    erros.append(f"Final {final} / {especie}: {erro}")
        return salvas, erros

    # ── Cálculo de data prevista ─────────────────────────────────────────────

    def _data_prevista(self, regra: RegraVencimento, ano: int) -> str:
        dia = regra.dia_vencimento or calendar.monthrange(ano, regra.mes_vencimento)[1]
        dia = min(dia, calendar.monthrange(ano, regra.mes_vencimento)[1])
        return date(ano, regra.mes_vencimento, dia).isoformat()

    # ── Previsão cruzando regras x veículos reais ────────────────────────────

    def previsao(
        self,
        ano: Optional[int] = None,
        cliente_id: Optional[int] = None,
        especie: Optional[str] = None,
        final_placa: Optional[str] = None,
        apenas_sem_licenciamento: bool = False,
    ) -> list[dict]:
        ano = ano or date.today().year
        regras = {(r.final_placa, r.especie): r for r in self.listar_regras() if r.ativo}

        q = (
            self._session.query(Veiculo, Cliente)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS))
        )
        if cliente_id:
            q = q.filter(Veiculo.cliente_id == cliente_id)
        if especie:
            q = q.filter(Veiculo.especie == especie)

        licenciados = {
            vid for (vid,) in
            self._session.query(Licenciamento.veiculo_id).filter(Licenciamento.ano_referencia == ano)
        }

        resultado = []
        for v, c in q.order_by(Cliente.nome, Veiculo.placa).all():
            final = final_da_placa(v.placa)
            if final_placa and final != final_placa:
                continue
            regra = regras.get((final, v.especie)) if final else None
            ja_lancado = v.id in licenciados
            if apenas_sem_licenciamento and ja_lancado:
                continue
            resultado.append({
                "veiculo_id": v.id,
                "placa": v.placa,
                "final_placa": final,
                "especie": v.especie,
                "cliente_id": c.id,
                "cliente_nome": c.nome,
                "tem_regra": regra is not None,
                "vencimento_previsto": self._data_prevista(regra, ano) if regra else None,
                "ja_lancado_no_ano": ja_lancado,
            })
        return resultado

    # ── Lançamento em lote (com supervisão manual) ───────────────────────────

    def lancar_lote(self, itens: list[dict], ano: int) -> dict:
        """
        `itens`: lista de {"veiculo_id": int, "vencimento": "YYYY-MM-DD", "valor": opcional}.
        A data já vem definida pela tela (pré-preenchida pela regra, mas editável
        pelo usuário antes de confirmar) — aqui só valida e grava.
        Pula veículos que já têm licenciamento lançado para o ano, sem travar o resto do lote.
        """
        criados, pulados, erros = [], [], []
        for item in itens:
            vid = item.get("veiculo_id")
            venc = (item.get("vencimento") or "").strip()
            veiculo = self._session.get(Veiculo, vid) if vid else None
            if not veiculo:
                erros.append({"veiculo_id": vid, "erro": "Veículo não encontrado."})
                continue
            ja_existe = (
                self._session.query(Licenciamento.id)
                .filter_by(veiculo_id=vid, ano_referencia=ano)
                .first()
            )
            if ja_existe:
                pulados.append({"veiculo_id": vid, "placa": veiculo.placa, "motivo": "Já possui licenciamento neste ano."})
                continue
            if not venc:
                erros.append({"veiculo_id": vid, "placa": veiculo.placa, "erro": "Data de vencimento não informada."})
                continue

            registro = Licenciamento(
                veiculo_id=vid,
                ano_referencia=ano,
                vencimento=venc,
                valor=item.get("valor") or None,
                pago=False,
                observacao=item.get("observacao", "Lançado em lote via regra de final de placa."),
            )
            self._session.add(registro)
            criados.append({"veiculo_id": vid, "placa": veiculo.placa, "vencimento": venc})

        self._session.commit()
        return {"criados": criados, "pulados": pulados, "erros": erros}
