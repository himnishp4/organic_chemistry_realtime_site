(() => {
  // Theme switcher ----------------------------------------------------------
  // Stores the visitor's choice locally so light/dark mode persists across pages.
  const root = document.documentElement;
  const themeToggle = document.getElementById('theme-toggle');
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');

  function currentTheme() {
    return root.dataset.theme === 'dark' ? 'dark' : 'light';
  }

  function updateThemeControl() {
    if (!themeToggle) return;
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    themeToggle.setAttribute('aria-label', `Switch to ${next} theme`);
    themeToggle.setAttribute('title', `Switch to ${next} theme`);
  }

  function applyTheme(theme, persist = true) {
    root.dataset.theme = theme === 'dark' ? 'dark' : 'light';
    root.style.colorScheme = root.dataset.theme;
    if (persist) {
      try { localStorage.setItem('oc-theme', root.dataset.theme); } catch (_) {}
    }
    updateThemeControl();
  }

  updateThemeControl();
  themeToggle?.addEventListener('click', () => {
    applyTheme(currentTheme() === 'dark' ? 'light' : 'dark');
  });

  systemTheme.addEventListener?.('change', (event) => {
    let saved = null;
    try { saved = localStorage.getItem('oc-theme'); } catch (_) {}
    if (!saved) applyTheme(event.matches ? 'dark' : 'light', false);
  });

  // Liquid-glass sliding navigation ----------------------------------------
  // The active capsule follows the current route, glides beneath hovered
  // items, and returns to the active page when the pointer leaves the bar.
  const liquidNav = document.querySelector('.liquid-tabbar');
  const navSlider = liquidNav?.querySelector('.liquid-tabbar__slider');
  const navLinks = liquidNav ? [...liquidNav.querySelectorAll('a[data-nav-route]')] : [];

  function routeMatches(link) {
    const route = link.dataset.navRoute || link.getAttribute('href') || '';
    const path = window.location.pathname.replace(/\/$/, '') || '/';
    const normalized = route.replace(/\/$/, '') || '/';
    return normalized === '/' ? path === '/' : path === normalized || path.startsWith(`${normalized}/`);
  }

  let activeNavLink = navLinks.find(routeMatches) || null;
  if (!activeNavLink && window.location.pathname.startsWith('/lesson/')) {
    try {
      const remembered = sessionStorage.getItem('oc-last-nav');
      activeNavLink = navLinks.find((link) => link.getAttribute('href') === remembered) || null;
    } catch (_) {}
  }

  function positionNavSlider(link, instant = false) {
    if (!liquidNav || !navSlider || !link || window.innerWidth <= 980) return;
    const navRect = liquidNav.getBoundingClientRect();
    const linkRect = link.getBoundingClientRect();
    navSlider.style.setProperty('--slider-x', `${linkRect.left - navRect.left}px`);
    navSlider.style.setProperty('--slider-y', `${linkRect.top - navRect.top}px`);
    navSlider.style.setProperty('--slider-w', `${linkRect.width}px`);
    navSlider.style.setProperty('--slider-h', `${linkRect.height}px`);
    navSlider.classList.toggle('is-instant', instant);
    navSlider.classList.add('is-visible');
    navLinks.forEach((item) => item.classList.toggle('is-active', item === activeNavLink));
    if (instant) requestAnimationFrame(() => navSlider.classList.remove('is-instant'));
  }

  if (liquidNav && navSlider && navLinks.length) {
    const initial = activeNavLink || navLinks[0];
    requestAnimationFrame(() => positionNavSlider(initial, true));

    navLinks.forEach((link) => {
      link.addEventListener('pointerenter', () => positionNavSlider(link));
      link.addEventListener('focus', () => positionNavSlider(link));
      link.addEventListener('click', () => {
        try { sessionStorage.setItem('oc-last-nav', link.getAttribute('href') || ''); } catch (_) {}
      });
    });

    liquidNav.addEventListener('pointerleave', () => {
      if (activeNavLink) positionNavSlider(activeNavLink);
      else navSlider.classList.remove('is-visible');
    });
    liquidNav.addEventListener('focusout', (event) => {
      if (!liquidNav.contains(event.relatedTarget)) {
        if (activeNavLink) positionNavSlider(activeNavLink);
        else navSlider.classList.remove('is-visible');
      }
    });

    const syncSlider = () => {
      if (window.innerWidth <= 980) {
        navSlider.classList.remove('is-visible');
        return;
      }
      positionNavSlider(activeNavLink || navLinks[0], true);
    };
    window.addEventListener('resize', syncSlider, { passive: true });
    if (window.ResizeObserver) new ResizeObserver(syncSlider).observe(liquidNav);
  }

  // Live teacher updates ----------------------------------------------------
  const indicator = document.getElementById('live-indicator');
  if (document.body.dataset.livePage && window.EventSource) {
    let firstMessage = true;
    const source = new EventSource('/events');
    source.onopen = () => indicator?.classList.add('connected');
    source.onmessage = () => {
      if (firstMessage) {
        firstMessage = false;
        return;
      }
      if (indicator) {
        indicator.innerHTML = '<span></span> New teacher update';
        indicator.classList.add('updated');
      }
      window.setTimeout(() => window.location.reload(), 550);
    };
    source.onerror = () => indicator?.classList.remove('connected');
  }

  // Premium interactive atom background -----------------------------------
  // Pure Canvas: no external images, CDN, paid plugin, or framework needed.
  if (document.body.dataset.chemMotion !== 'true') return;

  const canvas = document.createElement('canvas');
  canvas.className = 'chem-motion-canvas premium-atomic-field';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let width = 0;
  let height = 0;
  let dpr = 1;
  let particles = [];
  let frame = 0;
  let last = performance.now();
  let pointerX = 0;
  let pointerY = 0;
  let atomX = 0;
  let atomY = 0;
  let targetX = 0;
  let targetY = 0;
  let dragging = false;

  const palette = {
    violet: [22, 163, 139],
    cyan: [72, 214, 196],
    blue: [24, 112, 101],
    pink: [218, 174, 92],
    white: [255, 255, 255],
  };

  const compact = () => width < 760;
  const rgb = (arr, a = 1) => `rgba(${arr[0]},${arr[1]},${arr[2]},${a})`;
  const rand = (min, max) => Math.random() * (max - min) + min;

  function makeParticles() {
    const count = compact() ? 34 : Math.min(85, Math.max(48, Math.round((width * height) / 26000)));
    particles = Array.from({ length: count }, (_, i) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: rand(.7, 2.2),
      vx: rand(-.08, .08),
      vy: rand(-.06, .06),
      alpha: rand(.08, .34),
      color: [palette.violet, palette.cyan, palette.blue][i % 3],
    }));
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    atomX = targetX = compact() ? width * .69 : width * .78;
    atomY = targetY = compact() ? Math.min(height * .34, 270) : height * .38;
    pointerX = width / 2;
    pointerY = height / 2;
    makeParticles();
    draw(performance.now(), 0);
  }

  function glowDot(x, y, radius, color, alpha = 1) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, radius * 4.4);
    g.addColorStop(0, rgb(color, .96 * alpha));
    g.addColorStop(.26, rgb(color, .45 * alpha));
    g.addColorStop(1, rgb(color, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, radius * 4.4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = rgb(color, alpha);
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawAmbientParticles(dt) {
    ctx.save();
    for (const p of particles) {
      if (!reduced && dt) {
        const s = Math.min(dt, 40) / 16.67;
        p.x += p.vx * s;
        p.y += p.vy * s;
        if (p.x < -10) p.x = width + 10;
        if (p.x > width + 10) p.x = -10;
        if (p.y < -10) p.y = height + 10;
        if (p.y > height + 10) p.y = -10;
      }
      glowDot(p.x, p.y, p.r, p.color, p.alpha);
    }
    ctx.restore();
  }

  function drawMolecularLattice(now) {
    const step = compact() ? 150 : 190;
    ctx.save();
    ctx.globalAlpha = compact() ? .045 : .06;
    ctx.strokeStyle = rgb(palette.cyan, .8);
    ctx.lineWidth = .75;
    const drift = (now * .0025) % step;
    for (let x = -step + drift; x < width + step; x += step) {
      for (let y = -step; y < height + step; y += step) {
        const px = x + Math.sin((y + now * .02) * .008) * 9;
        const py = y + Math.cos((x + now * .018) * .006) * 8;
        const r = 24;
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
          const a = Math.PI / 3 * i + Math.PI / 6;
          const xx = px + Math.cos(a) * r;
          const yy = py + Math.sin(a) * r;
          i ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy);
        }
        ctx.closePath();
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function ellipsePoint(cx, cy, rx, ry, angle, rotation) {
    const ex = Math.cos(angle) * rx;
    const ey = Math.sin(angle) * ry;
    const cr = Math.cos(rotation);
    const sr = Math.sin(rotation);
    return [cx + ex * cr - ey * sr, cy + ex * sr + ey * cr];
  }

  function drawOrbit(cx, cy, rx, ry, rotation, color, alpha) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(rotation);
    const grad = ctx.createLinearGradient(-rx, 0, rx, 0);
    grad.addColorStop(0, rgb(color, .04));
    grad.addColorStop(.5, rgb(color, alpha));
    grad.addColorStop(1, rgb(color, .04));
    ctx.strokeStyle = grad;
    ctx.lineWidth = compact() ? 1 : 1.25;
    ctx.shadowColor = rgb(color, .26);
    ctx.shadowBlur = 14;
    ctx.beginPath();
    ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  function drawNucleus(cx, cy, size, now) {
    const pulse = 1 + Math.sin(now * .0015) * .035;
    const s = size * pulse;

    const halo = ctx.createRadialGradient(cx, cy, s * .2, cx, cy, s * 2.8);
    halo.addColorStop(0, rgb(palette.violet, .38));
    halo.addColorStop(.32, rgb(palette.cyan, .14));
    halo.addColorStop(1, rgb(palette.blue, 0));
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(cx, cy, s * 2.8, 0, Math.PI * 2);
    ctx.fill();

    const core = ctx.createRadialGradient(cx - s * .3, cy - s * .35, s * .15, cx, cy, s);
    core.addColorStop(0, 'rgba(255,255,255,.98)');
    core.addColorStop(.16, rgb(palette.cyan, .95));
    core.addColorStop(.56, rgb(palette.violet, .94));
    core.addColorStop(1, 'rgba(20,24,70,.98)');
    ctx.fillStyle = core;
    ctx.shadowColor = rgb(palette.violet, .8);
    ctx.shadowBlur = 28;
    ctx.beginPath();
    ctx.arc(cx, cy, s, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Proton/neutron highlights inside the nucleus.
    const beads = [
      [-.28, -.18, palette.cyan],
      [.23, -.22, palette.pink],
      [-.16, .28, palette.violet],
      [.30, .20, palette.blue],
    ];
    for (const [ox, oy, color] of beads) {
      const bx = cx + ox * s;
      const by = cy + oy * s;
      const bg = ctx.createRadialGradient(bx - 2, by - 2, 0, bx, by, s * .26);
      bg.addColorStop(0, 'rgba(255,255,255,.92)');
      bg.addColorStop(.28, rgb(color, .92));
      bg.addColorStop(1, rgb(color, .15));
      ctx.fillStyle = bg;
      ctx.beginPath();
      ctx.arc(bx, by, s * .24, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawPremiumAtom(now) {
    const scale = compact() ? .68 : Math.min(1.02, Math.max(.82, width / 1450));
    const nucleus = 27 * scale;
    const orbitData = [
      { rx: 164 * scale, ry: 56 * scale, rot: -.35, speed: .00055, color: palette.cyan, phase: .6 },
      { rx: 164 * scale, ry: 56 * scale, rot: .72, speed: -.00048, color: palette.violet, phase: 2.5 },
      { rx: 156 * scale, ry: 52 * scale, rot: 1.57, speed: .00062, color: palette.blue, phase: 4.4 },
    ];

    // Smooth pointer parallax unless the atom is being dragged.
    if (!dragging) {
      const px = (pointerX / Math.max(width, 1) - .5) * (compact() ? 15 : 34);
      const py = (pointerY / Math.max(height, 1) - .5) * (compact() ? 10 : 22);
      const homeX = compact() ? width * .69 : width * .78;
      const homeY = compact() ? Math.min(height * .34, 270) : height * .38;
      targetX = homeX + px;
      targetY = homeY + py;
    }
    atomX += (targetX - atomX) * .055;
    atomY += (targetY - atomY) * .055;

    // A subtle glass aura behind the orbital atom.
    const aura = ctx.createRadialGradient(atomX, atomY, 0, atomX, atomY, 240 * scale);
    aura.addColorStop(0, 'rgba(16,185,129,.14)');
    aura.addColorStop(.46, 'rgba(218,174,92,.055)');
    aura.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = aura;
    ctx.beginPath();
    ctx.arc(atomX, atomY, 240 * scale, 0, Math.PI * 2);
    ctx.fill();

    for (const orbit of orbitData) {
      drawOrbit(atomX, atomY, orbit.rx, orbit.ry, orbit.rot, orbit.color, .31);
      const a = reduced ? orbit.phase : now * orbit.speed + orbit.phase;
      const [ex, ey] = ellipsePoint(atomX, atomY, orbit.rx, orbit.ry, a, orbit.rot);
      glowDot(ex, ey, 5.3 * scale, orbit.color, .94);
      // tiny opposite electron for a richer premium field
      const [ex2, ey2] = ellipsePoint(atomX, atomY, orbit.rx, orbit.ry, a + Math.PI, orbit.rot);
      glowDot(ex2, ey2, 2.4 * scale, palette.white, .32);
    }

    drawNucleus(atomX, atomY, nucleus, now);

    if (!compact()) {
      ctx.save();
      ctx.font = '600 10px Inter, ui-sans-serif, system-ui, sans-serif';
      ctx.letterSpacing = '0.16em';
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(202,216,255,.40)';
      ctx.fillText('ELECTRON CLOUD', atomX, atomY + 128 * scale);
      ctx.restore();
    }
  }

  function draw(now, dt) {
    ctx.clearRect(0, 0, width, height);
    drawMolecularLattice(now);
    drawAmbientParticles(dt);
    drawPremiumAtom(now);
  }

  function animate(now) {
    const dt = now - last;
    last = now;
    draw(now, dt);
    frame = requestAnimationFrame(animate);
  }

  window.addEventListener('pointermove', (event) => {
    pointerX = event.clientX;
    pointerY = event.clientY;
    if (dragging) {
      targetX = Math.max(90, Math.min(width - 90, event.clientX));
      targetY = Math.max(110, Math.min(height - 90, event.clientY));
    }
  }, { passive: true });

  window.addEventListener('pointerdown', (event) => {
    const radius = compact() ? 120 : 190;
    if (Math.hypot(event.clientX - atomX, event.clientY - atomY) <= radius) {
      dragging = true;
      targetX = event.clientX;
      targetY = event.clientY;
      document.body.classList.add('atom-dragging');
    }
  }, { passive: true });

  window.addEventListener('pointerup', () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove('atom-dragging');
  }, { passive: true });

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 150);
  }, { passive: true });

  resize();
  if (!reduced) frame = requestAnimationFrame(animate);

  document.addEventListener('visibilitychange', () => {
    if (reduced) return;
    if (document.hidden) cancelAnimationFrame(frame);
    else {
      last = performance.now();
      frame = requestAnimationFrame(animate);
    }
  });
})();
