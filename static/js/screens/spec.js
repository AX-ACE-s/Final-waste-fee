// 규격 확인 화면
// 화면 틀(확정한 내용 · AI가 본 특징 · 규격 질문 자리): 기능① 박상훈 님 원본
// 규격 질문·실측 판정·보정(오른쪽 '규격 질문' 카드): 기능② 강문정 (/api/spec/estimate)
//
// 받는 값:  state.regionId, state.item / itemRef (확정된 품목), state.description·quantity (설명에서 읽은 값),
//           state.recognition.observed_features (AI가 사진에서 본 특징, 사진으로 찾았을 때만)
// 넘길 값:  state.estimate (확정 결과 + ③ fee_detail), state.spec 에 확정된 규격을 담고 go('result')
import { estimate } from '../api.js';
import { h } from '../dom.js';
import { go } from '../nav.js';
import { regionText, state } from '../state.js';

const decided = (r) => ['result', 'needs_confirmation'].includes(r?.status);

export function renderSpec() {
  // 사진으로 찾은 품목을 그대로 골랐을 때만 AI의 관찰이 이 품목에 대한 것이다.
  const features = state.itemSource === 'ai' ? Object.entries(state.recognition?.observed_features ?? {}) : [];

  const trail = h('p', { class: 'trail', id: 'trail' });
  const warn = h('p', { class: 'notice notice-warn', hidden: true });
  const qBox = h('div', { class: 'q-box', id: 'qBox' });
  const verifyBox = h('div', { class: 'verify-box', id: 'verifyBox' });
  const error = h('p', { class: 'notice notice-error', role: 'alert', hidden: true });
  const nextButton = h('button', { class: 'btn btn-primary', type: 'button', id: 'toResult', disabled: true, onclick: () => go('result') },
    '수수료·배출 안내 보기');
  const qtyInput = h('input', { id: 'qty', type: 'number', min: 1, max: 50, value: state.quantity, class: 'qty-input',
    'aria-label': '개수', onchange: changeQuantity });

  function showError(text) {
    error.textContent = text || '';
    error.hidden = !text;
  }
  const run = (fn) => (...args) => Promise.resolve(fn(...args)).catch((e) => showError(e.message));

  function changeQuantity() {
    const qty = Math.round(Number(qtyInput.value) || 1);
    if (!(qty >= 1 && qty <= 50)) { showError('개수는 1~50 사이로 입력해 주세요.'); return; }
    state.quantity = qty;
    if (state.answers) { state.answers.quantity = qty; run(next)(); }
  }

  async function next() {
    showError('');
    const r = await estimate({
      region_id: state.regionId,
      standard_code: state.itemRef?.standard_code || null,
      local_item_id: state.itemRef?.local_item_id || null,
      answers: state.answers,
    });
    state.estimate = r;
    draw(r);
  }

  function draw(r) {
    verifyBox.replaceChildren();
    state.spec = null;
    state.fee = null;
    nextButton.disabled = !decided(r);
    if (r.status === 'question') return showQ(r.question, r.warning);
    if (r.status === 'invalid') {
      const f = r.field || '';
      if (f.startsWith('measure.')) delete state.answers.measure[f.split('.')[1]];
      if (f === 'amount') delete state.answers.amount;
      if (f === 'spec') delete state.answers.spec;
      if (r.question) return showQ(r.question, null, r.message);
      return showError(r.message);
    }
    if (decided(r)) return showConfirmed(r);
    showQ(null, null, r.message || '처리할 수 없는 응답입니다.');
  }

  function renderTrail(items) {
    const xs = (items || []).filter((t) => !t.startsWith('지자체 품목'));
    const plain = (t) => t.replace(/설명에서 읽음 · /g, '').replace(/^인용\(사용 인원\): (\d+)인$/, '$1인용')
      .replace(/^단 수: (\d+)단$/, '$1단').replace(/^종류: /, '');
    trail.textContent = xs.length ? '입력한 내용 · ' + xs.map(plain).join(' · ') : '';
  }

  const choiceButtons = (q) => h('div', { class: 'chips' },
    q.options.map((o) => h('button', {
      class: 'chip', type: 'button',
      onclick: run(() => {
        if (q.id === 'local_item') state.answers.local_item = Number(o.value);
        else if (q.id === 'group') state.answers.group = o.value;
        else if (q.id === 'spec') state.answers.spec = Number(o.value);
        return next();
      }),
    }, o.label)));

  function showQ(q, warning, message) {
    warn.textContent = warning || '';
    warn.hidden = !warning;
    renderTrail([]);
    qBox.replaceChildren();
    if (!q) { if (message) showError(message); return; }
    qBox.append(h('p', { class: 'q-label' }, q.label));
    if (q.help) qBox.append(h('p', { class: 'small' }, q.help));
    if (q.type === 'choice') {
      qBox.append(choiceButtons(q));
      if (message) showError(message);
      return;
    }
    // 숫자(실측값) 질문: cm/m 바꿔 입력 가능, 설명에서 읽은 값은 미리 채우되 확인을 받는다
    let unit = q.unit;
    const input = h('input', { id: 'measure', type: 'number', step: 'any', inputMode: 'decimal', placeholder: `${q.unit} 단위`,
      'aria-label': q.label, value: q.prefill ?? '' });
    const unitPart = q.allow_m
      ? h('span', { class: 'unit-toggle' }, ['cm', 'm'].map((u) => h('button', {
          type: 'button', class: u === 'cm' ? 'on' : '',
          onclick: (event) => {
            unit = u;
            for (const b of event.currentTarget.parentElement.children) b.classList.toggle('on', b === event.currentTarget);
          },
        }, u)))
      : h('span', { class: 'unit' }, q.unit);
    const fieldError = h('p', { class: 'field-error' }, message || '');
    const submit = run(() => {
      const raw = input.value.trim();
      if (raw === '') { fieldError.textContent = '값을 입력하거나 아래에서 규격을 골라 주세요.'; return; }
      let v = Number(raw);
      if (q.allow_m && unit === 'm') v = Math.round(v * 1000) / 10;
      if (q.id === 'amount') state.answers.amount = v; else state.answers.measure[q.dim] = v;
      return next();
    });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    qBox.append(
      h('div', { class: 'row' }, h('div', { class: 'grow' }, input), unitPart,
        h('button', { class: 'btn btn-primary', type: 'button', id: 'measureGo', onclick: submit }, '확인')),
      q.prefill_note && h('p', { class: 'notice notice-warn' }, q.prefill_note),
      fieldError,
      q.fallback && h('div', { class: 'fallback' }, h('p', { class: 'q-label' }, q.fallback.label), choiceButtons(q.fallback)),
    );
    input.focus();
  }

  // 규격이 정해지면 확정 규격·입력 내용과 (선택) 실측 확인·보정만 남긴다
  function showConfirmed(r) {
    warn.hidden = true;
    const res = r.result || r;
    renderTrail(res.inputs || []);
    qBox.replaceChildren();
    if (r.status === 'needs_confirmation') {
      qBox.append(h('p', { class: 'notice notice-warn' }, r.message));
      return;
    }
    state.spec = res.spec.raw;
    state.fee = r.fee_detail || null;
    qBox.append(h('p', { class: 'chosen' }, `확정된 규격: ${res.spec.raw}`),
      h('p', { class: 'small' }, '아래 버튼을 누르면 예상 수수료와 배출 안내를 볼 수 있어요.'));
    if (res.correction) {
      verifyBox.append(h('p', { class: 'notice notice-warn' }, res.correction.message));
      if (res.correction.spec_id) {
        verifyBox.append(h('button', { class: 'btn', type: 'button', id: 'applyFix',
          onclick: run(() => { state.answers.spec = res.correction.spec_id; return next(); }) }, '실측 기준 규격으로 바꾸기'));
      }
    }
    if (res.verify?.length) {
      verifyBox.append(h('p', { class: 'small' }, '고른 규격이 맞는지 실측값으로 확인할 수 있어요 (선택)'));
      for (const v of res.verify) {
        const inp = h('input', { id: 'vf_' + v.dim, type: 'number', step: 'any' });
        verifyBox.append(
          h('label', { class: 'field', htmlFor: inp.id }, `${v.label} (${v.unit}) — 고른 규격: ${v.range}`),
          h('div', { class: 'row' }, h('div', { class: 'grow' }, inp),
            h('button', { class: 'btn verify-go', type: 'button', onclick: run(() => {
              if (inp.value === '') return;
              state.answers.measure[v.dim] = Number(inp.value);
              return next();
            }) }, '실측으로 확인')),
        );
      }
    }
    nextButton.focus();
  }

  function restart() {
    // 설명에서 읽은 값도 버리고 처음부터 직접 답한다
    state.answers = { measure: {}, quantity: state.quantity };
    run(next)();
  }

  // 처음 들어왔으면 질문을 시작하고, 뒤로 돌아왔으면 마지막 상태를 그대로 보여 준다
  if (state.estimate && state.answers) draw(state.estimate);
  else {
    state.answers = { measure: {}, quantity: state.quantity, description: state.description };
    run(next)();
  }

  return h('div', { class: 'screen' },
    h('h1', {}, '규격을 확인할게요'),

    h('div', { class: 'cols cols-photo' },
      h('div', { class: 'stack' },
        h('section', { class: 'card' },
          h('div', { class: 'card-head' },
            h('h2', {}, '확정한 내용'),
            h('button', { class: 'btn btn-text', type: 'button', onclick: () => go('item') }, '품목 바꾸기'),
          ),
          h('dl', { class: 'summary' },
            h('dt', {}, '배출 지역'), h('dd', {}, regionText()),
            h('dt', {}, '품목'), h('dd', {}, state.item),
            h('dt', {}, '개수'), h('dd', {}, qtyInput, ' 개'),
          ),
        ),

        features.length > 0 && h('section', { class: 'card' },
          h('h2', {}, 'AI가 사진에서 본 특징'),
          h('dl', { class: 'summary' }, features.map(([name, value]) => [h('dt', {}, name), h('dd', {}, value)])),
          h('p', { class: 'small' }, '사진만으로 본 추정이에요. 규격을 정할 때 참고로만 쓰입니다.'),
        ),
      ),

      h('section', { class: 'card' },
        h('h2', {}, '규격 질문'),
        h('p', { class: 'small' }, `${regionText()} 수수료표에서 금액을 가르는 것만 물어볼게요.`),
        trail,
        warn,
        qBox,
        verifyBox,
        error,
        h('button', { class: 'btn btn-text restart', type: 'button', id: 'restart', onclick: restart }, '처음부터 다시 답하기'),
      ),
    ),

    h('div', { class: 'actions' },
      h('button', { class: 'btn', type: 'button', onclick: () => go('item') }, '이전'),
      nextButton,
    ),
  );
}
