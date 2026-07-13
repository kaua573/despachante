# Sistema de Despachante

Sistema de gestão para despachante veicular. Controla clientes, veículos, IPVA, licenciamento, multas e documentos, com login por usuário, permissões, relatórios configuráveis exportáveis em PDF/Excel e backup automático do banco.

Roda localmente: sobe um servidor na própria máquina e é usado pelo navegador (não depende de internet nem de servidor externo).

---

## Requisitos (desenvolvimento)

- Python 3.8 ou superior
- pip
- Windows, Linux ou macOS

Para uso final em computadores comuns (sem instalar Python), veja [Gerar o instalador (.exe)](#gerar-o-instalador-exe).

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
FLASK_ENV=         # development | production | desktop. Padrão: development.
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

O arquivo `despachante.db` é criado automaticamente na raiz do projeto (em desenvolvimento) ou em `%APPDATA%\SistemaDespachante` (quando instalado via `.exe` — veja abaixo).

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
Login inicial: `admin` / `admin123` — o sistema força a troca de senha no primeiro acesso.

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
├── config.py              # Configurações por ambiente (dev / prod / desktop)
├── run.py                 # Ponto de entrada em desenvolvimento (servidor Flask debug)
├── launcher.py             # Ponto de entrada do .exe empacotado (Waitress, sem console)
├── despachante.spec        # Receita do PyInstaller para gerar o .exe
├── installer.iss           # Script do Inno Setup para gerar o instalador
├── seed.py                 # Popula o banco com dados de teste
├── requirements.txt        # Dependências para rodar o sistema
├── requirements-build.txt  # Dependência extra só para gerar o .exe (PyInstaller)
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

O sistema faz backup automático do banco na pasta `backups/` (em desenvolvimento) ou `%APPDATA%\SistemaDespachante\backups` (instalado via `.exe`), no intervalo configurado (padrão: 30 minutos). Backups com mais de 5 dias são removidos automaticamente.

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

## Gerar o instalador (.exe)

Para distribuir o sistema em computadores que não têm Python instalado, o projeto é empacotado em um instalador Windows comum (tela de boas-vindas, escolha de pasta, atalho na área de trabalho, botão "Concluir"). Quem instalar só clica duas vezes no `.exe` — nada de terminal, nada de CMD aberto durante o uso.

### Como funciona

- **`launcher.py`** substitui o `run.py` como ponto de entrada: sobe o sistema com **Waitress** (servidor de produção, sem o modo debug do Flask) e abre o navegador padrão automaticamente em `http://127.0.0.1:5000`.
- **`despachante.spec`** (PyInstaller) empacota o Python, as dependências, os templates e os arquivos estáticos num único programa, com `console=False` — ou seja, sem janela preta de terminal.
- **`config.py`** detecta quando está rodando a partir do `.exe` (`sys.frozen`) e passa a gravar banco de dados, uploads e backups em `%APPDATA%\SistemaDespachante`, que é sempre gravável, mesmo instalado em "Arquivos de Programas". Os dados sobrevivem a reinstalações e atualizações do programa.
- **`installer.iss`** (Inno Setup) empacota tudo isso num instalador `.exe` único, com as telas típicas de instalação (idioma, pasta de destino, atalho, execução ao final).

### Passo a passo (rodar no Windows, onde o executável vai ser usado)

```bash
# 1. Ambiente com as dependências completas (sistema + build)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-build.txt

# 2. Gera a pasta do programa (dist\SistemaDespachante\)
pyinstaller despachante.spec

# 3. (opcional, mas recomendado) Teste o .exe gerado antes de empacotar o instalador
dist\SistemaDespachante\SistemaDespachante.exe

# 4. Instale o Inno Setup (https://jrsoftware.org/isinfo.php) e compile o instalador
iscc installer.iss
```

O instalador final fica em `installer_output\SistemaDespachante_Setup.exe` — é esse arquivo que você distribui e executa nos computadores dos usuários.

> **Importante:** o PyInstaller empacota para o sistema operacional em que ele roda. Para gerar o `.exe`, o build precisa ser feito **no Windows** (não é possível gerar um `.exe` a partir do Linux/macOS).

### Onde ficam os dados depois de instalado

```
%APPDATA%\SistemaDespachante\
├── despachante.db
├── backups\
└── app\static\uploads\
    ├── documentos\
    └── logo\
```

Isso normalmente é `C:\Users\<usuário>\AppData\Roaming\SistemaDespachante`. Para trocar de computador ou restaurar um backup, basta copiar essa pasta inteira.

### Atualizando uma instalação existente

Basta rodar o novo `SistemaDespachante_Setup.exe` por cima — o Inno Setup substitui os arquivos do programa em `Arquivos de Programas`, mas nunca toca em `%APPDATA%\SistemaDespachante`, então os dados do usuário (clientes, veículos, backups) são preservados.
