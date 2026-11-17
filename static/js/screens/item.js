// 품목 확인 화면: AI 후보와 판단 근거를 보고 품목을 확정한다. 못 찾으면 직접 검색한다.
// 화면·AI 후보·가전 무상수거 안내: 기능① 박상훈 님 원본
// 이름·설명 검색('3인용 쇼파 2개' → 소파, 3인용·2개 미리 채움)과 목록에서 고르기: 기능② 강문정
import { getSpecItems, parseDescription, resolveItem } from '../api.js';
import { h } from '../dom.js';
import { go } from '../nav.js';
import { clearSpecStep, regionText, state } from '../state.js';

const FREE_PICKUP_GUIDE = 'https://www.15990903.or.kr/portal/cnts/userGuide.do';

export function renderItem() {
  const recognition = state.recognition;
  const candidates = recognition?.recognized ? recognition.candidates : [];
  // 처음에는 AI의 1순위 후보를 골라 둔다. 이전에 확정한 품목이 있으면 그것을 유지한다.
  // 선택값: { key, name, source: 'ai'|'search'|'list', ref }
  let selected = state.itemKey
    ? { key: state.itemKey, name: state.item, source: state.itemSource, ref: state.itemRef }
    : candidates.length ? { key: 'ai:' + candidates[0].item, name: candidates[0].item, source: 'ai', ref: null } : null;
  let parsed = null;  // 설명 읽기 결과

  const nextButton = h('button', { class: 'btn btn-primary', type: 'button', id: 'itemNext', onclick: confirm }, '이 품목으로 계속');
  const message = h('p', { class: 'notice notice-error', role: 'alert', hidden: true });
  const applianceNotice = h('p', { class: 'notice notice-info', hidden: true },
    '가전제품은 폐가전 무상방문수거 대상일 수 있어요. 유료로 신고하기 전에 ',
    h('a', { href: FREE_PICKUP_GUIDE, target: '_blank', rel: 'noopener' }, '이용 기준(새 창)'),
    '을 먼저 확인해 보세요.',
  );

  function select(next) {
    selected = next;
    for (const input of document.querySelectorAll('input[name="item"]')) input.checked = input.value === selected?.key;
    if (next.source !== 'list') listSelect.value = '';
    refresh();
  }

  function refresh() {
    nextButton.disabled = !selected;
    const picked = candidates.find((c) => 'ai:' + c.item === selected?.key);
    // 서버가 알려준 가전 여부는 1순위 후보 기준이므로, 1순위를 골랐을 때만 안내한다.
    applianceNotice.hidden = !(recognition?.is_appliance && picked === candidates[0]);
  }

  async function confirm() {
    if (!selected) return;
    message.hidden = true;
    let ref = selected.ref;
    let code = ref?.standard_code || null;
    try {
      // ①의 후보는 수수료표 원문 품목명이라, ②가 질문할 수 있게 지역 품목 번호로 바꾼다
      if (selected.source === 'ai' && !ref) {
        const found = await resolveItem(state.regionId, selected.name);
        ref = { local_item_id: found.local_item_id };
        code = found.standard_code;
      }
    } catch (error) {
      message.textContent = error.message;
      message.hidden = false;
      return;
    }
    if (state.itemKey !== selected.key) clearSpecStep(); // 품목이 바뀌면 뒤 단계는 다시
    state.itemKey = selected.key;
    state.item = selected.name;
    state.itemSource = selected.source;
    state.itemRef = ref;
    state.itemCode = code;  // 표준 품목 코드 (④ 체크리스트 품목 연결에 씀)
    // 설명에서 읽은 크기·개수는 검색 결과에서 고른 품목에만 쓴다
    const fromSearch = selected.source === 'search';
    state.description = fromSearch ? state.searchQuery : '';
    state.quantity = fromSearch && parsed?.quantity ? parsed.quantity : 1;
    go('spec');
  }

  const radio = (option) =>
    h('input', {
      type: 'radio', name: 'item', value: option.key,
      checked: selected?.key === option.key,
      onchange: () => select(option),
    });

  // --- AI 후보 ---
  const candidateOption = (candidate) =>
    h('label', { class: 'option' },
      radio({ key: 'ai:' + candidate.item, name: candidate.item, source: 'ai', ref: null }),
      h('span', { class: 'option-title' },
        candidate.item,
        candidate.category && h('span', { class: 'badge' }, candidate.category),
        h('span', { class: `badge ${candidate.confidence === '높음' ? 'badge-high' : ''}` }, `AI 확신 ${candidate.confidence}`),
      ),
      candidate.evidence.length > 0 && h('div', { class: 'option-body' },
        h('span', { class: 'label' }, '이렇게 판단했어요'),
        h('ul', {}, candidate.evidence.map((text) => h('li', {}, text))),
      ),
    );

  // --- 직접 검색 (②: 비슷한 말·설명 읽기) ---
  const searchInput = h('input', { id: 'search', type: 'search', value: state.searchQuery, placeholder: '예: 소파, 3인용 쇼파 2개', autocomplete: 'off' });
  const readNote = h('p', { class: 'notice notice-info', hidden: true });
  const searchResults = h('div', { class: 'options', role: 'status' });
  let allItems = null;  // 지역 품목 전체 (목록에서 고르기)

  const stdOption = (s) => ({ key: 'std:' + s.code, name: s.name, source: 'search', ref: { standard_code: s.code } });
  const locOption = (u) => ({ key: 'loc:' + u.local_item_id, name: u.name, source: 'search', ref: { local_item_id: u.local_item_id } });
  const optionRow = (option) => h('label', { class: 'option' }, radio(option), h('span', { class: 'option-title' }, option.name));

  async function runSearch(event) {
    event?.preventDefault();
    const query = searchInput.value.trim();
    if (!query) return;
    state.searchQuery = query;
    readNote.hidden = true;
    let found = { standard: [], local_only: [] };
    let notFound = '';
    const [items, reading] = await Promise.all([
      getSpecItems(state.regionId, query).catch((error) => { notFound = error.message; return null; }),
      parseDescription(state.regionId, query).catch(() => null),
    ]);
    if (items) found = items;
    parsed = reading;
    const options = [...found.standard.map(stdOption), ...found.local_only.map(locOption)];
    // 설명에서 알아낸 품목을 맨 앞에 두고 골라 둔다 (예: '3인용 쇼파 2개' → 소파)
    const code = parsed?.items?.[0];
    if (code) {
      let known = options.find((o) => o.key === 'std:' + code);
      if (known) options.splice(options.indexOf(known), 1);
      else known = (await loadAllItems()).standard.filter((s) => s.code === code).map(stdOption)[0];
      if (known) options.unshift(known);
    }
    const parts = [...(parsed?.labels ?? []), ...(parsed?.quantity ? [`${parsed.quantity}개`] : [])];
    if (parts.length && options.length) {
      readNote.textContent = `설명에서 읽은 내용: ${parts.join(' · ')} — 규격 질문에 바로 반영돼요.`;
      readNote.hidden = false;
    }
    searchResults.replaceChildren(
      ...(options.length
        ? options.map(optionRow)
        : [h('p', { class: 'small' }, notFound || `'${query}'에 해당하는 품목이 ${regionText()} 수수료표에 없어요. 다른 이름으로 찾아보세요.`)])
    );
    // 직접 검색했거나 아직 고른 것이 없을 때만 골라 둔다 (돌아왔을 때 사용자가 고른 것을 덮지 않게)
    if (options.length && (code || options.length === 1) && (event || !selected)) select(options[0]);
  }

  // --- 목록에서 고르기 ---
  const listSelect = h('select', {
    id: 'itemList',
    onchange: () => {
      const opt = listSelect.selectedOptions[0];
      if (!listSelect.value) return;
      const [kind, id] = listSelect.value.split(':');
      select({ key: listSelect.value, name: opt.textContent, source: 'list',
               ref: kind === 'std' ? { standard_code: id } : { local_item_id: Number(id) } });
    },
  }, h('option', { value: '' }, '불러오는 중…'));

  async function loadAllItems() {
    if (!allItems) allItems = await getSpecItems(state.regionId);
    return allItems;
  }
  loadAllItems()
    .then((d) => {
      listSelect.replaceChildren(
        h('option', { value: '' }, '선택하세요'),
        h('optgroup', { label: '품목' }, d.standard.map((s) => h('option', { value: 'std:' + s.code }, s.name))),
        d.local_only.length > 0 && h('optgroup', { label: '그 밖의 우리 지역 품목' },
          d.local_only.map((u) => h('option', { value: 'loc:' + u.local_item_id }, u.name))),
      );
      if (selected?.source === 'list') listSelect.value = selected.key;
    })
    .catch(() => listSelect.replaceChildren(h('option', { value: '' }, '목록을 불러오지 못했어요')));

  if (state.searchQuery) runSearch();

  refresh();

  const choices = h('div', { class: 'stack' },
    recognition && !recognition.recognized && h('p', { class: 'notice notice-warn', role: 'status' }, recognition.message),

    candidates.length > 0 && h('section', { class: 'card' },
      h('h2', {}, 'AI가 찾은 후보'),
      h('div', { class: 'options' }, candidates.map(candidateOption)),
      applianceNotice,
      h('p', { class: 'small' }, 'AI의 판단은 틀릴 수 있어요. 근거를 보고 직접 확인해 주세요.'),
    ),

    h('section', { class: 'card' },
      h('h2', {}, candidates.length ? '찾는 품목이 없나요?' : '품목 이름으로 찾기'),
      h('form', { class: 'row', onsubmit: runSearch },
        h('label', { class: 'visually-hidden', htmlFor: 'search' }, '품목 이름 또는 설명'),
        h('div', { class: 'grow' }, searchInput),
        h('button', { class: 'btn', type: 'submit', id: 'searchBtn' }, '검색'),
      ),
      readNote,
      searchResults,
      h('label', { class: 'field' }, `또는 ${regionText()} 품목 목록에서 고르기`, listSelect),
    ),

    message,
    h('div', { class: 'actions' },
      h('button', { class: 'btn', type: 'button', onclick: () => go('home') }, '이전'),
      nextButton,
    ),
  );

  const title = h('h1', {}, candidates.length ? '이 품목이 맞나요?' : '품목을 골라 주세요');

  // 사진이 없으면(이름으로 찾기) 한 단으로, 있으면 왼쪽에 사진을 크게 보여 근거와 견주어 볼 수 있게 한다.
  if (!state.photoUrl) return h('div', { class: 'screen narrow' }, title, choices);

  return h('div', { class: 'screen' },
    title,
    h('div', { class: 'cols cols-photo' },
      h('section', { class: 'card sticky' },
        h('h2', {}, '올린 사진'),
        h('img', { class: 'photo-large', src: state.photoUrl, alt: '올린 사진' }),
        h('p', { class: 'small' }, `${regionText()} 수수료표에 있는 품목 중에서 찾았어요.`),
      ),
      choices,
    ),
  );
}
