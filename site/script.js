(function () {
  var stepper = document.querySelector('.stepper');
  if (!stepper) return;

  var tabs = Array.prototype.slice.call(stepper.querySelectorAll('[role="tab"]'));
  var panels = Array.prototype.slice.call(stepper.querySelectorAll('[role="tabpanel"]'));
  var prev = stepper.querySelector('[data-dir="-1"]');
  var next = stepper.querySelector('[data-dir="1"]');
  var counter = stepper.querySelector('[data-current]');
  var current = 0;

  function show(i, focusTab) {
    current = Math.max(0, Math.min(panels.length - 1, i));
    tabs.forEach(function (tab, j) {
      var on = j === current;
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.tabIndex = on ? 0 : -1;
    });
    panels.forEach(function (panel, j) {
      panel.hidden = j !== current;
    });
    prev.disabled = current === 0;
    next.disabled = current === panels.length - 1;
    counter.textContent = current + 1;
    if (focusTab) tabs[current].focus();
  }

  tabs.forEach(function (tab, i) {
    tab.addEventListener('click', function () { show(i); });
    tab.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight') show(i + 1, true);
      else if (e.key === 'ArrowLeft') show(i - 1, true);
      else if (e.key === 'Home') show(0, true);
      else if (e.key === 'End') show(panels.length - 1, true);
      else return;
      e.preventDefault();
    });
  });

  prev.addEventListener('click', function () { show(current - 1); });
  next.addEventListener('click', function () { show(current + 1); });

  show(0);
})();
