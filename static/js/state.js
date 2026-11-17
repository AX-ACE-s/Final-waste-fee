// 화면들이 함께 쓰는 값. 한 화면에서 정한 값을 다음 화면이 여기서 읽는다.
// 새로고침하면 사라진다(사진 등 개인정보를 브라우저에 남기지 않기 위해 저장하지 않음).
export const state = {
  // 배출 지역 (②의 지역 목록에서 고름). sido·sigungu 는 수수료표 원문 표기(①에 넘김)
  regionId: null,
  regionName: '',     // 화면 표시용 '부산광역시 해운대구'
  sido: '',
  sigungu: '',

  // ① 품목 확인 단계에서 채워진다
  photo: null,        // 서버로 보낸 사진(Blob)
  photoUrl: '',       // 미리보기 주소
  recognition: null,  // POST /recognize 응답 전체
  searchQuery: '',    // 이름·설명으로 찾기에 입력한 말
  item: '',           // 사용자가 확정한 품목 이름  ← 다음 단계의 출발점
  itemSource: '',     // 'ai'(사진 후보에서 선택) | 'search'(이름·설명 검색) | 'list'(목록에서 선택)
  itemKey: '',        // 화면에서 고른 항목 구분값 ('ai:소파', 'std:SOFA', 'loc:123')
  itemRef: null,      // ②가 쓰는 품목 키 { standard_code } 또는 { local_item_id }
  itemCode: null,     // 표준 품목 코드 (④ 체크리스트 품목 연결)
  description: '',    // 설명 문장 (②가 크기·인용 등을 미리 읽음)
  quantity: 1,

  // ② 규격 확인 단계
  answers: null,      // ②에 보내는 답 { measure, quantity, description, spec, ... }
  estimate: null,     // ②의 마지막 응답 (확정되면 ③의 fee_detail 포함)
  spec: null,         // 확정된 규격 문구

  // ③ 수수료·배출 안내 단계
  fee: null,          // ③ fee_detail
  cart: [],           // 담은 품목 (같은 지역끼리 합계)
  added: null,        // 마지막으로 담은 결과 (같은 결과를 두 번 담지 않게)
  cartRegion: '',
};

export function setPhoto(blob) {
  if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
  state.photo = blob;
  state.photoUrl = blob ? URL.createObjectURL(blob) : '';
}

/** 품목 찾기를 새로 시작할 때: 이전 결과를 지운다. (지역·담은 품목은 그대로) */
export function clearItemStep() {
  state.recognition = null;
  state.searchQuery = '';
  state.item = '';
  state.itemSource = '';
  state.itemKey = '';
  state.itemRef = null;
  state.itemCode = null;
  state.description = '';
  state.quantity = 1;
  clearSpecStep();
}

/** 품목이 바뀌면 규격·수수료는 다시 */
export function clearSpecStep() {
  state.answers = null;
  state.estimate = null;
  state.spec = null;
  state.fee = null;
}

export function resetAll() {
  setPhoto(null);
  clearItemStep();
}

export function setRegion(g) {
  if (state.regionId !== g.id) { state.cart = []; state.cartRegion = ''; }  // 지역이 바뀌면 합계를 비운다
  state.regionId = g.id;
  state.regionName = `${g.sido} ${g.sigungu}`;
  state.sido = g.sido;
  state.sigungu = g.sigungu === '(시 전체)' ? '없음' : g.sigungu;  // 세종처럼 시군구가 없는 곳의 원문 표기
}

export const region = () => ({ sido: state.sido, sigungu: state.sigungu });
export const regionText = () => state.regionName;

// 두 페이지(수수료 확인 · 배출 전 체크리스트)를 오가도 진행 상황이 남도록 이 탭 안에서만 잠깐 보관한다.
// 사진은 개인정보가 담길 수 있어 보관하지 않는다. 탭을 닫으면 사라진다.
const KEY = 'waste-fee-state';
const SKIP = new Set(['photo', 'photoUrl']);

export function saveState(hash) {
  try {
    const data = Object.fromEntries(Object.entries(state).filter(([k]) => !SKIP.has(k)));
    sessionStorage.setItem(KEY, JSON.stringify(data));
    sessionStorage.setItem('waste-fee-hash', hash || '');
  } catch { /* 저장할 수 없는 환경이면 그냥 넘어간다 */ }
}

export function restoreState() {
  try {
    const data = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (data) for (const [k, v] of Object.entries(data)) if (k in state && !SKIP.has(k)) state[k] = v;
  } catch { /* 없거나 깨졌으면 처음부터 */ }
}
