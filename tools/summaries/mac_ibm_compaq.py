"""The Macintosh line, IBM's own machines, and Compaq."""

SUMMARIES = {
    # --- Apple Macintosh --------------------------------------------------
    "apple-lisa": """
        The first commercial computer with a graphical interface, a mouse and
        protected memory, and a spectacular failure at ten thousand dollars. Almost
        all unsold stock was buried in a Utah landfill, which is why survivors are
        among the most valuable machines in computing. Its Twiggy drives were replaced
        by Sony 3.5-inch units on the Lisa 2, and its ideas went straight into the
        Macintosh that killed it.
        """,
    "mac-128k": """
        The original Macintosh: a 9-inch screen, a mouse, 128K and no expansion of any
        kind, sold on the promise that a computer could be used without a manual. The
        memory is too small for the software that followed within months, so most were
        upgraded — an untouched 128K with the original board and the signatures moulded
        inside the case is the collector's machine.
        """,
    "mac-512k": """
        The Macintosh with enough memory to be useful. Nicknamed the Fat Mac, it is
        what made MacPaint and MacWrite practical and what the early Mac software
        library actually assumes. Same sealed case and same lack of slots, so the
        machine still has to be opened with a long screwdriver — which Apple intended.
        """,
    "mac-plus": """
        The compact Mac finished: a megabyte of socketed, expandable RAM and a SCSI
        port, which finally let a hard disc be attached without a third-party
        contraption. It stayed on sale for four years, longer than any Mac before it,
        and it is the compact to have — capable enough to be useful, plentiful enough
        to be affordable.
        """,
    "mac-se": """
        The Plus with an internal drive bay and a single expansion slot, and the first
        compact Mac with a fan — which is why more of them survive in working order.
        The slot took accelerators and Ethernet cards, so an SE is often found
        upgraded. The keyboard and mouse moved to ADB here, which is the connector to
        check you have.
        """,
    "mac-se-30": """
        The best compact Macintosh, and by common consent one of the best Macs ever
        made: an SE case with the Mac IIx's 68030 and FPU, 32-bit colour capability on
        an external monitor, and 128MB of addressable memory. Fast, expandable and
        beautifully compact. Prices reflect all of that, and the analogue board
        capacitors are the standard restoration job.
        """,
    "mac-classic": """
        Apple's answer to the clone makers at the bottom of the market: a Plus-class
        machine in the compact case at under a thousand dollars, with a ROM disc that
        would boot System 6 with no drive attached at all. Cheap, slow, and made in
        very large numbers, which makes it the easiest compact Mac to find and the
        least interesting to own.
        """,
    "mac-classic-ii": """
        A Classic case with an LC's 68030 board, which makes it markedly faster than
        the Classic but crippled by a 16-bit memory bus. The last of the black-and-
        white compacts — the end of the shape Apple had sold since 1984. The battery
        leaks and the capacitors go; both are routine now.
        """,
    "mac-color-classic": """
        The compact Mac with a colour Trinitron screen, and the one people are
        sentimental about: the same footprint Apple had used for nine years, in
        colour, with a slide-out logic board. Underpowered as sold and famously easy
        to improve, so most surviving examples have been "Mystic" upgraded with an LC
        575 board. Sought after and expensive.
        """,
    "mac-ii": """
        The Macintosh opened up: a 68020, six NuBus slots, colour, and a separate
        monitor — everything the original Mac deliberately refused. It is the machine
        that got the Mac into desktop publishing and onto engineers' desks. Large,
        heavy and endlessly expandable, and the first Mac that could be treated as a
        workstation.
        """,
    "mac-iix": """
        The Mac II with a 68030 and an FDHD floppy drive that could read PC discs, which
        mattered in mixed offices. Otherwise the same six-slot chassis. The
        interesting one only if you want an 030 in the big case; otherwise the IIci
        beside it is the better machine.
        """,
    "mac-iici": """
        The most highly regarded of the classic Macs: a 68030 at 25MHz with video
        built in, three NuBus slots, and a cache slot that lifts it further. It became
        the standard professional Mac of the turn of the nineties and stayed in use
        for years. If you want one desktop 68k Mac, this is the usual recommendation.
        """,
    "mac-iifx": """
        Apple's speed machine: a 68030 at 40MHz with two dedicated I/O processors and
        its own peculiar 64-pin SIMMs, sold at a price that earned it the nickname
        "wicked fast" and a great deal of eye-rolling. The odd memory is the practical
        problem — it fits nothing else, and finding it is the reason many sit unused.
        """,
    "mac-iisi": """
        The cheap colour Mac II: an 030 at 20MHz with video on board and one slot
        reachable only through an adapter, sold as the affordable way into colour
        Macintosh. Compromised by design and common as a result, which makes it a
        sensible first 68030 Mac. The capacitors and the battery both need attention.
        """,
    "mac-lc": """
        The pizza-box Mac that put colour into schools: a low, wide case, a 68020, and
        a Processor Direct Slot that took the Apple IIe card — so a classroom could run
        its existing Apple II software on the new machine. That card is the historically
        interesting part. Hobbled by a 16-bit bus and a 10MB memory ceiling.
        """,
    "mac-lc-ii": """
        The LC with a 68030, in the same pizza-box case and with the same 16-bit bus
        holding it back. Sold in enormous numbers into education, so it is the easiest
        colour 68k Mac to find. Takes the same IIe card as the LC. Unexciting, cheap,
        and a perfectly good way to run System 7.
        """,
    "mac-lc-iii": """
        The LC done properly: a 68030 at 25MHz on a full 32-bit bus, which makes it
        roughly twice the machine the LC II was. It is the best of the pizza-box LCs
        and the board people put into Color Classics. Common, capable, and the sensible
        choice of the three.
        """,
    "mac-quadra-700": """
        The first of the Quadras: a 68040 at 25MHz in an upright case, with built-in
        Ethernet and video, aimed at the professional market in 1991. Fast enough to
        do serious Photoshop work at the time, and the machine that established the
        Quadra name. Handsome, and the 040 heatsink is the giveaway.
        """,
    "mac-quadra-605": """
        A 68040 in the smallest case Apple made — a low, flat box barely bigger than
        the drive inside it. Cheap, quick for a 68k Mac, and the last hurrah of the
        line before PowerPC. Popular with people who want a fast 040 that fits on a
        shelf, and the case is fragile.
        """,
    "mac-quadra-840av": """
        The fastest 68k Macintosh Apple ever shipped: a 68040 at 40MHz with an AT&T
        DSP handling sound, telephony and video capture. The AV features were ahead of
        their time and barely supported. It is the end of the 68000 line and the
        machine to have if you want the top of it.
        """,
    "mac-portable": """
        Apple's first battery machine, and a lesson in priorities: a superb active-
        matrix screen and a lead-acid battery in a sixteen-pound case that cost as
        much as a car deposit. It is not a laptop in any useful sense. The batteries
        are long dead and the machines will not run without one unless modified, which
        is the first thing to establish.
        """,
    "powerbook-100": """
        The PowerBook that set the shape of the laptop: Sony built it to Apple's
        design with the palm rest and the centred trackball that every laptop copied.
        The cheapest of the launch three and the slowest, with no internal floppy. The
        historically important one, and the PRAM battery leaks and destroys boards.
        """,
    "powerbook-170": """
        The top of the 1991 PowerBook launch: a 68030 with an FPU and an active-matrix
        screen, which is the difference that matters — the passive screens of its
        siblings smear, and this one does not. The best of the first generation and the
        one worth finding with a good display.
        """,
    "powerbook-180": """
        The best of the classic PowerBooks: a 33MHz 68030, an FPU, and a superb 4-bit
        greyscale active-matrix screen. Fast, well built and pleasant to use, and the
        machine most people mean when they say the early PowerBooks were good. Screen
        and battery condition decide the price.
        """,
    "powerbook-duo-230": """
        Apple's subnotebook: four pounds, no floppy, no ports to speak of, and a
        docking station that swallowed the whole machine and turned it into a desktop.
        The Duo Dock is the interesting half of the idea and the harder half to find.
        Ahead of its time, and awkward without its accessories.
        """,
    "power-macintosh-6100": """
        The first PowerPC Macintosh, and the transition made visible: a 601 in a
        cheap pizza-box case running most 68k software through emulation, sometimes
        slower than the machines it replaced. Historically important as the start of
        the PowerPC era, and the DOS-compatible version with a 486 card on a riser is
        the collectable variant.
        """,
    "power-macintosh-7100": """
        The middle of the 1994 PowerPC launch, and the machine at the centre of a
        famous story: its internal codename was "Carl Sagan", who objected, so Apple
        renamed it "BHA" — for "butt-head astronomer" — and got sued again. A
        competent three-slot desktop, and the anecdote is most of the appeal.
        """,
    "power-macintosh-8100": """
        The top of the first PowerPC range: a 601 at 80MHz in the Quadra 800's tower
        with three NuBus slots and fast SCSI, sold to publishing and rendering users
        who needed the speed immediately. The most capable of the launch three and the
        one that actually justified the transition.
        """,
    # --- IBM PC -----------------------------------------------------------
    "ibm-5150": """
        The original IBM PC, and the machine whose architecture the industry still
        runs on. IBM built it in a year from bought-in parts and published the
        technical reference, including the BIOS listing — which let Compaq and
        everyone after it build compatibles and took the standard out of IBM's hands.
        Cassette port, five slots, and a keyboard that outlasts everything. The
        foundation of the whole platform.
        """,
    "ibm-5160": """
        The XT: a hard disc as standard, eight slots and 640K addressable, which is
        the configuration DOS software assumed for the rest of the decade. It is the
        practical original PC — the 5150 is more historic, the XT is more usable — and
        the machine most period expansion cards were designed around. Full-height
        drives and a power supply that will run forever.
        """,
    "ibm-5155": """
        IBM's answer to the Compaq Portable, two years late: XT internals in a
        luggable case with a nine-inch amber screen and a fold-up keyboard. Thirty
        pounds of it. It sold poorly against Compaq's own machine, which makes it
        markedly less common than the desktop XT, and it is a striking object.
        """,
    "ibm-5162": """
        The XT/286: an AT-class 286 board in an XT case, and — because it runs zero
        wait state memory — genuinely faster than the 6MHz PC/AT it sat below in the
        price list. IBM quietly withdrew it. That accidental superiority is the whole
        story, and it makes the 5162 an interesting oddity rather than just another
        286.
        """,
    "ibm-4860": """
        IBM's home computer, and one of its famous failures: cartridge slots, an
        infrared "Chiclet" keyboard nobody could type on, and a price that made no
        sense beside a Commodore 64. IBM replaced the keyboard and cut the price, then
        killed it after a year. Worth having as the moment IBM discovered it did not
        understand the home market.
        """,
    "ibm-5140": """
        The PC Convertible: IBM's first laptop, a clamshell with two 3.5-inch drives
        and an LCD that hinged back, in 1986. Slow, expensive, and it lost to Toshiba
        and Compaq almost immediately. Its real legacy is the 3.5-inch drive, which
        IBM's adoption made the standard. Uncommon, and the snap-on modules are the
        parts that go missing.
        """,
    # --- IBM PS/1 and PS/2 ------------------------------------------------
    "ps1-2011": """
        The first PS/1: an all-in-one 286 with the power supply in the monitor, sold
        in high-street shops with software in ROM and a modem fitted, aimed at the
        home buyer IBM had failed to reach with the PCjr. Simple, sealed, and
        unexpandable by design. The monitor is part of the machine, so a complete one
        matters.
        """,
    "ps2-8525": """
        The bottom of the PS/2 range: an 8086 in a one-piece case with the monitor
        built in, sold overwhelmingly into schools. The Model 25 is where a great many
        people first met the PS/2 keyboard and mouse ports, and its MCGA video is a
        peculiarity — 256 colours at 320×200 but no proper text modes beyond CGA's.
        Heavy, tough, and common.
        """,
    "ps2-8530-286": """
        The Model 30 given a 286, keeping the ISA slots that the expensive PS/2s did
        not have. That combination — an AT-class processor with ordinary slots in the
        PS/2 case — makes it arguably the most practical machine in the whole range,
        and it sold accordingly into small business.
        """,
    "ps2-8535": """
        A 386SX desktop from IBM's cost-reduced second wave, with ISA slots rather
        than Micro Channel — by 1991 IBM had conceded the argument. Unremarkable
        hardware in the PS/2's excellent case, and easy to keep running precisely
        because it takes ordinary cards.
        """,
    "ps2-8550": """
        The desktop Micro Channel machine from the 1987 launch, and the one that made
        IBM's case for the new bus: a 286 at 10MHz with everything integrated and
        tool-free access inside — the PS/2 chassis design is genuinely excellent and
        opens without a screwdriver. Needs its reference diskette to configure, which
        is the standard MCA obstacle.
        """,
    "ps2-8560": """
        The floor-standing 286 of the launch range: Micro Channel, room for full-length
        cards and a pair of drives, sold as a departmental server or a heavy
        workstation. Enormously well built and enormously heavy. Less common than the
        desktops simply because fewer people needed a tower.
        """,
    "ps2-8570": """
        The desktop 386DX PS/2, and the machine IBM sold as the serious Micro Channel
        workstation — an 80 in a box that fits on a desk. Cache options and processor
        complex cards make it more upgradeable than most of the range. A good one is
        the best-balanced MCA machine to own.
        """,
    # --- Compaq -----------------------------------------------------------
    "compaq-portable": """
        The machine that created the clone industry. Compaq reverse-engineered IBM's
        BIOS cleanly, put the result in a sewing-machine-sized case with a handle, and
        sold $111 million of them in the first year — the fastest start in American
        business history at the time. Everything that followed in the PC market
        follows from this. Heavy, superbly made, and historically about as important
        as a PC gets.
        """,
    "compaq-portable-plus": """
        The Portable with an internal hard disc, which in 1983 meant a 10MB drive
        shock-mounted in a machine designed to be carried — not an obvious combination.
        It made the luggable a genuine desktop replacement. Same excellent build as
        the Portable, and the drive is usually what has failed.
        """,
    "compaq-portable-ii": """
        Lighter, smaller and 286-powered: Compaq's second-generation luggable, and much
        the most pleasant of the family to actually handle. It arrived before IBM had a
        credible portable of its own and sold well into business. A good example is a
        genuinely usable AT-class machine.
        """,
    "compaq-portable-iii": """
        The luggable reinvented: a slim case with a gas-plasma screen that folds down
        over the keyboard, and an expansion box on the back for ISA cards. The orange
        plasma display is the reason people want one — it is beautiful and nothing else
        looks like it. It also runs extremely hot.
        """,
    "compaq-portable-386": """
        The Portable III chassis with a 386DX, which in 1988 made it one of the fastest
        computers you could buy at any size, let alone one with a handle. The plasma
        screen again, and the same heat. Expensive when new and consequently uncommon
        now.
        """,
    "compaq-deskpro": """
        Compaq's first desktop, and the machine that established the pattern for the
        next decade: take IBM's architecture and make it faster. An 8086 at 8MHz when
        IBM was selling a 4.77MHz 8088, with a proper set of slots. It is where the
        clone makers stopped following and started leading.
        """,
    "compaq-deskpro-286": """
        Compaq's AT-class desktop, quicker than IBM's own 5170 and available sooner in
        the configurations businesses wanted. Nothing surprising in it — that was the
        point. Solidly built, common enough to find, and a good example of the clone
        market having simply overtaken the originator on execution.
        """,
    "compaq-deskpro-386": """
        The machine that broke IBM's grip. Compaq shipped a 386 in 1986, a full year
        before IBM, and the industry realised the standard no longer belonged to IBM
        at all — from here on it belonged to Intel and Microsoft. Arguably the single
        most consequential PC clone ever made.
        """,
    "compaq-deskpro-386s": """
        The 386SX version, bringing 386 instructions to a mid-range price on a 16-bit
        bus. Compaq's build quality applied to a mass-market part, which makes it a
        pleasant, unexciting machine and a common one. A good period DOS box.
        """,
    "compaq-deskpro-486": """
        Compaq at the top of the market again: a 486DX at 25MHz in 1989, aimed at
        workstation buyers and priced accordingly. Well made, heavy, and quick enough
        to be worth running. EISA options on some configurations are the detail to
        look for.
        """,
    "compaq-deskpro-en": """
        A Pentium II business desktop from the end of the story: Compaq by 1998 was
        the largest PC maker in the world and shipping machines like this by the
        million into corporate estates. Interesting less as hardware than as the
        endpoint — the year before the Digital acquisition and the merger with HP that
        ended the name.
        """,
    "compaq-slt-286": """
        Compaq's first real laptop: a 286 with a removable battery and a detachable
        keyboard, and among the first portables with a VGA-capable display. It weighs
        fourteen pounds, which was light for 1988. The battery and the screen are the
        two things that decide whether one is worth having.
        """,
    "compaq-lte": """
        The machine that made "notebook" a category: Compaq put a full PC with a hard
        disc into something the size of a hardback in 1989, and the industry followed
        within a year. Small, well made and genuinely portable in a way nothing before
        it was. An important laptop and an uncommon one.
        """,
    "compaq-lte-lite": """
        The LTE developed properly: a 386SL designed for battery use, a decent screen
        and a case that still looks modern. These sold heavily to business travellers
        and are the notebook most people picture when they think of the early
        nineties. Batteries are dead; everything else usually works.
        """,
    "compaq-contura": """
        A budget 486 notebook from 1992, sold in volume when the laptop stopped being
        exotic. Unremarkable by design, which is its interest: it marks the point at
        which portable computing became an ordinary purchase rather than a statement.
        Plentiful and cheap.
        """,
    "compaq-prolinea": """
        Compaq's price-war machine. Faced with mail-order clones undercutting it in
        1992, Compaq built a deliberately cheap line and won the fight — this is the
        machine that took the company to number one and squeezed the smaller builders
        out. Ordinary hardware with a significant commercial story behind it.
        """,
    "compaq-presario": """
        Compaq's move into the home: a consumer brand with sound, a modem and software
        preloaded, sold through high-street retail rather than dealers. It worked, and
        Presario became one of the biggest-selling PC names of the nineties. The start
        of the era when a PC was bought in a shop like a television.
        """,
}
