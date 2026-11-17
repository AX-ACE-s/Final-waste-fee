"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const won = (n) => Number(n).toLocaleString("ko-KR") + "원";

const S = { regions: [], regionId: null, item: null, answers: { measure: {} }, last: null, cart: [], cartRegion: null };

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || body.error || `요청 실패 (${res.status})`);
  return body;
}

function go(step) {
  for (let i = 1; i <= 4; i++) $(`#step${i}`).hidden = i !== step;
  document.querySelectorAll("#steps li").forEach((li) => {
    const n = +li.dataset.step;
    li.className = n === step ? "on" : n < step ? "done" : "";
    li.setAttribute("aria-current", n === step ? "step" : "false");
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------- STEP 1: 지역 ---------- */
async function loadRegions() {
  S.regions = await api("/api/spec/regions");
  $("#sido").innerHTML = `<option value="">선택</option>` + S.regions.map((r) => `<option>${esc(r.sido)}</option>`).join("");
  $("#sigungu").innerHTML = `<option value="">시·도를 먼저 고르세요</option>`;
}
function fillSigungu(sido, selectId) {
  const r = S.regions.find((x) => x.sido === sido);
  $("#sigungu").innerHTML = `<option value="">선택</option>` +
    (r ? r.sigungu.map((g) => `<option value="${g.id}">${esc(g.sigungu)}</option>`).join("") : "");
  if (selectId) $("#sigungu").value = selectId;
}
function setRegion(id) {
  S.regionId = id ? +id : null;
  S.item = null;
  $("#aiResult").innerHTML = "";
  $("#start").disabled = true;
  const g = S.regions.flatMap((r) => r.sigungu).find((x) => x.id === S.regionId);
  $("#regionInfo").textContent = g ? `관리기관: ${g.manager_org || "미기재"}` : "";
  loadItems();
}
$("#sido").addEventListener("change", (e) => { fillSigungu(e.target.value); setRegion(null); });
$("#sigungu").addEventListener("change", (e) => setRegion(e.target.value));

$("#addrBtn").addEventListener("click", searchAddr);
$("#addr").addEventListener("keydown", (e) => { if (e.key === "Enter") searchAddr(); });
async function searchAddr() {
  const q = $("#addr").value.trim();
  const list = $("#addrList");
  list.innerHTML = "";
  if (!q) return;
  const nq = q.replace(/\s+/g, "");
  // 1) 이미 가진 지역 목록에서 먼저 찾기 ("강남구"처럼 짧게 입력해도 바로 선택 가능)
  const local = nq.length < 2 ? [] : S.regions
    .flatMap((r) => r.sigungu.map((g) => ({ ...g, sido: r.sido })))
    .filter((g) => (g.sido + g.sigungu).replace(/\s+/g, "").includes(nq)).slice(0, 8);
  const items = local.map((g) => ({ kind: "region", label: `${g.sido} ${g.sigungu}`, sido: g.sido, region_id: g.id }));
  const render = (hint) => {
    list.innerHTML = items.map((it, i) => `<li data-i="${i}" class="${it.supported === false ? "no" : ""}">
        ${it.kind === "region" ? `<b>${esc(it.label)}</b> <small>지역으로 선택</small>` : esc(it.label)}
        ${it.supported === false ? "<br><small>이 지역 수수료 데이터는 아직 없어요</small>" : ""}</li>`).join("") +
      (hint ? `<li class="no">${esc(hint)}</li>` : "");
    list.querySelectorAll("li[data-i]").forEach((li) => li.addEventListener("click", () => {
      const it = items[+li.dataset.i];
      if (it.supported === false) return;
      $("#sido").value = it.sido; fillSigungu(it.sido, it.region_id); setRegion(it.region_id);
      list.innerHTML = "";
    }));
  };
  render(local.length ? "" : "검색 중이에요…");
  try {
    const rows = await api(`/api/address?q=${encodeURIComponent(q)}`);
    rows.forEach((r) => items.push({ kind: "addr", label: r.road_addr, sido: r.sido, region_id: r.region_id, supported: r.supported }));
    render(items.length ? "" : "검색 결과가 없어요. 동 이름이나 건물명을 함께 입력해 보세요.");
  } catch (e) {
    // 주소 API가 안 되거나 검색어가 넓어도, 지역을 찾았다면 에러 대신 선택지를 보여 준다
    render(local.length ? "더 정확한 주소로 찾으려면 동 이름이나 건물명까지 입력해 보세요." : e.message);
  }
}

/* ---------- STEP 1: ① 사진으로 품목 찾기 ---------- */
$("#photo").addEventListener("change", () => {
  const f = $("#photo").files[0];
  if (!f) { $("#preview").hidden = true; return; }
  $("#preview").src = URL.createObjectURL(f); $("#preview").hidden = false;
});
$("#identify").addEventListener("click", async () => {
  const box = $("#aiResult");
  const f = $("#photo").files[0];
  if (!S.regionId) { box.innerHTML = `<p class="err">지역을 먼저 골라 주세요.</p>`; return; }
  if (!f) { box.innerHTML = `<p class="err">사진을 먼저 선택해 주세요.</p>`; return; }
  const fd = new FormData(); fd.append("image", f); fd.append("region_id", S.regionId);
  box.innerHTML = `<p class="muted small">사진을 살펴보는 중이에요…</p>`;
  try {
    const res = await fetch("/api/spec/identify", { method: "POST", body: fd });
    const r = await res.json();
    if (!res.ok) throw new Error(r.error || r.detail || "사진 인식에 실패했어요.");
    if (!r.candidates || !r.candidates.length) {
      box.innerHTML = `<p class="read">${esc(r.message || "맞는 품목을 찾지 못했어요. 아래에서 직접 검색해 주세요.")}</p>`; return;
    }
    box.innerHTML = `<p class="muted small">AI 추천 — 맞는 품목을 눌러 확정해 주세요${r.observations ? ` · 관찰: ${esc(r.observations)}` : ""}</p>` +
      r.candidates.map((c, i) => `<div class="cand"><button type="button" class="chip" data-ai="${i}">${esc(c.item)}
        <small>${Math.round(c.confidence * 100)}%</small></button><span class="ev">${esc(c.evidence)}</span></div>`).join("");
    box.querySelectorAll("[data-ai]").forEach((b) => b.addEventListener("click", () => {
      const c = r.candidates[+b.dataset.ai];
      document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === b));
      S.item = c.standard_code ? { standard_code: c.standard_code, name: c.standard_name || c.item, from_photo: c.item }
                               : { local_item_id: c.local_item_id, name: c.item, from_photo: c.item };
      S.description = "";
      $("#start").disabled = false;
    }));
  } catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
});

/* ---------- STEP 1: 품목 ---------- */
let itemTimer;
$("#itemQ").addEventListener("input", () => { clearTimeout(itemTimer); itemTimer = setTimeout(loadItems, 200); });
async function loadItems() {
  $("#itemErr").textContent = "";
  $("#itemList").innerHTML = ""; $("#localOnly").innerHTML = ""; $("#localOnlyBox").hidden = true;
  if (!S.regionId) { $("#itemList").innerHTML = `<p class="muted small">지역을 먼저 골라 주세요.</p>`; return; }
  const q = $("#itemQ").value.trim();
  try {
    const d = await api(`/api/spec/items?region_id=${S.regionId}&q=${encodeURIComponent(q)}`);
    let cat = "";
    $("#itemList").innerHTML = d.standard.map((s) => {
      const head = s.category !== cat ? `<div class="cat">${esc((cat = s.category))}</div>` : "";
      return `${head}<button type="button" class="chip" data-code="${esc(s.code)}" data-name="${esc(s.name)}">${esc(s.name)}</button>`;
    }).join("");
    if (d.local_only.length) {
      $("#localOnlyBox").hidden = false;
      if (q) $("#localOnlyBox").open = true;
      $("#localOnly").innerHTML = d.local_only.map((u) =>
        `<button type="button" class="chip" data-local="${u.local_item_id}" data-name="${esc(u.name)}">${esc(u.name)}</button>`).join("");
    }
    document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => pickItem(b)));
  } catch (e) { $("#itemErr").textContent = e.message; }
  await readDescription(q);
}

// 설명 문장 읽기: 품목 자동 선택 + 읽은 치수·수량 표시
async function readDescription(q) {
  const box = $("#descInfo");
  box.hidden = true; S.description = "";
  if (!q || !S.regionId) return;
  let d;
  try { d = await api(`/api/spec/parse?region_id=${S.regionId}&text=${encodeURIComponent(q)}`); } catch { return; }
  if (d.items.length) {
    const chip = document.querySelector(`.chip[data-code="${d.items[0]}"]`);
    if (chip) pickItem(chip);
  }
  if (d.quantity) $("#qty").value = d.quantity;
  if (d.labels.length || d.quantity) {
    S.description = q;
    const parts = [...d.labels, ...(d.quantity ? [`${d.quantity}개`] : [])];
    box.innerHTML = `설명에서 읽었어요: <b>${parts.map(esc).join(" · ")}</b><br><span class="small">규격 질문에 자동으로 반영돼요.</span>`;
    box.hidden = false;
  } else {
    S.description = q;  // 종류 단어(양문형, 라텍스 등)도 읽을 수 있게 전달
  }
}
function pickItem(b) {
  document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === b));
  S.item = b.dataset.code ? { standard_code: b.dataset.code, name: b.dataset.name }
                          : { local_item_id: +b.dataset.local, name: b.dataset.name };
  $("#start").disabled = false;
}

$("#start").addEventListener("click", () => {
  const qty = +$("#qty").value;
  if (!(qty >= 1 && qty <= 50)) { $("#itemErr").textContent = "개수는 1~50 사이로 입력해 주세요."; return; }
  S.answers = { measure: {}, quantity: qty, description: S.description || "" };
  const g = S.regions.flatMap((r) => r.sigungu.map((x) => ({ ...x, sido: r.sido }))).find((x) => x.id === S.regionId);
  $("#pickedItem").textContent = `${g.sido} ${g.sigungu} · ${S.item.name}${S.item.from_photo ? " (사진 추천)" : ""} · ${qty}개`;
  go(2); next();
});

/* ---------- STEP 2: 규격 질문 ---------- */
async function next(warning) {
  const body = { region_id: S.regionId, standard_code: S.item.standard_code || null,
                 local_item_id: S.item.local_item_id || null, answers: S.answers };
  let r;
  try { r = await api("/api/spec/estimate", { method: "POST", body: JSON.stringify(body) }); }
  catch (e) { return showQ(null, e.message); }
  S.last = r;
  if (r.status === "question") return showQ(r.question, r.warning || warning);
  if (r.status === "invalid") {
    if (r.field && r.field.startsWith("measure.")) delete S.answers.measure[r.field.split(".")[1]];
    if (r.field === "amount") delete S.answers.amount;
    if (r.field === "spec") delete S.answers.spec;
    return r.question ? showQ(r.question, null, r.message) : showQ(null, r.message);
  }
  if (r.status === "result" || r.status === "needs_confirmation") return showConfirm(r);
  showQ(null, r.message || "처리할 수 없는 응답이에요.");
}

function renderTrail(sel, items) {
  $(sel).innerHTML = (items || []).map((t) => `<li>${esc(t)}</li>`).join("");
}

function optionsHtml(q) {
  return `<div class="opts">${q.options.map((o) =>
    `<button type="button" class="opt" data-qid="${esc(q.id)}" data-v="${esc(o.value)}">${esc(o.label)}</button>`).join("")}</div>`;
}

function showQ(q, warning, error) {
  $("#qWarn").hidden = !warning; $("#qWarn").textContent = warning || "";
  const box = $("#qBox");
  if (!q) { box.innerHTML = `<p class="err">${esc(error || "")}</p>`; return; }
  let html = `<p class="q-label" id="qlabel">${esc(q.label)}</p>${q.help ? `<p class="q-help">${esc(q.help)}</p>` : ""}`;
  if (q.type === "choice") html += optionsHtml(q);
  if (q.type === "number") {
    html += `<div class="row">
      <input id="numIn" type="number" inputmode="decimal" step="any" aria-labelledby="qlabel" placeholder="${esc(q.unit)} 단위" value="${q.prefill ?? ""}">
      ${q.allow_m ? `<span class="unit-toggle" role="group" aria-label="단위"><button type="button" class="on" data-u="cm">cm</button><button type="button" data-u="m">m</button></span>`
                  : `<span class="muted">${esc(q.unit)}</span>`}
      <button class="btn" id="numOk" type="button">확인</button></div>
      ${q.prefill_note ? `<p class="prefill-note">${esc(q.prefill_note)}</p>` : ""}
      <p class="err" role="alert">${esc(error || "")}</p>`;
    if (q.fallback) html += `<div class="fallback"><p class="q-label">${esc(q.fallback.label)}</p>${optionsHtml(q.fallback)}</div>`;
  } else if (error) html += `<p class="err" role="alert">${esc(error)}</p>`;
  box.innerHTML = html;

  box.querySelectorAll(".opt").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.qid, v = b.dataset.v;
    if (id === "local_item") S.answers.local_item = +v;
    else if (id === "group") S.answers.group = v;
    else if (id === "spec") S.answers.spec = +v;
    next();
  }));
  let unit = "cm";
  box.querySelectorAll(".unit-toggle button").forEach((b) => b.addEventListener("click", () => {
    unit = b.dataset.u;
    box.querySelectorAll(".unit-toggle button").forEach((x) => x.classList.toggle("on", x === b));
  }));
  const ok = $("#numOk");
  if (ok) {
    const submit = () => {
      const raw = $("#numIn").value.trim();
      if (raw === "") { box.querySelector(".err").textContent = "값을 입력하거나 아래에서 규격을 골라 주세요."; return; }
      let v = Number(raw);
      if (q.allow_m && unit === "m") v = Math.round(v * 1000) / 10;
      if (q.id === "amount") S.answers.amount = v; else S.answers.measure[q.dim] = v;
      next();
    };
    ok.addEventListener("click", submit);
    $("#numIn").addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    $("#numIn").focus();
  }
}

// 처음부터: 설명에서 읽은 값도 버리고 직접 답한다
$("#restart").addEventListener("click", () => { S.answers = { measure: {}, quantity: S.answers.quantity }; next(); });

/* ---------- STEP 3: 입력 확인 + 실측 보정 ---------- */
function showConfirm(r) {
  go(3);
  const res = r.result || r;
  renderTrail("#confirmTrail", [...(res.inputs || []), res.spec ? `적용 규격: ${res.spec.raw}` : null].filter(Boolean));
  const vb = $("#verifyBox");
  vb.innerHTML = "";
  if (r.status === "needs_confirmation") {
    vb.innerHTML = `<div class="warn">${esc(r.message)}</div>`;
    $("#toResult").textContent = "확인 안내 보기";
    return;
  }
  $("#toResult").textContent = "예상 수수료 보기";
  if (res.correction) {
    vb.innerHTML += `<div class="warn">${esc(res.correction.message)}</div>` +
      (res.correction.spec_id ? `<button class="btn" id="applyFix" type="button">실측 기준 규격으로 바꾸기</button>` : "");
    const a = $("#applyFix");
    if (a) a.addEventListener("click", () => { S.answers.spec = res.correction.spec_id; next(); });
  }
  if (res.verify && res.verify.length) {
    vb.innerHTML += `<p class="q-help">고른 규격이 맞는지 실측값으로 확인할 수 있어요 <span class="muted">(선택)</span></p>` +
      res.verify.map((v) => `<label class="lbl" for="vf_${esc(v.dim)}">${esc(v.label)} (${esc(v.unit)}) — 고른 규격: ${esc(v.range)}</label>
        <input id="vf_${esc(v.dim)}" data-dim="${esc(v.dim)}" type="number" step="any" inputmode="decimal">`).join("") +
      `<div class="row"><button class="btn ghost" id="verifyBtn" type="button">실측으로 확인</button></div>`;
    $("#verifyBtn").addEventListener("click", () => {
      vb.querySelectorAll("input[data-dim]").forEach((i) => { if (i.value !== "") S.answers.measure[i.dataset.dim] = Number(i.value); });
      next();
    });
  }
}
$("#back3").addEventListener("click", () => { delete S.answers.spec; S.answers.measure = {}; delete S.answers.amount; go(2); next(); });
$("#toResult").addEventListener("click", () => showResult(S.last));

/* ---------- STEP 4: 결과 ---------- */
function sourceHtml(src) {
  const kind = { standard_data: "공공데이터포털 표준데이터", standard_data_preview: "표준데이터(미리보기 발췌, 개발용)", manual_ordinance: "조례 확인 수동 보완" }[src.kind] || src.kind;
  return `<div class="src"><b>데이터 출처</b><br>
    ${esc(src.dataset)} · ${esc(kind)}<br>
    데이터 기준일: ${esc(src.base_date || "미기재")} · 관리기관: ${esc(src.manager_org || "미기재")}<br>
    ${src.url ? `<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.url)}</a><br>` : ""}
    ${src.ordinance_url ? `조례: <a href="${esc(src.ordinance_url)}" target="_blank" rel="noopener">${esc(src.ordinance_name || "자치법규")}</a><br>` : ""}
    <a href="${esc(src.ordinance_search_url)}" target="_blank" rel="noopener">국가법령정보센터에서 지역 조례 확인하기</a></div>`;
}
function feeDetailHtml(f) {
  // ③ 수수료 산정·근거 안내(core/fees.py) 결과: 설명 문장, 경계값 주의, 다른 규격 비교, 조례 별표 원문 링크
  const ol = (f.basis.ordinance_links || []);
  const alts = f.alternatives || [];
  return `
    <p class="explain">${esc(f.explanation || "")}</p>
    ${f.boundary_warning ? `<p class="caution">${esc(f.boundary_warning)}</p>` : ""}
    ${f.conflict ? `<p class="conflict">${esc(f.notice)} 등록된 금액: ${f.candidates.map((c) => `${esc(c.fee_text)}(${esc(c.data_date)}${c.category ? ", " + esc(c.category) : ""})`).join(" / ")}</p>` : ""}
    ${alts.length ? `<h3>다른 규격과 비교</h3><table class="alt"><thead><tr><th>규격</th><th>수수료</th><th>차이</th></tr></thead><tbody>
      ${alts.map((a) => `<tr class="${a.conflict ? "conf" : ""}"><td>${esc(a.spec)}</td><td>${esc(a.fee_text)}</td>
        <td class="${a.diff > 0 ? "up" : a.diff < 0 ? "down" : ""}">${esc(a.diff_text || "-")}</td></tr>`).join("")}</tbody></table>` : ""}
    ${ol.length ? `<h3>조례 별표 원문 (법제처)</h3><ul>${ol.map((l) => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.ordinance)} ${esc(l.name)}</a></li>`).join("")}</ul>
      <p class="muted small">금액을 자동 대조한 것이 아니라, 지자체 조례의 수수료 표 원문으로 연결하는 링크예요.</p>` : ""}
    ${!f.conflict ? `<p class="read">${esc(f.notice)}</p>` : ""}`;
}
function showResult(r) {
  go(4);
  const box = $("#resultBox");
  const f = r.fee_detail;
  S.lastFee = f || null;
  $("#copy").hidden = !(f && f.copy_text); $("#copyMsg").textContent = "";
  $("#addCart").hidden = !(f && !f.conflict);
  if (r.status === "needs_confirmation") {
    box.innerHTML = `<div class="warn">${esc(r.message)}</div>
      <p><b>${esc(r.region)}</b> · ${esc(r.item)} (지역 품목명: ${esc(r.local_item)})</p>
      ${f ? `<p class="fee pending">${esc(f.fee_text)}</p>${feeDetailHtml(f)}` : `
      <table class="cands"><thead><tr><th>등록된 규격</th><th>수수료</th><th>기준일</th></tr></thead><tbody>
      ${r.candidates.map((c) => `<tr><td>${esc(c.spec)}</td><td>${won(c.fee)}</td><td>${esc(c.base_date || "")}</td></tr>`).join("")}
      </tbody></table><p class="muted small">관할 지자체(${esc(r.source.manager_org || "")})에 어느 기준이 맞는지 확인해 주세요.</p>`}
      ${sourceHtml(r.source)}`;
    return;
  }
  const x = r.result;
  const total = f ? f.total_text : won(x.total_fee);
  const each = f ? f.fee_text : won(x.unit_fee);
  box.innerHTML = `
    <p class="muted">${esc(x.region.sido)} ${esc(x.region.sigungu)} · ${esc(x.standard_item || x.local_item)}</p>
    <p class="fee ${f && f.fee === null ? "pending" : ""}">${esc(total)}</p>
    <p class="muted small">${x.quantity > 1 ? `개당 ${esc(each)} × ${x.quantity}개` : esc(each)}${!f && x.units > 1 ? ` (${x.units}단위)` : ""}</p>
    ${x.warnings.map((w) => `<div class="warn">${esc(w)}</div>`).join("")}
    ${x.correction ? `<div class="caution">${esc(x.correction.message)}</div>` : ""}
    <dl class="kv">
      <dt>지자체</dt><dd>${esc(x.region.sido)} ${esc(x.region.sigungu)}</dd>
      <dt>표준 품목</dt><dd>${esc(x.standard_item || "(미매핑)")}</dd>
      <dt>지역 품목명</dt><dd>${esc(x.local_item)}${f && f.basis.category ? `<span class="tag">${esc(f.basis.category)}</span>` : ""}</dd>
      <dt>적용 규격</dt><dd>${esc(x.spec.raw)}</dd>
      <dt>입력 내용</dt><dd>${esc(x.inputs.join(" · ") || "-")}</dd>
    </dl>
    ${f ? feeDetailHtml(f) : ""}
    <h3>산정 근거</h3><ol class="basis">${x.basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ol>
    ${sourceHtml(x.source)}`;
}

/* ---------- 근거 복사 · 여러 품목 합계 (③) ---------- */
$("#copy").addEventListener("click", async () => {
  if (!S.lastFee) return;
  try { await navigator.clipboard.writeText(S.lastFee.copy_text); $("#copyMsg").textContent = "근거를 복사했어요."; }
  catch { $("#copyMsg").textContent = "복사하지 못했어요. 브라우저 권한을 확인해 주세요."; }
});
$("#addCart").addEventListener("click", async () => {
  const f = S.lastFee; if (!f || f.conflict) return;
  if (S.cartRegion && S.cartRegion !== f.basis.region) S.cart = [];
  S.cartRegion = f.basis.region;
  const per = f.basis.decided_by && f.basis.decided_by.startsWith("단가");
  for (let i = 0; i < (f.quantity || 1); i++)
    S.cart.push({ item: f.basis.item, spec: f.basis.spec, measure: per ? S.answers.amount : null, label: `${f.basis.item} · ${f.basis.spec}` });
  await renderCart();
  $("#addCart").hidden = true;
});
async function renderCart() {
  $("#cartCard").hidden = S.cart.length === 0;
  if (!S.cart.length) return;
  try {
    const r = await api("/api/fee/total", { method: "POST", body: JSON.stringify({ region: S.cartRegion, entries: S.cart }) });
    $("#cart").innerHTML = r.results.map((x, i) => `<li>${esc(S.cart[i].label)} — ${esc(x.fee_text)}</li>`).join("");
    $("#cartTotal").textContent = `합계 ${r.total_text}`;
    $("#cartNote").textContent = r.unconfirmed ? `금액 확인이 필요한 ${r.unconfirmed}개는 합계에서 뺐어요.` : `${S.cartRegion} 기준 예상 합계예요.`;
  } catch (e) { $("#cartNote").textContent = e.message; }
}
$("#cartClear").addEventListener("click", () => { S.cart = []; S.cartRegion = null; renderCart(); });

$("#again").addEventListener("click", () => { S.item = null; document.querySelectorAll(".chip").forEach((c) => c.classList.remove("on")); $("#start").disabled = true; go(1); });

loadRegions().then(() => go(1)).catch((e) => { $("#itemErr").textContent = e.message; });
