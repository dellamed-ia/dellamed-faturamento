"""Criptografa os dados com o PIN e injeta no template do dashboard.

Uso:
  DASHBOARD_PIN=xxxx python scripts/build.py --data build/data.json --out index.html

O PIN vem SEMPRE de variável de ambiente (GitHub Secret). Nunca grave o PIN nem
o data.json em texto aberto no repositório.
"""
import argparse, base64, gzip, json, os, sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERACOES = 600_000
ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="build/data.json")
    ap.add_argument("--template", default=str(ROOT / "template" / "dashboard.html"))
    ap.add_argument("--out", default=str(ROOT / "index.html"))
    a = ap.parse_args()

    pin = os.environ.get("DASHBOARD_PIN", "").strip().upper()
    if not pin:
        sys.exit("ERRO: defina a variável de ambiente DASHBOARD_PIN.")

    dados = json.loads(Path(a.data).read_text(encoding="utf-8"))
    if not dados.get("rows"):
        sys.exit("ERRO: data.json sem linhas. Página não atualizada.")

    bruto = gzip.compress(json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    salt, iv = os.urandom(16), os.urandom(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERACOES).derive(pin.encode("utf-8"))
    cifrado = AESGCM(chave).encrypt(iv, bruto, None)
    b64 = lambda x: base64.b64encode(x).decode()
    enc = json.dumps({"s": b64(salt), "v": b64(iv), "n": ITERACOES, "c": b64(cifrado)})

    html = Path(a.template).read_text(encoding="utf-8")
    if "__ENC__" not in html:
        sys.exit("ERRO: template sem o marcador __ENC__.")
    Path(a.out).write_text(html.replace("__ENC__", enc, 1), encoding="utf-8")
    print(f"OK: {a.out} gerado com {len(dados['rows'])} registros (dados criptografados).")


if __name__ == "__main__":
    main()
