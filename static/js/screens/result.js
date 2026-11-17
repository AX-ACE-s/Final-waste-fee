// 수수료·배출 안내 화면
// 화면 틀과 '연결 예정' 자리: 기능① 박상훈 님 원본
// 예상 수수료·산정 근거·다른 규격 비교·조례 링크·근거 복사·합계: 기능③ 정하영 (②가 넘긴 fee_detail)
// 배출 전 체크리스트·신청 연결: 기능④ 지윤 (별도 페이지 /checklist/ 로 이동. 구청별 안내는 서울 25개 자치구)
// 추천 배출일·문의 자료: 아직 담당 기능 없음 → '연결 예정'
//
// 받는 값: state.estimate (②의 확정 결과 + ③ fee_detail), state.sido·sigungu, state.itemCode
// 주의: 금액은 ③이 공공데이터에서 계산한 값만 보여 준다. 지어내지 않는다.
import { checklistLink, feeTotal, getChecklist } from '../api.js';
import { h } from '../dom.js';
import { go } from '../nav.js';
import { resetAll, state } from '../state.js';

const PENDING = '연결 예정';
const won = (n) => Number(n).toLocaleString('ko-KR') + '원';
const slot = (text) => h('div', { class: 'slot' }, h('span', { class: 'slot-tag' }, PENDING), text);
const rows = (pairs) => pairs.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]);

export function renderResult() {
  const r = state.estimate;
  const f = r.fee_detail;

  // ---------------------------------------------------------------- 예상 수수료 (③)
  const feeCard = f ? feeFromDetail(r, f) : feeFallback(r);

  // ---------------------------------------------------------------- 담은 품목 (③ 합계)
  const cartList = h('ul', { class: 'cart' });
  const cartTotal = h('p', { class: 'total' });
  const cartCard = h('section', { class: 'card', id: 'cartCard', hidden: true },
    h('div', { class: 'card-head' }, h('h2', {}, '담은 품목'),
      h('button', { class: 'btn btn-text', type: 'button', onclick: () => { state.cart = []; state.cartRegion = ''; drawCart(); } }, '비우기')),
    cartList, cartTotal);

  async function drawCart() {
    cartCard.hidden = state.cart.length === 0;
    cartList.replaceChildren(...state.cart.map((c) => h('li', {}, `${c.item} · ${c.spec} · ${c.fee_text}`)));
    if (!state.cart.length) return;
    const t = await feeTotal(state.cartRegion, state.cart.map((c) => ({ item: c.item, spec: c.spec, measure: c.measure })));
    cartTotal.textContent = '합계 ' + t.total_text + (t.unconfirmed ? ` (금액 확인이 필요한 ${t.unconfirmed}건 제외)` : '');
  }
  drawCart().catch(() => {});

  function addToCart(button) {
    if (!f || f.conflict || f.fee === null) return;
    if (state.cartRegion && state.cartRegion !== f.basis.region) state.cart = [];
    state.cartRegion = f.basis.region;
    const perUnit = (f.basis.decided_by || '').startsWith('단가');
    for (let i = 0; i < (f.quantity || 1); i++) {
      state.cart.push({ item: f.basis.item, spec: f.basis.spec, measure: perUnit ? state.answers?.amount : null, fee_text: f.fee_text });
    }
    state.added = state.estimate;  // 같은 결과를 두 번 담지 않게
    button.disabled = true;
    button.textContent = '담았어요';
    drawCart().catch(() => {});
  }

  // ---------------------------------------------------------------- 배출 전 체크리스트·신청 (④)
  const checklistBody = h('div', { class: 'stack-sm' }, h('p', { class: 'small' }, '불러오는 중…'));
  const applyBody = h('div', { class: 'stack-sm' },
    h('button', { class: 'btn btn-block', type: 'button', disabled: true }, `공식 신청 페이지로 이동 (${PENDING})`));

  checklistLink(state.sido, state.sigungu, state.itemCode)
    .then(async (link) => {
      checklistBody.replaceChildren(
        h('p', { class: 'small' }, link.available
          ? `${state.sigungu} · ${link.item_name} 기준으로 신고 전·준비·내놓기 단계별 확인 항목을 모아 두었어요.`
          : link.reason),
        h('a', { class: 'btn btn-primary btn-block', id: 'toChecklist', href: link.url }, '배출 전 체크리스트 보기'),
      );
      if (!link.available) return;
      const cl = await getChecklist(state.sigungu, link.item);
      applyBody.replaceChildren(
        h('a', { class: 'btn btn-block', href: cl.apply.url, target: '_blank', rel: 'noopener noreferrer' }, cl.apply.label),
        cl.apply.hint && h('p', { class: 'small' }, cl.apply.hint),
      );
    })
    .catch((error) => checklistBody.replaceChildren(h('p', { class: 'small' }, error.message)));

  function startOver() {
    // 지역과 담은 품목은 그대로 두고 다음 물건을 확인한다
    resetAll();
    go('home');
  }

  return h('div', { class: 'screen' },
    h('h1', {}, '수수료와 배출 방법'),

    h('div', { class: 'cols' },
      h('div', { class: 'stack' }, feeCard, cartCard),

      h('div', { class: 'stack' },
        h('section', { class: 'card' },
          h('h2', {}, '배출 전 체크리스트'),
          checklistBody,
        ),
        h('section', { class: 'card' },
          h('h2', {}, '추천 배출일'),
          slot('날씨 예보와 내 일정을 반영한 배출일 추천'),
        ),
        h('section', { class: 'card' },
          h('h2', {}, '신청과 문의'),
          applyBody,
          h('button', { class: 'btn btn-block', type: 'button', disabled: true }, `미수거·지연 문의 자료 만들기 (${PENDING})`),
        ),
      ),
    ),

    h('div', { class: 'actions' },
      h('button', { class: 'btn', type: 'button', onclick: () => go('spec') }, '이전'),
      h('button', { class: 'btn btn-primary', type: 'button', id: 'startOver', onclick: startOver }, '다른 물건 확인하기'),
    ),
  );

  // ③의 계산 결과 그대로: 금액·한 줄 요약·주의 문구는 바로, 산정 근거는 접어 둔다
  function feeFromDetail(res, d) {
    const qty = d.quantity || 1;
    const b = d.basis;
    const copyMsg = h('span', { class: 'small', role: 'status' });
    const addButton = h('button', { class: 'btn btn-primary', type: 'button', id: 'addCart',
      hidden: Boolean(d.conflict) || d.fee === null, onclick: (e) => addToCart(e.currentTarget) }, '목록에 담기');
    if (state.added === state.estimate) { addButton.disabled = true; addButton.textContent = '담았어요'; }

    async function copyEvidence() {
      try {
        await navigator.clipboard.writeText(d.copy_text);
      } catch { // 클립보드 권한이 없거나 http 환경이면 임시 입력칸으로 복사
        const ta = h('textarea', { value: d.copy_text });
        ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.append(ta); ta.select();
        const ok = document.execCommand('copy');
        ta.remove();
        if (!ok) { copyMsg.textContent = '복사하지 못했어요. 직접 선택해 복사해 주세요.'; return; }
      }
      copyMsg.textContent = '복사했어요.';
    }

    const basisRows = [['지역', b.region], ['품목', b.item], ['분류', b.category || '-'], ['규격', `${b.spec} (${b.decided_by})`],
      ...(res.result?.inputs?.length ? [['입력 내용', res.result.inputs.join(' · ')]] : []),
      ...(b.calc_note ? [['계산', b.calc_note]] : []),
      ['데이터 기준일', b.data_date], ['제공기관', b.provider]];
    const alts = d.alternatives || [];
    const ordin = b.ordinance_links || [];

    return h('section', { class: 'card', id: 'feeCard' },
      h('h2', {}, '예상 수수료'),
      h('p', { class: `fee ${d.conflict ? 'pending' : 'ready'}`, id: 'fee' }, qty > 1 ? d.total_text : d.fee_text),
      qty > 1 && d.fee !== null && h('p', { class: 'small' }, `개당 ${d.fee_text} × ${qty}개`),
      h('p', { class: 'fee-line' }, `${b.region} · ${b.item} ${b.spec}`, ' ',
        h('span', { class: 'small' }, `· ${b.data_date} 기준 · 출처 공공데이터포털`)),
      d.boundary_warning && h('p', { class: 'notice notice-warn' }, d.boundary_warning),
      d.conflict && h('p', { class: 'notice notice-error' }, d.notice + ' 등록된 금액: ' +
        d.candidates.map((c) => `${c.fee_text}(${c.data_date}${c.category ? ', ' + c.category : ''})`).join(' / ')),
      !d.conflict && h('p', { class: 'small' }, d.notice),
      h('div', { class: 'row' },
        addButton,
        d.copy_text && h('button', { class: 'btn', type: 'button', id: 'copyBasis', onclick: copyEvidence }, '근거 복사'),
        copyMsg,
      ),
      h('details', { class: 'more', id: 'more' },
        h('summary', {}, '산정 근거 자세히 보기'),
        d.explanation && h('p', { class: 'explain' }, d.explanation),
        h('dl', { class: 'summary basis' }, rows(basisRows),
          h('dt', {}, '출처'), h('dd', {}, h('a', { href: b.source_url, target: '_blank', rel: 'noopener' }, b.source))),
        alts.length > 0 && h('div', {},
          h('h3', { class: 'sub-title' }, '다른 규격과 비교'),
          h('table', { class: 'alt' },
            h('thead', {}, h('tr', {}, h('th', {}, '규격'), h('th', {}, '수수료'), h('th', {}, '차이'))),
            h('tbody', {}, alts.map((a) => h('tr', { class: a.conflict ? 'conf' : '' },
              h('td', {}, a.spec), h('td', {}, a.fee_text),
              h('td', { class: a.diff > 0 ? 'up' : a.diff < 0 ? 'down' : '' }, a.diff_text || '-')))))),
        ordin.length > 0 && h('div', {},
          h('h3', { class: 'sub-title' }, '조례 별표 원문 (법제처)'),
          h('ul', { class: 'links' }, ordin.map((l) => h('li', {}, h('a', { href: l.url, target: '_blank', rel: 'noopener noreferrer' }, l.name)))),
          h('p', { class: 'small' }, '금액을 직접 대조한 것이 아니라, 지자체 조례의 수수료 표 원문으로 연결하는 링크예요.')),
      ),
    );
  }

  // ③과 연결하지 못한 경우(드묾): ②의 결과로 최소한만 보여 준다
  function feeFallback(res) {
    if (res.status === 'needs_confirmation') {
      return h('section', { class: 'card', id: 'feeCard' },
        h('h2', {}, '예상 수수료'),
        h('p', { class: 'fee pending', id: 'fee' }, '금액 확인 필요'),
        h('p', { class: 'fee-line' }, `${res.region} · ${res.local_item}`),
        h('p', { class: 'notice notice-warn' }, res.message),
        h('p', { class: 'small' }, '등록된 규격·금액: ' + res.candidates.map((c) => `${c.spec} ${won(c.fee)}`).join(' / ')),
      );
    }
    const x = res.result;
    return h('section', { class: 'card', id: 'feeCard' },
      h('h2', {}, '예상 수수료'),
      h('p', { class: 'fee ready', id: 'fee' }, won(x.total_fee)),
      h('p', { class: 'fee-line' }, `${x.region.sido} ${x.region.sigungu} · ${x.local_item} ${x.spec.raw}`),
      h('dl', { class: 'summary basis' }, rows([['입력 내용', x.inputs.join(' · ')], ['데이터 기준일', x.source.base_date || '-'],
        ['제공기관', x.source.manager_org || '-']])),
      h('p', { class: 'small' }, '표준데이터 기준 예상 금액이며, 실제 금액은 지자체 신청 시 확정됩니다.'),
    );
  }
}
