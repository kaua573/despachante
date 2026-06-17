# Sistema de Despachante

## Como usar

### Requisitos
- Python 3.8 ou superior instalado
- Bibliotecas: Flask, reportlab

Instalar dependências:
```
pip install flask reportlab
```

### Iniciar o sistema

**Windows:** Clique duas vezes em `iniciar.bat`

**Linux/Mac:**
```
python app.py
```

### Acessar
Após iniciar, abra o navegador em: **http://localhost:5000**

---

## Popular com dados de teste (opcional)

Para testar o sistema com dados fictícios variados (clientes, veículos em todas
as situações, IPVA/licenciamento pagos/pendentes/vencidos, multas e documentos):

```
python seed.py
```

⚠️ Atenção: isso **apaga todos os dados atuais** e substitui por dados de simulação.

---

## O que o sistema faz

### 🏠 Tela inicial (Dashboard)
- Totais de clientes, veículos ativos, IPVA/licenciamento vencidos e multas pendentes
- Lista de vencimentos de **IPVA** e **Licenciamento** dos próximos 30 dias, com indicação visual de quanto falta (ou há quanto tempo venceu)

### 👥 Clientes
Campos: nome, telefone, CPF e email (obrigatórios) e observação (opcional).
Cada cliente tem uma aba de **documentos anexados**, com nome, data, categoria,
observação e upload de arquivo (a data de cadastro é automática).

Botão **PDF** gera um relatório do cliente, com opção de escolher o que incluir:
dados do cliente, informações dos veículos, IPVA e/ou licenciamento.

### 🚗 Veículos (por cliente)
Campos: placa, RENAVAM, proprietário, marca/modelo, espécie (passeio, carga,
reboque) e situação (ativo, desativado, vendido) — todos obrigatórios, mais
observação (opcional).

O campo **proprietário** é o nome que consta no documento do veículo, podendo
ser diferente do cliente responsável pelo cadastro (ex: veículo no nome do
cônjuge, filho ou empresa, mas controlado por este cliente no sistema).

### 📋 Painel do veículo
Três abas: **IPVA**, **Licenciamento** e **Multas**, cada uma com filtro por
status (pago/pendente) e registro de valor, vencimento, data de pagamento e
observações.

## Banco de dados
O arquivo `despachante.db` é criado automaticamente na mesma pasta do sistema.
Os documentos enviados ficam em `static/uploads/documentos/`.
Faça backup desses dois (arquivo + pasta) regularmente!
