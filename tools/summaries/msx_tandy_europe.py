"""MSX, Tandy, and the European home computers."""

SUMMARIES = {
    # --- MSX --------------------------------------------------------------
    "msx-hx-10": """
        One of the first MSX machines in Europe, and a good illustration of what the
        standard was for: Microsoft and ASCII specified the hardware so that any
        maker's cartridge ran on any maker's machine — the thing the Japanese market
        had been missing. Toshiba's launch model, well built, with a full-travel
        keyboard.
        """,
    "msx-hx-20": """
        Toshiba's second-generation MSX1, with 64K and a built-in word processor in
        ROM. Sold in Europe as MSX was making its short-lived push against the
        Spectrum and C64. Solid, unexciting, and a straightforward way into the MSX1
        library.
        """,
    "msx-hb-75": """
        Sony's first HitBit, and the machine that made MSX look desirable: proper
        industrial design, a personal database in ROM with battery-backed memory to
        keep it, and Sony's build quality throughout. The HitBit line is the one MSX
        collectors generally want.
        """,
    "msx-hb-101": """
        A HitBit sold with a cartridge slot arrangement and styling aimed at the
        Japanese domestic market. Sony's MSX1 machines are consistently the
        best-finished of the standard, and this is a good example of it. Less common
        in Europe than the 501P.
        """,
    "msx-hb-501p": """
        The European HitBit, and among the most widely sold MSX1 machines in Britain,
        the Netherlands and Spain: 64K, a good keyboard, a cassette port and Sony's
        finish. If you want one MSX1 that is easy to find in Europe and pleasant to
        use, it is usually this.
        """,
    "msx-cx5m": """
        Yamaha's MSX, and the reason MSX matters to musicians: it takes the SFG FM
        synthesiser module and a real music keyboard, turning it into a genuine DX-era
        synthesiser with sequencing. Used seriously in studios. The module and keyboard
        are what make it valuable, and they are often missing.
        """,
    "msx-vg-8010": """
        Philips's first MSX, and the machine that pushed the standard hardest in the
        Netherlands — where MSX did better than anywhere outside Japan. 32K, a solid
        case, and Philips's European distribution behind it.
        """,
    "msx-vg-8020": """
        The MSX1 most European households actually had: 64K, a decent keyboard, and
        Philips selling it through every high street in the Benelux. Common, reliable
        and the obvious first MSX1. The keyboard membrane is the usual repair.
        """,
    "msx-svi-728": """
        Spectravideo's MSX machine, from the company whose earlier SV-328 had been the
        template the MSX standard was built from. That lineage is the interesting part:
        the SVI-728 is the standardised version of the machine that inspired the
        standard.
        """,
    "msx-canon-v-20": """
        Canon's MSX1, sold in Britain and Europe with 64K. Canon was one of the many
        Japanese makers the standard brought into computing briefly before they went
        back to cameras and printers. Uncommon in the UK and a tidy machine.
        """,
    "msx-jvc-hc-7gb": """
        JVC's MSX for the British market — the GB suffix says so. JVC's involvement was
        brief and the machines are correspondingly scarce here. Standard MSX1 hardware
        in a maker's case you would not otherwise associate with computers.
        """,
    "msx-mitsubishi-ml-f80": """
        Mitsubishi's MSX1, sold mainly in Japan. Another of the large industrial names
        that the MSX standard drew in for a couple of years. Ordinary specification,
        uncommon outside its home market.
        """,
    "msx-sanyo-phc-28": """
        Sanyo's MSX1, notable in the family for the light-pen port that some Sanyo
        models carried — a Sanyo speciality that no other MSX maker pursued. Otherwise
        standard hardware.
        """,
    "msx-daewoo-dpc-200": """
        Korea's contribution to MSX. Daewoo built MSX machines for the Korean domestic
        market and for export to Europe under several names, and the Korean MSX scene
        produced its own software. An unusual branch of the standard's history.
        """,
    "msx-goldstar-fc-200": """
        Goldstar — later LG — building MSX for Korea and export. Korean MSX machines
        are a distinct and under-documented part of the standard's story, and this is
        one of the more commonly encountered of them.
        """,
    "msx2-hb-f1xd": """
        A Sony MSX2 with a disc drive built in, and the generation where the standard
        got serious: 128K of video memory, 512 colours, hardware scrolling and a
        sprite engine that made Konami's MSX2 games genuinely impressive. The F1
        machines are well regarded.
        """,
    "msx2-hb-f1xv": """
        The last of Sony's F1 MSX2 line, with the improved video chip and a disc drive.
        A late, well-developed MSX2 and one of the better machines for running the
        MSX2 library, which is the strongest part of the whole standard.
        """,
    "msx2-hb-f900": """
        Sony's top MSX2: a full expansion-slot chassis with two drives and 256K, aimed
        at professional and development use rather than the living room. The most
        capable Japanese MSX2 Sony made and a serious collector's machine.
        """,
    "msx2-fs-a1": """
        Panasonic's cost-cutting masterstroke: an MSX2 at a price that undercut every
        rival and effectively took the Japanese MSX2 market. It is why MSX2 sold at all
        in volume, and it is the common Japanese MSX2 as a direct result.
        """,
    "msx2-fs-a1f": """
        The FS-A1 with a disc drive built in — the configuration most MSX2 software
        actually needs, since the good MSX2 titles came on disc. The practical Panasonic
        MSX2 and easy enough to find.
        """,
    "msx2-nms-8250": """
        Philips's MSX2 for Europe, and the machine the European MSX2 scene was built
        on: a proper keyboard, a 3.5-inch drive, RGB output and 128K. Widely sold in
        the Netherlands and Spain. The best MSX2 to own if you are in Europe.
        """,
    "msx2-vg-8235": """
        Philips's earlier European MSX2, with a single-sided drive that is the one
        practical limitation — some later disc software assumes double-sided. Otherwise
        a solid MSX2 and common in the Benelux.
        """,
    "msx2p-fs-a1wsx": """
        An MSX2+: the Japan-only final revision of the standard, adding 19,268-colour
        modes, hardware horizontal scrolling and the MSX-MUSIC FM chip as standard.
        The scrolling is what makes late MSX2+ games look startlingly good. Never sold
        outside Japan.
        """,
    "msx-turbo-r-fs-a1st": """
        The last MSX ever made, and only Panasonic made it: the R800, a much faster
        processor developed for the machine, alongside a Z80 for compatibility, with
        a MIDI interface and a PCM sound chip. Japan only, expensive, and the end of
        a standard that ran nine years.
        """,
    "msx-turbo-r-fs-a1gt": """
        The top turbo R and the final MSX machine of all: the A1ST's hardware with
        MIDI in and out, more memory and Panasonic's best finish. Made in small
        numbers for the Japanese market in 1991 and now the most sought-after MSX
        there is.
        """,
    # --- Tandy ------------------------------------------------------------
    "trs-80-model-1": """
        One of the three machines that started personal computing in 1977, and the one
        sold through a chain of high-street shops — Radio Shack had three thousand of
        them, which is how the TRS-80 outsold the Apple II early on. Notoriously
        radiated so much interference that the FCC took an interest. The expansion
        interface is the part that goes missing.
        """,
    "trs-80-model-2": """
        Tandy's business machine, and a completely different design from the Model I: a
        4MHz Z80, an 8-inch floppy drive and a metal case, aimed at accountants rather
        than hobbyists. Expensive when new, heavy, and the 8-inch media is now the real
        obstacle to using one.
        """,
    "trs-80-model-3": """
        The Model I's problems fixed: everything in one case, the interference dealt
        with, lower case as standard and disc drives that fit inside. It is the
        practical classic TRS-80 and the one most of the software library assumes. Very
        well built.
        """,
    "trs-80-model-4": """
        The last of the Z80 TRS-80 desktops: 128K, an 80×24 display and CP/M
        compatibility, which finally gave the line access to the wider business
        software catalogue. Runs Model III software too, so it is the most capable
        machine of the family.
        """,
    "trs-80-model-100": """
        The machine journalists actually used. A full-size keyboard, an eight-line LCD,
        a built-in modem and twenty hours from four AA cells, in 1983 — reporters filed
        copy from anywhere for a decade, and it is the last product Bill Gates wrote
        code for personally. One of the genuinely great portable designs.
        """,
    "trs-80-model-102": """
        The Model 100 slimmed down and cost-reduced, with the same keyboard and the
        same extraordinary battery life. Functionally near-identical and rather nicer
        to carry. Both are still used by writers, which is a remarkable thing to say
        about a machine from 1986.
        """,
    "trs-80-mc-10": """
        Tandy's cheapest computer: 4K, a chiclet keyboard and a 6803, sold against the
        Sinclair machines in 1983 and dropped within a year. Very limited, and
        consequently a footnote — but a cheap and cheerful one with a small and
        determined following.
        """,
    "tandy-coco": """
        The Color Computer, and an oddity in Tandy's Z80-based catalogue: a 6809, the
        best 8-bit processor anybody made, with Microsoft BASIC and a cartridge slot.
        The 6809 is why OS-9 — a genuine multitasking, multi-user operating system —
        ran on a home computer in 1980.
        """,
    "tandy-coco-2": """
        The CoCo cost-reduced into a smaller case with a better keyboard. The most
        common of the three and the one most CoCo software targets. Same 6809 and the
        same OS-9 capability, which is where the interest lies.
        """,
    "tandy-coco-3": """
        The CoCo done properly: 128K expandable to 512K, a 640×192 sixteen-colour mode
        and a proper memory management unit, which made OS-9 Level II genuinely usable.
        The best of the family by a wide margin and the one worth seeking out.
        """,
    # --- Oric, Dragon, Osborne, Jupiter, SAM ------------------------------
    "oric-1": """
        Britain's other 1983 home computer, and the one that got closest to the
        Spectrum on price while offering a proper keyboard and the AY sound chip
        Sinclair left out. Let down by a buggy ROM and unreliable tape loading, both
        of which the Atmos fixed. It sold well in France, which is where the platform
        survived.
        """,
    "oric-atmos": """
        The Oric-1 corrected: a fixed ROM, reliable tape loading and a proper black-and
        -red case with real keys. Too late for Britain, where Oric collapsed, but it
        became a genuinely popular machine in France and has an active French following
        to this day.
        """,
    "oric-telestrat": """
        The last Oric, made in France after the British company failed: a redesigned
        machine with cartridge slots, a Minitel interface and a business bent. Very few
        were made and it is among the rarest of the British-designed home computers,
        French-built though it is.
        """,
    "dragon-32": """
        A Welsh-built CoCo relative: the same 6809 and broadly compatible hardware,
        made in Port Talbot and sold as a British machine with a proper keyboard and a
        parallel printer port the Tandy lacked. It failed commercially in 1984, but the
        6809 and the Welsh manufacturing make it a distinctive collectable.
        """,
    "dragon-64": """
        The Dragon 32 with 64K, a serial port and OS-9 available — which turns it from
        a games machine into something that runs a real operating system. The better of
        the two and the one the surviving Dragon community mostly uses.
        """,
    "tano-dragon-64": """
        The Dragon 64 built under licence in New Orleans by Tano, for the American
        market, after the British company's troubles began. Very few were made before
        Tano gave up, which makes it substantially rarer than the Welsh machines and a
        genuine curiosity.
        """,
    "osborne-1": """
        The first commercially successful portable computer: a complete CP/M machine
        with two drives and a five-inch screen in a sewing-machine case, bundled with
        more software than it cost. Adam Osborne then announced its successor early,
        sales of this stopped dead, and the company failed — the origin of the phrase
        "the Osborne effect".
        """,
    "osborne-executive": """
        The machine that killed the company: announced while the Osborne 1 was still
        selling, which stopped those sales before this could ship. Better in every way
        — a seven-inch screen, more memory, a proper case — and a permanent business
        school lesson about pre-announcement.
        """,
    "jupiter-ace": """
        The computer that spoke Forth instead of BASIC, from two ex-Sinclair engineers.
        Forth is faster and more compact than interpreted BASIC and almost nobody
        wanted to learn it, so the Ace sold a few thousand and the company folded
        within a year. That failure makes it one of the most sought-after British home
        computers there is.
        """,
    "sam-coupe": """
        The Spectrum's would-be successor, from Miles Gordon Technology in 1989: a 6MHz
        Z80, 256K, proper graphics modes, a six-channel sound chip and a Spectrum
        emulation mode. It arrived four years too late into a 16-bit market and the
        company failed twice. Beloved by a small, active community and genuinely good
        hardware.
        """,
    # --- other British and European ---------------------------------------
    "camputers-lynx": """
        A Cambridge-built machine with unusually good high-resolution graphics for
        1983 and a well-regarded BASIC, undone by having almost no software and a
        company that lasted a year. Uncommon and technically more interesting than its
        obscurity suggests.
        """,
    "camputers-lynx-96": """
        The 96K Lynx, and the configuration the machine really needed — the extra
        memory makes its high-resolution modes usable. Camputers folded in 1984, so
        production was short and surviving machines are scarce.
        """,
    "camputers-lynx-128": """
        The top of a very short line: 128K, and the last Lynx before Camputers went
        under. Made in tiny numbers, well built, and one of the harder British home
        computers of the era to find in working order.
        """,
    "memotech-mtx512": """
        A beautifully made British machine: a brushed aluminium case, a proper
        keyboard, a Z80 and a TMS9918, from a company that had made ZX81 expansions.
        It looks and feels far more expensive than it was and had almost no software.
        The build quality alone makes it worth having.
        """,
    "enterprise-128": """
        A Hungarian-designed British machine, delayed so long that its own name changed
        twice before release — Elan, then Flan, then Enterprise. Two custom chips, 672
        colours and a wedge case with a built-in joystick. It arrived in 1985 into a
        market that had already chosen, and is now collected in Hungary in particular.
        """,
    "grundy-newbrain": """
        The machine that nearly became the BBC Micro: developed at Newbury Labs and a
        serious contender for the BBC contract before Acorn won it. A single-line
        vacuum-fluorescent display on the AD model, CP/M capability, and a design
        aimed at being expanded rather than played with. Historically interesting for
        the contract it lost.
        """,
    "tatung-einstein": """
        A British-designed, Taiwanese-built CP/M machine with disc drives built in,
        aimed at small business and at software developers — a good deal of Spectrum
        and CPC software was actually written on Einsteins, which is its real claim.
        Well made and uncommon.
        """,
    "compukit-uk101": """
        A British kit computer from 1979, derived from the Ohio Scientific Superboard
        and sold through Practical Electronics as a magazine project. You built it
        yourself from a bag of parts. It taught a generation of British engineers to
        solder, and surviving examples reflect whoever built them.
        """,
    "microtan-65": """
        Tangerine's expandable 6502 board, sold bare and grown by adding cards on a
        rack — a hobbyist system rather than a product. Tangerine's people went on to
        found Oric. Interesting as a British modular machine and as the company's
        first step.
        """,
    "nascom-1": """
        A British Z80 kit from 1977, sold as a bare board with a keyboard, and one of
        the first computers a British hobbyist could actually buy and build. Fairly
        demanding to assemble. Historically significant in Britain and now
        genuinely rare.
        """,
    "nascom-2": """
        The Nascom 1 developed: a 4MHz Z80, Microsoft BASIC in ROM and a proper
        expansion bus, still sold as a kit. It became the standard British hobbyist
        machine before the Spectrum and it is the more usable of the two. Often found
        in a homebuilt case, which is part of the charm.
        """,
    "mk14": """
        Clive Sinclair's first computer: a £40 single-board kit with a calculator
        keypad and a seven-segment display, sold by Science of Cambridge in 1978. It
        is barely a computer and it is where Sinclair's whole computing business began
        — the direct ancestor of the ZX80. Historically important and often found
        badly built.
        """,
    "rm-380z": """
        The machine that computerised British schools before Acorn: Research Machines
        built serious, robust Z80 systems for education from 1977, and a great many
        British children met a computer in a maths room through one of these. Heavy,
        modular and built to survive teenagers.
        """,
    "rm-link-480z": """
        The networked classroom machine: Research Machines built the 480Z to work as a
        cluster over its own network with a shared disc, which is how British schools
        actually ran computer rooms in the early eighties. That networking is the
        interesting part and it long predates it being ordinary.
        """,
    "rm-nimbus": """
        The PC-186 was Research Machines going its own way: an 80186 machine that ran
        MS-DOS but was not PC compatible, networked for the classroom, and consequently
        the machine on which a great many British children first used Windows. Ubiquitous
        in British schools and now surprisingly hard to find.
        """,
    "grid-compass-1101": """
        The first clamshell laptop ever made, and one of the most significant computers
        in the collection of any museum: a magnesium case, a bright electroluminescent
        display, bubble memory instead of a disc, and a price around eight thousand
        dollars in 1982. NASA flew them on the Space Shuttle. Extremely rare and
        extremely important.
        """,
    "kaypro-ii": """
        The Osborne beaten at its own game: a CP/M luggable in a painted metal case
        with a proper nine-inch screen — big enough to actually use, which the
        Osborne's five-inch was not — and a pile of bundled software. It took the
        portable CP/M market and is robust enough that many still work.
        """,
    "kaypro-2x": """
        The Kaypro developed: double-sided drives and a better keyboard, in the same
        indestructible metal case. These were sold hard to writers and small
        businesses and turn up more often than almost any other CP/M machine, usually
        still working.
        """,
    "abc-80": """
        Sweden's own computer, and the machine that taught Swedish schools: a Z80 with
        a well-regarded BASIC, sold by Luxor and adopted nationally in education.
        Almost unknown outside Scandinavia and central to computing history within it.
        """,
    "abc-800": """
        The ABC 80's successor, with high-resolution graphics and disc drives, sold
        into Swedish offices and laboratories. Luxor's machines dominated Sweden the
        way Acorn's dominated British schools, and this is the professional one.
        """,
    "philips-p2000t": """
        Philips's own home computer, using mini-cassette tapes rather than compact
        cassettes and sold mainly in the Netherlands and Germany. Notable for the
        Teletext display option, a very Philips preoccupation. An unusual machine from
        a company better known for making everybody else's components.
        """,
    "matra-alice": """
        A bright red French home computer, built by Matra and Hachette from the Tandy
        MC-10 design and sold with an educational bent — the colour and the French
        keyboard are what make it memorable. Nothing else looks like it, which is most
        of the reason people want one.
        """,
    "thomson-mo5": """
        The machine of the French "plan informatique pour tous", which put computers
        into every French school in 1985 — so this is the machine a generation of
        French children learned on, much as the BBC Micro was in Britain. Light pen
        rather than joystick, and enormous domestic significance.
        """,
    "thomson-to7": """
        Thomson's first home computer and the start of the French national platform: a
        6809 with a cartridge slot and a light pen, and a membrane keyboard that
        nobody defends. Historically important in France and awkward to use.
        """,
    "thomson-to7-70": """
        The TO7 with more memory and a better keyboard, and the version that went into
        French schools alongside the MO5. The most commonly encountered Thomson and the
        practical one of the early pair.
        """,
    "thomson-mo6": """
        The MO5 developed, with more memory, better graphics and a proper keyboard, in
        1986. Sold in France and, as the Olivetti Prodest PC128, in Italy. The best of
        the MO line and a good deal less common than the MO5.
        """,
    "thomson-to8": """
        The most capable Thomson: 256K, improved graphics modes and a built-in disc
        controller, aimed at the French home and education markets in 1986. If you
        want a Thomson that is genuinely pleasant to use, this is it.
        """,
    "thomson-to9": """
        Thomson's business machine: a TO-series computer with a built-in 3.5-inch drive
        and bundled office software, sold at a price that met neither the home nor the
        professional market convincingly. Uncommon, and interesting as the top of a
        national platform.
        """,
    "didaktik-gama": """
        A Czechoslovak Spectrum clone, built in Slovakia because the real thing was
        effectively unobtainable behind the Iron Curtain. Better keyboard than a
        Sinclair, 80K of memory, and a whole domestic software scene that grew around
        it. Essential to understanding eastern European computing.
        """,
    "didaktik-m": """
        The later Didaktik, closer to Spectrum compatibility and widely used in Czech
        and Slovak schools. These machines are how a generation in Czechoslovakia met
        computing, and the local software written for them is a body of work that
        exists nowhere else.
        """,
    "elwro-800-junior": """
        A Polish Spectrum-compatible built for schools, with a CP/M mode and a
        network interface for a classroom cluster — considerably more ambitious than a
        straight clone. Made in Wrocław in modest numbers and central to Polish
        educational computing.
        """,
    "pravetz-82": """
        Bulgaria's Apple II clone, made in Pravets and exported across the Eastern
        bloc. Bulgaria was the Comecon countries' computer factory, and these machines
        are how Apple II software reached the other side of the Iron Curtain. Solidly
        built and historically fascinating.
        """,
    "pravetz-8d": """
        Bulgaria's Oric Atmos clone, sold as a home machine while the 82 served
        schools and offices. That a Bulgarian state factory chose to copy an Oric is
        itself a curious detail of the period. Uncommon outside eastern Europe.
        """,
    "robotron-z9001": """
        East Germany's home computer, from the Robotron combine, running on the U880 —
        the DDR's own unlicensed Z80 copy. Built to a shortage economy's constraints
        and sold at prices that put it beyond most families. A significant object in
        the history of computing behind the Wall.
        """,
    "robotron-kc-85-3": """
        The DDR's school computer: a modular grey box with expansion slots, built by
        Robotron for East German education and industry. The KC 85 line has an active
        following in Germany and the machines are well documented — unusually so for
        eastern bloc hardware.
        """,
    "robotron-a5105": """
        A late East German machine, more capable than the KC 85 and intended for
        schools, arriving in 1989 — which is to say, just as the state that
        commissioned it ceased to exist. Very few were made, and the timing makes it a
        poignant collectable.
        """,
    "elektronika-bk-0010": """
        A Soviet home computer built around the K1801VM1, a single-chip implementation
        of the PDP-11 instruction set — so this is a DEC minicomputer architecture in a
        home machine, which nothing in the West ever was. That alone makes it one of
        the most interesting machines of the period.
        """,
    "videoton-tvc": """
        Hungary's home computer, made by Videoton for the domestic market and schools.
        Hungary had an unusually lively computing culture for a Comecon country, and
        the TVC is its home-grown machine. Rare outside Hungary.
        """,
    "video-genie": """
        A Hong Kong-built TRS-80 Model I clone, sold across Europe where Tandy's own
        distribution was thin, with a built-in cassette deck the original lacked. One
        of the first Far Eastern clones of an American computer and a small landmark
        for that reason.
        """,
    "colour-genie": """
        EACA's own design rather than a clone: a Z80 machine with colour, sound and a
        proper keyboard, sold in Britain and Germany where it acquired a following
        that outlasted the company — EACA collapsed in 1983. The German scene kept it
        alive and there is more software than there should be.
        """,
    "exidy-sorcerer": """
        An arcade company's home computer, and a genuinely clever one: the character
        set is redefinable, which gave it pseudo-graphics well beyond its
        specification, and software came on "ROM PACs" in eight-track cassette shells.
        Sold well in Australia and the Netherlands. Unusual and well regarded.
        """,
    "sol-20": """
        The first computer sold with a case, a keyboard and a power supply as one
        product — before the 1977 trio, from Processor Technology, with walnut side
        panels and Lee Felsenstein's design. It is arguably the first personal computer
        in the modern sense and is now a serious collector's item.
        """,
    "altair-8800": """
        The machine that started it all. The January 1975 Popular Electronics cover
        created the personal computer industry, the Homebrew Computer Club formed
        around it, and Microsoft's first product was a BASIC written for it. Front
        panel switches and lights, no keyboard, no screen. Among the most historically
        valuable computers there is.
        """,
    "imsai-8080": """
        The Altair done properly: better engineered, better supported, and the machine
        that made the S-100 bus a real standard. It is also the computer on the desk in
        WarGames, which is how most people know it. A serious and quite common early
        S-100 machine.
        """,
    "heathkit-h8": """
        Heathkit applying its famous kit-building discipline to computers: an 8080
        system with an octal front panel, superb documentation and manuals that
        actually taught electronics. Heathkit kits were built by people who wanted to
        understand the machine, and it shows in the survivors.
        """,
    "heathkit-h89": """
        The all-in-one Heathkit: terminal, computer and disc drive in one case, running
        Z80 and HDOS or CP/M. Sold as a kit or assembled, and widely used by engineers
        and radio amateurs. The documentation remains the best of any machine of the
        era.
        """,
    "osi-superboard-ii": """
        A complete computer on one bare board for under three hundred dollars in 1979 —
        processor, keyboard, video and BASIC, with no case at all. Ohio Scientific's
        design was copied in Britain as the Compukit UK101. You supplied the box, which
        is why no two look alike.
        """,
    "franklin-ace-1000": """
        An Apple II clone good enough that Apple sued and won, in a case that
        established copyright in ROM code — one of the most consequential lawsuits in
        software history. Franklin's machine had more memory and a better keyboard than
        the machine it copied. Collected for the legal history as much as the hardware.
        """,
    "victor-9000": """
        Chuck Peddle's machine — the man who designed the 6502 and the PET — and
        technically far better than the IBM PC it competed with: variable-speed drives
        holding twice the data, a high-resolution display, and superb sound. It was not
        PC compatible, so it lost. A brilliant machine and a clear lesson about
        standards.
        """,
    "olivetti-m20": """
        Olivetti going its own way with the Zilog Z8001, a 16-bit processor that was
        not Intel's — released in 1982, just as the industry was settling on the 8088.
        Beautifully made and commercially doomed by the choice. The most interesting
        Olivetti of the period for exactly that reason.
        """,
    "olivetti-m24": """
        Olivetti's answer to the IBM PC and a better machine than it: a full 16-bit
        8086 on a 16-bit bus, so genuinely faster than the 8088 original, with
        Olivetti's industrial design throughout. Sold in America as the AT&T PC 6300
        and very successful in Europe.
        """,
    "olivetti-m10": """
        Olivetti's version of the Kyocera design that also became the TRS-80 Model 100
        and the NEC PC-8201 — with one improvement nobody else made: the screen tilts.
        Same excellent keyboard and battery life. The tilting display makes it the nicest
        of the family to use.
        """,
    "zenith-z100": """
        A dual-processor machine with both an 8088 and an 8085, so it ran CP/M-85 and
        MS-DOS software — Zenith hedging in 1982 on which standard would win. Not PC
        compatible. Well built, and the S-100 slots make it expandable in ways a PC was
        not.
        """,
    "zenith-z150": """
        Zenith's PC compatible, and the machine that won it enormous US government
        contracts — Zenith Data Systems supplied the American federal government and
        military in bulk through the eighties. Solidly built, and surviving examples
        often carry government asset tags.
        """,
    "zenith-z171": """
        A luggable PC with twin floppy drives and an LCD that folds down over the
        keyboard, sold heavily to the US government. One of the more usable portables
        of 1985 and much less common in Europe than in America.
        """,
    "zenith-supersport": """
        The laptop that won the US Air Force's enormous 1988 procurement, which is why
        so many exist and why so many are marked with military inventory numbers. A
        good, ordinary 8088 laptop with an extraordinary sales history.
        """,
    "zenith-z386": """
        Zenith's 386 desktop, sold into the government and corporate contracts the
        company specialised in. Unremarkable hardware, notable as the top of a line
        from a maker that was for a while the largest supplier of PCs to the US
        federal government.
        """,
    "zenith-eazy-pc": """
        An all-in-one PC with the monitor built in, a NEC V40, and no expansion slots
        at all — Zenith aiming at first-time buyers in 1987 and misjudging what they
        wanted. It failed. The sealed, slotless design makes it an interesting dead end.
        """,
}
