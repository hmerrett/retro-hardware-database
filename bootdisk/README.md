# Making the detector boot floppy

**One 720 KB MS-DOS 6.22 floppy (`dos62.img`) that scans a machine with no typing.**
Power the PC on with the floppy in the drive; it boots, runs MSD automatically,
writes the report to the next free `SCANnn.TXT`, and tells you it's done. Switch
off, move the floppy to the next machine, repeat. Then read the reports off and
import them (`../imports/README.md`).

Boots and runs on everything from an 8088 up (MSD is real-mode and fits ~512 KB).
The 720 KB image works in any 3.5" drive (720K or 1.44M read it); the 5.25"-only
**IBM 5150 needs its own 360 KB build** — a different disk format, see Flash.

## On the machine

1. Insert the floppy, power on.
2. It boots and prints `Scanning this machine…`, runs MSD (~15 s), and saves
   `A:\SCANnn.TXT` (the first free number: `SCAN01`, then `SCAN02`, …).
3. It prints `DONE`. Power off and move the floppy to the next PC.

No id to type. DOS batch has no date/time/random variables, so reports are
auto-numbered; MSD stamps the real date/time and the machine's identity (CPU,
BIOS) *inside* each report, which is how you tell them apart at import. About 15
reports fit per disk — read them off and delete them to reuse it. If MSD ever
hangs mid-scan on a machine, reboot; if it repeats, edit `SCAN.BAT` to use
`MSD /I /P …` (skips the initial probe).

## Why MSD (and not HWiNFO)

HWiNFO needs a 386, plus a 226 KB device database, plus a DPMI host — ~460 KB that
forces a 1.44 MB disk, and it can't run on the 8088/286 at all. MSD is ~160 KB,
runs on an 8088, ships with MS-DOS 6.22, and writes a full report with a single
non-interactive switch (`MSD /P file`). The trade is detail: MSD reports CPU, OS,
BIOS, video type and COM/LPT counts, but not chipset or drive CHS. For this
catalogue that's the right call — simple beats thorough here.

(If you ever want HWiNFO's richer detail on a specific 386+ box, the manual path
still exists — see the end.)

## What's on `dos62.img`

Stripped MS-DOS 6.22, ready to flash (~412 KB free):

- `IO.SYS`, `MSDOS.SYS`, `COMMAND.COM` — bootable MS-DOS 6.22
- `MSD.EXE` — the detector (ships with 6.22)
- `AUTOEXEC.BAT` — runs `SCAN.BAT` on boot
- `SCAN.BAT` — picks the next free `SCANnn.TXT`, runs `MSD /P` into it
- `CONFIG.SYS` — `FILES`/`BUFFERS` only
- `DETECT.BAT` / `DET386.BAT` / `DETMSD.BAT` — the manual/named path (optional)

## Flash it with Greaseweazle

```
gw write --format ibm.720 dos62.img      # 3.5" 720K disk (1.44M drives read it too)
```

`gw write --help` lists formats. To change the files on the image first:
`unix2dos bootdisk/*.BAT bootdisk/CONFIG.SYS` then
`mcopy -o -i dos62.img bootdisk/SCAN.BAT bootdisk/AUTOEXEC.BAT ::/`.

**IBM 5150 (360 KB 5.25") — separate image.** You can't write `dos62.img` to a
360 KB disk: it's a 720 KB filesystem (737,280 B, 80 cylinders, media `0xF9`),
while a 360 KB disk is 368,640 B / 40 cylinders / media `0xFD`, and its files
reach byte 366 KB (past track 40) anyway. Build a 360 KB image from a bootable
360 KB DOS disk (`FORMAT A: /S` a 360 KB disk on any DOS PC — or the 5150 itself —
then `gw read --format ibm.360 msd360.img`), strip it to `IO.SYS`/`MSDOS.SYS`/
`COMMAND.COM`, and:

```
mcopy -o -i msd360.img /path/to/MSD.EXE ::/
mcopy -o -i msd360.img bootdisk/SCAN.BAT bootdisk/AUTOEXEC.BAT bootdisk/CONFIG.SYS ::/
gw write --format ibm.360 msd360.img
```

6.22 + MSD ≈ 300 KB fits a 360 KB disk with room for ~2 reports; a leaner DOS
(3.3/5.0) leaves more. Drop a bootable 360 KB image in `bootdisk/` and I'll strip
and populate it the same way I did `dos62.img`.

## Read the reports back, then import

Bring the floppy back, image it, pull the reports off:

```
gw read --format ibm.720 back.img
mcopy -i back.img "::/SCAN*.TXT" ../imports/
python ../scripts/import_report.py
```

Because the reports are auto-named, the importer shows each one's detected CPU/BIOS
and asks which machine it belongs to:

```
SCAN03.txt: not an asset id — detected cpu=80386, bios=IBM (11/02/88), os=MS-DOS 6.22, ...
  attach to which asset id? (RH-xxxx, blank=skip): RH-0207
```

Type the asset id (blank to skip) and it proposes the usual updates — it only fills
blank fields and writes nothing until you confirm. It can't see ISA cards, so keep
cataloguing those by hand.

> **MSD parsing is verified** against a real MSD 2.11 report (an IBM PS/2 386):
> CPU, OS, BIOS, video and COM/LPT counts all read correctly. The field map is
> `detect_msd()` in `scripts/import_report.py`.

## Optional: the manual / named path

If you'd rather name a report after its asset id at scan time (so the importer
auto-links it, no attach step), interrupt the auto-scan (Ctrl-C) and type:

```
DETECT RH-0207            writes A:\RH-0207.TXT (MSD here, HWiNFO if present)
DETECT RH-0207 3          force HWiNFO   (needs HWINFO.EXE + HWINFO.DAT + CWSDPMI)
DETECT RH-0207 6          force MSD
```

`DETECT` auto-picks HWiNFO if `HWINFO.EXE` is on the disk, else MSD. For full
HWiNFO detail build a 1.44 MB disk with `HWINFO.EXE` + `HWINFO.DAT` + `CWSDPMI.EXE`
added (they don't fit 720 KB alongside everything else).

> **Other images:** `dos5.img` is a leaner MS-DOS 5.0 base (add `MSD.EXE` from a
> 6.x set); `boot.img` is the retired FreeDOS 386-only disk.
