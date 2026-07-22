"""
Migração: adiciona as colunas "valor_integral" e "desconto_percentual" na
tabela "ipva".

NÃO apaga nada — só cria duas colunas novas. Registros que já existem ficam
com esses dois campos em branco (é esperado: eles nunca tiveram esse dado
salvo). Novos cadastros e edições feitos depois de instalar a versão
corrigida do sistema passam a gravar certinho.

Pode rodar mais de uma vez sem problema (não dá erro se a coluna já existir).

USO:
    1) Feche o Sistema Despachante completamente antes de rodar isso
       (confira no Gerenciador de Tarefas se "SistemaDespachante.exe" não
       ficou aberto em segundo plano).
    2) Rode este script apontando para o despachante.db:

       python migrar_ipva_desconto.py "C:/caminho/para/despachante.db"

       Se rodar sem nenhum argumento, ele tenta achar o despachante.db
       sozinho nesta mesma pasta ou em uma subpasta "dados\" ao lado dela.

    3) Depois de rodar, recompile o sistema (pyinstaller + Inno Setup) com
       o código já corrigido e reinstale por cima — os dados continuam lá.
"""
import os
import sqlite3
import sys


def localizar_banco() -> str:
    if len(sys.argv) > 1:
        caminho = sys.argv[1]
        if not os.path.isfile(caminho):
            raise SystemExit(f"Arquivo não encontrado: {caminho}")
        return caminho

    pasta_script = os.path.dirname(os.path.abspath(__file__))
    candidatos = [
        os.path.join(pasta_script, "despachante.db"),
        os.path.join(pasta_script, "dados", "despachante.db"),
    ]
    for c in candidatos:
        if os.path.isfile(c):
            return c

    raise SystemExit(
        "Não encontrei o despachante.db automaticamente.\n"
        "Rode assim, passando o caminho completo do arquivo:\n"
        '    python migrar_ipva_desconto.py "C:\\caminho\\para\\despachante.db"'
    )


def coluna_existe(cursor: sqlite3.Cursor, tabela: str, coluna: str) -> bool:
    cursor.execute(f"PRAGMA table_info({tabela})")
    return any(linha[1] == coluna for linha in cursor.fetchall())


def main() -> None:
    caminho_db = localizar_banco()
    print(f"Banco de dados: {caminho_db}")

    # Cópia de segurança antes de mexer, só por precaução.
    caminho_backup = caminho_db + ".antes_migracao_desconto.bak"
    with open(caminho_db, "rb") as origem, open(caminho_backup, "wb") as destino:
        destino.write(origem.read())
    print(f"Cópia de segurança criada em: {caminho_backup}")

    conexao = sqlite3.connect(caminho_db)
    cursor = conexao.cursor()

    houve_alteracao = False

    if not coluna_existe(cursor, "ipva", "valor_integral"):
        cursor.execute("ALTER TABLE ipva ADD COLUMN valor_integral NUMERIC(10, 2)")
        print('Coluna "valor_integral" adicionada.')
        houve_alteracao = True
    else:
        print('Coluna "valor_integral" já existia — nada a fazer.')

    if not coluna_existe(cursor, "ipva", "desconto_percentual"):
        cursor.execute("ALTER TABLE ipva ADD COLUMN desconto_percentual NUMERIC(5, 2)")
        print('Coluna "desconto_percentual" adicionada.')
        houve_alteracao = True
    else:
        print('Coluna "desconto_percentual" já existia — nada a fazer.')

    conexao.commit()
    conexao.close()

    if houve_alteracao:
        print("\nMigração concluída com sucesso. Nenhum dado existente foi apagado.")
    else:
        print("\nNada a fazer — as colunas já existiam nesse banco.")


if __name__ == "__main__":
    main()
