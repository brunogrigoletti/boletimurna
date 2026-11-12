# Verificação do QR Code do Boletim de Urna

Trabalho prático de Segurança de Sistemas (PUCRS).

Aplicação web local que simula o **encerramento da votação** numa seção
eleitoral e a **leitura e verificação** do QR Code do Boletim de Urna (BU),
seguindo o *QR Code no Boletim de Urna: Manual para Criação de Aplicativo de
Leitura* (TSE, 2026), disponível em
<https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/manual-do-qr-code-no-boletim-de-urna/@@display-file/file/manual-do-qr-code-no-boletim-de-urna.pdf>.

Seção simulada: **Seção 31, 159ª Zona Eleitoral, PUCRS (Prédio 50), Porto
Alegre/RS**, com o **resultado real do 1º turno de 2026** para Presidente
(317 votos válidos, 4 brancos, 3 nulos).

> **Simulação didática.** Não é o sistema oficial. Os votos são reais. Os
> códigos de processo, pleito, eleição, urna, carga e local, os horários, as
> habilitações e o número de eleitores aptos (400) são **ilustrativos**. As
> chaves e certificados são gerados localmente.

## Como funciona

1. **Urna**: exibe o resultado da seção. Ao encerrar a votação, monta o
   conteúdo do BU no formato do manual, calcula o **SHA-512**, assina com
   **ECDSA P-521** e imprime três QR Codes: o do BU e os dois do certificado
   da urna.
2. **Laboratório do atacante** (quadro escuro, abaixo): o atacante muda os
   votos de cada candidato e clica em **Atualizar conteúdo do boletim**. Os
   registros alterados aparecem em vermelho, e os totais são ajustados, como
   faria um atacante cuidadoso. Depois ele escolhe o que fazer com o HASH
   (manter ou recalcular) e com a assinatura e o certificado (copiar a
   assinatura original, ou assinar com a própria chave e trocar o
   certificado), e gera os QR Codes adulterados. Ele nunca tem a chave
   privada da urna.
3. **Leitura e verificação**: decodifica as **imagens** dos QR Codes e mostra
   cada etapa de validação. O totalizador só contabiliza BUs aprovados em
   todas elas e recusa um segundo BU para a mesma seção (replay).

## Formato do QR Code (manual, seção 1.4)

```
QRBU:1:1 VRQR:6.0 ORIG:VOTA ... ZONA:159 SECA:31 IDUE:... APTO:400 COMP:324 FALT:76 ...
IDEL:2101 CARG:1 TIPO:0 VERC:... 13:160 14:6 21:1 22:131 30:4 55:4 70:10 80:1
APTA:400 ... NOMI:317 BRAN:4 NULO:3 TOTC:324 HASH:<SHA-512 em hex> ASSI:<assinatura em hex>
```

- Registros `CHAVE:VALOR` separados por espaço, só com caracteres do modo
  alfanumérico do QR Code. Por isso **não há nomes** no QR Code: os
  candidatos aparecem pelo número.
- Só entram os candidatos que receberam votos.
- `HASH`: SHA-512 da seção de conteúdo. `ASSI`: assinatura sobre o
  SHA-512 dos bytes do HASH, como no código de exemplo do manual.
- Certificado da urna: X.509 em DER, em hexadecimal, dividido em dois QR
  Codes (`QRCE:1:2 IDUE:... MDUE:2015 CERT:...`).

## Etapas de verificação

| # | Etapa | Origem |
|---|---|---|
| 1 | Leitura dos QR Codes (BU e certificado) | manual, 1.4 e 1.6.2 |
| 2 | Formato e versão: QRBU, VRQR 6.0, alfanumérico, campos obrigatórios | manual, 1.4 a 1.4.3 |
| 3 | Integridade: SHA-512 recalculado = `HASH` | manual, 1.4.3 |
| 4 | Certificado da urna: junta os `CERT`, decodifica o X.509, chave P-521, `IDUE` igual ao do BU | manual, 1.6.2 e 1.6.3 |
| 5 | Cadeia de confiança: o certificado foi emitido pela AC da Justiça Eleitoral (simulada) | **fora do manual** |
| 6 | Assinatura: `ASSI` confere com o `HASH` e a chave do certificado | manual, 1.6.1 e 1.6.3 |

O manual não descreve como confiar no certificado que vem impresso no próprio
BU: a chave pública usada na verificação sai desse certificado. Só com as
etapas do manual, um atacante que gere um par de chaves e um certificado
próprios e os imprima no lugar dos originais teria o BU aceito. A etapa 5,
acrescentada nesta simulação, fecha essa brecha: o certificado precisa ter
sido emitido pela AC da Justiça Eleitoral (aqui, `chaves/ac_raiz.crt`). Não
foi verificado como os aplicativos reais fazem essa validação.

## Instalação

Requer Python 3.10 ou superior.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Execução

```bash
python app.py
```

Abra **http://127.0.0.1:5000** no navegador.

Na primeira emissão são criados, em `chaves/`:

- `ac_raiz.pem` / `ac_raiz.crt`: a AC raiz simulada, que emite o certificado da urna;
- `urna.pem` / `urna.crt`: o par de chaves da urna e o certificado emitido pela AC;
- `atacante.pem` / `atacante.crt`: a chave do atacante e um certificado falso, que copia os nomes da urna e da AC (criados no primeiro ataque que os usa).

Para começar do zero, apague a pasta `chaves/`.

## Roteiro de demonstração

Antes: **Encerrar votação e emitir BU**, **Ler QR Codes e verificar** (tudo ✓)
e **Contabilizar** duas vezes (a segunda é rejeitada: replay).

Em cada passo, mude os votos no laboratório (por exemplo, 50 votos do 13 para
o 22), clique em **Atualizar conteúdo do boletim**, escolha as opções, gere os
QR Codes adulterados e verifique.

| # | HASH | ASSI e certificado | Resultado |
|---|---|---|---|
| 1 | manter | manter | HASH ✗, mas **ASSI ✓**: a assinatura protege o hash, e o hash protege os dados |
| 2 | recalcular | manter | HASH ✓, **ASSI ✗**: recalcular o hash é fácil; assinar sem a chave, não |
| 3 | recalcular | chave do atacante + certificado falso | todas as etapas do manual ✓; só a **cadeia de confiança ✗** |
| 4 | manter | chave do atacante + certificado falso | HASH ✗ e cadeia ✗ |

## Limitações (discutidas no relatório)

- A assinatura garante que o BU não foi alterado **depois** de emitido e que
  veio de uma urna certificada. Ela **não** prova que os votos registrados
  pela urna correspondem às intenções dos eleitores.
- A segurança depende da cadeia de confiança dos certificados e da proteção
  da chave privada. Na urna real, a chave fica no hardware de segurança; aqui,
  num arquivo.
- O BU cabe em um único QR Code. O manual prevê vários, com hash cumulativo.
- As urnas 2020 e 2022 usam EdDSA (Ed521), que a biblioteca `cryptography`
  não implementa. Aqui é usado o ECDSA P-521 das urnas 2013 e 2015.
- Os nomes dos candidatos, no sistema real, vêm de um arquivo de complemento
  assinado pelo TSE (manual, 1.7). Aqui estão fixos no código.

## Estrutura

```
app.py              servidor Flask (rotas da API)
bu.py               formato do BU, chaves e certificados, emissão, adulteração,
                    QR Code, verificação e totalizador
templates/          página
static/             CSS e JavaScript da interface
```

## Referência

TRIBUNAL SUPERIOR ELEITORAL. *QR Code no boletim de urna: manual para criação
de aplicativo de leitura*. Brasília: TSE, 2026.
