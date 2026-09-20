/* Printing a label on a NIIMBOT over Web Bluetooth.
 *
 * Ours rather than the library's. NiimBlueLib is the reference implementation of
 * this protocol and is what the constants below were read out of -- but it is
 * published as CommonJS, so using it would mean a bundler, and this project has
 * been careful not to need one (ADR-0013, ADR-0026). What is actually needed here
 * is one printer family, one page, no ribbon and no templates, which is a few
 * hundred lines rather than a dependency tree.
 *
 * Derived from NIIMBLUE / niimbluelib (MIT, https://github.com/MultiMote/niimbluelib):
 * the packet framing, the command numbers, the B1 print sequence and the way a row
 * of pixels is counted are all theirs. The mistakes are ours.
 *
 * Covers the B1 and the B21: a 384-dot head at 203dpi, fed top first.
 *
 * Not the B18, which this used to claim and should not have. It is the same family
 * by name and a different printer by every number that matters here -- a 96-dot
 * head, a twelfth of the width, and a page fed sideways, so a label drawn for a B1
 * would come out of it as a stripe. Read off niimbluelib's model library rather
 * than assumed from the name.
 *
 * Other models differ in the print sequence rather than in the framing, which is
 * why this says which ones it is for instead of pretending to be general.
 */

/* [0x55, 0x55, CMD, LEN, DATA..., CHECKSUM, 0xAA, 0xAA] where the checksum is the
   command, the length and every byte of the data, exclusive-ored together. */
const HEAD = [0x55, 0x55];
const TAIL = [0xaa, 0xaa];

const TX = {
  printStart: 0x01,
  pageStart: 0x03,
  setPageSize: 0x13,
  setDensity: 0x21,
  setLabelType: 0x23,
  printBitmapRowIndexed: 0x83,
  printEmptyRow: 0x84,
  printBitmapRow: 0x85,
  printStatus: 0xa3,
  pageEnd: 0xe3,
  printEnd: 0xf3,
};

const RX = {
  printStart: 0x02,
  pageStart: 0x04,
  setPageSize: 0x14,
  setDensity: 0x31,
  setLabelType: 0x33,
  printStatus: 0xb3,
  pageEnd: 0xe4,
  printEnd: 0xf4,
};

/* The service every NIIMBOT serves. The characteristic inside it is found by what
   it can do rather than by its own id, which is how the reference client does it
   and is why this works across a family whose characteristics differ. */
const SERVICE = "e7810a71-73ae-499d-8c15-faa9aef0c3f2";

/** What to ask the browser to show.
 *
 * Narrow first: named like a NIIMBOT, or advertising the service, which on a
 * desktop browser is a chooser with the printer in it and nothing else.
 *
 * Then everything, because the narrow one cannot be relied on. Filters behave
 * differently in Bluefy -- the only browser that reaches Bluetooth on iOS -- and
 * differently enough that the Web Bluetooth group has an open report about it with
 * no answer in it. A chooser listing every radio in the room is a poor thing to
 * offer somebody; a chooser listing nothing at all, on the one platform where we
 * cannot debug it, is worse.
 *
 * `optionalServices` is what makes the service reachable afterwards, and is
 * required in both shapes: without it the connection succeeds and every service on
 * the device is invisible.
 */
function chooser(showEverything) {
  if (showEverything || onApple()) {
    return { acceptAllDevices: true, optionalServices: [SERVICE] };
  }
  return {
    filters: [{ namePrefix: NAME_PREFIX }, { services: [SERVICE] }],
    optionalServices: [SERVICE],
  };
}

/** Whether this is the platform whose filtering cannot be trusted.
 *
 * Sniffing the browser, which is nearly always the wrong thing to do and is the
 * right thing here: this is not a guess about what a browser can do -- it is a
 * known defect in one implementation, on the one platform that has no second
 * implementation to offer instead. The cost of being wrong is a longer list. */
function onApple() {
  return /iPhone|iPad|iPod/.test(navigator.userAgent);
}

/** What the browser can see, without printing anything.
 *
 * For the case this could not otherwise get out of: a chooser that lists nothing,
 * on hardware nobody debugging it can hold. It connects, reads out every service
 * and characteristic, and prints none of them -- so the answer to "is it even
 * there" stops being a guess made from two rooms away.
 */
export async function probe() {
  if (!navigator.bluetooth) throw new Error("this browser has no Web Bluetooth at all");
  const device = await navigator.bluetooth.requestDevice(chooser(true));
  const report = { name: device.name || "(unnamed)", id: device.id, services: [] };
  const server = await device.gatt.connect();
  try {
    for (const service of await server.getPrimaryServices()) {
      const found = { uuid: service.uuid, characteristics: [] };
      for (const c of await service.getCharacteristics()) {
        const can = Object.keys(c.properties).filter((k) => c.properties[k]);
        found.characteristics.push({ uuid: c.uuid, can });
      }
      report.services.push(found);
    }
  } finally {
    server.disconnect();
  }
  report.usable = report.services.some((s) =>
    s.characteristics.some((c) => c.can.includes("notify") && c.can.includes("writeWithoutResponse"))
  );
  return report;
}

/* A NIIMBOT *serves* that service and does not necessarily *advertise* it, which
   are different things and the difference is the whole of why an earlier version
   of this found nothing: an advertisement has 31 bytes to fit everything in, so
   most of these printers spend them on their name -- "B1-G327071185" -- and leave
   the service to be discovered after connecting.
   A chooser filtered on the service alone is therefore an empty chooser, with
   nothing on screen to say the printer was ever there. Matching the name as well
   is what the reference client does, and it is the same reasoning: a filter that
   shows one device too many costs a glance, and one that shows none costs an
   afternoon. */
const NAME_PREFIX = "B";

/* The print head, in dots: a B1 and a B21 both have 384 of them. Used to decide
   how a row's black pixels are counted (see `rowCounts`) and to refuse a label too
   wide to come out whole. */
const PRINTHEAD = 384;

/* Between packets. The printer is a small microcontroller on a BLE link and will
   drop what it is sent while it is busy; the reference client waits too. */
const GAP_MS = 10;

/* Both of these are numbers out of the protocol's own tables, and both were once
   written here from the look of them rather than read off the table.
   `SINGLE_COLOUR = 1` was wrong: 1 is DoubleColor, and a two-colour page takes a
   different row format entirely -- so the printer accepted every packet, answered
   every one, and made nonsense of rows it had been told were something else. The
   trace was clean because nothing had gone wrong; it was answering a different
   question. */
const LABEL_WITH_GAPS = 1; /* LabelType.WithGaps: die-cut labels on a backing strip */
const SINGLE_COLOUR = 0; /* PageColorType.SingleColor */
const DENSITY = 3; /* of 1..5 on a B1, and its own default. */

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

function u16(n) {
  return [(n >> 8) & 0xff, n & 0xff];
}

function packet(command, data) {
  const body = data || [];
  let checksum = command ^ body.length;
  for (const byte of body) checksum ^= byte;
  return new Uint8Array([...HEAD, command, body.length, ...body, checksum, ...TAIL]);
}

/* --- the label as dots ---------------------------------------------------- */

/** One row's worth of bytes, most significant bit first, and a black pixel is a 1. */
function packRow(pixels, width, y, bytesPerRow) {
  const row = new Uint8Array(bytesPerRow);
  let black = 0;
  for (let x = 0; x < width; x++) {
    /* The label is one bit deep already, so any pixel that is not white is ink.
       Reading the red channel is enough to tell which. */
    if (pixels[(y * width + x) * 4] < 128) {
      row[x >> 3] |= 1 << (7 - (x & 7));
      black++;
    }
  }
  return { row, black };
}

/* A row with no more than this many black dots is not sent as a bitmap at all --
   it is sent as a list of where they are. Not an optimisation: the reference
   implementation's note against the indexed packet is "printer powers off if black
   pixel count > 6", and a row of two dots sent the other way is what a rule with no
   stated reason looks like from the outside. */
const FEW = 6;

/** Where the black dots are, as the indexed packet lists them: each position two
 * bytes, big endian, counting from the most significant bit of each byte -- the
 * same way `packRow` put them in. */
function pixelIndexes(row) {
  const out = [];
  for (let bytePos = 0; bytePos < row.length; bytePos++) {
    for (let bitPos = 0; bitPos < 8; bitPos++) {
      if (row[bytePos] & (1 << (7 - bitPos))) out.push(...u16(bytePos * 8 + bitPos));
    }
  }
  return out;
}

/** How many black pixels a row packet declares, in the shape the printer wants.
 *
 * Three counts, one per third of the head, when the row fits in three chunks --
 * otherwise the total, big-endian, in the last two of the three bytes. Straight
 * out of the reference implementation; the printer uses it to pace itself. */
function rowCounts(row, black) {
  const chunk = Math.floor(PRINTHEAD / 8 / 3);
  if (row.length > chunk * 3) {
    const [high, low] = u16(black);
    return [0, low, high];
  }
  const parts = [0, 0, 0];
  row.forEach((value, byteN) => {
    const which = Math.floor(byteN / chunk);
    if (which > 2) return;
    for (let bit = 0; bit < 8; bit++) if (value & (1 << bit)) parts[which]++;
  });
  return parts;
}

/** A PNG blob as rows of dots. */
export async function toRows(blob) {
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(bitmap, 0, 0);
  const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
  const bytesPerRow = Math.ceil(bitmap.width / 8);
  const rows = [];
  for (let y = 0; y < bitmap.height; y++) rows.push(packRow(data, bitmap.width, y, bytesPerRow));
  return { rows, width: bytesPerRow * 8, height: bitmap.height };
}

/* --- talking to the printer ----------------------------------------------- */

class Printer {
  constructor(characteristic) {
    this.channel = characteristic;
    this.waiting = null;
    /* Every packet out and every packet in, in order. The printer is otherwise a
       box that takes bytes and produces paper, and when the paper is wrong there
       is nothing to look at -- which is how two wrong diagnoses were made from a
       photograph before this existed. */
    this.trace = [];
    this.counts = { empty: 0, indexed: 0, bitmap: 0 };
    characteristic.addEventListener("characteristicvaluechanged", (event) => {
      this.heard(new Uint8Array(event.target.value.buffer));
    });
  }

  note(line) {
    /* The rows are thousands of near-identical lines; the first two of each kind
       say everything the thousandth would. */
    if (this.trace.length < 400) this.trace.push(line);
  }

  /** A notification. Only the command byte matters here: this asks the printer to
      do things and waits to be told it did, and never reads an answer back. */
  heard(bytes) {
    this.note(`  <- ${[...bytes].map((b) => b.toString(16).padStart(2, "0")).join(" ")}`);
    if (bytes.length < 7 || bytes[0] !== 0x55 || bytes[1] !== 0x55) return;
    const command = bytes[2];
    if (this.waiting && this.waiting.expect === command) {
      const done = this.waiting;
      this.waiting = null;
      done.resolve(bytes);
    }
  }

  async send(command, data, expect, timeoutMs = 5000) {
    await sleep(GAP_MS);
    const bytes = packet(command, data);
    this.note(`-> 0x${command.toString(16)} len ${(data || []).length} (packet ${bytes.length})`);
    let wrote;
    try {
      wrote = this.channel.writeValueWithoutResponse(bytes.buffer);
    } catch (e) {
      /* A packet larger than the negotiated MTU throws here rather than being
         split, and a row of 384 dots is 61 bytes against a default MTU of 23. */
      this.note(`   !! the write itself was refused: ${e.message || e}`);
      throw e;
    }
    if (expect === undefined) return wrote;
    const heard = new Promise((resolve, reject) => {
      this.waiting = { expect, resolve, reject };
      setTimeout(() => {
        if (this.waiting && this.waiting.expect === expect) {
          this.waiting = null;
          reject(new Error("the printer did not answer — is it awake?"));
        }
      }, timeoutMs);
    });
    await wrote;
    return heard;
  }

  /** The B1 family's sequence. The order is the printer's, not ours. */
  async print(page, say) {
    await this.send(TX.setDensity, [DENSITY], RX.setDensity);
    await this.send(TX.setLabelType, [LABEL_WITH_GAPS], RX.setLabelType);
    await this.send(TX.printStart, [...u16(1), 0, 0, 0, 0, SINGLE_COLOUR], RX.printStart);
    await this.send(TX.pageStart, [], RX.pageStart);
    await this.send(
      TX.setPageSize,
      [...u16(page.height), ...u16(page.width), ...u16(1)],
      RX.setPageSize
    );

    for (let y = 0; y < page.rows.length; y++) {
      const { row, black } = page.rows[y];
      if (black === 0) {
        /* A blank row is said rather than sent: it is three bytes instead of fifty,
           and a label is mostly blank. */
        this.counts.empty++;
        await this.send(TX.printEmptyRow, [...u16(y), 1]);
      } else if (black <= FEW) {
        this.counts.indexed++;
        /* A handful of dots goes as a list of where they are. This is the packet
           that was missing when the first real label came out as two bands at the
           edges of the paper: a rule, in the printer, that this did not know about. */
        await this.send(TX.printBitmapRowIndexed, [
          ...u16(y),
          ...rowCounts(row, black),
          1,
          ...pixelIndexes(row),
        ]);
      } else {
        this.counts.bitmap++;
        await this.send(TX.printBitmapRow, [...u16(y), ...rowCounts(row, black), 1, ...row]);
      }
      if (y % 24 === 0) say(`printing… ${Math.round((y / page.rows.length) * 100)}%`);
    }

    this.note(
      `rows: ${this.counts.bitmap} bitmap, ${this.counts.indexed} indexed, ` +
        `${this.counts.empty} empty, ${page.rows.length} in the image`
    );
    await this.send(TX.pageEnd, [], RX.pageEnd, 10000);
    say("waiting for the paper…");
    /* Asked until it stops answering "not yet". The printer moves the label past
       the head after the page ends, and cutting the connection before then leaves
       it half out. */
    for (let tries = 0; tries < 40; tries++) {
      await sleep(300);
      try {
        await this.send(TX.printStatus, [1], RX.printStatus, 2000);
        break;
      } catch (e) {
        /* Still busy. */
      }
    }
    await this.send(TX.printEnd, [], RX.printEnd, 10000);
  }
}

/** A pattern whose printed shape says what the printer did to it.
 *
 * Every corner is different and every edge is different, so whatever comes out
 * says which way up it went, which way round, whether it was stretched and by how
 * much -- in one label, from a photograph, without anybody having to describe it.
 *
 *   - a solid square in the TOP LEFT, a third the height
 *   - a single thin line down the LEFT edge, full height
 *   - a thick bar along the TOP edge, full width
 *   - a ladder of five rungs down the RIGHT edge, evenly spaced
 *
 * Read it like this: the square marks the origin, the thick bar marks the first
 * row printed, the thin line marks the first column, and the rungs count. Five
 * rungs squashed into a corner is a scale; rungs along the bottom is a rotation;
 * a square in the top right is a mirror.
 */
export function pattern(width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const c = canvas.getContext("2d");
  c.fillStyle = "#fff";
  c.fillRect(0, 0, width, height);
  c.fillStyle = "#000";
  const unit = Math.round(height / 3);
  c.fillRect(0, 0, unit, unit); /* the origin */
  c.fillRect(0, 0, 2, height); /* the first column */
  c.fillRect(0, 0, width, 8); /* the first row */
  for (let n = 0; n < 5; n++) {
    const y = Math.round((height / 6) * (n + 1));
    c.fillRect(width - unit, y, unit, 4);
  }
  return canvas;
}

/** Print that pattern, at the size of the given stock. */
export async function printPattern(mediaWidth, mediaHeight, say) {
  const canvas = pattern(mediaWidth, mediaHeight);
  const blob = await new Promise((done) => canvas.toBlob(done, "image/png"));
  return print(blob, "", say);
}

/** The same, and hand back everything that was said on the wire. */
export async function tracePattern(mediaWidth, mediaHeight, say) {
  const canvas = pattern(mediaWidth, mediaHeight);
  const blob = await new Promise((done) => canvas.toBlob(done, "image/png"));
  const lines = [`image: ${canvas.width} x ${canvas.height}`];
  try {
    const trace = await print(blob, "", say);
    return lines.concat(trace || []);
  } catch (e) {
    return lines.concat([`FAILED: ${e.message || e}`], e.trace || []);
  }
}

/* --- what the button calls ------------------------------------------------ */

/**
 * Print one label. `blob` is the PNG the register rendered, `say` reports
 * progress to whoever pressed the button.
 *
 * The device chooser is the browser's own, and it only appears in answer to a
 * click — which is why this is called from the button's handler and not from
 * anything that runs on its own.
 */
export async function print(blob, media, say, showEverything) {
  const page = await toRows(blob);
  if (page.width > PRINTHEAD) {
    throw new Error(`that label is ${page.width} dots wide and the head is ${PRINTHEAD}`);
  }
  say("choose your printer…");
  let device;
  try {
    device = await navigator.bluetooth.requestDevice(chooser(showEverything));
  } catch (e) {
    /* NotFoundError is both "you pressed cancel" and "there was nothing to pick",
       and the browser will not say which. If the narrow chooser came up empty the
       caller is offered the wide one, which is the only thing that reliably works
       on iOS -- see `chooser`. */
    if (e && e.name === "NotFoundError" && !showEverything) {
      const nothing = new Error("no printer in the list");
      nothing.showEverything = true;
      throw nothing;
    }
    throw e;
  }
  say("connecting…");
  let server;
  try {
    server = await device.gatt.connect();
  } catch (e) {
    /* Nearly always the same thing: a BLE printer talks to one thing at a time,
       and the NIIMBOT app is still holding it. Backgrounding that app is not
       enough -- it has to be closed. */
    throw new Error("could not connect — close the NIIMBOT app if it is open, then try again");
  }
  const channel = await findChannel(server);
  if (!channel) {
    server.disconnect();
    /* Naming what was picked, because in the wide chooser it is entirely possible
       to have picked a pair of headphones. */
    throw new Error(`${device.name || "that device"} is not a NIIMBOT — nothing on it to print with`);
  }
  await channel.startNotifications();
  const printer = new Printer(channel);
  try {
    await printer.print(page, say);
    say(`printed on ${device.name || "the printer"}`);
    return printer.trace;
  } catch (e) {
    e.trace = printer.trace;
    throw e;
  } finally {
    /* Always, including after a failure: a printer left connected will not pair
       with anything else, and the next attempt would fail for a reason that has
       nothing to do with what went wrong the first time. */
    try {
      server.disconnect();
    } catch (e) {
      /* Already gone. */
    }
  }
}

/** The characteristic to talk on, found by what it can do rather than by its id --
    the family's characteristics differ and their capabilities do not. */
async function findChannel(server) {
  const services = await server.getPrimaryServices();
  for (const service of services) {
    for (const characteristic of await service.getCharacteristics()) {
      const can = characteristic.properties;
      if (can.notify && can.writeWithoutResponse) return characteristic;
    }
  }
  return null;
}
