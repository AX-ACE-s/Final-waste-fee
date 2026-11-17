// 화면 요소를 만드는 작은 도우미.
// 글자는 항상 textContent로 들어가므로, AI나 서버가 보낸 글이 화면에서 코드로 실행되지 않는다.
//
// 예: h('button', { class: 'btn', onclick: save }, '저장')
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key in el) el[key] = value;
    else el.setAttribute(key, value);
  }
  el.append(...children.flat(Infinity).filter((child) => child != null && child !== false));
  return el;
}
