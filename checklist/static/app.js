// 배출 전 체크리스트·신청 연결 화면 (웹)
// 위에서 자치구·사는 곳·물건을 고르면 같은 페이지 아래에 확인 목록이 나온다.
// 다른 기능(품목 인식·수수료 산정)에서 넘어올 때는 주소에 값을 붙이면 미리 선택된다.
//   예) /?district=마포구&item=fridge&housing=apartment

/* API-START */
async function getOptions() {
  return (await fetch("/api/options")).json();
}
async function getChecklist(query) {
  const res = await fetch("/api/checklist?" + new URLSearchParams(query));
  const data = await res.json();
  if (!res.ok) throw new Error(data.error);
  return data;
}
/* API-END */

const $ = (id) => document.getElementById(id);
const state = { district: "", item: "", housing: "house" };
const checked = new Map(); // "구|품목|주거" -> Set(확인한 항목 id)
let opts = null;
let tab = "";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  node.append(...children.filter((c) => c !== null && c !== ""));
  return node;
}

/* ---------- 고르기 ---------- */
async function init() {
  try {
    opts = await getOptions();
  } catch {
    $("result").replaceChildren(el("p", { class: "error" }, "목록을 불러오지 못했습니다. 서버(app.py)가 켜져 있는지 확인하세요."));
    return;
  }
  const params = new URLSearchParams(location.search);
  if (opts.districts.includes(params.get("district"))) state.district = params.get("district");
  if (opts.items.some((i) => i.id === params.get("item"))) state.item = params.get("item");
  if (opts.housing.some((h) => h.id === params.get("housing"))) state.housing = params.get("housing");
  const chosen = opts.items.find((i) => i.id === state.item);
  tab = chosen ? chosen.category : opts.categories[0].id;

  for (const name of opts.districts) $("district").append(el("option", { value: name }, name));
  $("district").value = state.district;
  $("district").addEventListener("change", (e) => {
    state.district = e.target.value;
    $("notice").hidden = true;
    $("districtPill").classList.remove("need");
    refresh();
  });

  for (const h of opts.housing) {
    const b = el("button", { type: "button", class: "pill" }, h.name);
    b.dataset.id = h.id;
    b.addEventListener("click", () => { state.housing = h.id; drawHousing(); refresh(); });
    $("housing").append(b);
  }
  drawHousing();

  for (const cat of opts.categories) {
    const b = el("button", { type: "button", class: "tab", role: "tab" }, cat.name);
    b.dataset.id = cat.id;
    b.addEventListener("click", () => { tab = cat.id; $("q").value = ""; drawItems(); });
    $("tabs").append(b);
  }
  $("q").addEventListener("input", drawItems);
  drawItems();
  refresh();
}

function drawHousing() {
  for (const b of $("housing").children) {
    b.classList.toggle("on", b.dataset.id === state.housing);
    b.setAttribute("aria-pressed", b.dataset.id === state.housing);
  }
}

function drawItems() {
  const q = $("q").value.trim();
  // 검색어가 있으면 종류와 상관없이 전체에서 찾는다
  const list = q
    ? opts.items.filter((i) => i.name.includes(q))
    : opts.items.filter((i) => i.category === tab);
  // 검색 결과가 없으면 ‘그 밖의 물건’ 버튼을 대신 보여 준다
  const shown = list.length ? list : opts.items.filter((i) => i.id === "etc");
  for (const b of $("tabs").children) b.setAttribute("aria-selected", !q && b.dataset.id === tab);
  $("items").replaceChildren(...shown.map((it) => {
    const b = el("button", { type: "button", class: "chip" }, it.name);
    b.setAttribute("aria-pressed", it.id === state.item);
    b.addEventListener("click", () => pick(it.id));
    return b;
  }));
  $("none").hidden = list.length > 0;
}

async function pick(itemId) {
  state.item = itemId;
  drawItems();
  if (!state.district) {
    $("notice").hidden = false;
    $("districtPill").classList.add("need");
    $("district").focus();
    return;
  }
  await refresh();
  $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- 확인 목록 ---------- */
async function refresh() {
  if (!state.district || !state.item) return;
  try {
    render(await getChecklist(state));
  } catch (e) {
    $("result").replaceChildren(el("p", { class: "error" }, e.message));
  }
}

function render(data) {
  const key = [data.district, data.item.id, data.housing].join("|");
  if (!checked.has(key)) checked.set(key, new Set());
  const done = checked.get(key);
  const total = data.stages.reduce((n, s) => n + s.entries.length, 0);

  const count = el("p", { class: "count" });
  const fill = el("i");
  const left = el("p", { class: "left" });
  const apply = el("a", { class: "apply", href: data.apply.url, target: "_blank", rel: "noopener noreferrer" }, data.apply.label);

  function update() {
    const remaining = total - done.size;
    count.textContent = `${total}개 중 ${done.size}개 확인`;
    fill.style.width = `${(done.size / total) * 100}%`;
    left.textContent = remaining ? `확인할 항목이 ${remaining}개 남았습니다` : "모두 확인했습니다. 이제 신청하세요";
    apply.classList.toggle("waiting", remaining > 0);
  }

  const cards = data.stages.map((stage, i) => {
    const card = el("section", { class: "card" },
      el("h2", {}, el("span", { class: "num" }, String(i + 1)), stage.name));
    for (const entry of stage.entries) {
      const box = el("input", { type: "checkbox", checked: done.has(entry.id) });
      box.addEventListener("change", () => {
        box.checked ? done.add(entry.id) : done.delete(entry.id);
        update();
      });
      const row = el("label", { class: "check" }, box, el("span", { class: "text" }, entry.text));
      if (entry.why) row.append(el("span", { class: "why" }, entry.why));
      if (entry.local) row.append(el("span", { class: "local known" }, `${data.district} 기준: ${entry.local}`));
      else if (entry.needs_local_check) row.append(el("span", { class: "local unknown" }, `${data.district} 기준은 구청 안내에서 확인`));
      card.append(row);
    }
    return card;
  });

  const go = el("div", { class: "go" }, left, apply);
  if (data.apply.hint) go.append(el("p", { class: "hint" }, data.apply.hint));

  const basis = el("p", { class: "basis" },
    `안내 기준일 ${data.basis.updated}` +
    (data.basis.district_verified_on ? `, ${data.district} 정보 확인일 ${data.basis.district_verified_on}` : "") +
    ". 출처: ");
  data.basis.sources.forEach((s, i) => {
    if (i) basis.append(", ");
    basis.append(el("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.name));
  });

  update();
  $("result").replaceChildren(
    el("div", { class: "head" },
      el("h2", { class: "title" }, `${data.district} ${data.item.name} 내놓기 전에`),
      count, el("div", { class: "bar" }, fill)),
    el("div", { class: "cards" }, ...cards),
    go,
    basis,
  );
}

init();
