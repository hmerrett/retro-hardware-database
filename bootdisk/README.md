# Making the detector boot floppy

These files go onto a DOS boot floppy so a retro PC can report its own hardware.
Once you have a `REPORT.TXT`, see `../imports/README.md` for the import step.

## Which HWiNFO binary

HWiNFO for DOS ships two executables, split by CPU:

- `HWINFO.EXE` — 386 and newer
- `HWINFO16.EXE` — 8086/8088 and 286 only

Put **both** on a 1.44MB disk; `DETECT.BAT` picks between them. On a 360KB 5.25"
disk for an XT/286 the space is tight — use `HWINFO16.EXE` only.

For this collection: the IBM 5150s (8088) and Amstrad PC2286 (286) need
`HWINFO16.EXE`; everything 386-class and up uses `HWINFO.EXE`.

## The files

- `DETECT.BAT` — one-key menu: 3 = 386+, 6 = 286-or-older, defaults to 386 after 5s
- `DET386.BAT` — prompts for the asset id, runs `HWINFO.EXE`, writes `A:\<id>.TXT` (8.3-safe name)
- `DETECT16.BAT` — prompts for the asset id, runs `HWINFO16.EXE`, writes `A:\<id>.TXT`
- `AUTOEXEC.BAT` — runs `DETECT.BAT` on boot

`DETECT.BAT` relies on `CHOICE`, which ships with FreeDOS and MS-DOS 6+. On older
MS-DOS it is missing — run `DETECT16` or `DET386` directly, or point
`AUTOEXEC.BAT` at `DETECT16` on an XT/286 disk.

## The report file

Each detector prompts for the machine's asset id and writes the report to
`A:\<id>.TXT` (e.g. `A:\RH-0005.TXT`) using HWiNFO's report switch, `-r A:\<id>.TXT`
(the filename is a separate argument). Boot one machine
after another with the same floppy and the reports pile up on the disk. If a build
ignores `-r` and opens its menu, save the report by hand to that same
`A:\<id>.TXT`. `-r` can stall mid-scan on some machines — if it hangs, reboot and
press F2 in HWiNFO to save the screen to the file instead.

## 1. Build the image (Linux)

Prereqs:

    sudo apt install mtools
    pip install greaseweazle

Start from a bootable DOS image called `boot.img` — a 1.44MB FreeDOS boot floppy
for 386+, or a 360KB MS-DOS boot floppy for the XT/286 machines.

Give the batch files DOS (CRLF) line endings, then copy everything into the image
(`mcopy` writes into the FAT filesystem with no mount or root):

    unix2dos bootdisk/*.BAT bootdisk/FDCONFIG.SYS
    mcopy -o -i boot.img bootdisk/DETECT.BAT bootdisk/DET386.BAT bootdisk/DETECT16.BAT ::/
    mcopy -o -i boot.img bootdisk/AUTOEXEC.BAT bootdisk/FDCONFIG.SYS ::/
    mcopy -o -i boot.img /path/to/HWINFO.EXE /path/to/HWINFO16.EXE /path/to/HIMEM.EXE ::/

`HIMEM.EXE` (from the FreeDOS base image) plus `FDCONFIG.SYS`'s `DOS=HIGH` push the
kernel into the HMA. Without them the 386 HWiNFO build runs out of conventional
(base 640K) memory — so if you strip a base image down, **keep `HIMEM.EXE`**.

No `unix2dos`? `sed -i 's/$/\r/' bootdisk/*.BAT` does the same.

## 2. Flash it with Greaseweazle

Drive on the 34-pin ribbon, a correct-capacity disk inserted:

    gw write --format ibm.1440 boot.img

Match the format to the target drive: `ibm.1440` (3.5" HD), `ibm.720` (3.5" DD),
`ibm.1200` (5.25" HD), `ibm.360` (5.25" DD / XT). `gw write --help` lists them.

## 3. Run it on each machine, then read the reports back

Boot each PC from the floppy, enter its asset id at the prompt, let it write
`A:\<id>.TXT`, then move the floppy to the next machine. Do as many as you like on
one disk. Bring it back to the Greaseweazle, read it to an image, and pull every
report off at once (the importer accepts upper- or lower-case `.TXT`):

    gw read --format ibm.1440 back.img
    mcopy -i back.img "::/RH-*.TXT" ../imports/

## 4. Import — it proposes, you confirm

    python ../scripts/import_report.py

runs every report in `imports/`; append an id (e.g. `RH-0005`) to do just one.
Writes nothing until you confirm. Fills CPU/RAM/disk/video — it can't see ISA
cards, so keep cataloguing those by hand.
