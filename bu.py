"""
Simulação da leitura e verificação do QR Code do Boletim de Urna (BU),
baseada em: TSE. "QR Code no boletim de urna: manual para criação de
aplicativo de leitura". Brasília: TSE, 2026.

Segue o manual:
  - conteúdo em registros CHAVE:VALOR separados por espaço, só com caracteres
    do modo alfanumérico do QR Code, em três seções: cabeçalho (QRBU, VRQR),
    conteúdo do boletim e segurança (HASH, ASSI)            [manual, 1.4]
  - HASH = SHA-512 da seção de conteúdo, em hexadecimal      [manual, 1.4.3]
  - ASSI = assinatura ECDSA com curva P-521 (urnas 2013 e 2015), verificada
    sobre SHA-512(bytes do HASH), como no código Python do manual [1.6]
  - certificado da urna em QR Codes próprios (QRCE, IDUE, MDUE, CERT), em
    DER codificado em hexadecimal, dividido em dois QR Codes [manual, 1.6.2]

Simplificações e acréscimos desta simulação:
  - o BU cabe em um único QR Code (o manual prevê até vários, com hash
    cumulativo) e só tem o cargo de Presidente;
  - não há EdDSA Ed521 (urnas 2020+), que a biblioteca `cryptography` não tem;
  - o manual não descreve como confiar no certificado que vem no próprio BU.
    Esta simulação acrescenta a validação da CADEIA DE CONFIANÇA (o certificado
    deve ter sido emitido pela AC da Justiça Eleitoral, simulada aqui); sem
    ela, um atacante que troque o certificado por um seu seria aceito;
  - códigos de processo, pleito, eleição, urna, carga, local, horários e
    habilitações são ILUSTRATIVOS. Os votos são o resultado real da seção.
"""
from __future__ import annotations

import hashlib
import io
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import qrcode
import zxingcpp
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from PIL import Image, UnidentifiedImageError

VRQR = "6.0"                       # versão do formato descrita no manual
LIMITE_QR = 1100                   # caracteres por QR Code (manual, 1.4)
ALFANUMERICO = re.compile(r"^[0-9A-Z $%*+\-./:]*$")
ASSINATURA = ec.ECDSA(hashes.SHA512())   # ECDSA sobre SHA-512(HASH)

# ------------------------------------------------------------------ dados
SECAO = {
    "municipio": "Porto Alegre",
    "uf": "RS",
    "muni": 88013,            # código TSE do município
    "zona": 159,
    "secao": 31,
    "local": "PUCRS - Prédio 50",
    "loca": 1414,             # número do local (edital da 159ª ZE de 2020)
    "eleitores_aptos": 400,   # ilustrativo
}

URNA = {                       # ilustrativo
    "idue": "2017334",                    # número de série
    "mdue": "2015",                       # modelo (ECDSA P-521, certificado DER)
    "idca": "418273650192837465019283",   # código de identificação da carga
    "vers": "10.17.1.0",
}

# Candidatos à Presidência no 1º turno de 2026 (fonte: Wikipedia). No BU real
# os nomes não vão no QR Code: vêm de um arquivo de complemento (manual, 1.7).
CANDIDATOS = [
    {"numero": "13", "nome": "Lula", "partido": "PT"},
    {"numero": "14", "nome": "Renan Santos", "partido": "MISSÃO"},
    {"numero": "16", "nome": "Hertz Dias", "partido": "PSTU"},
    {"numero": "21", "nome": "Edmilson Costa", "partido": "PCB"},
    {"numero": "22", "nome": "Flávio Bolsonaro", "partido": "PL"},
    {"numero": "27", "nome": "Clariana Barão", "partido": "DC"},
    {"numero": "29", "nome": "Rui Costa Pimenta", "partido": "PCO"},
    {"numero": "30", "nome": "Romeu Zema", "partido": "NOVO"},
    {"numero": "35", "nome": "Wilson Grassi", "partido": "Democrata"},
    {"numero": "55", "nome": "Ronaldo Caiado", "partido": "PSD"},
    {"numero": "70", "nome": "Augusto Cury", "partido": "Avante"},
    {"numero": "80", "nome": "Samara Martins", "partido": "UP"},
]

# Resultado da Seção 31 no 1º turno de 2026 (Presidente). Ausentes = 0 votos.
RESULTADO = {
    "votos": {"13": 160, "22": 131, "70": 10, "14": 6, "55": 4, "30": 4, "21": 1, "80": 1},
    "brancos": 4,
    "nulos": 3,
}

HABILITACAO = {"HBBG": 15, "HBSB": 8}   # ilustrativo; HBBM = COMP - HBBG - HBSB

CAMPOS_OBRIGATORIOS = ["ORIG", "PLEI", "TURN", "FASE", "UNFE", "MUNI", "ZONA", "SECA",
                       "IDUE", "APTO", "COMP", "FALT", "IDEL", "CARG", "NOMI", "BRAN",
                       "NULO", "TOTC"]


# ------------------------------------------------------------------ texto do BU
def juntar(campos: list[tuple[str, str]]) -> str:
    return " ".join(f"{k}:{v}" for k, v in campos)


def separar(texto: str) -> list[tuple[str, str]]:
    """'K1:V1 K2:V2' -> [(K1, V1), (K2, V2)]. O valor pode conter ':' (ex.: HICA)."""
    campos = []
    for registro in texto.split():
        if ":" not in registro:
            raise ValueError(f"registro sem ':' -> {registro[:20]}")
        k, v = registro.split(":", 1)
        campos.append((k, v))
    return campos


def conteudo_da_secao() -> list[tuple[str, str]]:
    """Seção de conteúdo do BU da Seção 31 (manual, 1.4.2)."""
    r = RESULTADO
    nomi = sum(r["votos"].values())
    comp = nomi + r["brancos"] + r["nulos"]
    apto = SECAO["eleitores_aptos"]
    c = [
        ("ORIG", "VOTA"), ("ORLC", "LEG"), ("PROC", 2000), ("DTPL", "20261004"),
        ("PLEI", 2100), ("TURN", 1), ("FASE", "S"), ("UNFE", SECAO["uf"]),
        ("MUNI", SECAO["muni"]), ("ZONA", SECAO["zona"]), ("SECA", SECAO["secao"]),
        ("IDUE", URNA["idue"]), ("IDCA", URNA["idca"]), ("HIQT", 1),
        ("HICA", f"1:{URNA['idca']}"), ("VERS", URNA["vers"]),
        ("LOCA", SECAO["loca"]), ("APTO", apto), ("APTS", apto), ("APTT", 0),
        ("COMP", comp), ("FALT", apto - comp),
        ("HBBM", comp - HABILITACAO["HBBG"] - HABILITACAO["HBSB"]),
        ("HBBG", HABILITACAO["HBBG"]), ("HBSB", HABILITACAO["HBSB"]),
        ("DTAB", "20261004"), ("HRAB", "080000"), ("DTFC", "20261004"), ("HRFC", "170104"),
        ("IDEL", 2101), ("CARG", 1), ("TIPO", 0), ("VERC", "202607091043"),
    ]
    # Só entram os candidatos que receberam votos, em ordem de número.
    c += [(n, q) for n, q in sorted(r["votos"].items(), key=lambda kv: int(kv[0])) if q > 0]
    c += [("APTA", apto), ("APTS", apto), ("APTT", 0), ("NOMI", nomi),
          ("BRAN", r["brancos"]), ("NULO", r["nulos"]), ("TOTC", comp)]
    return [(k, str(v)) for k, v in c]


def interpretar(campos: list[tuple[str, str]]) -> dict:
    """Separa cabeçalho, votos do cargo e resumo do cargo."""
    cab, votos, resumo, estado = {}, {}, {}, "cab"
    for k, v in campos:
        if k == "CARG":
            estado = "cargo"
            cab.setdefault(k, v)
        elif estado == "cab":
            cab.setdefault(k, v)
        elif k.isdigit():
            votos[k] = v
        elif k in ("TIPO", "VERC") and estado == "cargo":
            cab.setdefault(k, v)
        else:
            estado = "resumo"
            resumo.setdefault(k, v)
    return {"cabecalho": cab, "votos": votos, "resumo": resumo}


def sha512_hex(texto: str) -> str:
    return hashlib.sha512(texto.encode("ascii", "replace")).hexdigest().upper()


def montar_texto_bu(conteudo: str, hash_hex: str, assi_hex: str) -> str:
    return f"QRBU:1:1 VRQR:{VRQR} {conteudo} HASH:{hash_hex} ASSI:{assi_hex}"


def analisar_texto_bu(texto: str) -> dict:
    """Quebra o texto de um QR Code do BU nas três seções do manual."""
    regs = texto.split()
    if not regs or not regs[0].startswith("QRBU:"):
        raise ValueError("não começa com a marca QRBU")
    i_hash = next((i for i, r in enumerate(regs) if r.startswith("HASH:")), None)
    if i_hash is None:
        raise ValueError("campo HASH ausente")
    if len(regs) < 2 or not regs[1].startswith("VRQR:"):
        raise ValueError("campo VRQR ausente")
    assi = next((r[5:] for r in regs[i_hash + 1:] if r.startswith("ASSI:")), None)
    return {
        "qrbu": regs[0][5:],
        "vrqr": regs[1][5:],
        "conteudo": " ".join(regs[2:i_hash]),
        "hash": regs[i_hash][5:],
        "assi": assi,
    }


# ------------------------------------------------------------------ chaves e certificados
PASTA_CHAVES = Path(__file__).parent / "chaves"
VALIDADE = (datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2027, 12, 31, tzinfo=timezone.utc))
NOME_AC = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Justica Eleitoral (simulada)"),
    x509.NameAttribute(NameOID.COMMON_NAME, "AC Raiz Simulada da Justica Eleitoral"),
])


def _chave(nome: str):
    arq = PASTA_CHAVES / f"{nome}.pem"
    if arq.exists():
        return serialization.load_pem_private_key(arq.read_bytes(), password=None)
    chave = ec.generate_private_key(ec.SECP521R1())
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    return chave


def _certificado(nome: str, sujeito: x509.Name, chave_publica, emissor: x509.Name,
                 chave_emissor, ac: bool) -> x509.Certificate:
    arq = PASTA_CHAVES / f"{nome}.crt"
    if arq.exists():
        return x509.load_pem_x509_certificate(arq.read_bytes())
    cert = (x509.CertificateBuilder()
            .subject_name(sujeito).issuer_name(emissor).public_key(chave_publica)
            .serial_number(x509.random_serial_number())
            .not_valid_before(VALIDADE[0]).not_valid_after(VALIDADE[1])
            .add_extension(x509.BasicConstraints(ca=ac, path_length=None), critical=True)
            .sign(chave_emissor, hashes.SHA512()))
    arq.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert


def _nome_urna() -> x509.Name:
    return x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"Urna Eletronica UE{URNA['mdue']}"),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, URNA["idue"]),
    ])


def certificado_ac():
    """Âncora de confiança: o único certificado em que o totalizador confia."""
    chave = _chave("ac_raiz")
    return _certificado("ac_raiz", NOME_AC, chave.public_key(), NOME_AC, chave, ac=True)


def chave_e_certificado_urna():
    """Par de chaves da urna (no real, fica no hardware de segurança) e o
    certificado emitido pela AC raiz."""
    chave_ac = _chave("ac_raiz")
    certificado_ac()
    chave = _chave("urna")
    return chave, _certificado("urna", _nome_urna(), chave.public_key(), NOME_AC, chave_ac, ac=False)


def chave_e_certificado_atacante():
    """O atacante cria seu próprio par de chaves e um certificado que COPIA os
    nomes da urna e da AC, mas que ele mesmo assina."""
    chave = _chave("atacante")
    return chave, _certificado("atacante", _nome_urna(), chave.public_key(), NOME_AC, chave, ac=False)


def textos_certificado(cert: x509.Certificate) -> list[str]:
    """Certificado em DER, hexadecimal, dividido em dois QR Codes (manual, 1.6.2)."""
    hexder = cert.public_bytes(serialization.Encoding.DER).hex().upper()
    n = 2
    tam = math.ceil(len(hexder) / n)
    return [f"QRCE:{i + 1}:{n} IDUE:{URNA['idue']} MDUE:{URNA['mdue']} CERT:{hexder[i * tam:(i + 1) * tam]}"
            for i in range(n)]


# ------------------------------------------------------------------ emissão e adulteração
def assinar(chave, hash_hex: str) -> str:
    return chave.sign(bytes.fromhex(hash_hex), ASSINATURA).hex().upper()


def _pacote(texto_bu: str, textos_cert: list[str], origem: str) -> dict:
    partes = analisar_texto_bu(texto_bu)
    campos = separar(partes["conteudo"])
    return {
        "texto_bu": texto_bu,
        "textos_cert": textos_cert,
        "conteudo_linhas": [f"{k}:{v}" for k, v in campos],
        "hash": partes["hash"],
        "bu": interpretar(campos),
        "origem": origem,
    }


def emitir_bu() -> dict:
    """O que a urna faz ao encerrar a votação: monta o conteúdo, calcula o
    SHA-512, assina com a chave privada e imprime o BU e o certificado."""
    chave, cert = chave_e_certificado_urna()
    conteudo = juntar(conteudo_da_secao())
    h = sha512_hex(conteudo)
    texto = montar_texto_bu(conteudo, h, assinar(chave, h))
    return _pacote(texto, textos_certificado(cert), "urna")


def adulterar(texto_bu_original: str, textos_cert_original: list[str], conteudo_adulterado: str,
              modo_hash: str = "recalcular", modo_assinatura: str = "manter") -> dict:
    """Simula um atacante que altera o conteúdo do BU e imprime novos QR Codes.
    Ele não tem a chave privada da urna.

    modo_hash        : 'manter'         reaproveita o HASH original
                       'recalcular'     calcula o SHA-512 do conteúdo alterado (qualquer um pode)
    modo_assinatura  : 'manter'         reaproveita a ASSI original (copiada do BU verdadeiro)
                       'atacante_cert'  assina com a chave do atacante e troca o certificado
    """
    orig = analisar_texto_bu(texto_bu_original)
    conteudo = " ".join(conteudo_adulterado.upper().split())
    if not conteudo:
        raise ValueError("o conteúdo do BU está vazio")
    h = sha512_hex(conteudo) if modo_hash == "recalcular" else orig["hash"]

    if modo_assinatura == "atacante_cert":
        chave, cert = chave_e_certificado_atacante()
        assi, certs, origem = assinar(chave, h), textos_certificado(cert), "atacante_cert"
    else:
        assi, certs, origem = orig["assi"], textos_cert_original, "atacante"

    texto = montar_texto_bu(conteudo, h, assi)
    if len(texto) > LIMITE_QR:
        raise ValueError(f"o BU ficou com {len(texto)} caracteres; o limite de um QR Code é {LIMITE_QR}")
    return _pacote(texto, certs, origem)


# ------------------------------------------------------------------ QR Code
def gerar_qr_png(texto: str, tamanho_modulo: int = 4) -> bytes:
    """Como o texto só usa caracteres alfanuméricos, a biblioteca escolhe o modo
    alfanumérico do QR Code, como faz a urna (libqrencode)."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=tamanho_modulo, border=4)
    qr.add_data(texto)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def ler_qr(imagem: bytes) -> str | None:
    try:
        img = Image.open(io.BytesIO(imagem)).convert("L")
    except (UnidentifiedImageError, OSError):
        return None
    for r in zxingcpp.read_barcodes(img):
        if r.format == zxingcpp.BarcodeFormat.QRCode and r.valid and r.text:
            return r.text
    return None


# ------------------------------------------------------------------ verificação
# Etapas descritas no manual do TSE (id, título, seção do manual, explicação).
ETAPAS = [
    ("leitura", "Leitura dos QR Codes", "1.4 e 1.6.2",
     "Decodifica as imagens: o BU vem no QR Code com a marca QRBU, e o certificado "
     "da urna em dois QR Codes com a marca QRCE."),
    ("estrutura", "Formato e versão (QRBU, VRQR)", "1.4 a 1.4.3",
     "Registros CHAVE:VALOR separados por espaço, só com caracteres do modo "
     "alfanumérico; sequência QRBU completa; versão do formato VRQR 6.0; campos "
     "obrigatórios, HASH e ASSI presentes."),
    ("hash", "Integridade: HASH (SHA-512)", "1.4.3",
     "Recalcula o SHA-512 da seção de conteúdo do boletim e compara com o campo HASH."),
    ("certificado", "Certificado da urna (QRCE)", "1.6.2 e 1.6.3",
     "Junta os campos CERT dos QR Codes do certificado, decodifica o X.509 (DER) e "
     "extrai a chave pública ECDSA P-521. O IDUE do certificado deve ser o do BU."),
    ("cadeia", "Cadeia de confiança do certificado", None,
     "Confere se o certificado foi assinado pela autoridade certificadora da Justiça "
     "Eleitoral (simulada aqui)."),
    ("assinatura", "Assinatura: ASSI (ECDSA P-521)", "1.6.1 e 1.6.3",
     "Verifica ASSI sobre o SHA-512 do HASH com a chave pública do certificado, "
     "como no código de exemplo do manual."),
]


def verificar(imagens: list[bytes] | None = None, textos: list[str | None] | None = None) -> dict:
    """Executa as etapas de verificação. Uma etapa cujo pré-requisito falhou
    fica como 'pulado'."""
    res: dict[str, tuple[str, str]] = {}
    if textos is None:
        textos = [ler_qr(img) for img in (imagens or [])]

    # 1. leitura
    ilegiveis = sum(t is None for t in textos)
    lidos = [t for t in textos if t]
    textos_bu = [t for t in lidos if t.startswith("QRBU:")]
    textos_ce = sorted((t for t in lidos if t.startswith("QRCE:")), key=lambda t: t.split()[0])
    if ilegiveis or not textos_bu:
        res["leitura"] = ("falha", f"{ilegiveis} imagem(ns) ilegível(is)" if ilegiveis else "nenhum QR Code de BU")
    else:
        res["leitura"] = ("ok", f"{len(textos_bu)} QR Code do BU e {len(textos_ce)} do certificado")

    # 2. estrutura
    partes = campos = bu = None
    if res["leitura"][0] == "ok":
        try:
            if len(textos_bu) != 1:
                raise ValueError("esta simulação lê BUs de um único QR Code")
            texto = textos_bu[0]
            if not ALFANUMERICO.match(texto):
                raise ValueError("há caracteres fora do modo alfanumérico do QR Code")
            partes = analisar_texto_bu(texto)
            if partes["qrbu"] != "1:1":
                raise ValueError(f"sequência QRBU:{partes['qrbu']} incompleta")
            if partes["vrqr"] != VRQR:
                raise ValueError(f"versão do formato VRQR:{partes['vrqr']} não suportada")
            campos = separar(partes["conteudo"])
            presentes = {k for k, _ in campos}
            faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in presentes]
            if faltando:
                raise ValueError("campos ausentes: " + ", ".join(faltando))
            if not re.fullmatch(r"[0-9A-F]{128}", partes["hash"]):
                raise ValueError("HASH não tem 128 dígitos hexadecimais (SHA-512)")
            if not partes["assi"] or not re.fullmatch(r"(?:[0-9A-F]{2})+", partes["assi"]):
                raise ValueError("ASSI ausente ou não hexadecimal")
            bu = interpretar(campos)
            c = bu["cabecalho"]
            res["estrutura"] = ("ok", f"{len(campos)} registros · zona {c['ZONA']}, seção {c['SECA']}, "
                                      f"turno {c['TURN']}, fase {c['FASE']}")
        except ValueError as e:
            res["estrutura"] = ("falha", str(e))
            partes = None

    hash_calc = None
    if partes:
        # 3. hash
        hash_calc = sha512_hex(partes["conteudo"])
        res["hash"] = ("ok", "SHA-512 recalculado = HASH") if hash_calc == partes["hash"] else \
                      ("falha", "SHA-512 recalculado ≠ HASH: o conteúdo mudou depois do cálculo do hash")

    # 4. certificado
    cert = None
    if res["leitura"][0] == "ok":
        try:
            if len(textos_ce) != 2:
                raise ValueError(f"esperados 2 QR Codes de certificado, lidos {len(textos_ce)}")
            hexcert, idues = "", set()
            for i, t in enumerate(textos_ce, start=1):
                regs = dict(separar(t))
                if regs.get("QRCE") != f"{i}:2":
                    raise ValueError("sequência QRCE incompleta")
                idues.add(regs.get("IDUE"))
                hexcert += regs.get("CERT", "")
            cert = x509.load_der_x509_certificate(bytes.fromhex(hexcert))
            pub = cert.public_key()
            if not (isinstance(pub, ec.EllipticCurvePublicKey) and pub.curve.name == "secp521r1"):
                raise ValueError("a chave do certificado não é ECDSA P-521")
            serie = cert.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
            idue_cert = serie[0].value if serie else None
            idue_bu = bu["cabecalho"].get("IDUE") if bu else None
            if bu and not (idues == {idue_bu} and idue_cert == idue_bu):
                raise ValueError(f"IDUE do certificado ({idue_cert}) diferente do BU ({idue_bu})")
            res["certificado"] = ("ok", f"X.509 da urna {idue_cert}, chave ECDSA P-521")
        except ValueError as e:
            res["certificado"] = ("falha", f"certificado inválido: {e}")
            cert = None

    if cert is not None:
        # cadeia de confiança (não descrita no manual)
        try:
            cert.verify_directly_issued_by(certificado_ac())
            res["cadeia"] = ("ok", "certificado emitido pela AC da Justiça Eleitoral (simulada)")
        except (ValueError, TypeError, InvalidSignature):
            res["cadeia"] = ("falha", "o certificado NÃO foi emitido pela AC da Justiça Eleitoral: "
                                      "é um certificado falso")

        # assinatura
        if partes:
            try:
                cert.public_key().verify(bytes.fromhex(partes["assi"]), bytes.fromhex(partes["hash"]), ASSINATURA)
                res["assinatura"] = ("ok", "ASSI confere com o HASH e a chave do certificado")
            except InvalidSignature:
                res["assinatura"] = ("falha", "ASSI não confere com o HASH e a chave do certificado")

    etapas = []
    for id_, titulo, secao_manual, explicacao in ETAPAS:
        status, detalhe = res.get(id_) or ("pulado", "não executada: depende de uma etapa anterior")
        etapas.append({"id": id_, "titulo": titulo, "secao_manual": secao_manual, "status": status,
                       "detalhe": detalhe, "explicacao": explicacao})

    return {
        "valido": all(e["status"] == "ok" for e in etapas),
        "etapas": etapas,
        "bu": bu,
        "textos": lidos,
        "hash_declarado": partes["hash"] if partes else None,
        "hash_calculado": hash_calc,
    }


# ------------------------------------------------------------------ totalizador
class Totalizador:
    """Só contabiliza BUs aprovados em todas as verificações e rejeita um
    segundo BU para a mesma seção (replay)."""

    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        self.aceitos: dict[tuple[str, str], dict] = {}
        self.log: list[dict] = []

    def receber(self, textos: list[str]) -> dict:
        r = verificar(textos=textos)
        agora = datetime.now().strftime("%H:%M:%S")
        secao = "?"
        if r["bu"]:
            cab = r["bu"]["cabecalho"]
            secao = f"{cab.get('ZONA')}/{cab.get('SECA')}"
        if not r["valido"]:
            falhas = [e["titulo"] for e in r["etapas"] if e["status"] == "falha"]
            motivo, aceito = "falhou em: " + ", ".join(falhas), False
        else:
            chave = (r["bu"]["cabecalho"]["ZONA"], r["bu"]["cabecalho"]["SECA"])
            if chave in self.aceitos:
                motivo, aceito = "BU duplicado: esta seção já foi contabilizada (replay)", False
            else:
                self.aceitos[chave] = r["bu"]
                motivo, aceito = "aceito e contabilizado", True
        self.log.insert(0, {"hora": agora, "secao": secao, "aceito": aceito, "motivo": motivo})
        return {"aceito": aceito, "motivo": motivo, **self.estado()}

    def estado(self) -> dict:
        candidatos: dict[str, int] = {}
        brancos = nulos = 0
        for bu in self.aceitos.values():
            for c, n in bu["votos"].items():
                candidatos[c] = candidatos.get(c, 0) + int(n)
            brancos += int(bu["resumo"]["BRAN"])
            nulos += int(bu["resumo"]["NULO"])
        return {
            "candidatos": dict(sorted(candidatos.items(), key=lambda kv: -kv[1])),
            "brancos": brancos,
            "nulos": nulos,
            "secoes": [f"{z}/{s}" for z, s in sorted(self.aceitos)],
            "log": self.log[:20],
        }
