# Making the detector boot floppy

One MS-DOS boot floppy that detects a retro PC's hardware and writes a report
named after the machine's asset id (`A:\RH-0005.TXT`). Boot it, type
`DETECT RH-0005`, carry the floppy to the next machine, then read the reports
back and import them. Once you have a report, see `../imports/README.md` for the
import step.

## Why this design (read this first)

The old disk booted from **FreeDOS**, whose kernel needs a **386** — so it
wouldn't even boot on the 8088 (IBM 5150) or 286 (Amstrad PC2286). Worse, the
`HWINFO16.EXE` we carried for "8086/286" was mislabelled: the resurrected
**HWiNFO for DOS v6.x needs a 386, ~550 KB free conventional RAM, and XMS** —
for *both* its binaries. So HWiNFO can never run on an XT (no XMS at all) or a
286, and the 512 KB target is out. That whole sub-386 tier needs a different,
lighter tool.

So:

- **Boot layer → MS-DOS / PC-DOS.** Real-mode DOS boots on everything from the
  8088 up, which is the actual fix for "won't boot below a 386". HWiNFO runs
  fine under MS-DOS on the 386+ machines.
- **Detector below a 386 → MSD** (Microsoft Diagnostics, ships with MS-DOS 6.x).
  `MSD /P <file>` writes a full report to a named file with no prompts — tiny
  (~155 KB), runs on an 8088 in 512 KB, and needs no XMS.
- **Detector at 386+ → HWiNFO**, as before (richer detail; the importer already
  knows its format).

One 720 KB disk holds all of it (budget below), so it's a single disk for the
whole fleet.

## What goes on the disk

The base is a **stripped MS-DOS 5.0** boot disk (`dos5.img`, 720 KB). The 32
install/setup files it shipped with (SETUP, FORMAT, FDISK, EMM386, the compressed
`*.SY_`/`*.CO_` files, etc.) were removed, keeping only the bootable system, and
the config + batch files were embedded — leaving **~590 KB free** for detectors.

Already in `dos5.img`:

- `IO.SYS`, `MSDOS.SYS`, `COMMAND.COM` — the bootable MS-DOS 5.0 system (~118 KB)
- `CONFIG.SYS` — sets `FILES`/`BUFFERS` (no HIMEM needed — see below)
- `AUTOEXEC.BAT` — sets `PATH`, prints the `DETECT RH-nnnn` banner
- `DETECT.BAT` — `DETECT RH-nnnn [3|6]`: picks the detector (CHOICE menu if
  present, else defaults to 386+)
- `DET386.BAT` — runs `HWINFO -r A:\<id>.TXT`
- `DETMSD.BAT` — runs `MSD /P A:\<id>.TXT`

Still to add (you supply — I can't redistribute these, and **MS-DOS 5.0 ships
neither MSD nor CHOICE**):

- `HWINFO.EXE` (~197 KB) + `CWSDPMI.EXE` (~33 KB) — from the HWiNFO for DOS v6.x
  package; the 386+ detector. CWSDPMI is what gives HWiNFO its memory (it drives
  the 386's extended RAM itself), so **no HIMEM/XMS is required**.
- `MSD.EXE` (~155 KB) — Microsoft Diagnostics from a **DOS 6.x** set (runs fine
  under 5.0); the 8088/286 detector.
- `HIMEM.SYS` — **not needed** (CWSDPMI covers the 386's memory). Only add it —
  `DEVICE=A:\HIMEM.SYS` + `DOS=HIGH` in `CONFIG.SYS` — if a memory-tight 386 ever
  reports "not enough memory".
- `CHOICE.COM` (~2 KB, optional) — from a DOS 6.x set, only if you want the 3/6
  menu. Without it, `DETECT RH-nnnn` defaults to HWiNFO; pass `6` by hand for a
  286/8088.

Budget: 118 (system) + ~3 (our files) + 197 + 33 + 155 + 2 ≈ **508 KB of
~730 KB** — ~220 KB spare.

> **`HWINFO16.EXE` is gone** — it needs a 386 too, so it never helped the 16-bit
> machines. Below a 386 we use MSD instead.

## On the machine

Boot the floppy. At the `A:\>` prompt type the asset id from the case label:

```
DETECT RH-0005
```

With `CHOICE.COM` present it asks **3** (386+, HWiNFO) or **6** (286/8088, MSD),
defaulting to 3 after 5 s. On plain MS-DOS 5.0 (no CHOICE) it goes straight to
386+/HWiNFO — so pass `6` by hand on a 286/8088: `DETECT RH-0005 6`. Either way it
writes `A:\RH-0005.TXT`; move the floppy to the next machine and the reports pile up.

Why typed, not prompted: MS-DOS's `COMMAND.COM` has no `SET /P` (that was a
FreeDOS feature), so the id comes in as a batch argument — no extra utility
needed. If MSD hangs mid-scan, reboot and run `MSD /I /P A:\RH-0005.TXT` (skips
the initial hardware probe); on odd video add `/B` for mono.

## 1. Add the detectors to the image (Linux)

Prereqs: `sudo apt install mtools` and `pip install greaseweazle`.

`dos5.img` here is already stripped and carries the config + batch files, so you
only add the binaries. `mtools` writes into the FAT with no mount:

```
mcopy -o -i dos5.img /path/to/HWINFO.EXE /path/to/CWSDPMI.EXE ::/
mcopy -o -i dos5.img /path/to/MSD.EXE ::/
mcopy -o -i dos5.img /path/to/CHOICE.COM ::/      # optional (enables the 3/6 menu)
mdir -i dos5.img ::/                              # check the list + free space
```

If you edit the batch/config files, give them DOS (CRLF) endings first
(`unix2dos bootdisk/*.BAT bootdisk/CONFIG.SYS`) and re-`mcopy` them.

Starting from a fresh 5.0 disk instead? Strip it the same way — keep only
`IO.SYS`, `MSDOS.SYS`, `COMMAND.COM`, delete the rest — then `mcopy` the six repo
files (`CONFIG.SYS`, `AUTOEXEC.BAT`, `DETECT.BAT`, `DET386.BAT`, `DETMSD.BAT`) in.

## 2. Flash it with Greaseweazle

Drive on the 34-pin ribbon, a 720 KB (3.5" DD) disk inserted:

```
gw write --format ibm.720 dos5.img
```

Match the format to the target drive: `ibm.720` (3.5" DD), `ibm.1440` (3.5" HD),
`ibm.1200` (5.25" HD), `ibm.360` (5.25" DD). `gw write --help` lists them.

> **Media note:** a stock **IBM 5150 has only 360 KB 5.25" drives** and can't
> read a 720 KB 3.5" disk. For a 5.25"-only XT, build a **360 KB MSD-only**
> variant: same files but **drop `HWINFO.EXE` + `CWSDPMI.EXE`** (they don't fit
> 360 KB and aren't needed sub-386), and boot straight into the MSD path
> (`DETECT RH-nnnn 6`).

## 3. Run each machine, then read the reports back

Boot each PC, `DETECT` its asset id, move on. Bring the floppy back, image it,
and pull every report off at once (importer takes upper- or lower-case `.TXT`):

```
gw read --format ibm.720 back.img
mcopy -i back.img "::/RH-*.TXT" ../imports/
```

## 4. Import — it proposes, you confirm

```
python ../scripts/import_report.py            # every report in imports/
python ../scripts/import_report.py RH-0005    # just one
```

`import_report.py` now reads **both** formats and auto-detects which: HWiNFO's
CP437 box report and MSD's plain-ASCII report, mapping both onto the same
CPU / OS / BIOS / video / ports / drives fields. It only fills blanks and writes
nothing until you confirm. It can't see ISA cards, so keep cataloguing those by
hand. MSD gives less detail than HWiNFO (usually no chipset/CHS on these old
boards) — expect CPU, OS, BIOS, video type and COM/LPT counts.

> **Calibrate MSD parsing once:** the MSD parser is written to MSD's documented
> layout but hasn't been checked against a real dump. After your first MSD scan,
> eyeball the proposed fields against the raw `RH-nnnn.TXT`; if a label differs
> on your MSD version, the map is in `detect_msd()` in `scripts/import_report.py`.
