# Verificação do QR Code do Boletim de Urna

Trabalho prático de Segurança de Sistemas (PUCRS).

Aplicação web local que simula o **encerramento da votação** numa seção
eleitoral e a **leitura e verificação** do QR Code do Boletim de Urna (BU),
seguindo o *QR Code no Boletim de Urna: Manual para Criação de Aplicativo de
Leitura* (TSE, 2026), disponível em
<https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/manual-do-qr-code-no-boletim-de-urna/@@display-file/file/manual-do-qr-code-no-boletim-de-urna.pdf>.
A validação da cadeia de confiança do certificado segue a hierarquia de
certificados da urna descrita na monografia *Segurança no Sistema Brasileiro
de Votação Eletrônica* (Schauren, UFRGS, 2016).

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
2. **QR Codes**: mostra as imagens geradas e o texto codificado no QR Code do
   BU, com as três seções destacadas.
3. **Leitura e verificação**: decodifica as **imagens** dos QR Codes e mostra
   cada etapa de validação. O totalizador só contabiliza BUs aprovados em
   todas elas e recusa um segundo BU para a mesma seção (replay).
4. **Laboratório do atacante**: o atacante muda os votos de cada candidato e
   clica em **Atualizar conteúdo do boletim**. Os registros alterados aparecem
   em vermelho, e os totais são ajustados, como faria um atacante cuidadoso.
   Depois ele escolhe o que fazer com o HASH (manter ou recalcular) e com a
   assinatura e o certificado (copiar a assinatura original, ou assinar com a
   própria chave e trocar o certificado), e gera os QR Codes adulterados. Ele
   nunca tem a chave privada da urna.

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
| 5 | Cadeia de confiança: AC URNA → certificado da fase → certificado da urna | Schauren, Fig. 4.7 e 5.12 |
| 6 | Assinatura: `ASSI` confere com o `HASH` e a chave do certificado | manual, 1.6.1 e 1.6.3 |

O manual não descreve como confiar no certificado que vem impresso no próprio
BU: a chave pública usada na verificação sai desse certificado. Só com as
etapas do manual, um atacante que gere um par de chaves e um certificado
próprios e os imprima no lugar dos originais teria o BU aceito. A etapa 5
fecha essa brecha.

Schauren (2016, seção 4.4) explica que os certificados das urnas não são
ICP-Brasil: são gerados na autoridade certificadora do TSE, e as chaves
públicas para validar o QR Code são publicadas no site do TSE (seção 5.12).
A hierarquia segue a Fig. 4.7 da monografia (TSE, Processo 20.038/2014): a
**AC URNA** (nível 0) emite um certificado para cada fase (oficial, simulado,
desenvolvimento; nível 1), e este emite o certificado de autenticação de cada
urna, `UEA<fase><id>` (nível 2). Como o BU desta simulação é simulado
(`FASE:S`), só o ramo **SIMULADO** é gerado, e a urna recebe o certificado
`UEAS2017334`. A âncora de confiança é o certificado da AC URNA
(`chaves/ac_urna.crt`).

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

- `ac_urna.*`: a AC URNA (nível 0), a âncora de confiança;
- `ac_fase.*`: o certificado da fase SIMULADO (nível 1);
- `urna.*`: o par de chaves e o certificado da urna (nível 2);
- `atacante.pem` / `atacante_falso.crt`: a chave do atacante e um certificado falso, que copia os nomes da urna e da fase (criados no primeiro ataque que os usa).

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
  da chave privada. Na urna real, a chave fica no hardware de segurança (o
  MSD, que também guarda os certificados de nível 0); aqui, num arquivo.
- A assinatura prova que o BU veio de *uma* urna certificada, não de *qual*
  urna nem de qual carga. No sistema real, isso é coberto por outros
  mecanismos, não simulados aqui: chaves separadas por modo de segurança (uma
  urna de treinamento não produz BU oficial; Schauren, 4.4) e a tabela de
  correspondências, que só aceita o BU cujo código de identificação da carga
  (`IDCA`) foi publicado para a seção (Schauren, 5.8).
- Da Fig. 4.7, só o ramo SIMULADO e o certificado de autenticação da urna
  são gerados; os ramos oficial e de desenvolvimento e os certificados de
  sigilo (`UES*`) ficam de fora.
- O manual de 2026 usa ECDSA P-521 (urnas UE2013 e UE2015) e EdDSA com a
  curva E-521 (urnas UE2020+). A biblioteca `cryptography` não implementa
  EdDSA/E-521; aqui é usado o ECDSA P-521.
- O BU cabe em um único QR Code. O manual prevê vários, com hash cumulativo.
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

## Referências

SCHAUREN, Luís Fernando. *Segurança no sistema brasileiro de votação
eletrônica*. Monografia (Bacharelado em Ciência da Computação). Porto Alegre:
UFRGS, Instituto de Informática, 2016.

TRIBUNAL SUPERIOR ELEITORAL. *QR Code no boletim de urna: manual para criação
de aplicativo de leitura*. Brasília: TSE, 2026.

ARANHA, Diego F. et al. *A note on high-security general-purpose elliptic
curves*. Cryptology ePrint Archive, Report 2013/647, 2013.

ED25519. *Ed25519: high-speed high-security signatures*. Disponível em:
<https://ed25519.cr.yp.to>.
