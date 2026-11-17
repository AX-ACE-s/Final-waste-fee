// 화면 전환을 맡는다. 주소 뒤의 #이름 이 바뀌면 그 화면을 그린다 (뒤로 가기 버튼도 동작).
// 화면 틀: 기능① 박상훈 님. 통합하면서 단계별로 ②(규격)·③(수수료)·④(체크리스트 연결)를 채웠다.
import { getHealth, getStatus } from './api.js';
import { h } from './dom.js';
import { go } from './nav.js';
import { restoreState, saveState, state } from './state.js';
import { renderHome } from './screens/home.js';
import { renderItem } from './screens/item.js';
import { renderSpec } from './screens/spec.js';
import { renderResult } from './screens/result.js';

const STEPS = ['품목 확인', '규격 확인', '수수료·배출 안내'];
const decided = () => ['result', 'needs_confirmation'].includes(state.estimate?.status);

// ready: 이 화면을 보려면 앞 단계에서 정해져 있어야 하는 것. 아니면 첫 화면으로 돌려보낸다.
const SCREENS = {
  home:   { step: 0, title: '시작',            render: renderHome,   ready: () => true },
  item:   { step: 0, title: '품목 확인',        render: renderItem,   ready: () => Boolean(state.regionId && (state.recognition || state.searchQuery)) },
  spec:   { step: 1, title: '규격 확인',        render: renderSpec,   ready: () => Boolean(state.item && state.itemRef) },
  result: { step: 2, title: '수수료·배출 안내', render: renderResult, ready: () => Boolean(state.item && decided()) },
};

function show() {
  const name = location.hash.slice(1) || 'home';
  const screen = SCREENS[name];
  if (!screen || !screen.ready()) {
    go('home');
    return;
  }

  document.getElementById('stepper').replaceChildren(
    ...STEPS.map((label, index) =>
      h('li', {
        class: index === screen.step ? 'current' : index < screen.step ? 'done' : '',
        'aria-current': index === screen.step ? 'step' : null,
      }, `${index + 1}. ${label}`)
    )
  );

  const main = document.getElementById('screen');
  main.replaceChildren(screen.render());
  saveState(location.hash);
  document.title = `${screen.title} | 우리동네 대형폐기물 AI 수거비용 안내`;
  window.scrollTo(0, 0);
  main.focus({ preventScroll: true }); // 화면이 바뀐 것을 화면낭독기 사용자도 알 수 있게
}

window.addEventListener('hashchange', show);
window.addEventListener('pagehide', () => saveState(location.hash));  // 체크리스트 페이지로 넘어갈 때 마지막 상태 보관
restoreState();
show();

getStatus()
  .then((status) => { document.getElementById('mockNotice').hidden = !status.mock_mode; })
  .catch(() => {});

// ③ 데이터 상태: 공공데이터포털에서 새로 받는 중이거나, 실제 데이터가 없어 샘플로 동작할 때 알린다
getHealth()
  .then((health) => {
    const notice = document.getElementById('dataNotice');
    if (health.refreshing) {
      notice.textContent = `공공데이터포털에서 최신 수수료 데이터를 받아오는 중이에요(${health.progress || '준비 중'}). 끝나면 새로고침해 주세요.`;
    } else if (health.sample_data) {
      notice.textContent = '시연용 샘플 데이터로 동작 중이에요. 표시되는 금액은 실제 금액이 아니에요.';
    } else return;
    notice.hidden = false;
  })
  .catch(() => {});
