'use strict';
/* ==========================================================================
   IPV · Fichas y Costos — Generador de códigos QR (sin dependencias)
   Autor: Ing. Yosvany Hernández Quintero
   ISO/IEC 18004 · modo byte (UTF-8) · corrección de errores M · versiones 1–10
   Uso: IPVQR.svg(texto, { size: 220, dark: '#183b34' }) → cadena SVG
   ========================================================================== */
(() => {
  // [ec por bloque, bloques g1, datos g1, bloques g2, datos g2] para nivel M
  const BLOCKS = [null, [10, 1, 16, 0, 0], [16, 1, 28, 0, 0], [26, 1, 44, 0, 0], [18, 2, 32, 0, 0], [24, 2, 43, 0, 0],
    [16, 4, 27, 0, 0], [18, 4, 31, 0, 0], [22, 2, 38, 2, 39], [22, 3, 36, 2, 37], [26, 4, 43, 1, 44]];
  const ALIGN = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]];
  const REMAINDER = [0, 0, 7, 7, 7, 7, 7, 0, 0, 0, 0];

  // Aritmética GF(256) con polinomio 0x11D
  const EXP = new Uint8Array(512), LOG = new Uint8Array(256);
  for (let i = 0, x = 1; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11D; }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);

  function generator(deg) {
    let g = [1];
    for (let i = 0; i < deg; i++) {
      const next = new Array(g.length + 1).fill(0);
      for (let j = 0; j < g.length; j++) { next[j] ^= g[j]; next[j + 1] ^= mul(g[j], EXP[i]); }
      g = next;
    }
    return g;
  }
  function ecc(data, deg) {
    const g = generator(deg), res = new Array(deg).fill(0);
    for (const byte of data) {
      const f = byte ^ res.shift(); res.push(0);
      for (let i = 0; i < deg; i++) res[i] ^= mul(g[i + 1], f);
    }
    return res;
  }

  function encode(text) {
    const bytes = [...new TextEncoder().encode(text)];
    let ver = 1;
    for (; ver <= 10; ver++) {
      const [, b1, d1, b2, d2] = BLOCKS[ver];
      const cap = b1 * d1 + b2 * d2;
      if (4 + (ver < 10 ? 8 : 16) + bytes.length * 8 <= cap * 8) break;
    }
    if (ver > 10) throw new Error('Texto demasiado largo para el código QR.');
    const [ecLen, b1, d1, b2, d2] = BLOCKS[ver];
    const capBytes = b1 * d1 + b2 * d2;
    const bits = [];
    const put = (v, n) => { for (let i = n - 1; i >= 0; i--) bits.push((v >>> i) & 1); };
    put(0b0100, 4); put(bytes.length, ver < 10 ? 8 : 16); bytes.forEach(b => put(b, 8));
    put(0, Math.min(4, capBytes * 8 - bits.length));
    while (bits.length % 8) bits.push(0);
    const data = [];
    for (let i = 0; i < bits.length; i += 8) data.push(parseInt(bits.slice(i, i + 8).join(''), 2));
    for (let pad = 0xEC; data.length < capBytes; pad ^= 0xEC ^ 0x11) data.push(pad);

    // Bloques + intercalado
    const blocks = [], eccs = [];
    let off = 0;
    for (let i = 0; i < b1 + b2; i++) {
      const len = i < b1 ? d1 : d2;
      const blk = data.slice(off, off + len); off += len;
      blocks.push(blk); eccs.push(ecc(blk, ecLen));
    }
    const out = [];
    for (let i = 0; i < Math.max(d1, d2); i++) blocks.forEach(b => { if (i < b.length) out.push(b[i]); });
    for (let i = 0; i < ecLen; i++) eccs.forEach(e => out.push(e[i]));
    return { ver, codewords: out };
  }

  function build(text) {
    const { ver, codewords } = encode(text);
    const n = ver * 4 + 17;
    const m = Array.from({ length: n }, () => new Array(n).fill(null)); // null = libre
    const fn = Array.from({ length: n }, () => new Array(n).fill(false));
    const set = (r, c, v) => { m[r][c] = v; fn[r][c] = true; };

    const finder = (r, c) => {
      for (let y = -1; y <= 7; y++) for (let x = -1; x <= 7; x++) {
        const rr = r + y, cc = c + x;
        if (rr < 0 || cc < 0 || rr >= n || cc >= n) continue;
        const inRing = y >= 0 && y <= 6 && x >= 0 && x <= 6 && (y === 0 || y === 6 || x === 0 || x === 6);
        const inCore = y >= 2 && y <= 4 && x >= 2 && x <= 4;
        set(rr, cc, inRing || inCore);
      }
    };
    finder(0, 0); finder(0, n - 7); finder(n - 7, 0);
    for (let i = 8; i < n - 8; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }
    const al = ALIGN[ver];
    const last = al.length - 1;
    al.forEach((r, i) => al.forEach((c, j) => {
      // Solo se omiten los tres que se solapan con los patrones de localización
      if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return;
      for (let y = -2; y <= 2; y++) for (let x = -2; x <= 2; x++) set(r + y, c + x, Math.max(Math.abs(x), Math.abs(y)) !== 1);
    }));
    // Reservar zonas de formato y versión
    for (let i = 0; i < 9; i++) { if (!fn[8][i]) set(8, i, false); if (!fn[i][8]) set(i, 8, false); }
    for (let i = 0; i < 8; i++) { set(8, n - 1 - i, false); set(n - 1 - i, 8, false); }
    set(n - 8, 8, true); // módulo oscuro
    if (ver >= 7) {
      let rem = ver;
      for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1F25);
      const vbits = (ver << 12) | rem;
      for (let i = 0; i < 18; i++) {
        const bit = ((vbits >>> i) & 1) === 1, a = n - 11 + (i % 3), b = Math.floor(i / 3);
        set(a, b, bit); set(b, a, bit);
      }
    }
    // Colocar datos en zigzag
    const bits = [];
    codewords.forEach(cw => { for (let i = 7; i >= 0; i--) bits.push((cw >>> i) & 1); });
    for (let i = 0; i < REMAINDER[ver]; i++) bits.push(0);
    let k = 0;
    for (let right = n - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let v = 0; v < n; v++) {
        for (let j = 0; j < 2; j++) {
          const c = right - j, upward = ((right + 1) & 2) === 0;
          const r = upward ? n - 1 - v : v;
          if (!fn[r][c]) { m[r][c] = bits[k++] === 1; }
        }
      }
    }
    // Máscara con menor penalización
    const MASKS = [(r, c) => (r + c) % 2 === 0, r => r % 2 === 0, (r, c) => c % 3 === 0, (r, c) => (r + c) % 3 === 0,
      (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0, (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
      (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0, (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0];
    const withFormat = (grid, mask) => {
      const g = grid.map(row => row.slice());
      const data = (0b00 << 3) | mask; // nivel M = 00
      let rem = data;
      for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
      const f = ((data << 10) | rem) ^ 0x5412;
      const bit = i => ((f >>> i) & 1) === 1;
      for (let i = 0; i <= 5; i++) g[i][8] = bit(i);
      g[7][8] = bit(6); g[8][8] = bit(7); g[8][7] = bit(8);
      for (let i = 9; i < 15; i++) g[8][14 - i] = bit(i);
      for (let i = 0; i < 8; i++) g[8][n - 1 - i] = bit(i);
      for (let i = 8; i < 15; i++) g[n - 15 + i][8] = bit(i);
      g[n - 8][8] = true;
      return g;
    };
    const penalty = g => {
      let p = 0;
      for (let pass = 0; pass < 2; pass++) for (let a = 0; a < n; a++) {
        let run = 1;
        for (let b = 1; b < n; b++) {
          const cur = pass ? g[b][a] : g[a][b], prev = pass ? g[b - 1][a] : g[a][b - 1];
          if (cur === prev) { run++; if (run === 5) p += 3; else if (run > 5) p++; } else run = 1;
        }
      }
      for (let r = 0; r < n - 1; r++) for (let c = 0; c < n - 1; c++) {
        const v = g[r][c]; if (v === g[r][c + 1] && v === g[r + 1][c] && v === g[r + 1][c + 1]) p += 3;
      }
      const pat = [true, false, true, true, true, false, true, false, false, false, false];
      const rev = pat.slice().reverse();
      for (let r = 0; r < n; r++) for (let c = 0; c <= n - 11; c++) {
        let h1 = true, h2 = true, v1 = true, v2 = true;
        for (let i = 0; i < 11; i++) {
          if (g[r][c + i] !== pat[i]) h1 = false; if (g[r][c + i] !== rev[i]) h2 = false;
          if (g[c + i][r] !== pat[i]) v1 = false; if (g[c + i][r] !== rev[i]) v2 = false;
        }
        p += 40 * (h1 + h2 + v1 + v2);
      }
      let dark = 0; g.forEach(row => row.forEach(v => { if (v) dark++; }));
      p += Math.floor(Math.abs(dark * 20 - n * n * 10) / (n * n)) * 10;
      return p;
    };
    let best = null, bestP = Infinity;
    for (let mask = 0; mask < 8; mask++) {
      const g = m.map((row, r) => row.map((v, c) => (fn[r][c] ? v : v !== MASKS[mask](r, c))));
      const final = withFormat(g, mask), p = penalty(final);
      if (p < bestP) { bestP = p; best = final; }
    }
    return best;
  }

  function svg(text, { size = 220, dark = '#183b34', light = '#ffffff', margin = 4 } = {}) {
    const g = build(text), n = g.length, total = n + margin * 2;
    let path = '';
    g.forEach((row, r) => row.forEach((v, c) => { if (v) path += `M${c + margin},${r + margin}h1v1h-1z`; }));
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${total}" width="${size}" height="${size}" shape-rendering="crispEdges" role="img" aria-label="Código QR"><rect width="100%" height="100%" fill="${light}"/><path d="${path}" fill="${dark}"/></svg>`;
  }

  const api = { build, svg };
  if (typeof window !== 'undefined') window.IPVQR = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
