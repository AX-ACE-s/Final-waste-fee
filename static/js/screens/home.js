// 첫 화면: 배출 지역 → 사진(또는 이름·설명)으로 품목 찾기 시작
// 화면·사진 올리기: 기능① 박상훈 님 원본
// 배출 지역(시·도/시·군·구 + 주소 검색): 기능② 강문정 (원본의 '연결 예정' 자리를 채움)
import { getSpecRegions, recognizePhoto, searchAddress } from '../api.js';
import { h } from '../dom.js';
import { prepareImage } from '../image.js';
import { go } from '../nav.js';
import { clearItemStep, region, setPhoto, setRegion, state } from '../state.js';

let regionsCache = null;  // [{ sido, sigungu: [{ id, sigungu, manager_org }] }]

export function renderHome() {
  // --- 배출 지역 ---
  const sidoSelect = h('select', { id: 'sido', onchange: () => fillSigungu(sidoSelect.value) });
  const sigunguSelect = h('select', {
    id: 'sigungu',
    onchange: () => { if (sigunguSelect.value) chooseRegion(Number(sigunguSelect.value)); },
  });
  const chosen = h('p', { class: 'small', id: 'regionChosen', hidden: true });
  const addrInput = h('input', { id: 'addr', type: 'search', placeholder: '주소나 동네 이름 (예: 해운대구 중동)', autocomplete: 'off' });
  const addrList = h('ul', { class: 'addr-list', 'aria-live': 'polite' });

  const placeholder = (text) => h('option', { value: '' }, text);

  function fillSigungu(sido, selectedId) {
    const r = regionsCache?.find((x) => x.sido === sido);
    sigunguSelect.replaceChildren(placeholder(r ? '선택하세요' : '시·도를 먼저 고르세요'),
      ...(r ? r.sigungu.map((g) => h('option', { value: String(g.id) }, g.sigungu)) : []));
    sigunguSelect.value = selectedId ? String(selectedId) : '';
  }

  function regionById(id) {
    for (const r of regionsCache ?? []) for (const g of r.sigungu) if (g.id === id) return { ...g, sido: r.sido };
    return null;
  }

  function chooseRegion(id) {
    const g = regionById(id);
    if (!g) return;
    if (state.regionId !== g.id) clearItemStep();
    setRegion(g);
    sidoSelect.value = g.sido;
    fillSigungu(g.sido, g.id);
    addrList.replaceChildren();
    chosen.textContent = `${state.regionName} 수수료표로 안내해요` + (g.manager_org ? ` · 관리기관 ${g.manager_org}` : '');
    chosen.hidden = false;
    showMessage('');
  }

  const loadRegions = regionsCache ? Promise.resolve(regionsCache) : getSpecRegions();
  loadRegions
    .then((data) => {
      regionsCache = data;
      sidoSelect.replaceChildren(placeholder('선택하세요'), ...data.map((r) => h('option', { value: r.sido }, r.sido)));
      if (state.regionId) chooseRegion(state.regionId);
      else fillSigungu('');
    })
    .catch((error) => showMessage(error.message));

  // 주소 검색: 가진 지역 목록에서 먼저 찾고(예: '강남구'), 행정안전부 도로명주소 검색 결과를 덧붙인다
  async function searchAddr(event) {
    event.preventDefault();
    const q = addrInput.value.trim();
    addrList.replaceChildren();
    if (!q) return addrInput.focus();
    const nq = q.replace(/\s+/g, '');
    const local = nq.length < 2 ? [] : (regionsCache ?? [])
      .flatMap((r) => r.sigungu.map((g) => ({ ...g, sido: r.sido })))
      .filter((g) => (g.sido + g.sigungu).replace(/\s+/g, '').includes(nq)).slice(0, 8);
    const rows = local.map((g) => ({ label: `${g.sido} ${g.sigungu}`, region_id: g.id, region: true }));
    const render = (hint) => addrList.replaceChildren(
      ...rows.map((row) => {
        const ok = row.supported !== false;
        return h('li', { class: ok ? '' : 'no', onclick: ok ? () => chooseRegion(row.region_id) : null },
          row.region ? [h('strong', {}, row.label), h('span', { class: 'small' }, ' 지역으로 선택')] : row.label,
          ok ? null : h('span', { class: 'small' }, ' · 이 지역 수수료 데이터는 아직 없어요'));
      }),
      hint ? h('li', { class: 'no' }, hint) : null,
    );
    render(local.length ? '' : '찾는 중이에요…');
    try {
      const found = await searchAddress(q);
      found.forEach((r) => rows.push({ label: r.road_addr, region_id: r.region_id, supported: r.supported }));
      render(rows.length ? '' : '검색 결과가 없어요. 동 이름이나 건물명을 함께 입력해 보세요.');
    } catch (error) {
      render(local.length ? '더 정확히 찾으려면 동 이름이나 건물명까지 입력해 보세요.' : error.message);
    }
  }

  // --- 사진 ---
  const preview = h('img', { class: 'photo-preview', alt: '고른 사진 미리보기', hidden: !state.photoUrl, src: state.photoUrl || null });
  const findButton = h('button', { class: 'btn btn-primary btn-block', type: 'button', hidden: !state.photo, onclick: findByPhoto },
    '이 사진으로 품목 찾기');
  const message = h('p', { class: 'notice notice-error', role: 'alert', hidden: true });
  const loading = h('p', { class: 'loading', role: 'status', hidden: true },
    h('span', { class: 'spinner', 'aria-hidden': 'true' }), '사진을 살펴보고 있어요…');

  function showMessage(text) {
    message.textContent = text;
    message.hidden = !text;
  }

  async function usePhoto(file) {
    if (!file) return;
    showMessage('');
    try {
      setPhoto(await prepareImage(file));
      preview.src = state.photoUrl;
      preview.hidden = false;
      findButton.hidden = false;
      dropTitle.textContent = '다른 사진으로 바꾸기';
      findButton.focus();
    } catch (error) {
      showMessage(error.message);
    }
  }

  async function findByPhoto() {
    if (!state.regionId) return showMessage('배출 지역을 먼저 골라 주세요.');
    showMessage('');
    loading.hidden = false;
    findButton.disabled = true;
    clearItemStep();
    try {
      state.recognition = await recognizePhoto(state.photo, region());
      go('item');
    } catch (error) {
      showMessage(error.message);
    } finally {
      loading.hidden = true;
      findButton.disabled = false;
    }
  }

  // 사진 올리는 곳: 누르면 파일 선택 창이 열리고, PC에서는 사진을 끌어다 놓을 수도 있다.
  // (휴대폰 브라우저에서는 같은 버튼으로 바로 촬영도 할 수 있다)
  const fileInput = h('input', {
    id: 'photoFile', class: 'visually-hidden', type: 'file', accept: 'image/*',
    onchange: (event) => {
      usePhoto(event.target.files[0]);
      event.target.value = ''; // 같은 사진을 다시 골라도 반응하도록
    },
  });
  const dropTitle = h('strong', {}, state.photo ? '다른 사진으로 바꾸기' : '사진 올리기');
  const dropzone = h('label', {
    class: 'dropzone', htmlFor: 'photoFile',
    ondragover: (event) => { event.preventDefault(); dropzone.classList.add('dragging'); },
    ondragleave: () => dropzone.classList.remove('dragging'),
    ondrop: (event) => {
      event.preventDefault();
      dropzone.classList.remove('dragging');
      usePhoto(event.dataTransfer.files[0]);
    },
  }, fileInput, dropTitle, h('span', { class: 'small' }, '눌러서 고르거나, 사진을 여기에 끌어다 놓으세요'));

  // --- 이름·설명으로 찾기 (검색은 ②의 설명 읽기) ---
  const nameInput = h('input', { id: 'itemName', type: 'search', placeholder: '예: 소파, 3인용 쇼파 2개', autocomplete: 'off' });

  function findByName(event) {
    event.preventDefault();
    const query = nameInput.value.trim();
    if (!query) return nameInput.focus();
    if (!state.regionId) return showMessage('배출 지역을 먼저 골라 주세요.');
    clearItemStep();
    setPhoto(null);
    state.searchQuery = query;
    go('item');
  }

  return h('div', { class: 'screen' },
    h('div', { class: 'stack' },
      h('h1', {}, '버릴 물건 사진 한 장으로 품목과 수수료를 확인하세요'),
      h('p', { class: 'lead' }, 'AI가 사진에서 품목 후보와 그렇게 본 이유를 알려드리고, 우리 동네 기준에 맞는 수수료까지 안내합니다.'),
    ),

    h('div', { class: 'cols home-grid' },
      h('section', { class: 'card area-region' },
        h('h2', {}, '1. 어디에서 배출하시나요?'),
        h('div', { class: 'row' },
          h('label', { class: 'field' }, '시·도', sidoSelect),
          h('label', { class: 'field' }, '시·군·구', sigunguSelect),
        ),
        h('form', { class: 'row', onsubmit: searchAddr },
          h('label', { class: 'visually-hidden', htmlFor: 'addr' }, '주소 또는 동네 이름'),
          h('div', { class: 'grow' }, addrInput),
          h('button', { class: 'btn', type: 'submit', id: 'addrBtn' }, '주소로 찾기'),
        ),
        addrList,
        chosen,
      ),

      h('section', { class: 'card area-photo' },
        h('h2', {}, '2. 버릴 물건 사진을 올려 주세요'),
        h('p', { class: 'small' }, '물건 하나가 전체가 보이도록 찍은 사진이 좋아요.'),
        dropzone,
        preview,
        findButton,
        loading,
        message,
        h('p', { class: 'small' }, '사진은 저장하지 않으며, 품목을 알아보기 위해 AI 서비스로 전송됩니다. 얼굴이나 주소가 찍히지 않게 해 주세요.'),
      ),

      h('section', { class: 'card area-name' },
        h('h2', {}, '사진이 없다면 이름으로 찾기'),
        h('form', { class: 'row', onsubmit: findByName },
          h('label', { class: 'visually-hidden', htmlFor: 'itemName' }, '품목 이름 또는 설명'),
          h('div', { class: 'grow' }, nameInput),
          h('button', { class: 'btn', type: 'submit', id: 'nameBtn' }, '찾기'),
        ),
        h('p', { class: 'small' }, '크기나 개수까지 쓰면 규격 질문을 줄여 드려요.'),
      ),
    ),
  );
}
