// 서버(Python)와 주고받는 부분. 화면 코드는 fetch를 직접 쓰지 않고 여기 함수만 부른다.
// ① 사진 인식(상훈)  /status, /recognize
// ② 규격 질문(문정)  /api/spec/*, /api/address
// ③ 수수료(하영)     /api/health, /api/fee/total  (금액·근거는 ②의 /api/spec/estimate 응답 fee_detail 로 함께 온다)
// ④ 체크리스트(지윤) /api/checklist, /api/checklist/link

async function request(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error('서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.');
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const msg = typeof body?.detail === 'string' ? body.detail : typeof body?.error === 'string' ? body.error : '';
    throw new Error(msg || '요청을 처리하지 못했어요.');
  }
  return body;
}

const postJson = (url, body) =>
  request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const qs = (params) => new URLSearchParams(params).toString();

// ---------------------------------------------------------------- ①
/** { mock_mode: true|false } */
export const getStatus = () => request('/status');

/** 사진 → 품목 후보와 근거. 응답 형식은 서버의 recognition/schemas.py 참고 */
export function recognizePhoto(photo, { sido, sigungu }) {
  const form = new FormData();
  form.append('photo', photo, 'photo.jpg');
  form.append('sido', sido);
  form.append('sigungu', sigungu);
  return request('/recognize', { method: 'POST', body: form });
}

// ---------------------------------------------------------------- ②
/** [{ sido, sigungu: [{ id, sigungu, manager_org }] }] */
export const getSpecRegions = () => request('/api/spec/regions');

/** 도로명주소 검색 → [{ road_addr, region_id, supported }] */
export const searchAddress = (q) => request('/api/address?' + qs({ q }));

/** 지역 품목 { standard: [{code,name,category}], local_only: [{local_item_id,name,category}] } (q 가 있으면 검색) */
export const getSpecItems = (regionId, q = '') => request('/api/spec/items?' + qs(q ? { region_id: regionId, q } : { region_id: regionId }));

/** 설명 문장 읽기 { items: [표준코드], hints, quantity, labels } */
export const parseDescription = (regionId, text) => request('/api/spec/parse?' + qs({ region_id: regionId, text }));

/** ①이 고른 수수료표 품목명 → { local_item_id, standard_code, standard_name } */
export const resolveItem = (regionId, item) => request('/api/spec/resolve?' + qs({ region_id: regionId, item }));

/** 다음 질문 1개, 또는 확정 결과(+ ③ fee_detail) */
export const estimate = (body) => postJson('/api/spec/estimate', body);

// ---------------------------------------------------------------- ③
export const getHealth = () => request('/api/health');
export const feeTotal = (region, entries) => postJson('/api/fee/total', { region, entries });

// ---------------------------------------------------------------- ④
/** 수수료 결과 → 체크리스트 페이지 주소 { available, url, item_name, reason } */
export const checklistLink = (sido, sigungu, code) => request('/api/checklist/link?' + qs({ sido, sigungu, code: code || '' }));

/** 체크리스트(신청 연결 정보 apply 포함) */
export const getChecklist = (district, item) => request('/api/checklist?' + qs({ district, item }));
