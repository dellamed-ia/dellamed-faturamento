"""Extrai os dados do app no Qlik Cloud e grava build/data.json.

Conecta no motor do Qlik (Engine API / QIX) por WebSocket com uma chave de API.
Tudo o que depende do seu app (nomes de campos, expressões, período) fica em
config/qlik.json, então não é preciso mexer neste código.

Variáveis de ambiente (GitHub Secrets):
  QLIK_TENANT   ex.: dellasense.us.qlikcloud.com
  QLIK_APP_ID   ID do app
  QLIK_API_KEY  chave de API do Qlik Cloud
"""
import argparse, itertools, json, math, os, sys
from datetime import datetime, timezone
from pathlib import Path
import websocket  # pacote websocket-client

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
ORDEM = ["linha", "segmento", "subgrupo"]


class Qix:
    def __init__(self, tenant, app_id, api_key):
        self.ws = websocket.create_connection(
            f"wss://{tenant}/app/{app_id}",
            header=[f"Authorization: Bearer {api_key}"],
            timeout=180,
        )
        self.seq = 0

    def call(self, handle, method, params):
        self.seq += 1
        self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self.seq, "handle": handle, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") != self.seq:
                continue  # notificações do motor (OnConnected etc.)
            if "error" in msg:
                e = msg["error"]
                raise RuntimeError(f"Qlik {method}: {e.get('message')} {e.get('parameter', '')}")
            return msg["result"]

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def numero(v):
    if v in (None, "NaN"):
        return 0
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    return 0 if math.isnan(v) else v


def cube(q, doc, dims, measures):
    """Cria um hipercubo de sessão e devolve todas as linhas (paginado)."""
    props = {
        "qInfo": {"qType": "dellamed-extract"},
        "qHyperCubeDef": {
            "qDimensions": [{"qDef": {"qFieldDefs": [d]}, "qNullSuppression": True} for d in dims],
            "qMeasures": [{"qDef": {"qDef": m}} for m in measures],
            "qSuppressZero": False,
            "qSuppressMissing": True,
            "qInitialDataFetch": [],
        },
    }
    h = q.call(doc, "CreateSessionObject", [props])["qReturn"]["qHandle"]
    layout = q.call(h, "GetLayout", [])["qLayout"]
    total, width = layout["qHyperCube"]["qSize"]["qcy"], len(dims) + len(measures)
    step = max(1, 10000 // width)
    out = []
    for top in range(0, total, step):
        pg = q.call(h, "GetHyperCubeData", ["/qHyperCubeDef", [{"qTop": top, "qLeft": 0, "qWidth": width, "qHeight": min(step, total - top)}]])
        for row in pg["qDataPages"][0]["qMatrix"]:
            out.append([c.get("qText", "") for c in row[: len(dims)]] + [numero(c.get("qNum")) for c in row[len(dims):]])
    q.call(doc, "DestroySessionObject", [layout["qInfo"]["qId"]])
    return out


def evaluate(q, doc, expr):
    return q.call(doc, "Evaluate", [expr])["qReturn"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/qlik.json")
    ap.add_argument("--out", default="build/data.json")
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))

    env = {k: os.environ.get(k, "").strip() for k in ("QLIK_TENANT", "QLIK_APP_ID", "QLIK_API_KEY")}
    falta = [k for k, v in env.items() if not v]
    if falta:
        sys.exit("ERRO: faltam variáveis de ambiente: " + ", ".join(falta))

    SET = cfg.get("set_analysis", "")
    med = {k: v.replace("{SET}", SET) for k, v in cfg["medidas"].items()}
    campos = cfg["campos"]

    q = Qix(env["QLIK_TENANT"], env["QLIK_APP_ID"], env["QLIK_API_KEY"])
    try:
        doc = q.call(-1, "OpenDoc", [env["QLIK_APP_ID"]])["qReturn"]["qHandle"]

        # 1) Tabela fato: linha × segmento × subgrupo
        rows, cli = [], {}
        for l, s, p, qt, fat, c in cube(q, doc, [campos[k] for k in ORDEM], [med["quantidade"], med["faturamento"], med["clientes"]]):
            if not (l and s and p) or (qt == 0 and fat == 0):
                continue
            rows.append([l, s, p, round(qt), round(fat, 2)])
            cli[f"{l}|{s}|{p}"] = int(c)

        # 2) Clientes distintos em cada combinação de filtros
        #    (contagem distinta não pode ser somada, então o Qlik calcula cada nível)
        cli["||"] = int(numero(evaluate(q, doc, med["clientes"])))
        for n in (1, 2):
            for combo in itertools.combinations(ORDEM, n):
                for row in cube(q, doc, [campos[k] for k in combo], [med["clientes"]]):
                    key = dict.fromkeys(ORDEM, "")
                    key.update(zip(combo, row[:n]))
                    cli[f"{key['linha']}|{key['segmento']}|{key['subgrupo']}"] = int(row[n])

        # 3) Rótulo do período
        periodo = cfg.get("periodo_rotulo", "")
        if not periodo and cfg.get("campo_data"):
            fd = cfg["campo_data"]
            ini = evaluate(q, doc, f"Date(Min({SET} [{fd}]),'YYYY-MM-DD')")
            fim = evaluate(q, doc, f"Date(Max({SET} [{fd}]),'YYYY-MM-DD')")
            try:
                di, df = datetime.strptime(ini, "%Y-%m-%d"), datetime.strptime(fim, "%Y-%m-%d")
                if di.year == df.year:
                    periodo = f"{MESES[di.month-1]}–{MESES[df.month-1]} {df.year}"
                else:
                    periodo = f"{MESES[di.month-1]}/{di.year}–{MESES[df.month-1]}/{df.year}"
                periodo += f" (até {df.strftime('%d/%m')})"
            except ValueError:
                periodo = f"{ini} a {fim}"
    finally:
        q.close()

    if not rows:
        sys.exit("ERRO: o Qlik não retornou linhas. Verifique config/qlik.json. Página não atualizada.")

    dados = {
        "meta": {"periodo": periodo, "atualizado": datetime.now(timezone.utc).isoformat(), "fonte": "Qlik Cloud", "cliAprox": False},
        "rows": rows,
        "cli": cli,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    # Só contagens no log: nenhum valor de negócio aparece nos registros do GitHub
    print(f"OK: {len(rows)} registros e {len(cli)} contagens de clientes extraídos.")


if __name__ == "__main__":
    main()
