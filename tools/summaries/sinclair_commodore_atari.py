"""Sinclair, the Commodore lines and Atari."""

SUMMARIES = {
    # --- Sinclair ZX ------------------------------------------------------
    "zx80": """
        The first computer in Britain to cost under a hundred pounds. Sinclair got
        there by leaving things out: the processor generates the video itself, so the
        screen goes blank whenever the machine computes, and there is 1K of memory
        and a touch-sensitive membrane keyboard. Crude by any measure and enormously
        important — it put a computer in ordinary British homes a year before anyone
        else tried. The white case yellows badly.
        """,
    "zx81": """
        The ZX80 reduced to one ULA and sold by mail order in kit or built form, and
        the machine that made home computing a mass British hobby — around a million
        and a half were sold. 1K of RAM, a wobbly 16K expansion that crashed if you
        breathed on it, and a display that flickers when it thinks. The black wedge is
        one of the most recognisable objects in computing.
        """,
    "zx-spectrum-16k": """
        The cheap Spectrum, and the one that shows what Sinclair's colour machine was
        really for: 16K was not enough for the games that made the platform, and most
        buyers either upgraded or replaced it within a year. Surviving unmodified 16K
        Issue 1 and 2 boards are the interesting ones — a genuinely original example
        is considerably scarcer than the 48K it sat beside.
        """,
    "zx-spectrum-48k": """
        The machine that defined British gaming. Colour, sound and 48K for £175 in
        1982, and a software industry — Ultimate, Ocean, Imagine — that grew up around
        it in bedrooms. The rubber keys and the attribute-clash colour are as famous
        as anything about it. Issue numbers matter to collectors, the early boards
        being both rarer and more failure-prone, and the ULA is the part that dies.
        """,
    "zx-spectrum-plus": """
        Sinclair's attempt to make the Spectrum look serious: an injected-moulded case
        with proper moulded keys, a reset button and a bigger footprint, wrapped round
        an unchanged 48K board. Widely disliked at the time for the keyboard's
        vagueness, but it is the same machine underneath and considerably nicer to
        type on than the rubber mat. The last Spectrum Sinclair designed before
        selling the company.
        """,
    "zx-spectrum-128": """
        128K, banked memory, and the AY sound chip that finally gave the Spectrum real
        music — the difference in a game's soundtrack between 48K and 128K is startling.
        Developed with Investrónica for the Spanish market and sold in Britain with an
        external heatsink so large it was nicknamed the toastrack. The last machine
        Sinclair sold under his own control, and uncommon in that form.
        """,
    "zx-spectrum-plus2": """
        Amstrad's first Spectrum after buying the name: the 128 with a tape deck built
        in, a grey case and a proper keyboard. Cheaper to make and much easier to
        live with, and it kept the AY sound. Purists dislike the Amstrad-era machines;
        practically, this is the easiest classic Spectrum to actually use, and the
        integrated Datacorder is the part that needs its belt.
        """,
    "zx-spectrum-plus3": """
        The Spectrum with a 3-inch disc drive — Amstrad's own drive, from the CPC —
        and the most capable machine of the line. The ROM changes for the disc
        interface broke compatibility with a slice of the earlier software, which is
        the trade. Comparatively uncommon, and the drive and its perishing belt are
        the reason most surviving examples do not work.
        """,
    "zx-spectrum-plus2a": """
        The +3 board with the disc drive replaced by a tape deck, in the +2's black
        case. That means it carries the +3's revised ROM and its compatibility
        problems without the drive that justified them, which is why it is the least
        loved Spectrum. Easily confused with the +2 and worth telling apart: the
        black case and the +2A badge are the tell.
        """,
    "zx-spectrum-plus2b": """
        The last Spectrum. A +2A with the power and video circuitry revised after
        Amstrad moved production, and the final machine to carry the name before the
        line was discontinued in 1990. Externally identical to a +2A, so the board
        markings are the only way to be sure which one is in front of you. The end of
        eight years and five million machines.
        """,
    "sinclair-ql": """
        Sinclair's business machine, and one of the great might-have-beens. A 68008
        with proper multitasking, a genuinely advanced BASIC, and Psion's office
        software — announced before it worked, shipped with a dongle hanging out of
        the back, and hobbled by the Microdrive tape loops nobody could make
        reliable. Linus Torvalds learned on one. It killed Sinclair's credibility in
        business and is now a serious collector's machine.
        """,
    # --- Commodore PET ----------------------------------------------------
    "pet-2001": """
        One of the three machines that started personal computing in 1977, and the one
        built like office equipment: a metal case with the screen, keyboard and tape
        drive all in it, ready to work out of the box. The original chiclet keyboard
        is dreadful and is what marks an early machine. Sold hard into schools and
        laboratories, where a great many stayed in service for a decade.
        """,
    "pet-3032": """
        The PET with the proper full-travel keyboard and 32K, sold into European
        business and education. The 3000 series is where the PET became a usable
        working machine rather than an impressive novelty, and the metal case means
        survivors are usually in better condition than their plastic contemporaries.
        The screen is the part that has usually gone soft.
        """,
    "pet-4032": """
        BASIC 4.0 and a 12-inch screen: the PET as most people who used one for work
        remember it. The new ROMs added proper disc commands, which mattered once
        Commodore's own drives were widespread. The most common of the big PETs and
        the one to start with — plentiful enough to be affordable and complete enough
        to be useful.
        """,
    "pet-8032": """
        The 80-column PET, and the reason the machine stayed on accountants' desks
        into the mid-eighties: a full-width business display when almost everything
        else offered forty characters. Same BASIC 4.0 as the 4032 with a different
        video circuit. WordPro and Commodore's own business software were written for
        this screen.
        """,
    "cbm-8296": """
        The last of the PET line: an 8032 rebuilt around 128K of banked memory in a
        low-profile case with a detachable keyboard, sold in 1984 when the C64 was
        already Commodore's whole business. Very few were made for Europe and almost
        none for America, which makes it the rare one — the end of a family that had
        run for seven years.
        """,
    "cbm-b128": """
        A commercial failure worth having. Commodore's B series was meant to succeed
        the PET in business with a 6509, bank-switched memory and a proper 80-column
        display; it arrived with almost no software, was cancelled, and the remaining
        stock was dumped. Interesting as the machine that occupies the gap between
        the PET and the C128, and genuinely uncommon.
        """,
    # --- Commodore 8-bit --------------------------------------------------
    "vic-20": """
        The first computer of any kind to sell a million. Commodore aimed it at
        ordinary shops rather than computer dealers, put William Shatner in the
        adverts, and undercut everything — with 5K of memory and a 22-column display
        that made most software a compromise. It is the machine that proved the mass
        market existed, and the one the C64 was built to replace a year later.
        """,
    "c64": """
        The best-selling computer model ever made, by a margin nobody has approached.
        The reason is two chips: the VIC-II, with hardware sprites and smooth
        scrolling, and the SID, a real analogue synthesiser that gave games music
        people still listen to. Commodore's own chip fabs let them price it at will
        and starve the competition. Breadbin and later boards differ; the SID
        revisions sound different, and collectors care which is fitted.
        """,
    "c64c": """
        The C64 in the C128's cream wedge case, with the board cost-reduced to fewer,
        larger chips and — in most examples — the 8580 SID, which sounds cleaner and
        thinner than the 6581 it replaced. That difference divides opinion sharply
        among people who care about C64 music. Mechanically the nicest C64 to own and
        the last version sold.
        """,
    "c64gs": """
        A C64 with the keyboard and ports taken away, sold as a cartridge console in
        1990 against the Mega Drive. Almost nothing was written for it, several of the
        cartridges needed a keyboard the machine did not have, and it was withdrawn
        quickly. Sold only in Europe and in small numbers, so a famous failure that is
        now one of the harder Commodore machines to find.
        """,
    "sx-64": """
        The first colour portable computer: a C64 with a five-inch screen and a 1541
        drive built into a metal case with a carrying handle, and no tape port, which
        cut it off from most of the software people owned. Heavy, expensive and
        impractical, and consequently a striking object and a genuine collector's
        piece.
        """,
    "max-machine": """
        Commodore's forgotten Japanese-market games machine, sold briefly in 1982 with
        cartridge software, 2K of memory and no way to expand. Its real significance
        is architectural: it is the direct ancestor of the C64, sharing the VIC-II and
        SID, and C64 cartridges will run on it. Very few were made and it is among the
        rarest Commodore machines of any kind.
        """,
    "c16": """
        Commodore aiming at the low end again and misjudging it: the 264 series had
        better BASIC and a 121-colour palette but no sprites and no SID, so it could
        not run C64 software or match it on games. The C16 is the cut-down version
        with 16K in a dark case. It sold poorly in Britain and well in eastern Europe,
        where it became a first machine for a generation.
        """,
    "c116": """
        The rarest of the 264 family: a C16 in a small rubber-keyed case sold almost
        exclusively in Germany and Hungary, and quickly dropped. Same limitations as
        the C16 — good BASIC, no sprites, no SID — in a shape that looks like nothing
        else Commodore made. Wanted mostly for its scarcity and its odd keyboard.
        """,
    "plus4": """
        The top of the 264 series, and Commodore's strangest product: a home computer
        with a word processor, spreadsheet, database and graphics package burned into
        ROM, aimed at a business buyer who was never going to want a machine with no
        sprites and a joystick port of its own design. It flopped comprehensively. The
        built-in software makes it genuinely interesting to use.
        """,
    "c128": """
        Three computers in one box: a C128 mode with 128K and 80 columns, a hardware
        C64 mode that is a real 6510 rather than an emulation, and a Z80 for CP/M.
        Bill Herd's team built it in five months, and it is the most technically
        ambitious 8-bit Commodore ever shipped. The C64 compatibility is what people
        actually used, which is both its strength and the reason its own mode has
        little software.
        """,
    "c128d": """
        The C128 in a metal desktop case with the 1571 drive built in and a detachable
        keyboard — the machine as a professional workstation rather than a home
        computer. Handsome, heavy, and much the nicest way to use CP/M or 80-column
        mode. The European metal-cased version is the one to have; it also has a fan,
        which the later plastic one does not.
        """,
    "c128dcr": """
        The cost-reduced 128D: a plastic case, no fan, and a revised board. Cheaper to
        make and quieter, and by some way the most common of the two-drive 128s in
        America. The missing fan is the reason to keep an eye on temperatures, and the
        plastic case is the reason the metal one is more sought after.
        """,
    # --- Commodore Amiga --------------------------------------------------
    "amiga-1000": """
        The original Amiga, and the machine that showed everybody what a home computer
        could be: pre-emptive multitasking, four-channel sampled sound and a custom
        chipset doing graphics in hardware, in 1985, while the PC world argued about
        CGA. Jay Miner's design. It boots from a Kickstart disc rather than ROM, the
        case is signed inside by the team, and it is the most collectable Amiga.
        """,
    "amiga-500": """
        The Amiga that mattered commercially: the 1000's architecture in a one-piece
        wedge at a price a family would pay, and consequently the machine that owned
        European home computing between 1988 and 1992. The games written for it —
        Lemmings, Sensible Soccer, Speedball — defined a generation. Check the
        battery-backed clock on any accelerator and the electrolytics; both leak and
        eat boards.
        """,
    "amiga-500-plus": """
        The A500 with Kickstart 2.0 and the ECS chipset, and a battery-backed clock on
        the motherboard that has destroyed a very large proportion of them — the
        leaking cell is the single most common Amiga fault there is. The newer ROM
        broke a handful of older games, which was resented at the time. A good
        unleaked board is worth finding.
        """,
    "amiga-600": """
        A cost-reduced A500 in a compact case with an IDE header and a PCMCIA slot,
        and no numeric keypad — Commodore's attempt at a cheap console-like Amiga
        that pleased almost nobody. The IDE and PCMCIA are genuinely useful now,
        which has quietly turned it into a good machine for modern storage
        adaptations. Same surface-mount capacitor problems as the rest of the late
        line.
        """,
    "amiga-1200": """
        The AGA Amiga most people wanted: 256 colours from a 16-million palette, a
        68EC020, IDE, PCMCIA and a proper trapdoor for accelerators, in the A500's
        shape. It arrived in 1992 just as Commodore ran out of money and the PC took
        the games market, so it never had the software the hardware deserved. The most
        upgraded and most actively used classic Amiga today.
        """,
    "amiga-2000": """
        The Amiga as a workstation: a big desktop case with Zorro II slots and PC
        bridgeboard options, which is how the Amiga got into television studios. The
        Video Toaster ran in one of these and changed what a small production company
        could do. Slow by 1987 standards without an accelerator, but the expansion is
        the whole point and there is a great deal of it about.
        """,
    "amiga-1500": """
        A British marketing exercise: an A2000 sold with two floppy drives instead of
        a hard disc and a bundle of software, at a price aimed at the home rather than
        the studio. Electrically an A2000, so it takes the same Zorro cards and
        accelerators. Sold only in the UK, which makes it an uncommon variant of a
        common machine.
        """,
    "amiga-3000": """
        The best-engineered Amiga: a 68030 at 25MHz, a proper SCSI controller, Zorro
        III, and a display enhancer that let it drive an ordinary VGA monitor — which
        no other Amiga of the period could do. Designed properly rather than to a
        price, and made in small numbers before Commodore's finances collapsed. The
        connoisseur's Amiga.
        """,
    "amiga-4000": """
        The top of the AGA line: an 030 or 040 in a desktop case with Zorro III, sold
        into video and rendering work where the Toaster and LightWave lived. It is the
        most capable Amiga Commodore shipped and the last desktop before the company
        folded in 1994. The Buster chip and the clock battery are the two things to
        check.
        """,
    "amiga-cdtv": """
        Commodore's attempt at the living room: an A500 in a black hi-fi case with a
        CD-ROM drive, a remote control and no keyboard, launched in 1991 as a
        multimedia player before there was any content to play. It failed completely.
        Interesting as an early CD-ROM machine and as the idea Philips and Apple were
        also getting wrong at the same moment.
        """,
    "amiga-cd32": """
        The first 32-bit CD games console sold anywhere, and Commodore's last product.
        AGA hardware with a CD drive and a pad, launched in 1993 to reasonable
        European sales before the company went under and left the platform stranded
        months later. The expansion port takes a module that turns it back into a
        computer. Wanted both as a console and as the end of Commodore.
        """,
    # --- Commodore PC -----------------------------------------------------
    "commodore-pc-10": """
        Commodore building somebody else's architecture: a straightforward XT clone
        sold through the dealer network that was shifting C64s, mostly into European
        small businesses. Unremarkable as a PC and interesting as a company decision —
        the firm that made its own chips buying in Intel's. Common in Germany, scarce
        elsewhere.
        """,
    "commodore-pc-20": """
        The PC 10 with a hard disc, which in 1985 was the difference between a
        curiosity and a working office machine. Same XT architecture and the same
        European dealer market. The 20MB drive is usually the part that has died, and
        a working original is worth keeping running.
        """,
    "commodore-pc-1": """
        Commodore's small PC: an 8088 with the power supply in an external brick and
        video on the board, in a case barely larger than a keyboard. It is a neat
        piece of packaging aimed squarely at Amstrad's PC1512 on price, and it was
        sold almost entirely in Germany. The compact case is the reason to want one.
        """,
    "commodore-colt": """
        A PC 10 successor built around the NEC V20 — a pin-compatible 8088 replacement
        that runs meaningfully faster — sold as a budget XT-class machine in 1988 when
        the world had moved to 286s. The V20 is the interesting part; almost nothing
        else about it is. Uncommon simply because nobody wanted an XT by then.
        """,
    "commodore-pc-40-iii": """
        The most capable PC Commodore sold: a 286 at 12MHz with VGA on the board, aimed
        at business buyers in 1989. By this point Commodore's PC line was an
        afterthought beside the Amiga and it sold accordingly. Worth having as the
        high-water mark of a line most people do not know existed.
        """,
    # --- Atari 8-bit ------------------------------------------------------
    "atari-400": """
        The cheap half of Atari's 1979 launch, and a machine designed by people who
        made arcade games: the ANTIC and CTIA chips give it display list interrupts
        and hardware sprites that nothing else at the price could touch. Atari fitted
        a membrane keyboard and a single cartridge slot to keep it out of the 800's
        way, and that keyboard is the reason most people remember it unkindly.
        """,
    "atari-800": """
        The proper version of Atari's first computers: a real keyboard, two cartridge
        slots, user-accessible RAM cards and a cast aluminium RF shield inside that
        makes it feel like industrial equipment. The custom chips were years ahead —
        Atari's arcade division designed them — and the machine is beautifully made.
        The best of the 8-bit Ataris to own, and the one to look for.
        """,
    "atari-1200xl": """
        Atari's misfire. Handsome, aluminium-trimmed, and incompatible with a slice of
        the software and hardware people already owned, thanks to changed ROMs and
        missing ports. It was withdrawn after a few months and replaced by the 600XL
        and 800XL. Short production, bad reputation and striking industrial design add
        up to a machine collectors want and users do not.
        """,
    "atari-600xl": """
        The cut-down XL: 16K, no built-in BASIC problems but not enough memory for
        much of the library, and the expectation that you would buy the 1064 expansion.
        Most people bought an 800XL instead. Same excellent chipset in a smaller case,
        and the least common of the XL pair.
        """,
    "atari-800xl": """
        The Atari 8-bit that sold: 64K, BASIC in ROM, the good chipset, and a price
        cut hard during the 1983 price war with Commodore. It is the most common of
        the line and the one most software assumes, which makes it the sensible
        starting point. The keyboard and the power supply are the usual weak spots.
        """,
    "atari-65xe": """
        The XL redone in the ST's styling after Jack Tramiel bought Atari — same 64K
        and the same chipset in a cheaper, lighter case, sold mainly in Europe where
        the 8-bit line kept selling for years after America lost interest. Function
        over sentiment: it is an 800XL that costs less and feels it.
        """,
    "atari-130xe": """
        128K of banked memory in the XE case, which gave the Atari 8-bit line a second
        life — a body of European software and demos was written specifically for the
        extra bank. The most capable stock Atari 8-bit, and the one to have if you
        want to run the later software rather than the classic cartridges.
        """,
    "atari-xegs": """
        A 65XE dressed as a console: a detachable keyboard, a light gun and a
        cartridge bundle, sold in 1987 to compete with the NES using hardware from
        1979. It did not work, but the styling is unlike anything else and it is a
        complete Atari 8-bit computer underneath, keyboard and all. Collected for the
        look as much as the machine.
        """,
    # --- Atari consoles ---------------------------------------------------
    "atari-2600": """
        The console that created the industry. A 6507 with 128 bytes of RAM and no
        frame buffer, so the program has to build the picture a scanline at a time in
        step with the beam — the hardest mainstream machine ever to program, and the
        reason its best games are feats of engineering. It sold thirty million, caused
        the 1983 crash, and every collection starts here.
        """,
    "atari-5200": """
        Atari's answer to Intellivision: essentially Atari 400 hardware in a console
        with notoriously bad non-centring analogue controllers, no backwards
        compatibility with the 2600 at launch, and a launch into a collapsing market.
        It lasted two years. The controllers are the reason most surviving examples do
        not really work, and rebuilt ones are a small industry.
        """,
    "atari-7800": """
        Designed in 1984, shelved during Atari's sale, and finally released in 1986
        into a market Nintendo already owned. The MARIA chip does far more sprites
        than the 2600 and it plays the whole 2600 library, which makes it the most
        practical classic Atari console. The sound is the weak point — it kept the
        2600's TIA — and the library is thin.
        """,
    "atari-lynx": """
        The first handheld with a colour backlit screen and hardware sprite scaling,
        designed by ex-Amiga engineers and released in 1989 — technically far beyond
        the Game Boy it lost to. It is also large, thirsty for six AA cells, and had
        almost no software. A striking piece of hardware and a clear illustration
        that the better machine does not win.
        """,
    "atari-jaguar": """
        Marketed as the first 64-bit console, which was a stretch: five processors,
        two of them 32-bit RISC, in an architecture so awkward that most developers
        used the 68000 as the main CPU and left the rest idle. It killed Atari as a
        hardware company. The Tempest 2000 soundtrack and the sheer strangeness of the
        design are the reasons to own one.
        """,
    # --- Atari ST ---------------------------------------------------------
    "atari-520st": """
        Built in under a year by Tramiel's Atari to beat the Amiga to market, and it
        did: a 68000 with a GEM desktop for well under a thousand dollars in 1985. The
        MIDI ports fitted as standard are the historically important detail — they
        made the ST the standard studio sequencer machine for a decade, and Cubase and
        Notator were written for it. Earliest boards have external power bricks.
        """,
    "atari-520stm": """
        The 520ST with the RF modulator fitted, so it works on a television rather than
        needing Atari's monitor. A small change that matters enormously for what the
        machine could be sold as at home. Otherwise the launch ST: 512K, external
        floppy, and the same MIDI ports.
        """,
    "atari-520stfm": """
        The ST as most people owned it: floppy drive and modulator both built in, 512K,
        one box. This is the volume machine of the European ST market and the one the
        games were written against. The internal single-sided drives were later
        replaced by double-sided; which one is fitted decides what disc images will
        run.
        """,
    "atari-520ste": """
        The enhanced ST: a blitter for faster graphics, a 4096-colour palette,
        hardware scrolling and stereo DMA sound. On paper it answers the Amiga
        properly. In practice a good deal of ST software was written for the plain
        machine and does not use — or sometimes does not tolerate — the new hardware,
        which is why the STE has a mixed reputation and a devoted demo scene.
        """,
    "atari-1040stf": """
        A megabyte and a double-sided drive as standard, which is what the ST needed
        to be a working machine rather than a games console: desktop publishing, MIDI
        sequencing and serious software all assume this specification. The most useful
        of the classic STs, and common enough to be affordable.
        """,
    "atari-1040ste": """
        The STE with a megabyte fitted — the best of the 16MHz-and-under STs and the
        one to buy if you want the blitter and the stereo sound with enough memory to
        use them. Same compatibility caveats as any STE: some early software objects
        to the new hardware.
        """,
    "atari-mega-st": """
        The ST as a professional tool: a low desktop box with a detachable keyboard,
        a blitter in later units, and an internal expansion bay, sold for desktop
        publishing and music. Calamus and the SLM laser printer turned these into
        serious typesetting machines in Germany, where the Mega ST had a following the
        rest of the range never matched.
        """,
    "atari-mega-ste": """
        A 16MHz 68000 with a cache, the STE chipset, VME expansion and SCSI, in the
        TT's case — the most capable ST-architecture machine Atari made. Aimed at the
        professional music and publishing users who had stayed loyal, and made in
        small numbers. Genuinely fast for the family and correspondingly hard to find.
        """,
    "atari-stacy": """
        A portable ST: the whole machine with a mono LCD, a trackball and a floppy
        drive in a case with a handle, sold to musicians who needed MIDI on the road.
        Atari famously shipped it with the battery compartment fitted but the batteries
        left out. Heavy, uncommon, and the screens have usually suffered.
        """,
    "atari-st-book": """
        Atari's proper laptop, and one of the rarest machines of the whole ST line —
        a few hundred were made. Remarkably thin for 1991, with no floppy drive, no
        backlight and a battery life measured in hours. It is a serious collector's
        item rather than a usable computer, and complete examples are very scarce.
        """,
    "atari-tt030": """
        Atari's Unix workstation ambition: a 68030 at 32MHz with fast RAM, VME slots
        and SCSI, running TOS or ASV. It was expensive, late, and sold in small
        numbers mainly in Germany. The fastest 68k machine Atari shipped, and the
        clearest evidence of where the company thought it was going before it stopped
        making computers.
        """,
    "atari-falcon030": """
        The last Atari computer, and the most interesting: a 68030 with a Motorola
        56001 DSP on the board, true colour video and eight-track direct-to-disc
        recording. It turned into a serious音 music workstation and still has an active
        following for exactly that reason. Atari cancelled it within two years to
        concentrate on the Jaguar. Sought after, and often found heavily upgraded.
        """,
}
