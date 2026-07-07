# Making the detector boot floppies

Two floppies, split by CPU, because HWiNFO needs a 386 **and** carries a 226 KB
device database that won't fit next to everything else on a 720 KB disk, while MSD
is tiny and runs on an 8088:

- **HWiNFO disk — 1.44 MB — for 386 and newer** (rich detail)
- **MSD disk — 720 KB (or 360 KB) — for 286 / 8088** (and any DOS PC)

Both carry the *same* batch files; `DETECT` auto-picks the detector. Boot a disk,
type `DETECT RH-0005`, carry it to the next machine, then read the reports back
and import them (`../imports/README.md`).

## Why this design (read this first)

The old disk booted from **FreeDOS**, whose kernel needs a **386** — so it
wouldn't even boot on the 8088 (IBM 5150) or 286 (Amstrad PC2286). And the
`HWINFO16.EXE` we carried for "8086/286" was mislabelled: the resurrected
**HWiNFO for DOS v6.x needs a 386** for *both* its binaries. So HWiNFO can never
run on an XT or 286; that whole sub-386 tier needs a different, lighter tool.

- **Boot layer → MS-DOS 6.22.** Real-mode DOS boots on everything from the 8088
  up (the actual fix for "won't boot below a 386"), and 6.22 bundles MSD.
- **Detector at 386+ → HWiNFO** (rich detail; the importer knows its format). It
  needs `HWINFO.EXE` (197 KB) + `HWINFO.DAT` (226 KB device database) + a DPMI
  host (`CWSDPMI.EXE`) — ~460 KB, so it rides on a 1.44 MB disk. 386+ machines
  have HD 3.5" drives anyway.
- **Detector below a 386 → MSD** (Microsoft Diagnostics). `MSD /P <file>` writes a
  full report to a named file with no prompts — ~155 KB, needs no XMS, runs on an
  8088. This is the 720 KB (or 360 KB) disk.

## The two disks

### MSD disk — `dos62.img` (720 KB) — ready to flash

For the 286 and 8088/8086. Stripped MS-DOS 6.22 + MSD + the toolchain; 414 KB
free. Contents:

- `IO.SYS`, `MSDOS.SYS`, `COMMAND.COM` — bootable MS-DOS 6.22
- `MSD.EXE` — the detector (ships with 6.22)
- `CONFIG.SYS` (`FILES`/`BUFFERS`), `AUTOEXEC.BAT` (banner), `DETECT.BAT`,
  `DET386.BAT`, `DETMSD.BAT`

It has no `HWINFO.EXE`, so `DETECT RH-0005` auto-runs MSD here. It also fits a
**360 KB 5.25" disk** unchanged — that's the one for the IBM 5150
(`gw write --format ibm.360 dos62.img`).

### HWiNFO disk — 1.44 MB — build it where `HWINFO.DAT` lives

For 386 and newer. You build this one on the box that has the HWiNFO files (the
226 KB `HWINFO.DAT` isn't in the repo). It carries the same toolchain plus
`HWINFO.EXE` + `HWINFO.DAT` + `CWSDPMI.EXE` (and `MSD.EXE` too, as a fallback —
there's plenty of room on 1.44 MB). With `HWINFO.EXE` present, `DETECT RH-0005`
auto-runs HWiNFO.

## On the machine

Boot the floppy and type the asset id from the case label:

```
DETECT RH-0005
```

`DETECT` auto-picks: **HWiNFO** if `HWINFO.EXE` is on the disk (the 1.44 MB disk),
else **MSD** (the 720/360 KB disk). Force it if needed: `DETECT RH-0005 3` (HWiNFO)
or `DETECT RH-0005 6` (MSD). It writes `A:\RH-0005.TXT`; move the floppy on and the
reports pile up.

No menu, no `CHOICE`: branching on the argument behaves the same on every DOS
version. (MS-DOS `COMMAND.COM` has no `SET /P`, so the id is a batch argument, not
a prompt.) If MSD hangs mid-scan, reboot and run `MSD /I /P A:\RH-0005.TXT`; on
odd video add `/B` for mono.

## Building the disks (Linux + mtools)

Prereqs: `sudo apt install mtools` and `pip install greaseweazle`. `mcopy` writes
into the FAT with no mount. If you edit the batch/config files first give them DOS
line endings: `unix2dos bootdisk/*.BAT bootdisk/CONFIG.SYS`.

**MSD disk** — `dos62.img` is ready; only rebuild it to change files:

```
mcopy -o -i dos62.img bootdisk/DETECT.BAT bootdisk/DET386.BAT bootdisk/DETMSD.BAT ::/
mcopy -o -i dos62.img bootdisk/CONFIG.SYS bootdisk/AUTOEXEC.BAT ::/
mdir -i dos62.img ::/
```

**HWiNFO disk** — start from a bootable **MS-DOS 6.22 1.44 MB** image (e.g.
`FORMAT A: /S` a 1.44 disk and `gw read --format ibm.1440` it, or strip a 6.22
install disk 1). Keep only `IO.SYS`/`MSDOS.SYS`/`COMMAND.COM`, then:

```
mcopy -o -i hwinfo.img HWINFO.EXE HWINFO.DAT CWSDPMI.EXE MSD.EXE ::/
mcopy -o -i hwinfo.img bootdisk/DETECT.BAT bootdisk/DET386.BAT bootdisk/DETMSD.BAT ::/
mcopy -o -i hwinfo.img bootdisk/CONFIG.SYS bootdisk/AUTOEXEC.BAT ::/
mdir -i hwinfo.img ::/            # ~460 KB used by HWiNFO; 1.44 MB has room to spare
```

## Flash with Greaseweazle

Drive on the 34-pin ribbon, the right disk inserted:

```
gw write --format ibm.1440 hwinfo.img     # HWiNFO disk, 386+ (3.5" HD)
gw write --format ibm.720  dos62.img      # MSD disk, 286/8088 (3.5" DD)
gw write --format ibm.360  dos62.img      # MSD disk for the 5150 (5.25" DD)
```

`gw write --help` lists formats (`ibm.1440`, `ibm.720`, `ibm.1200`, `ibm.360`).

## Run each machine, then read the reports back

Boot each PC, `DETECT` its asset id, move on. Bring the floppy back, image it, and
pull every report off at once (importer takes upper- or lower-case `.TXT`):

```
gw read --format ibm.1440 back.img        # match the disk's format
mcopy -i back.img "::/RH-*.TXT" ../imports/
```

## Import — it proposes, you confirm

```
python ../scripts/import_report.py            # every report in imports/
python ../scripts/import_report.py RH-0005    # just one
```

`import_report.py` reads **both** report formats and auto-detects which: HWiNFO's
CP437 box report and MSD's plain-ASCII report, mapping both onto the same
CPU / OS / BIOS / video / ports / drives fields. It only fills blanks and writes
nothing until you confirm. It can't see ISA cards, so keep cataloguing those by
hand. MSD gives less detail than HWiNFO (usually no chipset/CHS on these old
boards) — expect CPU, OS, BIOS, video type and COM/LPT counts.

> **MSD parsing is verified** against a real MSD 2.11 report (an IBM PS/2 386):
> CPU, OS, BIOS, video and COM/LPT counts all read correctly. If a label ever
> differs on another MSD version, the map is in `detect_msd()` in
> `scripts/import_report.py`.

> **`dos5.img`** is a leaner MS-DOS 5.0 MSD disk kept as an alternate (5.0 needs
> `MSD.EXE` copied in from a 6.x set). `boot.img` is the retired FreeDOS 386-only
> disk.
