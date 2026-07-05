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
- `DETECT386.BAT` — runs `HWINFO.EXE` directly
- `DETECT16.BAT` — runs `HWINFO16.EXE` directly
- `AUTOEXEC.BAT` — runs `DETECT.BAT` on boot

`DETECT.BAT` relies on `CHOICE`, which ships with FreeDOS and MS-DOS 6+. On older
MS-DOS it is missing — run `DETECT16` or `DETECT386` directly, or point
`AUTOEXEC.BAT` at `DETECT16` on an XT/286 disk.

## The report switch

The batch files invoke the tool as `HWINFO -rA:\REPORT.TXT`. HWiNFO's DOS report
switch has varied between builds, so if the program opens its interactive menu
instead of writing the file, just save the report to `A:\REPORT.TXT` from the
menu. Confirm the exact switch with `HWINFO /?` on your copy.

## 1. Build the image (Linux)

Prereqs:

    sudo apt install mtools
    pip install greaseweazle

Start from a bootable DOS image called `boot.img` — a 1.44MB FreeDOS boot floppy
for 386+, or a 360KB MS-DOS boot floppy for the XT/286 machines.

Give the batch files DOS (CRLF) line endings, then copy everything into the image
(`mcopy` writes into the FAT filesystem with no mount or root):

    unix2dos bootdisk/*.BAT
    mcopy -o -i boot.img bootdisk/DETECT.BAT bootdisk/DETECT386.BAT bootdisk/DETECT16.BAT ::/
    mcopy -o -i boot.img bootdisk/AUTOEXEC.BAT ::/
    mcopy -o -i boot.img /path/to/HWINFO.EXE /path/to/HWINFO16.EXE ::/

No `unix2dos`? `sed -i 's/$/\r/' bootdisk/*.BAT` does the same.

## 2. Flash it with Greaseweazle

Drive on the 34-pin ribbon, a correct-capacity disk inserted:

    gw write --format ibm.1440 boot.img

Match the format to the target drive: `ibm.1440` (3.5" HD), `ibm.720` (3.5" DD),
`ibm.1200` (5.25" HD), `ibm.360` (5.25" DD / XT). `gw write --help` lists them.

## 3. Run it, then read the report back

Boot the retro PC from the floppy; it writes `A:\REPORT.TXT`. Bring the disk back
to the Greaseweazle and pull the file off (read flux to an image, extract with
mtools):

    gw read --format ibm.1440 back.img
    mcopy -i back.img ::/REPORT.TXT ../imports/RH-0005.txt

## 4. Import — it proposes, you confirm

    python ../scripts/import_report.py RH-0005

Fills CPU/RAM/disk/video. It can't see ISA cards, so keep cataloguing those by hand.
