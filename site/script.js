(function () {
  var INTERVAL = 4000;
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function Frames(root) {
    var frames = Array.prototype.slice.call(root.querySelectorAll('.frame'));
    var bar = root.querySelector('.frames-bar');
    if (frames.length < 2 || !bar) {
      if (bar) bar.hidden = true;
      return { start: function () {}, stop: function () {} };
    }

    var dots = bar.querySelector('.frames-dots');
    var toggle = bar.querySelector('.frames-toggle');
    var buttons = frames.map(function (_, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-label', 'Image ' + (i + 1) + ' of ' + frames.length);
      b.addEventListener('click', function () { userPaused = true; go(i); sync(); });
      dots.appendChild(b);
      return b;
    });

    var index = 0;
    var timer = null;
    var userPaused = reducedMotion;
    var hovering = false;
    var active = false;

    function go(i) {
      index = (i + frames.length) % frames.length;
      frames.forEach(function (f, j) { f.hidden = j !== index; });
      buttons.forEach(function (b, j) {
        if (j === index) b.setAttribute('aria-current', 'true');
        else b.removeAttribute('aria-current');
      });
    }

    function running() { return active && !userPaused && !hovering && !document.hidden; }

    function sync() {
      clearInterval(timer);
      timer = null;
      if (running()) timer = setInterval(function () { go(index + 1); }, INTERVAL);
      toggle.textContent = userPaused ? 'Play' : 'Pause';
      toggle.setAttribute('aria-pressed', userPaused ? 'true' : 'false');
    }

    toggle.addEventListener('click', function () { userPaused = !userPaused; sync(); });
    root.addEventListener('mouseenter', function () { hovering = true; sync(); });
    root.addEventListener('mouseleave', function () { hovering = false; sync(); });
    root.addEventListener('focusin', function () { hovering = true; sync(); });
    root.addEventListener('focusout', function () { hovering = false; sync(); });
    document.addEventListener('visibilitychange', sync);

    go(0);
    return {
      start: function () { active = true; sync(); },
      stop: function () { active = false; sync(); }
    };
  }

  var stepper = document.querySelector('.stepper');
  if (!stepper) return;

  var tabs = Array.prototype.slice.call(stepper.querySelectorAll('[role="tab"]'));
  var panels = Array.prototype.slice.call(stepper.querySelectorAll('[role="tabpanel"]'));
  var galleries = panels.map(function (p) {
    var root = p.querySelector('.frames');
    return root ? Frames(root) : { start: function () {}, stop: function () {} };
  });
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
      if (j === current) galleries[j].start(); else galleries[j].stop();
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

  var fromHash = /^#step-(\d)$/.exec(location.hash);
  show(fromHash ? parseInt(fromHash[1], 10) - 1 : 0);
})();
