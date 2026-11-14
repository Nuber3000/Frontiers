"use strict";

window.FrontiersCardScroll = (() => {
  const selector = ".in-match #hand, .in-match .row-cards";
  let gesture = null, blockedClick = null;
  const container = target => target instanceof Element ? target.closest(selector) : null;
  const key = element => {
    if (element.id === "hand") return "hand";
    const row = element.closest(".combat-row");
    return `${row.dataset.side}:${row.dataset.row}`;
  };

  function finish() {
    if (!gesture) return;
    const previous = gesture;
    gesture = null;
    previous.element.classList.remove("card-scroll-dragging");
    document.body.classList.remove("dragging-cards");
    if (previous.dragging) blockedClick = {key: key(previous.element), until: performance.now() + 500};
    if (previous.element.hasPointerCapture(previous.id)) previous.element.releasePointerCapture(previous.id);
  }

  document.addEventListener("pointerdown", event => {
    if (event.pointerType !== "mouse" || event.button !== 0 || !event.isPrimary) return;
    finish();
    blockedClick = null;
    const element = container(event.target);
    if (!element || element.scrollWidth <= element.clientWidth + 1) return;
    gesture = {element, id: event.pointerId, x: event.clientX, left: element.scrollLeft, dragging: false};
  });
  document.addEventListener("pointermove", event => {
    if (!gesture || event.pointerId !== gesture.id) return;
    if (!(event.buttons & 1)) { finish(); return; }
    const distance = event.clientX - gesture.x;
    if (!gesture.dragging) {
      if (Math.abs(distance) < 6) return;
      gesture.dragging = true;
      gesture.element.setPointerCapture(event.pointerId);
      gesture.element.classList.add("card-scroll-dragging");
      document.body.classList.add("dragging-cards");
    }
    event.preventDefault();
    gesture.element.scrollLeft = gesture.left - distance;
  }, {passive: false});
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
    document.addEventListener(type, event => { if (gesture?.id === event.pointerId) finish(); });
  }
  window.addEventListener("blur", finish);
  document.addEventListener("dragstart", event => { if (container(event.target)) event.preventDefault(); });
  document.addEventListener("click", event => {
    const element = container(event.target);
    if (event.detail && blockedClick && performance.now() <= blockedClick.until
        && element && key(element) === blockedClick.key) {
      event.preventDefault();
      event.stopImmediatePropagation();
      blockedClick = null;
    }
  }, true);
  document.addEventListener("wheel", event => {
    const element = container(event.target);
    if (event.ctrlKey || !element || element.scrollWidth <= element.clientWidth + 1) return;
    const amount = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    const scale = event.deltaMode === 1 ? 28 : event.deltaMode === 2 ? element.clientWidth : 1;
    const before = element.scrollLeft;
    element.scrollLeft += amount * scale;
    if (element.scrollLeft !== before) event.preventDefault();
  }, {passive: false});

  return {
    remember() {
      return new Map([...document.querySelectorAll(selector)].map(element => [key(element), element.scrollLeft]));
    },
    restore(positions) {
      for (const element of document.querySelectorAll(selector)) element.scrollLeft = positions.get(key(element)) || 0;
    },
  };
})();
