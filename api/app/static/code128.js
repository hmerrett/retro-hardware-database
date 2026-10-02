// Reading a Code 128 barcode from a camera frame, for the browsers that cannot do
// it themselves (MANUAL §14, "Scanners"). Most phones can: Chrome on Android has a
// barcode detector built in, and app.js uses it where there is one. This is the
// rest -- an iPhone, mostly -- and is loaded only when that is what is needed.
//
// Written here rather than vendored, unlike the QR decoder: a barcode is a row of
// bars, and reading one along a line is a page of arithmetic that can be read in
// full, where a vendored reader would be hundreds of kilobytes that cannot.
//
// It reads along a few lines across the middle of the frame, both ways round, and
// takes the first that makes a whole barcode with a checksum that adds up. Each
// symbol is measured against its own width, so a label a little skewed or at an
// angle to the camera still reads; one held at forty-five degrees will not, and
// turning the phone is the answer.
(function () {
  'use strict';

  // Bar and space widths in modules, bar first: symbol n is PATTERNS[n]. The same
  // table as app/barcode.py, and the suite holds the two to each other.
  const PATTERNS = [
    '212222', '222122', '222221', '121223', '121322', '131222', '122213', '122312',
    '132212', '221213', '221312', '231212', '112232', '122132', '122231', '113222',
    '123122', '123221', '223211', '221132', '221231', '213212', '223112', '312131',
    '311222', '321122', '321221', '312212', '322112', '322211', '212123', '212321',
    '232121', '111323', '131123', '131321', '112313', '132113', '132311', '211313',
    '231113', '231311', '112133', '112331', '132131', '113123', '113321', '133121',
    '313121', '211331', '231131', '213113', '213311', '213131', '311123', '311321',
    '331121', '312113', '312311', '332111', '314111', '221411', '431111', '111224',
    '111422', '121124', '121421', '141122', '141221', '112214', '112412', '122114',
    '122411', '142112', '142211', '241211', '221114', '413111', '241112', '134111',
    '111242', '121142', '121241', '114212', '124112', '124211', '411212', '421112',
    '421211', '212141', '214121', '412121', '111143', '111341', '131141', '114113',
    '114311', '411113', '411311', '113141', '114131', '311141', '411131', '211412',
    '211214', '211232', '2331112',
  ];
  const STOP = 106;
  const STARTS = { 103: 'A', 104: 'B', 105: 'C' };
  const SHAPES = PATTERNS.map(function (p) { return p.split('').map(Number); });

  // The symbol six runs make, or -1: whichever pattern they are nearest once scaled
  // to eleven modules, if they are near enough to be that one and no other.
  function symbol(runs, at) {
    let sum = 0;
    for (let k = 0; k < 6; k++) sum += runs[at + k];
    if (!sum) return -1;
    const unit = sum / 11;
    let best = -1, bestErr = 1e9, second = 1e9;
    for (let n = 0; n < 106; n++) {
      const p = SHAPES[n];
      let err = 0;
      for (let k = 0; k < 6; k++) err += Math.abs(runs[at + k] / unit - p[k]);
      if (err < bestErr) { second = bestErr; bestErr = err; best = n; } else if (err < second) second = err;
    }
    return bestErr < 1.6 && second - bestErr > 0.4 ? best : -1;
  }

  function isStop(runs, at) {
    if (at + 7 > runs.length) return false;
    let sum = 0;
    for (let k = 0; k < 7; k++) sum += runs[at + k];
    const unit = sum / 13, p = SHAPES[STOP];
    let err = 0;
    for (let k = 0; k < 7; k++) err += Math.abs(runs[at + k] / unit - p[k]);
    return err < 1.8;
  }

  // The words a run of symbols says, or null when the checksum does not add up.
  function words(values) {
    if (values.length < 3) return null;
    const check = values[values.length - 1];
    let total = values[0];
    for (let k = 1; k < values.length - 1; k++) total += k * values[k];
    if (total % 103 !== check) return null;
    let set = STARTS[values[0]], out = '';
    for (let k = 1; k < values.length - 1; k++) {
      const v = values[k];
      if (set === 'C') {
        if (v < 100) out += (v < 10 ? '0' : '') + v;
        else if (v === 100) set = 'B';
        else if (v === 101) set = 'A';
      } else if (v === 99) set = 'C';
      else if (v === 100 && set === 'A') set = 'B';
      else if (v === 101 && set === 'B') set = 'A';
      else if (v < 96) out += String.fromCharCode(set === 'A' && v >= 64 ? v - 64 : v + 32);
    }
    return out;
  }

  // Light and dark runs along one line, light first: runs[0] is the white before the
  // first bar, which has to be wide enough to be a quiet zone.
  function runsAlong(line, cut) {
    const runs = [];
    let dark = false, n = 0;
    for (let x = 0; x < line.length; x++) {
      const d = line[x] < cut;
      if (d === dark) { n++; continue; }
      runs.push(n);
      dark = d;
      n = 1;
    }
    runs.push(n);
    return runs;
  }

  function decode(runs) {
    for (let at = 1; at + 6 <= runs.length; at += 2) {
      const start = symbol(runs, at);
      if (!(start in STARTS)) continue;
      const unit = (runs[at] + runs[at + 1] + runs[at + 2] + runs[at + 3] + runs[at + 4] + runs[at + 5]) / 11;
      if (runs[at - 1] < unit * 5) continue;
      const values = [start];
      let k = at + 6;
      while (k + 6 <= runs.length) {
        if (isStop(runs, k)) {
          const said = words(values);
          if (said) return said;
          break;
        }
        const v = symbol(runs, k);
        if (v < 0) break;
        values.push(v);
        k += 6;
      }
    }
    return null;
  }

  // ImageData in, the barcode's text out, or null. Lines from near the top of the
  // frame to near the bottom, because a small label's bars run along its foot; and
  // three cuts between light and dark on each, because a blurred bar is thinner or
  // fatter depending on where the cut falls, and one of the three is nearly right.
  window.rhdbCode128 = function (image) {
    const w = image.width, h = image.height, px = image.data;
    const line = new Float32Array(w);
    const LINES = 24;
    for (let s = 0; s < LINES; s++) {
      const y = Math.round(h * (0.08 + 0.84 * s / (LINES - 1)));
      let lo = 255, hi = 0;
      for (let x = 0; x < w; x++) {
        const o = (y * w + x) * 4;
        const l = 0.299 * px[o] + 0.587 * px[o + 1] + 0.114 * px[o + 2];
        line[x] = l;
        if (l < lo) lo = l;
        if (l > hi) hi = l;
      }
      if (hi - lo < 50) continue;
      const back = line.slice().reverse();
      for (const share of [0.5, 0.4, 0.6]) {
        const cut = lo + (hi - lo) * share;
        const said = decode(runsAlong(line, cut)) || decode(runsAlong(back, cut));
        if (said) return said;
      }
    }
    return null;
  };
})();
