# Sistema de Despachante

Sistema de gestão para despachante veicular. Controla clientes, veículos, IPVA, licenciamento, multas e documentos, com login por usuário, permissões, relatórios configuráveis exportáveis em PDF/Excel e backup automático do banco.

Aplicação web Flask. Em desenvolvimento roda localmente com SQLite; em produção roda no Google Cloud Run com banco PostgreSQL (veja a seção Deploy).

---

## Requisitos (desenvolvimento)

- Python 3.8 ou superior
- pip
- Windows, Linux ou macOS

---

## Instalação (desenvolvimento)

```bash
# 1. Clone o repositório
git clone https://github.com/kaua573/despachante.git
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

O arquivo `despachante.db` é criado automaticamente na raiz do projeto em desenvolvimento. Em produção o banco é o PostgreSQL definido em `DATABASE_URL`.

**Nota sobre migrações:** qualquer alteração de schema deve ser aplicada via `flask db upgrade`, nunca manualmente em produção.

---

## Popular com dados de teste

```bash
python seed.py
```

⚠️ Apaga **todos** os dados existentes antes de inserir. Cobre todos os cenários do sistema: clientes PF/PJ, veículos com placas Mercosul e padrão antigo, IPVA à vista/parcelado em vários estados, licenciamento e multas em diferentes situações, e documentos em categorias variadas.

---

## Executar (desenvolvimento)

**Windows:**
```
iniciar.bat
```

**Linux / macOS:**
```bash
python run.py
```

Acesse em: **http://localhost:5000**
Login inicial **apenas em desenvolvimento local**: `admin` / `admin123` — o sistema força a troca no primeiro acesso.
Em produção, cada escritório criado em `/super-admin` recebe uma senha inicial aleatória, mostrada uma única vez na tela de criação.

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
├── backups/              # Backups automáticos do banco (.db com timestamp)
├── migrations/            # Scripts Alembic de migração de schema
├── config.py              # Configurações por ambiente (dev / prod)
├── run.py                 # Ponto de entrada em desenvolvimento (servidor Flask debug)
├── wsgi.py                # Ponto de entrada em produção (Waitress / Cloud Run)
├── Dockerfile             # Imagem usada no deploy do Cloud Run
├── infra/                 # Scripts de limpeza de custos do Google Cloud
├── seed.py                 # Popula o banco com dados de teste
├── requirements.txt        # Dependências para rodar o sistema
└── .env.example
```

---

## Módulos do sistema

### Login e permissões
Autenticação por usuário e senha, com bloqueio automático após 5 tentativas incorretas (15 min), senha temporária expirável definida por um administrador, e perfis **administrador** / **operador** com permissões granulares por módulo.

### Dashboard
Totais de clientes, veículos ativos, IPVA/licenciamento vencidos e multas pendentes. Lista vencimentos dos próximos 30 dias com indicação visual de urgência. Painel com filtros e ordenação.

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
- Tema claro/escuro com espectro de cores personalizável
- Identidade do escritório (nome + logo — aparecem na navegação, favicon e PDFs)
- Personalização de PDFs (fonte, tamanho, cor, espaçamento)

### Administração (área admin)
Criação e gestão de usuários, perfis e permissões; log de ações do sistema.

---

## Backup

O sistema faz backup automático do banco SQLite na pasta `backups/` (em desenvolvimento), no intervalo configurado (padrão: 30 minutos). Backups com mais de 5 dias são removidos automaticamente.

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

---
