(function () {
  function wireFrames(panel) {
    var shots = Array.prototype.slice.call(panel.querySelectorAll('.frames-shots img'));
    var items = Array.prototype.slice.call(panel.querySelectorAll('.step-list li'));
    var ping = panel.querySelector('.shot-ping');
    if (!shots.length || !items.length) return;

    function setActive(index) {
      shots.forEach(function (img) { img.classList.toggle('active', Number(img.dataset.frame) === index); });
      items.forEach(function (li) { li.classList.toggle('active', Number(li.dataset.frame) === index); });
      if (ping) {
        var currentShot = shots.filter(function (img) { return Number(img.dataset.frame) === index; })[0];
        if (currentShot && currentShot.dataset.pingX != null) {
          ping.style.left = currentShot.dataset.pingX + '%';
          ping.style.top = currentShot.dataset.pingY + '%';
          ping.hidden = false;
        } else {
          ping.hidden = true;
        }
      }
    }

    items.forEach(function (li) {
      var index = Number(li.dataset.frame);
      li.addEventListener('click', function () { setActive(index); });
      li.addEventListener('mouseenter', function () {
        if (window.matchMedia('(hover: hover)').matches) setActive(index);
      });
    });

    setActive(Number(items[0].dataset.frame));
  }

  var stepper = document.querySelector('.stepper');
  if (!stepper) return;

  var tabs = Array.prototype.slice.call(stepper.querySelectorAll('[role="tab"]'));
  var panels = Array.prototype.slice.call(stepper.querySelectorAll('[role="tabpanel"]'));
  panels.forEach(wireFrames);
  var prev = stepper.querySelector('[data-dir="-1"]');
  var next = stepper.querySelector('[data-dir="1"]');
  var current = 0;

  var NEXT_LABELS = [
    'Next: Download the plugin',
    'Next: Enable developer mode',
    'Next: Install the ZIP',
    'Next: First launch'
  ];

  function show(i, focusTab) {
    current = Math.max(0, Math.min(panels.length - 1, i));
    tabs.forEach(function (tab, j) {
      var on = j === current;
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.tabIndex = on ? 0 : -1;
    });
    panels.forEach(function (panel, j) { panel.hidden = j !== current; });
    prev.hidden = current === 0;
    next.hidden = current === panels.length - 1;
    next.textContent = NEXT_LABELS[current] || 'Next';
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

  function openFromHash() {
    var match = /^#step-(\d)$/.exec(location.hash);
    if (!match) return;
    show(parseInt(match[1], 10) - 1);
    panels[current].scrollIntoView({ block: 'start' });
  }

  var fromHash = /^#step-(\d)$/.exec(location.hash);
  show(fromHash ? parseInt(fromHash[1], 10) - 1 : 0);
  window.addEventListener('hashchange', openFromHash);
})();

(function () {
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.querySelectorAll('.gallery-video video').forEach(function (video) {
    video.removeAttribute('autoplay');
    video.pause();
    video.currentTime = 0;
  });
})();

(function () {
  var lightbox = document.getElementById('lightbox');
  if (!lightbox) return;

  var lightboxImg = document.getElementById('lightbox-img');
  var lightboxVideo = document.getElementById('lightbox-video');
  var lightboxDescription = document.getElementById('lightbox-description');
  var lightboxCaption = document.getElementById('lightbox-caption');
  var prevBtn = lightbox.querySelector('.lightbox-prev');
  var nextBtn = lightbox.querySelector('.lightbox-next');

  var group = [];
  var groupIndex = -1;

  function itemFromElement(el) {
    var media = el.querySelector('img, video');
    var item = {
      desc: el.dataset.desc || '',
      credit: el.dataset.credit || ''
    };
    if (media.tagName === 'VIDEO') {
      item.type = 'video';
      item.src = media.currentSrc || media.src;
      item.poster = media.getAttribute('poster') || '';
      item.alt = media.getAttribute('aria-label') || '';
    } else {
      item.type = 'image';
      item.src = media.src;
      item.alt = media.alt;
    }
    return item;
  }

  function render() {
    var item = group[groupIndex];
    if (item.type === 'video') {
      lightboxImg.hidden = true;
      lightboxImg.src = '';
      lightboxVideo.hidden = false;
      lightboxVideo.poster = item.poster;
      lightboxVideo.src = item.src;
      lightboxVideo.play();
    } else {
      lightboxVideo.pause();
      lightboxVideo.hidden = true;
      lightboxVideo.removeAttribute('src');
      lightboxImg.hidden = false;
      lightboxImg.src = item.src;
      lightboxImg.alt = item.alt;
    }
    if (item.desc) {
      lightboxDescription.textContent = item.desc;
      lightboxDescription.hidden = false;
    } else {
      lightboxDescription.hidden = true;
    }
    lightboxCaption.textContent = item.credit || item.alt;
    var grouped = group.length > 1;
    prevBtn.hidden = !grouped;
    nextBtn.hidden = !grouped;
  }

  function openGroup(items, index) {
    group = items;
    groupIndex = index;
    render();
    lightbox.classList.add('open');
    lightbox.setAttribute('aria-hidden', 'false');
  }

  function step(delta) {
    if (group.length < 2) return;
    groupIndex = (groupIndex + delta + group.length) % group.length;
    render();
  }

  function closeLightbox() {
    lightbox.classList.remove('open');
    lightbox.setAttribute('aria-hidden', 'true');
    lightboxImg.src = '';
    lightboxVideo.pause();
    lightboxVideo.removeAttribute('src');
    group = [];
    groupIndex = -1;
  }

  function wireGroup(containerEls) {
    var items = containerEls.map(itemFromElement);
    containerEls.forEach(function (el, i) {
      el.querySelector('img, video').addEventListener('click', function () {
        openGroup(items, i);
      });
    });
  }

  wireGroup(Array.prototype.slice.call(document.querySelectorAll('#how .step-shot')));
  wireGroup(Array.prototype.slice.call(document.querySelectorAll('.gallery-grid > li')));

  prevBtn.addEventListener('click', function (e) { e.stopPropagation(); step(-1); });
  nextBtn.addEventListener('click', function (e) { e.stopPropagation(); step(1); });
  lightbox.addEventListener('click', function (e) { if (e.target === lightbox) closeLightbox(); });
  lightbox.querySelector('.lightbox-close').addEventListener('click', closeLightbox);
  document.addEventListener('keydown', function (e) {
    if (!lightbox.classList.contains('open')) return;
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowRight') step(1);
    else if (e.key === 'ArrowLeft') step(-1);
  });
})();
