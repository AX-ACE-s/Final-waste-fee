/** 다른 화면으로 이동. 예: go('item')  (실제로 화면을 그리는 일은 app.js가 한다) */
export function go(name) {
  if (location.hash === '#' + name) window.dispatchEvent(new Event('hashchange'));
  else location.hash = name;
}
