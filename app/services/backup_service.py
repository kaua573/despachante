"""
Serviço de backup automático do banco de dados.
Cria cópias com timestamp e remove arquivos mais antigos que 5 dias.
"""
import glob
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path


class BackupService:
    # Evento compartilhado entre instâncias para reagendamento imediato
    evento_reagendamento = threading.Event()

    # Período de retenção de backups em segundos (5 dias)
    RETENCAO_SEGUNDOS = 5 * 24 * 60 * 60

    _lock = threading.Lock()

    def __init__(self, backup_dir: str) -> None:
        self._backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)

    def fazer_backup(self, db_path: str = None) -> str | None:
        """
        Copia o banco de dados para backup_dir com timestamp no nome.
        Remove backups com mais de 5 dias.
        Retorna o caminho do arquivo criado, ou None se o banco não existe.
        """
        if db_path is None:
            # Localiza o arquivo despachante.db a partir da raiz do projeto
            raiz = Path(__file__).parent.parent.parent
            db_path = str(raiz / "despachante.db")

        with self._lock:
            destino = None
            if os.path.exists(db_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                destino = os.path.join(self._backup_dir, f"backup_{timestamp}.db")
                shutil.copy2(db_path, destino)

            self._remover_antigos()
            return destino

    def listar(self) -> list[dict]:
        """Retorna lista de backups salvos, ordenados do mais recente ao mais antigo."""
        arquivos = sorted(
            glob.glob(os.path.join(self._backup_dir, "backup_*.db")),
            reverse=True,
        )
        resultado = []
        for caminho in arquivos:
            resultado.append({
                "nome": os.path.basename(caminho),
                "tamanho_kb": round(os.path.getsize(caminho) / 1024, 1),
                "criado_em": datetime.fromtimestamp(
                    os.path.getmtime(caminho)
                ).strftime("%d/%m/%Y %H:%M:%S"),
            })
        return resultado

    def _remover_antigos(self) -> None:
        limite = time.time() - self.RETENCAO_SEGUNDOS
        for caminho in glob.glob(os.path.join(self._backup_dir, "backup_*.db")):
            try:
                if os.path.getmtime(caminho) < limite:
                    os.remove(caminho)
            except OSError:
                pass

    @classmethod
    def reagendar(cls) -> None:
        """Acorda a thread de backup para reaplicar o novo intervalo imediatamente."""
        cls.evento_reagendamento.set()
