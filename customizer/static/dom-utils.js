/* DOM manipulation utility functions */

export const $ = (selector) => document.querySelector(selector);
export const $$ = (selector) => document.querySelectorAll(selector);
export const byId = (id) => document.getElementById(id);

export function addClass(el, ...classes) {
  if (!el) return;
  el.classList.add(...classes);
}

export function removeClass(el, ...classes) {
  if (!el) return;
  el.classList.remove(...classes);
}

export function toggleClass(el, className) {
  if (!el) return;
  el.classList.toggle(className);
}

export function hasClass(el, className) {
  if (!el) return false;
  return el.classList.contains(className);
}

export function setVisible(el, visible) {
  if (!el) return;
  if (visible) {
    removeClass(el, "hidden");
  } else {
    addClass(el, "hidden");
  }
}

export function clearChildren(el) {
  if (!el) return;
  el.innerHTML = "";
}

export function setText(el, text) {
  if (!el) return;
  el.textContent = text;
}

export function setHTML(el, html) {
  if (!el) return;
  el.innerHTML = html;
}

export function setAttribute(el, key, value) {
  if (!el) return;
  el.setAttribute(key, value);
}

export function removeAttribute(el, key) {
  if (!el) return;
  el.removeAttribute(key);
}

export function getValue(el) {
  if (!el) return "";
  return el.value;
}

export function setValue(el, value) {
  if (!el) return;
  el.value = value;
}

export function on(el, event, handler) {
  if (!el) return;
  el.addEventListener(event, handler);
}

export function off(el, event, handler) {
  if (!el) return;
  el.removeEventListener(event, handler);
}

export function onClick(el, handler) {
  on(el, "click", handler);
}

export function onInput(el, handler) {
  on(el, "input", handler);
}

export function onChange(el, handler) {
  on(el, "change", handler);
}

export function findDataAttr(el, attrName) {
  if (!el) return undefined;
  return el.dataset[attrName];
}

export function setDataAttr(el, attrName, value) {
  if (!el) return;
  el.dataset[attrName] = value;
}
