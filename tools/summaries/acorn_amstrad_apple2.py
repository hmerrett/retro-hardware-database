"""Acorn, Amstrad, the Amstrad PCs and the Apple II line."""

SUMMARIES = {
    # --- Acorn ------------------------------------------------------------
    "acorn-atom": """
        Acorn's first complete computer, sold as a kit or built, and the machine that
        got the company into the room for the BBC contract. A 6502 with Acorn's own
        BASIC in ROM, expandable to floating point and colour, in a wedge case with a
        real keyboard when rivals offered calculator keys. Most interesting as the
        direct ancestor of the Proton prototype that became the BBC Micro, and as
        evidence of how quickly Acorn moved between 1980 and 1981.
        """,
    "bbc-model-a": """
        The cheap Beeb: 16K of memory, no printer or analogue ports fitted, and the
        expectation that a school would upgrade it later. Most were, which is why the
        Model A is markedly scarcer than the B despite being sold alongside it — an
        unmodified one, with the empty sockets still empty, is the find. Otherwise
        identical hardware, so it demonstrates Acorn's design intent: one board, sold
        at two prices, with the difference in what is fitted.
        """,
    "bbc-b-plus": """
        Acorn's stopgap between the Model B and the Master: 64K or 128K of memory
        with shadow RAM for the screen, freeing space that the B could not spare, and
        the 1770 floppy controller as standard. Sold mainly into schools already
        committed to the platform, and unloved at the time for being neither one
        thing nor the other. That makes it uncommon now, and it runs a body of later
        software that will not fit a Model B.
        """,
    "bbc-master-128": """
        The BBC Micro finished properly. 128K, the 65SC12 processor, a numeric keypad,
        the 1770 controller, and the ROM software — View, Viewsheet, ADFS, Terminal —
        built in rather than bought as chips. It is the machine the Model B should
        have been by 1986, and the one that stayed in British schools until the
        Archimedes replaced it. Watch the battery: leaking CMOS cells have destroyed
        a great many Master boards.
        """,
    "bbc-master-compact": """
        The Master unbundled into three boxes — keyboard, monitor, drive — and aimed
        at the home rather than the classroom. Cheaper than a Master 128 and with a
        3.5-inch drive when the rest of the platform was still on 5.25, which makes
        it the odd one out in the family and the awkward one to find media for. The
        least common Master, and the last BBC-badged machine Acorn made.
        """,
    "acorn-electron": """
        Acorn's cut-down Beeb for the home: one custom ULA doing the work of the
        Model B's several, which halved the cost and roughly halved the speed. It
        arrived to enormous demand at Christmas 1983 and Acorn could not build them,
        a failure that cost the company its independence. As hardware it is a neat
        piece of integration; as history it is the machine that broke Acorn, and the
        ULA is the part that fails.
        """,
    "acorn-a310": """
        One of the first ARM machines anybody could buy. The 1987 Archimedes launch
        put Acorn's own 32-bit processor — designed in-house because nothing on the
        market was good enough — into a desktop computer running Arthur, later RISC
        OS. It was faster than anything at the price and had almost no software. The
        significance is hard to overstate: every ARM core shipped since traces to
        this design.
        """,
    "acorn-a440": """
        The top of the 1987 Archimedes launch: 4MB of memory and a hard disc when the
        A310 had half a megabyte and floppies, aimed at technical and publishing work
        rather than schools. Expensive at the time and consequently uncommon now. The
        interest is the same as the A310's — early ARM2, and Acorn's argument that a
        British RISC design could beat the American 68000s — with the specification
        the argument deserved.
        """,
    "acorn-a3000": """
        The Archimedes that schools actually bought: one wedge case with the keyboard
        built in, priced for an education budget, and consequently the most common
        ARM machine of its generation in Britain. If you used a computer in a British
        classroom around 1990 it was probably this. Same ARM2 as the A310 in a
        cheaper package, and the case design that Acorn reused for the A3010 that
        followed it.
        """,
    "acorn-a5000": """
        The professional Archimedes: ARM3 at 25MHz, RISC OS 3, a high-density floppy
        and IDE on the board. It is the fastest and best-equipped of the classic
        Archimedes line before the Risc PC changed the shape of the range, and the
        one to have if you want a period ARM desktop that is genuinely pleasant to
        use rather than merely historically interesting.
        """,
    "acorn-a3010": """
        Acorn's last serious attempt at the British home market: an ARM250 — the
        ARM2 with the memory, video and I/O controllers folded into one chip — in the
        A3000's wedge case, sold through high-street shops with a joystick port and a
        games bundle. It did not work; the Amiga and the PC had the market. As
        hardware the ARM250 integration is the point, and it makes the machine simple
        and reliable.
        """,
    "acorn-a3020": """
        The A3010's school-and-office sibling: the same ARM250 wedge with an internal
        hard disc bay and a proper network socket for Acorn's Econet. Sold into
        education where the A3000 had been, and the version most likely to turn up
        with period software still on the drive. Fitted machines are more useful than
        A3010s and no harder to find.
        """,
    "acorn-a4000": """
        The A3020's boards in a separate desktop case with a detachable keyboard, for
        buyers who wanted an Archimedes that looked like a workstation rather than a
        home computer. Mechanically the most conventional of the ARM250 machines and
        the easiest to work in. Uncommon, having sold in far smaller numbers than the
        wedges either side of it.
        """,
    "acorn-a4": """
        The first ARM laptop. Acorn folded an ARM3 at 24MHz and RISC OS 3.11 into a
        clamshell with a mono LCD in 1992, years before anybody else shipped a
        portable RISC machine. Expensive, made in small numbers, and now genuinely
        rare — the screens and the batteries are the usual casualties. A landmark
        given what ARM laptops eventually became.
        """,
    "acorn-risc-pc": """
        Acorn's answer to the PC: a stackable "slice" case you could add height to,
        two processor sockets, and the option of a genuine 486 card so RISC OS and
        Windows ran on one desk at once. That second socket is the collector's draw,
        along with a case design nobody else attempted. The last Acorn desktop line
        before the company left the computer business.
        """,
    "acorn-a7000": """
        Named like a Risc PC and built like neither: an ARM7500 with the video, sound
        and I/O on the processor die, in a cost-reduced case for the education market.
        The integration makes it the simplest RISC OS machine of the period and the
        cheapest way into one, at the cost of the expandability the Risc PC was sold
        on. A useful, unglamorous machine that schools bought by the trolley.
        """,

    # --- Amstrad ----------------------------------------------------------
    "cpc-464": """
        The machine that made Amstrad a computer company: a Z80 with the tape deck
        built in, a proper keyboard, and a monitor in the box, sold at a price that
        undercut everything. Locomotive's BASIC is the best of its generation and the
        Amstrad-designed gate array gives it a genuinely good palette. The volume
        seller of the CPC range by a wide margin, and the one that turns up with its
        original green-screen monitor.
        """,
    "cpc-664": """
        Amstrad's shortest-lived machine. The 664 put a 3-inch disc drive in the 464's
        case and was replaced by the 6128 within months, having been made obsolete by
        Amstrad's own next announcement. That gives it a production run of about half
        a year and makes it easily the rarest of the mainstream CPCs — the one CPC
        collectors actually hunt for rather than merely acquire.
        """,
    "cpc-6128": """
        The CPC finished: 128K, a 3-inch disc drive, and CP/M Plus in the box, which
        turned a games machine into something that ran serious software. The banked
        memory is the interesting part, and the reason a body of CPC software will not
        run on a 464. The drive belts perish, which is the first thing to check, and
        the 3-inch discs are now the scarce consumable.
        """,
    "cpc-472": """
        A tax dodge in a case. Spain levied duty on computers with 64K or less and a
        keyboard without Ñ, so Amstrad's Spanish distributor shipped 464s with a
        daughterboard carrying an extra, entirely unused 8K of ROM and a modified
        keyboard — enough to make the machine legally a 472. Sold only in Spain, in
        small numbers, and the pointless daughterboard is exactly why collectors want
        one.
        """,
    "cpc-464-plus": """
        Amstrad's 1990 revision of the CPC: hardware sprites, scrolling, a proper
        DMA sound engine and a cartridge slot, in a restyled case. Everything the
        original needed to compete, arriving about four years late into a market the
        Amiga had already taken. Backwards compatible with the 464, so it is the best
        CPC to own and the one almost nobody bought.
        """,
    "cpc-6128-plus": """
        The Plus hardware with 128K and a 3-inch drive — the top of the CPC line and
        the last machine of the family. The improved graphics and sound are worth
        having and the cartridge slot takes the GX4000 titles, which makes it the most
        capable Amstrad 8-bit by some distance. Sold badly, like everything in the
        Plus range, so it is uncommon.
        """,
    "gx4000": """
        Amstrad's console: the Plus chipset with the keyboard and tape deck taken
        away, launched in 1990 against the Mega Drive and the Super Famicom with
        8-bit hardware and a catalogue of about thirty games, several of which were
        CPC ports on a cartridge. It failed almost immediately and was cleared at
        knock-down prices. A famous commercial disaster, and cheap for what is
        genuinely capable hardware.
        """,
    "pcw-8256": """
        Not a home computer but a word processor that happened to be one. Amstrad sold
        the PCW as a complete writing machine — screen, printer, discs and LocoScript
        in one box — for the price of a typewriter, and shifted them by the million to
        people who would never have bought a computer. Underneath is a Z80 running
        CP/M Plus, so it takes the whole CP/M software catalogue.
        """,
    "pcw-8512": """
        The PCW with 512K and a second, larger disc drive, for people doing enough
        writing to be swapping discs. Same machine otherwise, and the extra memory
        makes it markedly better under CP/M than the 8256. The printer is the part
        that dies, and a PCW without its own printer is a much less interesting
        object than one with it.
        """,
    "pcw-9512": """
        The PCW with a daisywheel printer instead of the dot-matrix, sold to people
        who needed letters that looked typed rather than printed. That printer is the
        whole difference and the reason the 9512 cost more; it is also heavy, loud,
        and the first thing to fail. A complete working example with its own printer
        and daisywheels is uncommon.
        """,
    "pcw-9256": """
        The last of the PCWs, cost-reduced for 1991 with the memory and drive of an
        8256 in the later styling. By this point the PC had taken the market the PCW
        invented and Amstrad was clearing the line. Least regarded of the family, and
        consequently the cheapest way to have one — the CP/M machine underneath is
        the same as any other PCW's.
        """,
    "amstrad-nc100": """
        A Z80 notepad the size of a hardback: an eight-line screen, a full-travel
        keyboard, PCMCIA memory cards, and batteries that lasted weeks because there
        was nothing in it to drain them. Sold as a writer's machine and still used as
        one — there is an active following, and the serial port means text actually
        gets off it. One of Amstrad's genuinely well-judged products.
        """,
    "amstrad-nc200": """
        The NC100 with a sixteen-line backlit screen and a 3.5-inch floppy drive,
        which fixed the earlier machine's only real problem: getting the writing out.
        Heavier and hungrier for it, and sold in much smaller numbers, so it is the
        harder of the two to find. The drive is usually the part that has failed.
        """,

    # --- Amstrad PC -------------------------------------------------------
    "amstrad-pc1512": """
        The machine that broke the price of the PC in Britain. Amstrad sold a complete
        16-bit computer with monitor, mouse and GEM for under £400 in 1986 and took
        a quarter of the European market with it. Everything is subordinate to that
        price: the power supply is in the monitor, so the machine will not run without
        one, and there is no fan — which is why so many died of heat.
        """,
    "amstrad-pc2086": """
        Amstrad's 1988 successor to the 1640, with VGA on the board when VGA was
        still an expensive option elsewhere, and the 3.5-inch drive that the 2000
        series became notorious for. Still an 8086, so it is slow for its date, but
        the integrated VGA makes it a tidy period machine for DOS graphics. The
        2000-series hard disc problems are the reason to check what is fitted.
        """,
    "amstrad-pc2386": """
        The top of Amstrad's business range: a 386SX with VGA, sold to buyers who had
        outgrown a 1640 and had not yet lost faith in the brand. It is the most
        capable PC Amstrad made in the period and among the least common, the 2000
        series having been overtaken by its own reputation before it sold in volume.
        """,
    "amstrad-ppc512": """
        The first laptop-shaped PC most British buyers ever handled: a full keyboard,
        a supertwist LCD, two floppy drives and ten C-cells, with a modem socket on
        the back. It is not a laptop — it is far too heavy to use on one — but it runs
        for hours on shop batteries and folds shut, which in 1987 was remarkable at
        the price. The screen hinge is the usual break.
        """,
    "amstrad-ppc640": """
        The PPC512 with 640K and, in most configurations, an internal modem, which
        made it a genuinely useful machine for a travelling salesman in 1987. Same
        chassis and the same C-cell arrangement. The modem version is the one worth
        having, and the batteries left in the compartment for thirty years are the
        reason to open it before powering it up.
        """,

    # --- Apple II ---------------------------------------------------------
    "apple-ii": """
        The machine that created the personal computer market. Wozniak's design does
        more with fewer chips than anything of its generation — the disc controller
        and the colour graphics are famous pieces of engineering economy — and the
        open slots meant a whole industry grew inside it. VisiCalc, which ran here
        first, is what put computers on office desks. Original 1977 machines with the
        early boards are serious collector's items.
        """,
    "apple-ii-plus": """
        The II with Applesoft floating-point BASIC in ROM instead of Woz's integer
        version, and autostart, which meant the machine was usable without a manual.
        This is the Apple II that sold in volume through the early eighties and the
        one most surviving software expects. Mechanically and electrically it is a II,
        so it has the same slots and the same repairability.
        """,
    "apple-iie": """
        The Apple II consolidated: 64K, lower case, a proper keyboard and most of the
        common expansions folded onto the board, with two slots' worth of clutter
        removed. It stayed in Apple's catalogue for eleven years, longer than any
        other model the company has sold, largely because American schools kept
        buying it. The enhanced and platinum revisions are worth telling apart.
        """,
    "apple-iic": """
        Apple's portable II: the whole machine, with a disc drive, in a flat white
        case with a carrying handle and no slots at all. It is the II reduced to a
        sealed appliance, which is either the interesting part or the disappointing
        one depending on what you want from an Apple II. Snow-white industrial design
        by Frogdesign, and the machine that set Apple's look for the rest of the
        decade.
        """,
    "apple-iic-plus": """
        The last Apple II: a 4MHz 65C02, a 3.5-inch drive built in, and an internal
        power supply, in the IIc's case. Substantially faster than any other II and
        the only one with the modern drive as standard, which makes it the most
        practical of the line and the scarcest — it was sold quietly for two years
        while Apple's attention was entirely on the Macintosh.
        """,
    "apple-iigs": """
        The Apple II's 16-bit future, and the road Apple did not take. A 65C816 with
        a 4096-colour palette and an Ensoniq synthesiser giving thirty-two voices —
        sound hardware years ahead of the Amiga's — while staying compatible with the
        II software library. Apple deliberately clocked it slowly to protect the
        Macintosh, and the machine never got the support it deserved. The battery on
        the board leaks; check before powering up.
        """,
    "apple-iii": """
        Apple's first failure, and an instructive one. Aimed at business, it was
        designed without a fan on Jobs's insistence, and the heat lifted the chips
        out of their sockets — the official advice really was to drop the machine on
        a desk to reseat them. Recalled, revised, and abandoned. Worth having as the
        object lesson that paid for the Apple II's continued life.
        """,
}
