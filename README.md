# Simulador IBS/CBS — Backend (API)

API FastAPI que atua como proxy entre o frontend Vue.js e a **Calculadora RTC oficial** da Receita Federal (`consumo.tributos.gov.br`), adicionando lógica de projeção de transição tributária 2026–2033 conforme a LC 214/2025.

## Pré-requisitos

- Python 3.11+
- Calculadora RTC disponível em `localhost:8080` **ou** conexão com a API oficial

## Instalação

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Execução

```bash
uvicorn main:app --reload --port 8000
```

Ou use o script pronto:

```bash
start.bat   # Windows
```

A API estará disponível em `http://localhost:8000`.
Documentação interativa (Swagger): `http://localhost:8000/docs`

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/health` | Status da API |
| `GET` | `/api/situacoes-tributarias` | Lista de CSTs CBS/IBS disponíveis |
| `GET` | `/api/classificacoes-tributarias/{cst_id}` | Classificações (cClassTrib) para um CST |
| `POST` | `/api/calcular` | Cálculo com projeção interna LC 214/2025 (instantâneo) |
| `POST` | `/api/calcular-rtc` | Cálculo via API RTC para cada ano 2026–2033 em paralelo (~5s) |
| `POST` | `/api/gerar-xml` | Geração de XML NF-e com grupos RTC |

## Métodos de cálculo

### Projeção interna (`POST /api/calcular`)
- Chama a API RTC **uma vez** para obter os valores de 2026
- Projeta os anos 2027–2033 usando os fatores de transição da LC 214/2025
- Resposta instantânea

### Calculadora RTC por ano (`POST /api/calcular-rtc`)
- Chama a API RTC **8 vezes em paralelo** (uma por ano, 2026–2033)
- Utiliza as alíquotas oficiais retornadas pela API para cada período
- Tributos legados (ICMS/PIS-COFINS/IPI) calculados pelos mesmos fatores de transição
- Tempo de resposta: ~3–5s

## Estrutura

```
backend/
├── main.py                        # FastAPI app + CORS
├── requirements.txt
├── start.bat
├── models/
│   └── schemas.py                 # Modelos Pydantic (entrada e saída)
├── routers/
│   └── calculadora.py             # Definição das rotas
└── services/
    ├── calculadora_service.py     # Proxy para a API RTC
    ├── transicao_service.py       # Fatores LC 214/2025 + cálculo de transição
    └── projecao_rtc_service.py    # Projeção com 8 chamadas paralelas por ano
```

## Dependências

| Pacote | Versão | Uso |
|--------|--------|-----|
| `fastapi` | 0.115.6 | Framework web |
| `uvicorn[standard]` | 0.34.0 | Servidor ASGI |
| `httpx` | 0.28.1 | Chamadas HTTP assíncronas à API RTC |
| `pydantic` | 2.10.4 | Validação de schemas |

## Variáveis de ambiente

Nenhuma variável obrigatória. A URL da calculadora RTC é configurada diretamente em `services/calculadora_service.py`:

```python
ONLINE_URL = "https://consumo.tributos.gov.br/api-rtc"
LOCAL_URL  = "http://localhost:8080"
```

A API tenta a URL online primeiro e faz fallback para local se indisponível.

## Créditos

| Papel | Responsável |
|-------|-------------|
| Concepção, análise, planejamento e requisitos | **Chrystiomar** |
| Codificação | [Claude Code](https://claude.ai/claude-code) (Anthropic) |
