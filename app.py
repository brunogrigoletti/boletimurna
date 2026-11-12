"""
Aplicação local: Urna -> QR Codes -> Totalizador.

Uso:
    .venv\\Scripts\\python app.py
    abrir http://127.0.0.1:5000
"""
import base64

from flask import Flask, jsonify, render_template, request

import bu

app = Flask(__name__)
totalizador = bu.Totalizador()


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _com_imagens(pacote: dict) -> dict:
    """Acrescenta as imagens dos QR Codes (BU e certificado)."""
    return {
        **pacote,
        "qr_bu": _data_url(bu.gerar_qr_png(pacote["texto_bu"], 4)),
        "qr_cert": [_data_url(bu.gerar_qr_png(t, 3)) for t in pacote["textos_cert"]],
    }


@app.errorhandler(ValueError)
def _erro(e):
    return jsonify({"erro": str(e)}), 400


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def config():
    return jsonify({"secao": bu.SECAO, "candidatos": bu.CANDIDATOS,
                    "resultado": bu.RESULTADO})


@app.post("/api/emitir")
def emitir():
    """A urna emite sempre o BU com o resultado real da seção."""
    return jsonify(_com_imagens(bu.emitir_bu()))


@app.post("/api/adulterar")
def adulterar():
    d = request.get_json()
    pacote = bu.adulterar(
        texto_bu_original=d["texto_bu"],
        textos_cert_original=d["textos_cert"],
        conteudo_adulterado=d["conteudo"],
        modo_hash=d.get("hash", "recalcular"),
        modo_assinatura=d.get("assinatura", "manter"),
    )
    return jsonify(_com_imagens(pacote))


@app.post("/api/verificar")
def verificar():
    imagens = []
    for url in request.get_json().get("imagens", []):
        imagens.append(base64.b64decode(url.split(",", 1)[1] if "," in url else url))
    return jsonify(bu.verificar(imagens=imagens))


@app.post("/api/totalizar")
def totalizar():
    return jsonify(totalizador.receber(request.get_json()["textos"]))


@app.get("/api/totalizacao")
def estado():
    return jsonify(totalizador.estado())


@app.post("/api/reiniciar")
def reiniciar():
    totalizador.reiniciar()
    return jsonify(totalizador.estado())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
