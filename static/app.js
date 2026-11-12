"use strict";

const $ = (s) => document.querySelector(s);

// ------------------------------------------------------------------ estado
let SECAO = null;        // dados da seção (vêm do servidor)
let CANDIDATOS = [];     // [{numero, nome, partido}]
let RESULTADO = null;    // resultado real da seção: {votos, brancos, nulos}
let original = null;     // pacote emitido pela urna (o que o atacante intercepta)
let ultimaLeitura = null;

// ------------------------------------------------------------------ utilitários
async function api(url, corpo) {
  const resp = await fetch(url, {
    method: corpo === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const dados = await resp.json();
  if (!resp.ok) throw new Error(dados.erro || `erro ${resp.status}`);
  return dados;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 4500);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function nomeCandidato(numero) {
  const c = CANDIDATOS.find((c) => c.numero === numero);
  return c ? `${c.nome} (${c.partido})` : `Candidato ${numero}`;
}

// ------------------------------------------------------------------ painel 1: urna
function renderSecao() {
  $("#secao-nome").textContent = `Seção ${SECAO.secao}, ${SECAO.zona}ª Zona Eleitoral`;
  $("#secao-local").textContent = `${SECAO.local} · ${SECAO.municipio}/${SECAO.uf}`;}

function renderResultado() {
  const v = RESULTADO.votos;
  const validos = Object.values(v).reduce((s, n) => s + n, 0);
  const pct = (n) => (validos ? ((100 * n) / validos).toFixed(2).replace(".", ",") + "%" : "–");
  const ordenados = [...CANDIDATOS].sort((a, b) => (v[b.numero] || 0) - (v[a.numero] || 0) || a.numero - b.numero);
  $("#tab-candidatos tbody").innerHTML = ordenados.map((c) => {
    const n = v[c.numero] || 0;
    return `
    <tr class="${n ? "" : "zerado"}">
      <td><span class="cand-num">${esc(c.numero)}</span>
          <span class="cand-nome">${esc(c.nome)}</span><span class="cand-partido">${esc(c.partido)}</span></td>
      <td class="num-col">${n}</td>
      <td class="num-col">${pct(n)}</td>
    </tr>`;
  }).join("");
  const comparecimento = validos + RESULTADO.brancos + RESULTADO.nulos;
  $("#tab-candidatos tfoot").innerHTML = `
    <tr class="subtotal"><td>Votos válidos</td><td class="num-col">${validos}</td><td></td></tr>
    <tr><td>Brancos</td><td class="num-col">${RESULTADO.brancos}</td><td></td></tr>
    <tr><td>Nulos</td><td class="num-col">${RESULTADO.nulos}</td><td></td></tr>
    <tr class="subtotal"><td>Comparecimento</td><td class="num-col">${comparecimento}</td><td></td></tr>`;
}

$("#btn-emitir").onclick = async () => {
  try {
    const r = await api("/api/emitir", {});
    original = r;
    mostrarQRs(r);
    prepararLab(r);
  } catch (e) {
    toast(e.message);
  }
};

// ------------------------------------------------------------------ painel 2: QR Codes
const ROTULOS = {
  urna: "Emitido pela urna",
  atacante: "Adulterado pelo atacante",
  atacante_cert: "Adulterado pelo atacante (certificado falso)",
};

function mostrarQRs(r) {
  $("#qr-bu").src = r.qr_bu;
  $("#qr-cert-1").src = r.qr_cert[0];
  $("#qr-cert-2").src = r.qr_cert[1];
  $("#qr-vazio").hidden = true;
  $("#qr-area").hidden = false;
  const el = $("#qr-origem");
  el.className = "origem " + (r.origem === "urna" ? "urna" : "atacante");
  el.textContent = ROTULOS[r.origem];
  mostrarTexto(r.texto_bu);
  $("#btn-verificar").disabled = false;
}

function mostrarTexto(texto) {
  const m = texto.match(/^(QRBU:\S+ VRQR:\S+) (.*) (HASH:\S+) (ASSI:\S+)$/);
  $("#texto-bu").innerHTML = m
    ? `<span class="seg-cab">${esc(m[1])}</span> <span class="seg-dados">${esc(m[2])}</span> ` +
      `<span class="seg-hash">${esc(m[3])}</span> <span class="seg-ass">${esc(m[4])}</span>`
    : esc(texto);
  $("#texto-tam").textContent = texto.length;
}

// ---------- laboratório do atacante
let regsOriginais = [];      // [[chave, valor], ...] do BU emitido pela urna
let conteudoAtual = [];      // [{k, v, estado, antes}] exibido no laboratório

const separarReg = (r) => {
  const i = r.indexOf(":");
  return [r.slice(0, i), r.slice(i + 1)];
};
const ehCandidato = (k) => /^\d+$/.test(k);
const valorOriginal = (k) => Number((regsOriginais.find(([x]) => x === k) || [])[1]) || 0;

function prepararLab(r) {
  regsOriginais = r.conteudo_linhas.map(separarReg);
  $("#lab-votos").innerHTML = CANDIDATOS.map((c) => `
    <li>
      <label for="voto-${esc(c.numero)}"><span class="cand-num">${esc(c.numero)}</span>${esc(c.nome)}</label>
      <input type="number" min="0" step="1" id="voto-${esc(c.numero)}" data-numero="${esc(c.numero)}"
             value="${Number(r.bu.votos[c.numero] || 0)}">
    </li>`).join("");
  conteudoAtual = regsOriginais.map(([k, v]) => ({ k, v, estado: "igual" }));
  renderConteudo();
  $("#painel-lab").hidden = false;
}

// Monta o conteúdo adulterado a partir dos votos digitados. Como um atacante
// cuidadoso, também ajusta os totais (NOMI, TOTC, COMP, FALT, HBBM).
function montarConteudo(novos) {
  const iIni = regsOriginais.findIndex(([k]) => k === "VERC") + 1;
  const iFim = regsOriginais.findIndex(([k]) => k === "APTA");
  const antes = Object.fromEntries(regsOriginais.slice(iIni, iFim).filter(([k]) => ehCandidato(k)));

  // Votos dos candidatos: o BU só lista quem tem votos, em ordem de número.
  const numeros = [...new Set([...Object.keys(antes), ...Object.keys(novos)])].sort((a, b) => a - b);
  const candidatos = [];
  let nomi = 0;
  for (const n of numeros) {
    const a = Number(antes[n] || 0), d = Number(novos[n] || 0);
    nomi += d;
    if (!a && !d) continue;
    const estado = a === d ? "igual" : !a ? "novo" : !d ? "removido" : "alterado";
    candidatos.push({ k: n, v: String(d || a), estado, antes: String(a) });
  }

  const totc = nomi + valorOriginal("BRAN") + valorOriginal("NULO");
  const totais = {
    NOMI: nomi, TOTC: totc, COMP: totc,
    FALT: valorOriginal("APTO") - totc,
    HBBM: totc - valorOriginal("HBBG") - valorOriginal("HBSB"),
  };
  const ajustar = ([k, v]) => (k in totais && String(totais[k]) !== v
    ? { k, v: String(totais[k]), estado: "alterado", antes: v }
    : { k, v, estado: "igual" });

  return [...regsOriginais.slice(0, iIni).map(ajustar), ...candidatos, ...regsOriginais.slice(iFim).map(ajustar)];
}

function renderConteudo() {
  $("#conteudo-bu").innerHTML = conteudoAtual.map((r) => {
    const txt = esc(`${r.k}:${r.v}`);
    if (r.estado === "igual") return `<div>${txt}</div>`;
    if (r.estado === "removido") return `<div class="removido" title="registro removido (0 votos)">${txt}</div>`;
    const dica = r.estado === "novo" ? "registro novo" : `antes: ${r.antes}`;
    const marca = r.estado === "novo" ? `<span class="marca">novo</span>` : `<span class="antes">${esc(r.antes)}</span>`;
    return `<div class="mudou" title="${esc(dica)}">${txt}${marca}</div>`;
  }).join("");
}

$("#btn-atualizar").onclick = () => {
  const novos = {};
  for (const inp of document.querySelectorAll("#lab-votos input")) {
    const n = Number(inp.value);
    if (!Number.isInteger(n) || n < 0) {
      inp.focus();
      return toast("os votos devem ser números inteiros não negativos");
    }
    novos[inp.dataset.numero] = n;
  }
  conteudoAtual = montarConteudo(novos);
  renderConteudo();
  if (conteudoAtual.every((r) => r.estado === "igual")) toast("nenhum voto foi alterado");
};

$("#btn-restaurar").onclick = () => original && prepararLab(original);

$("#btn-adulterar").onclick = async () => {
  if (!original) return toast("nenhum BU emitido para interceptar");
  try {
    const conteudo = conteudoAtual.filter((r) => r.estado !== "removido").map((r) => `${r.k}:${r.v}`).join(" ");
    const r = await api("/api/adulterar", {
      texto_bu: original.texto_bu,
      textos_cert: original.textos_cert,
      conteudo,
      hash: document.querySelector("input[name=hash]:checked").value,
      assinatura: document.querySelector("input[name=ass]:checked").value,
    });
    mostrarQRs(r);
    $("#painel-qr").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    toast(e.message);
  }
};

// ------------------------------------------------------------------ painel 3: verificação
const SIMBOLO = { ok: "✓", falha: "✗", pulado: "–" };

$("#btn-verificar").onclick = async () => {
  try {
    const imagens = [$("#qr-bu").src, $("#qr-cert-1").src, $("#qr-cert-2").src];
    ultimaLeitura = await api("/api/verificar", { imagens });
    renderVerificacao(ultimaLeitura);
  } catch (e) {
    toast(e.message);
  }
};

function renderVerificacao(r) {
  $("#resultado").hidden = false;
  const v = $("#veredito");
  v.className = r.valido ? "ok" : "falha";
  v.textContent = r.valido
    ? "BU VÁLIDO: aprovado em todas as verificações"
    : "BU REJEITADO: " + r.etapas.filter((e) => e.status === "falha").map((e) => e.titulo).join(", ");

  const ol = $("#etapas");
  ol.innerHTML = "";
  r.etapas.forEach((e, i) => {
    const li = document.createElement("li");
    li.className = e.status;
    li.style.animationDelay = `${i * 110}ms`;
    li.innerHTML = `
      <span class="icone">${SIMBOLO[e.status]}</span>
      <span class="etapa-titulo">${esc(e.titulo)} ${e.secao_manual
        ? `<span class="fonte" title="Seção do manual do TSE">manual TSE ${esc(e.secao_manual)}</span>`
        : `<span class="fonte extra" title="Etapa não descrita no manual do TSE">fora do manual</span>`}</span>
      <span class="etapa-detalhe">${esc(e.detalhe)}</span>
      <span class="etapa-expl">${esc(e.explicacao)}</span>`;
    ol.appendChild(li);
  });

  if (r.hash_declarado && r.hash_calculado) {
    const li = document.createElement("li");
    li.className = r.hash_declarado === r.hash_calculado ? "ok" : "falha";
    li.style.animationDelay = `${r.etapas.length * 110}ms`;
    li.innerHTML = `
      <span class="icone">#</span>
      <span class="etapa-titulo">Hashes SHA-512 comparados</span>
      <span class="etapa-detalhe">HASH do QR: <code>${r.hash_declarado}</code></span>
      <span class="etapa-detalhe">recalculado: <code>${r.hash_calculado}</code></span>`;
    ol.appendChild(li);
  }

  renderBuLido(r.bu);
  $("#btn-totalizar").disabled = !r.textos || !r.textos.length;
}

const FASES = { O: "oficial", S: "simulado", T: "treinamento" };

function linhasBu(bu) {
  const c = bu.cabecalho, s = bu.resumo;
  const muni = c.MUNI === String(SECAO.muni) ? `${c.MUNI} (${SECAO.municipio})` : c.MUNI;
  return [
    ["Município (MUNI)", muni],
    ["Zona (ZONA)", c.ZONA],
    ["Seção (SECA)", c.SECA],
    ["Local (LOCA)", c.LOCA],
    ["Urna (IDUE)", c.IDUE],
    ["Turno / fase", `${c.TURN}º turno · ${FASES[c.FASE] || c.FASE}`],
    ["Aptos (APTO)", c.APTO],
    ["Comparecimento (COMP)", c.COMP],
    ["Faltosos (FALT)", c.FALT],
    ...Object.entries(bu.votos).map(([n, q]) => [`${n} · ${nomeCandidato(n)}`, q, "voto:" + n]),
    ["Nominais (NOMI)", s.NOMI],
    ["Brancos (BRAN)", s.BRAN],
    ["Nulos (NULO)", s.NULO],
    ["Total (TOTC)", s.TOTC],
  ];
}

function renderBuLido(bu) {
  const area = $("#bu-lido");
  if (!bu) {
    area.innerHTML = "";
    return;
  }
  // Referência só para a demonstração: o BU emitido pela urna.
  const ref = original ? Object.fromEntries(linhasBu(original.bu).map(([r, v, id]) => [id || r, v])) : null;
  const atuais = linhasBu(bu);
  // Candidatos que existiam no original e sumiram do BU lido (ficaram com 0 votos).
  if (original) {
    for (const n of Object.keys(original.bu.votos)) {
      if (!(n in bu.votos)) atuais.push([`${n} · ${nomeCandidato(n)}`, "0", "voto:" + n]);
    }
  }
  let html = `<h3>Dados lidos do QR Code</h3><table class="tabela"><tbody>`;
  for (const [rotulo, val, id] of atuais) {
    const orig = ref ? ref[id || rotulo] : undefined;
    const mudou = ref && String(orig ?? "0") !== String(val ?? "");
    html += `<tr><td>${esc(rotulo)}</td><td class="num-col ${mudou ? "diff" : ""}">${esc(val ?? "—")}${
      mudou ? `<span class="orig">${esc(orig ?? "0")}</span>` : ""}</td></tr>`;
  }
  html += `</tbody></table>`;
  if (ref) html += `<p class="nota">Em vermelho: diferenças em relação ao BU emitido pela urna (referência só para a demonstração).
    Os nomes dos candidatos não estão no QR Code: no sistema real vêm de um arquivo de complemento assinado.</p>`;
  area.innerHTML = html;
}

$("#btn-totalizar").onclick = async () => {
  if (!ultimaLeitura || !ultimaLeitura.textos) return;
  try {
    renderTotal(await api("/api/totalizar", { textos: ultimaLeitura.textos }));
  } catch (e) {
    toast(e.message);
  }
};

$("#btn-reiniciar").onclick = async () => renderTotal(await api("/api/reiniciar", {}));

function renderTotal(t) {
  const linhas = [
    ...Object.entries(t.candidatos).map(([c, n]) => [`${c} · ${nomeCandidato(c)}`, n]),
    ["Brancos", t.brancos], ["Nulos", t.nulos],
  ];
  $("#tab-total tbody").innerHTML = linhas
    .map(([c, n]) => `<tr><td>${esc(c)}</td><td class="num-col">${n}</td></tr>`)
    .join("");
  $("#secoes-aceitas").textContent = t.secoes.length
    ? `Seções contabilizadas: ${t.secoes.join(", ")}`
    : "Nenhuma seção contabilizada ainda.";
  $("#log").innerHTML = t.log
    .map((l) => `<li><span class="hora">${l.hora}</span>seção ${esc(l.secao)}:
      <span class="${l.aceito ? "aceito" : "rejeitado"}">${l.aceito ? "ACEITO" : "REJEITADO"}</span>
      ${l.aceito ? "" : "– " + esc(l.motivo)}</li>`)
    .join("");
}

// ------------------------------------------------------------------ início
(async () => {
  try {
    const cfg = await api("/api/config");
    SECAO = cfg.secao;
    CANDIDATOS = cfg.candidatos;
    RESULTADO = cfg.resultado;
    renderSecao();
    renderResultado();
    renderTotal(await api("/api/totalizacao"));
  } catch (e) {
    toast("não foi possível carregar a configuração: " + e.message);
  }
})();
