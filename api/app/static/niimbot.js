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
 * Covers the B1 family (B1, B21, B18): a 48mm head at 203dpi. Other models differ
 * in the print sequence rather than in the framing, which is why this says which
 * ones it is for instead of pretending to be general.
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

/* The service every NIIMBOT advertises. The characteristic inside it is found by
   what it can do rather than by its own id, which is how the reference client does
   it and is why this works across a family whose characteristics differ. */
const SERVICE = "e7810a71-73ae-499d-8c15-faa9aef0c3f2";

/* The print head, in dots. Only used to decide how a row's black pixels are
   counted -- see `rowCounts`. */
const PRINTHEAD = 384;

/* Between packets. The printer is a small microcontroller on a BLE link and will
   drop what it is sent while it is busy; the reference client waits too. */
const GAP_MS = 10;

const LABEL_WITH_GAPS = 1; /* die-cut labels on a backing strip, which is the roll */
const SINGLE_COLOUR = 1;
const DENSITY = 3; /* of 1..5 on a B1. Darker costs battery and bleeds thin strokes. */

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
    characteristic.addEventListener("characteristicvaluechanged", (event) => {
      this.heard(new Uint8Array(event.target.value.buffer));
    });
  }

  /** A notification. Only the command byte matters here: this asks the printer to
      do things and waits to be told it did, and never reads an answer back. */
  heard(bytes) {
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
    const wrote = this.channel.writeValueWithoutResponse(packet(command, data).buffer);
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
        await this.send(TX.printEmptyRow, [...u16(y), 1]);
      } else {
        await this.send(TX.printBitmapRow, [...u16(y), ...rowCounts(row, black), 1, ...row]);
      }
      if (y % 24 === 0) say(`printing… ${Math.round((y / page.rows.length) * 100)}%`);
    }

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

/* --- what the button calls ------------------------------------------------ */

/**
 * Print one label. `blob` is the PNG the register rendered, `say` reports
 * progress to whoever pressed the button.
 *
 * The device chooser is the browser's own, and it only appears in answer to a
 * click — which is why this is called from the button's handler and not from
 * anything that runs on its own.
 */
export async function print(blob, media, say) {
  const page = await toRows(blob);
  if (page.width > PRINTHEAD) {
    throw new Error(`that label is ${page.width} dots wide and the head is ${PRINTHEAD}`);
  }
  say("choose your printer…");
  const device = await navigator.bluetooth.requestDevice({
    filters: [{ services: [SERVICE] }],
    optionalServices: [SERVICE],
  });
  say("connecting…");
  const server = await device.gatt.connect();
  const channel = await findChannel(server);
  if (!channel) throw new Error("that device does not look like a NIIMBOT");
  await channel.startNotifications();
  try {
    await new Printer(channel).print(page, say);
    say(`printed on ${device.name || "the printer"}`);
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
