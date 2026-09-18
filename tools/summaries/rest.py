"""The remainder: the early consoles, VTech, TI, and the last PC clones."""

SUMMARIES = {
    # --- early consoles ---------------------------------------------------
    "channel-f": """
        The first programmable home console, and almost nobody remembers it. Fairchild
        got there in 1976 — a year before the Atari 2600 — with the first microprocessor
        console, interchangeable cartridges, and the first pause button. It also had
        the first joystick with a twist-and-plunge action. Comprehensively out-marketed
        by Atari, and now a significant and uncommon first.
        """,
    "odyssey-2": """
        Magnavox's console, and unusual for having a full membrane keyboard — the idea
        being that it would teach as well as entertain. Its "Master Strategy" series
        combined cartridges with board games, which nothing else attempted. It did well
        in Europe as the Videopac and lost America to Atari.
        """,
    "philips-videopac-g7000": """
        The Odyssey² as Europe knew it, and here it was a real success — the Videopac
        was a genuine rival to the Atari VCS in Britain, France and the Netherlands,
        with a distinct European catalogue of games in numbered boxes. The keyboard and
        the numbered cartridge library are the collectable parts.
        """,
    "philips-videopac-g7400": """
        The Videopac+ added a second graphics processor giving proper backgrounds
        behind the sprites, and could overlay the two — a real technical step, released
        in 1983 just as the console market collapsed. Sold only in Europe and briefly.
        Backwards compatible, scarce, and the enhanced games are worth seeing.
        """,
    "intellivision": """
        Mattel's console, and the first to seriously challenge Atari: better graphics,
        a synthesised voice module, and a disc controller with a numeric keypad and
        overlays that people either loved or loathed. The advertising campaign
        comparing it directly to the 2600 was among the first of its kind. Sold three
        million and defined the first console war.
        """,
    "colecovision": """
        The console that beat everybody on arcade fidelity: Donkey Kong in the box, a
        TMS9918 doing proper sprites, and an adapter that played Atari 2600 cartridges
        — which Atari sued over and lost. It was winning when the 1983 crash killed the
        entire market. The best of the pre-Nintendo consoles.
        """,
    "coleco-adam": """
        The ColecoVision turned into a full computer — and one of the great disasters
        of the era. It shipped late, the power supply lived in the printer so the
        machine would not run without it, and the tape drives could erase their own
        media with their own magnetic field. Coleco left the computer business.
        Fascinating, and complete working examples are uncommon.
        """,
    "bally-astrocade": """
        A pinball company's console, and a genuinely capable one: a Z80 with a decent
        display and a BASIC cartridge that turned it into a programmable computer, with
        a peculiar combined joystick, paddle and trigger controller. Sold through
        Bally's own channels and never widely. A small, devoted following.
        """,
    "arcadia-2001": """
        A cheap console sold under about forty different brand names worldwide, which
        makes identifying and collecting the family a study in itself. Released in 1982
        into the crash, with a small library of games that are mostly close relatives
        of arcade titles. Interesting mainly as a rebadging phenomenon.
        """,
    "vectrex": """
        The only home console with its own vector display — a built-in monochrome CRT
        drawing lines rather than pixels, so the graphics are razor sharp and glow the
        way arcade Asteroids did. Plastic screen overlays supplied the colour. Released
        in 1982 and killed by the crash, and quite unlike anything else ever sold for
        the home.
        """,
    # --- Spectravideo -----------------------------------------------------
    "svi-318": """
        The machine the MSX standard was built from: Spectravideo's design was close
        enough to what Microsoft and ASCII were specifying that the SV-318 is
        effectively the MSX prototype sold as a product. A rubber-keyed home machine
        with a built-in joystick nub. Historically important for what it became.
        """,
    "svi-328": """
        The SV-318's business sibling, with a proper keyboard, 80K and a numeric keypad
        — and the better machine by a wide margin. Sold with CP/M and disc options.
        Together with the 318 it is the direct ancestor of the whole MSX standard,
        which is a considerable thing for a machine so little known.
        """,
    # --- Texas Instruments ------------------------------------------------
    "ti-99-4": """
        The first 16-bit home computer, in 1979, and hobbled by nearly every decision
        around it: a calculator keyboard, a locked-down cartridge system, and a
        16-bit processor talking to memory through an 8-bit path that threw away most
        of its advantage. Sold poorly and was quickly replaced. Rare, and the more
        interesting of the pair for it.
        """,
    "ti-99-4a": """
        The TI-99/4 with a real keyboard, and the machine that fought Commodore in the
        1983 price war — and lost so badly that TI left the home computer business
        after writing off hundreds of millions. Genuinely good sound and speech
        synthesis. Its failure is what let the C64 take the market outright.
        """,
    "ti-cc-40": """
        A handheld BASIC computer aimed at engineers, with a 31-character display and
        battery-backed memory that kept your program for months. Its Hexbus peripheral
        system was meant to connect printers and drives; the drive never shipped, so
        the machine could never save to tape or disc. A capable orphan.
        """,
    # --- VTech ------------------------------------------------------------
    "laser-110": """
        VTech's cheapest home computer: 4K, a monochrome display and a chiclet
        keyboard, sold to undercut the Sinclair machines. VTech went on to make
        children's educational toys for decades, and these early Lasers are where that
        business started.
        """,
    "laser-200": """
        The colour version of VTech's entry machine, sold in Britain and Australia as
        the Laser 200 and in America as the VZ-200 — one machine under a great many
        names, which is the VTech pattern. A small, cheap, unambitious computer with a
        surprisingly durable Australian following.
        """,
    "laser-210": """
        The Laser 200 with more memory, sold across Europe and Australasia under
        several badges. The extra RAM is the whole difference. Common in Australia,
        where the VZ series was genuinely popular, and scarce almost everywhere else.
        """,
    "laser-310": """
        The top of VTech's small Z80 line: more memory again and a better keyboard, sold
        as the VZ-300 in Australia where it had a real user base and a magazine of its
        own. The most usable of the family.
        """,
    "laser-350": """
        VTech moving upmarket: better graphics and a proper keyboard, aimed at the
        Amstrad and Spectrum end of the market rather than the very bottom. Sold in
        small numbers and now the obscure member of an already obscure family.
        """,
    "laser-500": """
        A 64K VTech with high-resolution graphics and a full keyboard in a wedge case,
        sold mainly in Europe. It is a competent machine that arrived with no software
        and no reputation. Uncommon and better than its standing suggests.
        """,
    "laser-700": """
        The top of VTech's own-design line, with 128K and disc options. By this point
        VTech's computer business was being overtaken by the machines it had tried to
        undercut, and the 700 sold very little. The rarest of the Lasers.
        """,
    "laser-3000": """
        VTech's Apple II clone, and a good one: mostly compatible, faster, with better
        graphics modes than the machine it copied and a detachable keyboard. Sold as
        the Laser 3000 and the BASIS-like Apple alternatives were legally contentious
        throughout. An interesting clone rather than a slavish one.
        """,
    "laser-128": """
        The Apple II clone that survived the lawsuits: VTech wrote its own ROM cleanly
        enough that Apple could not stop it, and the Laser 128 was sold in American
        department stores for years — a fully compatible IIc-class machine with an
        expansion slot the real IIc lacked. The most successful Apple clone ever.
        """,
    "creativision": """
        VTech's console, sold in Europe and Australasia under a dozen names, and unusual
        for using a 6502 when almost every console of the period used a Z80 or an 8048.
        A keyboard overlay turned it into a BASIC computer. Uncommon, and the Australian
        Dick Smith Wizzard badge is the one most often seen.
        """,
    # --- Tandon -----------------------------------------------------------
    "tandon-pca": """
        Tandon's AT-class machine, from the drive maker that supplied half the industry
        — including IBM. A 286 sold hard on price into British business through the
        mid-eighties. Well built, since Tandon knew how to make mechanical things, and
        the drives fitted are usually its own.
        """,
    "tandon-pca-12": """
        The PCA at 12MHz, which by 1988 was what a business buyer expected of a 286.
        Tandon's British operation sold a great many of these before the company left
        the computer trade to concentrate on storage. Solid and unglamorous.
        """,
    "tandon-pac-386sx": """
        Tandon's 386SX, and the interesting one: the PAC line used removable hard disc
        cartridges — a Tandon speciality — so the whole drive could be locked in a
        drawer at night. That security idea was ahead of its time and is what makes the
        machine worth having.
        """,
    # --- Opus -------------------------------------------------------------
    "opus-pc-ii": """
        Opus Supplies had made disc drives and expansions for the BBC Micro before
        moving into PC clones as the British education market shifted. The PC II is an
        XT-class machine sold on price through the computer press. Almost none were
        kept, which is precisely what makes a survivor interesting.
        """,
    "opus-pc-iii-turbo": """
        A 10MHz XT-class machine — "turbo" meaning faster than IBM's 4.77MHz, which was
        the whole selling point of the clone trade in 1988. Opus assembled these from
        bought-in boards for the British market. A representative machine from the
        anonymous middle of the industry.
        """,
    "opus-pc-iv-turbo": """
        Opus's 286 at 12MHz, sold into British small business and education at the end
        of the eighties. The interest is documentary rather than technical: this is what
        most of Britain's first PCs actually were, and hardly any of them were kept.
        """,
    # --- DZT --------------------------------------------------------------
    "book-8088": """
        A new machine, not an old one: a 2023 handheld built around a genuine Intel
        8088 with CGA and an XT-compatible architecture, in a small clamshell. It
        exists because people wanted to run 1981 software on 1981 silicon in something
        pocketable, and it answers a question the period never got round to asking.
        """,
    "hand-386": """
        A 2023 handheld built on the ALi M6117 — a 386SX core still made for embedded
        controllers — with a small screen and a thumb keyboard. It runs DOS games on
        real hardware in the palm of your hand, and belongs in a collection as the
        modern end of a story that starts with the 5150.
        """,
    # --- Exelvision -------------------------------------------------------
    "exl-100": """
        A French machine built by ex-Texas Instruments engineers around TI's own
        TMS7020, with wireless infrared keyboard and joysticks in 1984 — years before
        that was ordinary — and a speech synthesiser as standard. Technically
        adventurous, commercially unsuccessful, and unlike anything else of its
        generation.
        """,
}
