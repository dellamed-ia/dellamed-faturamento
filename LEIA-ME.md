# Dashboard Segmentos e Mix · Dellamed

Página com PIN que se atualiza sozinha todo dia às 8h30 com dados do Qlik Cloud.
Os dados ficam criptografados dentro do `index.html`: quem abrir o código-fonte
não vê números, clientes, segmentos nem produtos.

## O que tem aqui

| Arquivo | Para que serve |
|---|---|
| `index.html` | A página publicada (já gerada com a planilha Jan–Ago 2026, PIN 2809DL) |
| `template/dashboard.html` | Modelo do dashboard, sem dados |
| `scripts/extract_qlik.py` | Busca os dados no Qlik |
| `scripts/build.py` | Criptografa com o PIN e gera o `index.html` |
| `scripts/from_xlsx.py` | Plano B: gera os dados a partir da planilha |
| `config/qlik.json` | Nomes de campos e expressões do seu app no Qlik |
| `.github/workflows/atualizar-dashboard.yml` | Agenda diária das 8h30 |

## 1. Criar o repositório e publicar

1. No GitHub, crie um repositório novo (ex.: `relatorio-segmentos`).
2. Copie todo o conteúdo desta pasta para ele pelo GitHub Desktop, incluindo as pastas ocultas `.github` e o arquivo `.gitignore`. Faça commit e push.
3. Em **Settings → Pages**: Source = *Deploy from a branch*, branch `main`, pasta `/ (root)`. Salve.
4. Em alguns minutos o link fica `https://SEU-USUARIO.github.io/relatorio-segmentos/`.

Nesse ponto a página já funciona com os dados da planilha.

## 2. Cadastrar os segredos

Em **Settings → Secrets and variables → Actions → New repository secret**, crie:

| Nome | Valor |
|---|---|
| `DASHBOARD_PIN` | `2809DL` |
| `QLIK_TENANT` | `dellasense.us.qlikcloud.com` |
| `QLIK_APP_ID` | ID do app no Qlik |
| `QLIK_API_KEY` | chave de API do Qlik Cloud |

Os segredos nunca aparecem no código nem nos logs.

## 3. Ajustar `config/qlik.json`

Troque pelos nomes reais do app no Qlik:

- `campos`: nomes dos campos de linha, segmento e subgrupo.
- `medidas`: expressões de faturamento comercial, quantidade e clientes distintos. Mantenha `{SET}` dentro do `Sum(...)` e do `Count(...)`.
- `set_analysis`: período. O padrão pega o ano corrente pelo campo `Ano`.
- `campo_data`: campo de data, usado para escrever o período (ex.: "Jan–Set 2026 (até 28/09)"). Se preferir texto fixo, preencha `periodo_rotulo`.

## 4. Testar

Em **Actions → Atualizar dashboard → Run workflow**. Se ficar verde, a página foi atualizada.
Se ficar vermelho, a página anterior continua no ar e o GitHub avisa por e-mail. Abra o log:
ele mostra só a mensagem de erro e contagens, nunca valores.

## Trocar o PIN

Altere o segredo `DASHBOARD_PIN` e rode o workflow manualmente. O PIN não diferencia maiúsculas de minúsculas.

## Atualizar pela planilha (plano B)

```
pip install -r requirements.txt
python scripts/from_xlsx.py Dados_dellamed_mix_e_clientes.xlsx --periodo "Jan–Set 2026"
DASHBOARD_PIN=2809DL python scripts/build.py
```
(no Windows PowerShell: `$env:DASHBOARD_PIN="2809DL"; python scripts/build.py`)
Depois commit do `index.html`. A pasta `build/` e a planilha estão no `.gitignore` e não sobem.

## Observações

- O agendamento do GitHub usa fila compartilhada: a execução das 8h30 pode começar com 5 a 20 minutos de atraso.
- O link do GitHub Pages é público. A proteção está na criptografia, por isso o PIN nunca deve ser escrito no repositório.
