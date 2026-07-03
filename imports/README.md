# Importing hardware from a machine's own report

Boot each retro PC from a small DOS "detector" disk, let it write a text report
of what it sees (CPU, RAM, disk, video…), then drop that report in here and let
`scripts/import_report.py` propose updates to that machine's row — you approve
before anything is written.

## 1. Make the boot disk

Any DOS boot floppy or USB with a hardware-detection tool works. Good options:

- **HWiNFO for DOS** — strong coverage on 386/486/Pentium; writes a full report.
- **MSD** (Microsoft Diagnostics) — ships with MS-DOS 6.x. Run `MSD`, then
  *File → Report…* and tick everything, or try `MSD /F A:\REPORT.TXT`.
- **AIDA16** — lots of detail; save its report from the menu.

Put the tool plus `DETECT.BAT` (below) on a FreeDOS boot floppy or USB.

## 2. DETECT.BAT

A starting point — swap in your tool's "write report to a file" command:

    @echo off
    echo Detecting hardware, please wait...
    MSD /F A:\REPORT.TXT
    echo Report written to A:\REPORT.TXT
    pause

## 3. Name the report after the asset id

Rename the file to the machine's asset id and copy it into this folder:

    imports/RH-0005.txt

## 4. Import — it proposes, you confirm

    python scripts/import_report.py            # every report in imports/
    python scripts/import_report.py RH-0005     # just one

It prints what it detected and exactly what it would change, and does nothing
until you say yes.

## What it can and can't do

Fills in CPU, RAM, hard-disk model/geometry and video. It **can't** see ISA
cards (no plug-and-play on the ISA bus), and motherboard/chipset identity is
unreliable on pre-PCI machines — so you still catalogue the cards by hand, as
now. The report just does the tedious core for you.
