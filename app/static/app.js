(() => {
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

  // Motion chemistry background -------------------------------------------
  // Pure Canvas: no images, CDN, framework, or paid service required.
  if (document.body.dataset.chemMotion !== 'true') return;

  const canvas = document.createElement('canvas');
  canvas.className = 'chem-motion-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const compact = () => window.innerWidth < 700;
  let width = 0;
  let height = 0;
  let dpr = 1;
  let molecules = [];
  let frameId = 0;
  let last = performance.now();

  const formulas = ['C₆H₆', 'R–OH', 'R–NH₂', 'COOH', 'Nu:⁻', 'E⁺', 'CH₃', 'C=O'];
  const types = ['benzene', 'alcohol', 'carbonyl', 'amine'];

  const rand = (min, max) => Math.random() * (max - min) + min;

  function newMolecule(index, count) {
    const columns = compact() ? 2 : 4;
    const row = Math.floor(index / columns);
    const col = index % columns;
    const colW = width / columns;
    const rows = Math.ceil(count / columns);
    const rowH = height / Math.max(rows, 1);
    return {
      x: colW * (col + 0.5) + rand(-colW * 0.25, colW * 0.25),
      y: rowH * (row + 0.5) + rand(-rowH * 0.25, rowH * 0.25),
      vx: rand(-2.6, 2.6),
      vy: rand(-2.0, 2.0),
      rotation: rand(0, Math.PI * 2),
      vr: rand(-0.025, 0.025),
      scale: rand(compact() ? 0.62 : 0.72, compact() ? 0.94 : 1.15),
      type: types[index % types.length],
      formula: formulas[index % formulas.length],
      phase: rand(0, Math.PI * 2),
      alpha: rand(0.45, 0.88),
    };
  }

  function rebuild() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = compact() ? 7 : Math.min(16, Math.max(10, Math.round((width * height) / 95000)));
    molecules = Array.from({ length: count }, (_, i) => newMolecule(i, count));
    draw(performance.now(), 0);
  }

  function bond(x1, y1, x2, y2, doubleBond = false) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    if (!doubleBond) return;
    const dx = x2 - x1;
    const dy = y2 - y1;
    const length = Math.hypot(dx, dy) || 1;
    const ox = (-dy / length) * 4;
    const oy = (dx / length) * 4;
    ctx.beginPath();
    ctx.moveTo(x1 + ox, y1 + oy);
    ctx.lineTo(x2 + ox, y2 + oy);
    ctx.stroke();
  }

  function atom(x, y, label, accent = false) {
    ctx.beginPath();
    ctx.arc(x, y, label ? 12 : 4, 0, Math.PI * 2);
    ctx.fillStyle = accent ? 'rgba(168,119,45,.13)' : 'rgba(13,107,79,.10)';
    ctx.fill();
    if (!label) return;
    ctx.fillStyle = accent ? 'rgba(129,85,20,.40)' : 'rgba(13,91,68,.42)';
    ctx.font = '700 10px Inter, ui-sans-serif, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x, y + 0.5);
  }

  function drawBenzene() {
    const r = 34;
    const pts = Array.from({ length: 6 }, (_, i) => {
      const a = i * Math.PI / 3 - Math.PI / 6;
      return [Math.cos(a) * r, Math.sin(a) * r];
    });
    for (let i = 0; i < 6; i++) {
      const a = pts[i];
      const b = pts[(i + 1) % 6];
      bond(a[0], a[1], b[0], b[1], i % 2 === 0);
      atom(a[0], a[1], '');
    }
    ctx.beginPath();
    ctx.arc(0, 0, 17, 0, Math.PI * 2);
    ctx.stroke();
  }

  function drawAlcohol() {
    const pts = [[-48, 4], [-18, -12], [12, 4], [42, -12]];
    for (let i = 0; i < pts.length - 1; i++) bond(...pts[i], ...pts[i + 1]);
    pts.slice(0, 3).forEach(p => atom(...p, ''));
    atom(42, -12, 'O', true);
    bond(52, -18, 68, -30);
    atom(72, -33, 'H');
  }

  function drawCarbonyl() {
    atom(-28, 6, '');
    atom(0, -4, 'C');
    bond(-19, 2, -9, -2);
    bond(9, -8, 34, -25, true);
    atom(42, -30, 'O', true);
    bond(8, 2, 37, 16);
    atom(46, 21, '');
  }

  function drawAmine() {
    atom(-42, 12, '');
    atom(-15, -2, '');
    bond(-34, 8, -24, 3);
    bond(-5, -5, 20, -18);
    atom(28, -22, 'N', true);
    bond(37, -27, 52, -38);
    bond(37, -17, 55, -8);
    atom(58, -42, 'H');
    atom(61, -5, 'H');
  }

  function drawMolecule(m, now) {
    const breathe = 1 + Math.sin(now * 0.00065 + m.phase) * 0.035;
    ctx.save();
    ctx.translate(m.x, m.y);
    ctx.rotate(m.rotation);
    ctx.scale(m.scale * breathe, m.scale * breathe);
    ctx.globalAlpha = m.alpha;
    ctx.lineWidth = 1.25;
    ctx.lineCap = 'round';
    ctx.strokeStyle = 'rgba(13,107,79,.23)';

    if (m.type === 'benzene') drawBenzene();
    else if (m.type === 'alcohol') drawAlcohol();
    else if (m.type === 'carbonyl') drawCarbonyl();
    else drawAmine();

    ctx.rotate(-m.rotation * 0.35);
    ctx.font = '800 9px Inter, ui-sans-serif, system-ui, sans-serif';
    ctx.fillStyle = 'rgba(49,68,62,.24)';
    ctx.textAlign = 'center';
    ctx.fillText(m.formula, 0, 58);
    ctx.restore();
  }

  function drawReactionArrow(now) {
    if (compact()) return;
    const y = height * 0.75 + Math.sin(now * 0.00035) * 12;
    const x = width * 0.50;
    ctx.save();
    ctx.globalAlpha = 0.14;
    ctx.strokeStyle = 'rgba(168,119,45,.65)';
    ctx.fillStyle = 'rgba(168,119,45,.60)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 8]);
    ctx.beginPath();
    ctx.moveTo(x - 70, y);
    ctx.lineTo(x + 70, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(x + 70, y);
    ctx.lineTo(x + 58, y - 6);
    ctx.lineTo(x + 58, y + 6);
    ctx.closePath();
    ctx.fill();
    ctx.font = '600 10px Georgia, serif';
    ctx.textAlign = 'center';
    ctx.fillText('mechanism', x, y - 12);
    ctx.restore();
  }

  function draw(now, dt) {
    ctx.clearRect(0, 0, width, height);
    drawReactionArrow(now);
    molecules.forEach(m => {
      if (!prefersReducedMotion && dt) {
        const step = Math.min(dt, 40) / 16.67;
        m.x += m.vx * step;
        m.y += m.vy * step;
        m.rotation += m.vr * 0.12 * step;
        const margin = 95;
        if (m.x < -margin) m.x = width + margin;
        if (m.x > width + margin) m.x = -margin;
        if (m.y < -margin) m.y = height + margin;
        if (m.y > height + margin) m.y = -margin;
      }
      drawMolecule(m, now);
    });
  }

  function animate(now) {
    const dt = now - last;
    last = now;
    draw(now, dt);
    frameId = requestAnimationFrame(animate);
  }

  let resizeTimer;
  window.addEventListener('resize', () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(rebuild, 160);
  }, { passive: true });

  rebuild();
  if (!prefersReducedMotion) frameId = requestAnimationFrame(animate);

  document.addEventListener('visibilitychange', () => {
    if (prefersReducedMotion) return;
    if (document.hidden) {
      cancelAnimationFrame(frameId);
    } else {
      last = performance.now();
      frameId = requestAnimationFrame(animate);
    }
  });
})();
