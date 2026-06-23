# Sistema de Despachante

Sistema de gestão para despachante veicular. Controla clientes, veículos, IPVA, licenciamento, multas e documentos, com relatórios configuráveis exportáveis em PDF e Excel.

---

## Requisitos

- Python 3.8 ou superior
- pip
- Sistema operacional: Windows, Linux ou macOS

---

## Instalação

```bash
# 1. Clone o repositório
git clone <url-do-repositorio>
cd despachante

# 2. Crie e ative o ambiente virtual
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt
```

---

## Configuração

Copie o arquivo de exemplo e ajuste conforme necessário:

```bash
cp .env.example .env
```

Variáveis disponíveis em `.env.example`:

```
SECRET_KEY=        # Chave secreta do Flask. Troque em produção.
DATABASE_URL=      # Opcional. Padrão: SQLite local (despachante.db).
                   # Para PostgreSQL: postgresql://user:senha@host/banco
FLASK_ENV=         # development | production. Padrão: development.
```

Em desenvolvimento, nenhuma variável é obrigatória — o sistema sobe com os valores padrão.

---

## Banco de dados

```bash
# Cria as tabelas (primeira execução)
python run.py

# Se estiver usando Flask-Migrate para migrações incrementais:
flask db upgrade
```

O arquivo `despachante.db` é criado automaticamente na raiz do projeto.

**Nota sobre migrações:** qualquer alteração de schema deve ser aplicada via `flask db upgrade`, nunca manualmente em produção. A migration `migrations/add_tipo_pagamento_ipva.py` adiciona a coluna `tipo_pagamento` na tabela `ipva` — aplique-a se estiver atualizando um banco existente:

```bash
flask db upgrade
```

---

## Popular com dados de teste

```bash
python seed.py
```

⚠️ Apaga **todos** os dados existentes antes de inserir. Cobre todos os cenários do sistema:

- Clientes pessoa física e jurídica, inclusive um cliente sem veículos
- Veículos com placas Mercosul e padrão antigo, nas espécies passeio / carga / reboque
- IPVA: à vista pago, pendente e vencido; parcelado em 2×, 3×, 4× e 5× em diferentes estados
- Licenciamento: pago, pendente, vencido, próximo do vencimento
- Multas: 5 órgãos autuadores, pagas com e sem desconto, pendentes e vencidas
- Documentos em categorias variadas

---

## Executar

**Windows:**
```
iniciar.bat
```

**Linux / macOS:**
```bash
python run.py
```

Acesse em: **http://localhost:5000**

---

## Estrutura de pastas

```
despachante/
├── app/
│   ├── models/          # Modelos SQLAlchemy (uma classe por arquivo)
│   ├── routes/          # Blueprints Flask — só roteamento e validação de entrada
│   ├── services/        # Toda a lógica de negócio
│   ├── templates/       # Jinja2; herança a partir de base.html
│   └── static/
│       ├── icons/       # SVGs usados via helper Jinja icon()
│       └── uploads/
│           ├── documentos/  # Arquivos enviados pelos usuários
│           └── logo/        # Logo do escritório
├── backups/             # Backups automáticos do banco (.db com timestamp)
├── migrations/          # Scripts Alembic de migração de schema
├── config.py            # Configurações por ambiente (dev / prod)
├── run.py               # Ponto de entrada da aplicação
├── seed.py              # Popula o banco com dados de teste
├── requirements.txt
└── .env.example
```

---

## Módulos do sistema

### Dashboard
Totais de clientes, veículos ativos, IPVA/licenciamento vencidos e multas pendentes. Lista vencimentos dos próximos 30 dias com indicação visual de urgência.

### Clientes
Cadastro com CPF validado, telefone e e-mail. Cada cliente tem uma aba de documentos anexados (PDF, imagens, Word, Excel) com categoria e data. Geração de relatório PDF individual com seleção de seções.

### Veículos
Vinculados a um cliente. Suporta proprietário diferente do cliente (veículo no nome do cônjuge, empresa etc.). Situações: ativo, desativado, vendido. Espécies: passeio, carga, reboque.

### IPVA
Registro por ano de referência. Dois modos de pagamento:
- **À vista** — quitação única via botão no painel
- **Parcelado** — até 5 parcelas mensais, quitadas individualmente; a quitação total fica bloqueada enquanto o modo for parcelado

### Licenciamento
Registro por ano de referência com vencimento, valor e status de pagamento.

### Multas
Registro com auto de infração, órgão autuador, data, descrição, valor e vencimento.

### Relatórios
Relatórios configuráveis para IPVA, licenciamento e multas. Filtros por data, status, placa e cliente. Agrupamento por qualquer campo. Campos reordenáveis por drag-and-drop. Exportação em PDF e Excel. Templates de configuração salvos no banco.

### Configurações
- Senha de exclusão (padrão `0000` — troque imediatamente)
- Backup automático a cada X minutos com retenção de 5 dias
- Tema claro/escuro com 6 opções de cor
- Identidade do escritório (nome + logo — aparecem na navegação, favicon e PDFs)
- Personalização de PDFs (fonte, tamanho, cor, espaçamento)

---

## Backup

O sistema faz backup automático do `despachante.db` na pasta `backups/` no intervalo configurado (padrão: 30 minutos). Backups com mais de 5 dias são removidos automaticamente.

**Recomendação:** copie periodicamente a pasta inteira para um pendrive ou serviço de nuvem. O backup interno não substitui cópia externa.

---

## Comandos úteis

```bash
# Iniciar em modo desenvolvimento
python run.py

# Aplicar migrações pendentes
flask db upgrade

# Criar nova migration após alterar um model
flask db migrate -m "descricao da mudanca"

# Shell interativo com contexto da aplicação
flask shell

# Popular banco com dados de teste (apaga dados existentes)
python seed.py
```
