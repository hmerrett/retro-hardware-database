# What the software does

Every heading below is a test file; every line under it is a test the suite runs.
This document is **generated** from `api/tests/` -- it is not written by hand and
must not be edited. A test named for the behaviour it describes becomes a
readable line here, which is the practical reason the naming rule exists.

It describes the software as its tests hold it. It is therefore honest about what
is checked and silent about what is not: a behaviour no test covers does not
appear, however important it is. For the shape of the system rather than its
behaviours, see `architecture.md`.

Regenerate with:

    RHDB_UPDATE_BEHAVIOUR=1 pytest api/tests/test_architecture.py



*1393 behaviours, from 30 files.*


## Api

*test_api.py — 551 behaviours*


**Typed columns**

- year and date come back typed
- a year that is not a number is refused
- a date that is not a date is refused
- not recorded is null not zero
- creating from the form with both blank  
  These were String columns; when they became SMALLINT and DATE the create path still passed "" straight through, and the form 500'd.
- the form accepts a day first date
- clearing a typed field from the form

**Condition**

- a value outside the vocabulary survives an edit  
  The select had no option for such a value, so saving the form posted an empty string and the value was lost without a word.
- the current value is offered once
- a new thing claims nothing about its condition  
  It used to open on "Working", so anything added and not thought about was recorded as working when nobody had checked.
- a condition can be taken back off

**Disposal**

- disposing records a flag a date and a note
- disposing with nothing typed still records the day
- restoring clears all three
- a disposal without a date still reads as disposed  
  Every disposal in the collection predates the date field, which is why the flag is its own column rather than being inferred from the date.

**Disposing A machine takes its parts with it**

- the parts installed in it are disposed too
- a part mounted on a card in it goes too  
  A disk on a controller carries the controller's id, not the machine's, so the walk has to follow the whole tree rather than one column.
- a part outside the machine is left alone
- a part already disposed keeps its own record
- restoring the machine brings those parts back
- restoring leaves a part that went separately  
  Only what went out with the machine comes back with it.
- the json api cascades the same way  
  The rule belongs to the data, not to the GUI: the MCP server and the command-line tools go through PATCH and must not leave a machine disposed with its parts still reading as held.
- editing a disposed machine does not re dispose  
  The cascade fires on the change, not on the state, so a later edit cannot overwrite a part that was restored on its own.

**Deleting is only for what is already disposed**

- the item page offers it once disposed
- the confirmation refuses an item still held
- and so does the delete itself  
  Not only the page that leads to it: a form posted at a restored item must not go through on the strength of having once been offered.

**The delete confirmation**

- the right url deletes it
- anything else deletes nothing
- the bare path is enough  
  Pasting from the address bar is the expected act, but the host is not the part that identifies anything -- the asset id is.
- and so is a paste that travelled  
  Another host, a trailing slash, a query the gallery added, whitespace a copy picked up: all the same act of fetching the thing's identity.
- the page shows the url to paste

**A delete takes everything with it**

- the rows filed under it go
- the photos go from disk
- a machines drive and memory rows go
- the json api cleans up the same way  
  The MCP server and the command-line tools delete through here, and used to leave the photos behind on disk.

**What A linked item is told when its host goes**

- a part in a deleted machine is kept and unlinked
- a part mounted on a deleted part is kept and unlinked
- the tick deletes the parts that went with it
- without the tick they stay
- the tick follows the whole tree  
  A disk on a controller carries the card's id, not the machine's.
- a held part deep in the tree is unlinked not deleted  
  The disk was restored on its own, so it stays -- and must not be left pointing at the controller card that went.
- a part still held survives the tick  
  A part restored on its own, or fitted after the machine went, is still in the collection.
- a deleted part leaves no history behind it  
  The parts deleted alongside the machine take their own history with them, and are not told they came out of something on the way out.

**The confirmation page says what will go**

- it counts the photos and the history
- it counts one of a thing without the s
- it leaves out a line it has no number for  
  A part with no photograph does not get told that no photographs will be deleted; the list is what is going, not a form with blanks.
- it offers the tick only when there is something to tick
- it says which parts it will not touch
- a failed confirmation keeps the tick

**The delete confirmation is not public**

- a visitor is sent to the login
- the item page it hangs off is still public  
  Only the confirmation moved behind the login, not the item itself.
- both histories say what happened

**Links**

- a new part stands alone
- blank means standalone on the wire
- the standalone filter finds unlinked parts
- a link to something that does not exist is refused
- deleting a computer unlinks its parts
- deleting a host part unlinks what was mounted on it
- deleting a computer does not delete its parts

**Installed ram**

- the module grid becomes a total and a string
- a plain amount over the wire becomes a number
- setting a total does not wipe a breakdown
- replacing a total with a note does not leave the old figure  
  Passing None once meant "leave the total alone", so the stale number stayed and the string read '16 MiB; 16MB (2 banks)'.
- clearing the grid clears the memory
- parity reaches the stored total

**Drives**

- a typed field becomes rows and renders back
- the row editor replaces the drives
- an emptied row removes that drive
- routing a floppy to a machine survives the next save  
  The routing path used to append text to the rendered string, which the next save re-rendered away.
- the form records both halves of a bezel
- a shade with no yellowing is a clean drive
- both come back into the form  
  Each menu has to hold what was saved, or the next save would quietly drop it -- the same trap a select with no option for its value always is.
- a row with only a bezel is still a drive  
  Nothing else known about it yet, but the bezel was looked at.
- the edit form carries the chart  
  The chart is next to the menus because that is where the choice is made: a bezel is held up to the screen and the nearest one taken.
- a bezel is searchable  
  It rides on the drives string, which the search index reads, so "which machines have a yellowed floppy" is a question the box can answer.
- routing a drive reads its bezel
- routing a drive takes the bezel from its menus  
  Adding a drive from the part form is where most of them get added, so the menus are there too rather than only in the machine's own form.
- the menu wins over the same thing typed
- a blank menu leaves what was typed
- the history names the bezel that was picked
- the routed form offers the menus and the chart
- a routed drive with no machine keeps its bezel  
  No machine to route to, so it becomes a storage part after all -- and the bezel picked on the way in comes with it.
- routing a floppy creates no part

**A drive kept as A part**

- the description is kept
- the form opens on it again
- a no op save does not drop it
- editing it is not ignored
- duplicating carries it across
- a second one started from it opens on it  
  The duplicate-then-edit route: /parts/new?from= fills the form in from an existing part, and the description is part of what it describes.
- a machine to route to still wins

**Picking A floppy S capacity**

- the pick lands on the machines drive row
- the picker wins over the description  
  The same rule the bezel menus follow: a pick is a deliberate answer, so it beats the same thing said in passing in the prose.
- picking nothing leaves what the description said
- a drive kept as a part records it too
- a designation is not turned into a byte count  
  1.44MB is 1475 KiB only by convention.
- a ram size still normalises  
  The other half of that guard: only storage is exempt, and a memory amount still lands in the KiB column that makes it sort and compare.
- a floppys size is no column at all  
  It is not a quantity, so it is not one of storage_spec's typed columns: it rides as a plain attribute, the way an unmanaged key does.
- custom records what was typed
- custom with nothing typed records nothing
- a kind that takes no such disk ignores a stale pick  
  Choosing 1.44MB and then changing the kind leaves the radio checked and off-screen.
- a hard disk ignores it as well
- the form opens on the pick again
- a custom one opens on the box
- a capacity alone still describes a floppy  
  Picking a capacity and typing no description is an ordinary gesture now the picker exists; the kind's menu label must not land in the model.
- editing a kept drive changes it

**Picking the bay A drive fits**

- the pick lands on the machines drive row
- the picker wins over the description
- picking nothing leaves what the description said
- an optical drive gets one too  
  The capacity picker is a floppy's alone; this one is not.
- a hard disk is asked its bay as well  
  It used to be a routed drive's question alone.
- custom records a bay the list does not name  
  An Amstrad CF-2 is a 3" disk, and drivedb's parser reads a typed 3" as 3.5" -- the shorthand it has always meant.
- a description that names no kind gets one from the menu  
  drivedb infers "floppy" from a size only a floppy has -- but it infers while reading the text, and "Sony MPF920" names neither a kind nor a size.
- an optical drive is not called a floppy  
  Which is why the menu answers rather than the 5.25" being taken as proof: early CD-ROM drives are 5.25" too.
- a kind the description does name is left alone
- a routed drive takes its make and model from identity  
  A routed drive never becomes a Part, so what was typed under Identity used to be dropped on the floor -- survivable while the description was always on screen and could carry the name, not now that it is not.
- what the description still says is not written over  
  What is left of a description once the pickers have taken their share is the words they could not say.
- the form reopens on the pick
- the typed box cannot outgrow the column it lands in  
  The drive row's form_factor is a String(16); a picker that let you type more than that would fail on save rather than on the form.

**Picking what an optical drive takes**

- both picks land on the machines drive row
- a drive kept as a part records them
- the rating is stored as a number of its own  
  Not in the rpm column: 48× and 5400 rpm are different quantities, and one column could not sort or compare both.
- a hard disks speed is still its spindles  
  The same key, from a group of its own: a disk is asked its rpm and a reader its × rating, and one list must never offer both.
- a kind that takes no disc ignores a stale pick  
  Choosing CD-RW and then changing the kind leaves the radio checked and off-screen.
- the picker wins over the description
- picking nothing leaves what the description said
- custom records what was typed
- a rating the list does not name is kept as it was typed  
  It is no kind of number, so it lands where every unparseable quantity does -- kept verbatim rather than dropped on the floor.
- the form opens on the picks again
- a pick can be taken back off  
  Choosing "not recorded" has to clear it, rather than the hidden text box below quietly putting it back.
- a medium alone still describes the drive  
  Picking a medium and typing no description is an ordinary gesture now the picker exists; the kind's menu label must not land in the model.
- the typed boxes cannot outgrow the columns they land in
- an optical drive says what it takes on its label

**A storage part S interface**

- it is recorded
- a part with none is refused
- an edit that drops it is refused too
- another type is not asked  
  Only storage attaches by a bus worth naming this way; a sound card's interface is its own free-text field and must not start being required.
- a drive routed to a machine is not asked  
  It becomes a row on that machine rather than a part, and has no interface column of its own to fill.
- custom records a bus the list does not name
- custom with nothing typed is refused
- the form opens on the pick again
- a bus outside the list opens on the box  
  The one disk on file recorded as 'ATA' has to survive being edited: a radio group with no room for it would retag it as whatever was ticked.
- a spare of a routed kind is asked on screen  
  The bug: no machine to route to, so it becomes a part -- and the field it has to fill was hidden by the kind alone.
- editing a routed kind is asked on screen too
- building a drive into a machine still routes
- a spare optical drive records its discs and its bus together  
  The two questions are independent: what the drive is, from the pickers the kind brings, and how it attaches, from the part's own field.
- the blocks the script toggles are all still there  
  Which of these is on screen is decided in the script, so it is not something this suite can see.
- a slimline drive and a sound card bus are on offer  
  A 26-pin flex cable is not the 34-pin header of a desktop drive, and the early CD-ROMs hung off a sound card rather than a disk controller.

**Reopening A drive on what it saved**

- one answer is checked per group
- saving it untouched changes nothing
- a group for another kind is sitting on nothing  
  Not even on "not recorded", which is an answer too and would post a blank over the real one for exactly the same reason.

**The maker league table**

- best record first worst last
- a maker with too few parts does not qualify  
  One working card is not a record, and on a sample of one it would top the table.
- a tie goes to the bigger sample  
  Equal records; the one who earned it over more parts has the better case for it.
- unknown is not a maker  
  "Unknown" and "Generic" stand for "we do not know" and "nobody in particular"; neither belongs in a league table of manufacturers.
- restored does not count as working  
  A part that had to be restored is evidence of the opposite.
- a part no longer here is not counted  
  It may have been sold in perfect order; the register is what is here.
- the bars are drawn against a hundred  
  A percentage scaled to its own best row would draw 92% as a full bar and read as "all of them".

**A picker opens on nothing**

- the install menu opens on nothing
- it says nothing about where the part is  
  The machine's name must not be the chosen option -- that is the misreading.
- choosing one still installs it
- posting a blank does nothing rather than 404  
  The menus will not submit empty, so this only arrives from something posting straight at the endpoint -- where the empty string used to be looked up as an asset id.
- the board menu on a machine opens on nothing too

**Remembering how you left it**

- the cookie the page writes is the one the server names  
  The name is a template global rather than a string in two places, because a cookie written under one name and read under another is not remembered.
- a sort that no longer exists is not trusted  
  A stale or hand-edited cookie naming a sort the page dropped would otherwise leave the grid sorted by nothing.
- it is written on the sorts own change and not on every keystroke
- the helpers are defined before the page uses them  
  The gallery's script lives in the content block, so anything it calls has to be defined above it in the document.

**The cookie notice**

- it is offered on a first visit
- dismissing it takes it out of the markup  
  Not hidden by a script on every page thereafter -- the server knows from the cookie and leaves it out.
- it is on every page not just the gallery
- it does not block the page  
  A notice, not a gate: no overlay, and the cards are reachable behind it.

**The gallery opens shuffled**

- random is the first option and so the default
- the shuffle is dealt once and held  
  Filtering and searching re-sort on every keystroke, so a shuffle that re-dealt each time would throw the cards up in the air while you typed.
- a photoless item still sorts last  
  The same rule the recency sorts follow: a shuffle that opens on a screenful of unphotographed things looks like a broken page, not a random one.

**What is gone is not counted**

- a binned part leaves the totals
- the count of disposals does count them
- a disposed year does not stretch the range
- a disposed machine is not the best equipped

**The shuffled figures**

- every figure in the pool leads somewhere real  
  The page's own sweep only sees the handful it drew, and some of these lead to an item page rather than to /browse, so neither is covered there.
- the fixture reaches every group of figures  
  The sweep above proves the links work; this proves the sweep saw them.
- a figure about the register itself need not link  
  Most tiles are links; the ones counting history entries are not, because an entry in a history is not an item the gallery can show.
- a binned board is not a board the collection has  
  The themed groups read the spec tables, and a spec row has no disposed flag of its own -- so each of them joins back to the part that owns it.
- a tile with no link still renders as a tile  
  The figures about the register carry no href, which is a shape the tile markup has to answer for: not a link with an empty destination, but a plain tile.
- every condition beyond the two above gets a figure  
  Four of the six values in entry.CONDITIONS have a figure naming them, and they name it as a string.
- no figure is offered with nothing to say  
  An empty register answers none of them rather than answering them blank.
- only a handful is shown
- no two tiles show the same number  
  The storage total and the hard disks that are nearly all of it both read the same figure on the real register.
- a different draw each time  
  Seeded rather than looked at twice and hoped over: two draws from the same pool can legitimately coincide, and a test that fails once a fortnight is worse than no test.
- the share link says the collection not the draw  
  Whichever eight came up is not what a crawler or a chat window should quote back.

**Reading the inch mark as typed**

- every inch mark reads the same
- the number no longer lands in the model
- a quote that is not an inch mark is left alone  
  Only a number in front of it makes it a measurement.

**A floppy S small label**

- the bay and the disk share one line  
  They are read as one thing -- "a 3.5-inch 1.44MB" -- and joined they cannot be split by the squeeze that drops the last line, which would otherwise leave the less useful half behind.
- either alone still says what it knows
- a drive with neither holds no line open
- a hard disk reads as it always did  
  One table serves both because the keys do not overlap.
- it reaches the printed label

**Specs**

- writing specs canonicalises the string
- a spec the columns cannot hold is still shown
- the typed rows are the read path for the page
- saving a part keeps a spec the form does not manage  
  The form has no field for an unrecognised key, so it is read back from part_attribute and re-appended rather than being dropped on save.

**A storage parts bezel**

- the form records both
- they come back into the form
- editing keeps them
- the part page shows the swatch for the pair  
  One piece of plastic, so both rows carry the swatch of the two together rather than a shade beside a separate stage.
- a drive with no bezel recorded shows no swatch

**The build walk**

- a pc is walked through building it out
- a catalogue machine is not  
  A Spectrum is a sealed thing described by what it was built as.
- the banner is only for whoever is signed in  
  It is an instruction to do the next thing, and a reader has nothing to do.

**A serial number**

- a machine records and shows one
- a part does too
- both forms ask for one
- the form can take a serial back off
- a duplicate does not carry the serial across  
  The whole point of the field: no two objects ever wore the same number, so a copy that inherited one would be asserting something false about the second thing -- and the copy is made to be filled in, not to be believed.
- an item is found by its serial  
  A machine can be looked up by the number on its own back, which is the question a serial is written down to answer.

**Notes keep their lines**

- a parts notes are shown in the lines they were typed in
- a machines notes are too

**A link in what was typed is A link**

- a url in a parts notes
- a url in a machines summary
- a url in the source it came from
- a url in a history note
- a part number is not a hostname
- the note around the link is still text

**A display part**

- the form records what a screen is  
  Every answer picked from the group it is offered in, and the sockets ticked rather than chosen between.
- an answer that is not offered is typed beside custom
- a socket the list does not name joins the ticked ones
- an answer never offered is refused rather than kept  
  A group's answer is checked against the list it was offered from, the same way a drive's is: something posted straight at the endpoint that was never on the form is not an answer to the question that was asked.
- the groups are built from the one table  
  The form and the server read the same list, so a question cannot appear on screen that the server passes over.
- a screen records every refresh rate it does  
  The 50 Hz is the point: a tube that meets a television-rate mode and also does 85 Hz at its best VGA one is two useful screens, and recording only the higher figure would answer the question nobody driving an Archimedes asks.
- a screen with two rates records both  
  The reason the rates are ticked rather than chosen between: a tube that locks to 15 kHz and to 31 kHz does both, and made to choose, its record would have to leave out the half that makes it worth owning.
- a multiscan records the range it claims  
  An Acorn AKF18 is 15-38 kHz by its user guide -- a range, not a set -- and ticking every figure inside it would be recording rates nobody stated.
- the numbers land in typed columns  
  Not in the string.
- a trinitron is still found by asking for crts
- the form reopens on what it saved  
  The answers come back checked, in the units a person writes: the group sits on 21", not on 210.
- a saved answer from outside the list reopens on custom  
  Somebody else's record, or one typed before the list said otherwise, is not lost by being reopened: the group chooses custom and the box holds it.
- editing a screen keeps its numbers
- a screen records a bezel like a drive
- the page shows the swatch for the pair
- a screen with no photograph gets a monitor  
  Rather than the box every unrecognised type falls back to.
- the small label leads with the size and the tube  
  What identifies a monitor across a room.
- it reaches the printed label
- the type menu offers it

**Pages and discovery**

- the index lists what exists
- an item page titles itself by name  
  The title used to be the asset id alone, which told a search result nothing about the machine.
- an unnamed item does not repeat its id
- the sitemap lists every item
- the sitemap omits pages it does not want indexed
- robots points at the sitemap
- an item url redirects to the right kind
- a label renders as a pdf

**How big the drive is on its label**

- a drive says how big it is
- a drive with no capacity recorded just says what it is  
  Half the drives on file have no capacity against them; none of them should get a blank line held open for one.
- capacity worked out from the geometry counts too  
  A drive recorded by its cylinders/heads/sectors has its capacity derived rather than stated, and the label carries that just the same.
- other kinds of part are left alone  
  Only the types whose name does not say the thing you want off the label.
- a machine is left alone
- the full label still lists it among the specs
- the drive s own label still renders

**A label S code can actually be read**

- a code is never a micro qr  
  Left to itself segno reaches for a Micro QR whenever the data will fit in one, and most readers cannot decode those.
- the url on a label is a full size code too
- the code holds the url that resolves to either kind  
  /items/<tag> is what the scanner navigates to and what the printed code says, so it has to keep working for a machine and for a part alike.

**The capacity gets A line of its own**

- the capacity is the last line
- the longest name on file still leaves room  
  It takes three lines of its own; the capacity gets a fourth, and on a 51x19mm label all four fit without the type having to give.
- where the height does run short the type gives first  
  Squeezed, it shrinks the name to buy the capacity its line rather than dropping the line.
- nothing is held open when there is no capacity
- the capacity survives a name that cannot fit at all  
  Past the point where shrinking helps, the name is clipped and the capacity is kept -- on a drive it is the thing being looked for.
- a label with barely any room still says something  
  Rather than dividing by a line count of zero, or drawing off the label.
- the geometry gets a line under the capacity  
  An old BIOS wants cylinders/heads/sectors before it will talk to the drive, so it goes on the label with them -- prefixed, because three numbers with no word in front of them could be anything.
- the capacity outranks the geometry when only one fits  
  Squeezed past shrinking the type, the last line is the one to go.

**Where A figure is rounded and where it is not**

- the page says it the way a person would
- the form is given it to the kilobyte
- saving that form back untouched does not move the number  
  The corruption the split exists to prevent.
- the stored string is exact too  
  It is the wire format for the REST API and the MCP tools, and it is parsed back by the next write, so it holds the figure rather than a rounding.
- memory is said in megabytes where that is the word for it  
  Not only drives: a 2 MiB SIMM read '2048 KiB' on every page it appeared on.

**The brand on the page**

- the header carries the logo and the name
- a page with no photo shares as the site card  
  It used to share as bare text.
- a photographed item still shares its own photo  
  The card is the fallback, not a replacement: a photograph of the thing itself is a better preview than a logo.

**Walking from item to item**

- the middle item points both ways
- the ends have nothing beyond them
- it walks across computers and parts alike  
  One register, so the walk is over both -- the next asset after a machine may well be a card that is not in it.
- the buttons name where they go  
  The title is the neighbour's name, so a walk is not blind.
- a lone item offers neither
- the gallery hands over the order it is showing  
  Sorted and filtered as the visitor left it, which is the order their prev/next should follow -- not the register's.
- the item page prefers that order
- a swipe across the page is left to the browser  
  Walking the register is the two buttons' job.

**Sorting the gallery**

- a machine carries every key the menu sorts on
- a part carries them too
- what is not recorded is blank rather than absent  
  A missing attribute reads as undefined in the sort; an empty one is what the blanks-last rule looks for.
- machines lead the category order  
  Category sorts by the vocabulary's own order, not the label's spelling, and a computer is not one of the part types.
- the menu offers each of them

**History**

- creating an item is recorded
- a change is recorded field by field
- deleting an item takes its history with it

**The clock shows only when signed in**

- the history gives the minute to whoever can edit it
- a visitor gets the day alone
- a machine history is the same
- the gallery sort keys lose the time too  
  They are not on show, but a timestamp in the page source is a timestamp published all the same.
- the cards arrive newest change first  
  Dates alone are all the sort keys a visitor gets, and the browser's sort is stable, so the order the cards arrive in is what still settles a run of edits made on the same day.

**Photo lookup**

- the bare asset id is the primary
- numbered extras sort numerically not as text
- a named suffix comes after the numbered ones
- another asset is not picked up
- an asset whose id is a prefix of another  
  RH-0001 must not swallow RH-00019's photo, and the hyphen is what separates an id from a suffix.
- the index shows a photo it finds on disk

**Duplication**

- a duplicated part is not in the same machine
- a duplicated part is not mounted on the same host
- a duplicated part keeps what describes the model
- a duplicated part drops what belongs to the original
- a computer can be duplicated
- a duplicated computer has none of the original s parts
- a duplicated computer keeps its memory and drives
- a duplicated computer s memory survives editing it  
  The copy needs its own child rows, not just the rendered strings, or the first save would render them away.
- both sides record the duplication

**Choosing photos**

- the button is the site s own lower case one
- it uploads without a button press
- the button is still there for a browser without scripts  
  The submit hides itself from the script above rather than being absent, so the form still works where that script never runs.

**The code that puts A phone on the item**

- a machine page carries a code for its own url
- a part page carries one too  
  Not only machines: a card or a drive is photographed off the bench as often as the machine it came out of.
- the code lands on something that is really there  
  The fragment is the upload form's own id, and the code sits in the same column as that form -- a desktop being scanned from across the bench.
- the code rides in the photo column
- it is a standard symbol not a micro one  
  Same reason as the labels: most readers, the gallery's own scanner included, decode standard QR only.
- a visitor is not offered one  
  A code leading to a page with no upload button on it is a promise the site will not keep.
- a phone that arrives logged out is sent back to the item  
  Scanning is most of the way to the picture; being handed the gallery after logging in and told to find the thing in your hands again is not.

**Logging out stays where you are**

- it goes back to the page it was done from
- a search is part of where you were  
  The gallery with a search in the address is not the gallery.
- an edit form lands on the item it was editing  
  The form is behind the login, so going back to it would bounce straight to the login just left.
- anything else is the gallery
- the form carries the page it is on
- the way in carries it the same way

**Photographs on A create form**

- a machine is photographed as it is created
- a part is photographed as it is created
- several arrive together and the first is the primary
- a file that is not an image creates nothing at all  
  Checked before the machine is written rather than after.
- a drive folded into a machine photographs the machine  
  A floppy becomes a row on the machine rather than an asset of its own, so it has no tag of its own to file a photograph under: the machine it went into is the only place they can go.
- the form offers the picker and can carry a file
- an edit form does not offer it  
  The item already has a page, where a photograph uploads the moment it is picked; a second, slower way to do the same thing on the edit form would only be a way of doing it worse.
- the picker is not the one that uploads on selection  
  That script is bound by id to the item page's form.

**The icon set**

- the background stays transparent
- the apple icon is deliberately not  
  iOS composites transparency on black, so this one is flattened on white.
- each slot is the square it claims
- the logo keeps its own shape  
  The header and the photo watermark are not square slots, so they get the tight crop: letterboxing the mark would shrink it on the photo, and the header would carry a logo with air above and below it.
- the share card is opaque and the shape those slots want  
  Several of the sites that show a card composite a transparent PNG onto black, so this one brings its own background.
- the master is cropped to its artwork  
  No transparent margin left on the master, so every icon made from it uses the whole slot.

**Watermark**

- our own photo comes back marked
- the mark grows with the photo  
  It is a proportion of the short edge, not a fixed number of pixels, so it stays legible on a 5712px photo and unobtrusive on a small one.
- a reference photo is left alone  
  Someone else's picture of the same model is not ours to sign.
- the cache directory is not served
- the cache is keyed on the mark s parameters  
  A cached copy is otherwise only rebuilt when its source photo changes, so changing the size used to leave every existing watermark at the old one.
- the cache is keyed on the compositing too  
  Changing how the copy is made, rather than the numbers it is made with, also has to miss the old cache -- baking in the orientation did.

**A photo lying on its side**

- it arrives the way up it should be seen
- a crop keeps the region it was dragged over  
  The box arrives as fractions of the photo as displayed, so it has to land on the same way up that the serving path produced.
- a preview is told the size that will arrive  
  The og:image dimensions let a link preview lay the image out without fetching it, so they have to describe the copy that is actually served.

**Starting from an existing part**

- the form offers the makers already recorded
- the models already recorded are offered too
- a make and model pair is matchable with its asset id
- starting from a part fills in what describes the model
- the prefilled form creates rather than edits  
  The source must not be overwritten: the form posts to /parts/new.
- it says where the values came from
- nothing of the original object is offered  
  The boxes, specifically, and not the whole page.
- opening the prefilled form changes nothing
- the type follows the part it started from
- a stale link gives a blank form rather than an error
- it keeps the machine the part is being added to

**The numbers page**

- it is public
- it renders with nothing in the register  
  A fresh install is a real state, and several figures are ratios: the page must not divide by zero on day one.
- the headline counts everything
- the top maker is the one with most parts
- bars are scaled to the largest value
- memory totals come from the typed column
- the traffic report is still private
- it is offered to search engines

**Following A figure to its items**

- every figure on the page leads somewhere real  
  A sweep of the whole page.
- a maker leads to that maker s parts
- a category leads to the parts in it
- the best equipped machine leads to the parts in it
- the disposed count shows the disposed items  
  The gallery hides disposed items unless asked; a page reached from the figure that counted them must not, or it contradicts the number clicked.
- the gallery itself still hides them
- an unknown view is a 404
- a view of a machine that is gone is a 404
- it is public like the figures it came from
- it is kept out of the search index  
  Filtered slices of the gallery are not pages worth indexing; the items in them already have their own.

**Every object has its portrait**

- the figure is on the page every visit  
  The tiles are eight drawn from a pool of dozens, so a figure in there is on the page perhaps a quarter of the time.
- it is not dealt into the shuffle as well  
  Promoted out, not copied out.
- the figure and the queue are the same answer  
  The whole point of the stage.
- what has gone is not waiting for a camera  
  A disposed item is a record of something that has left, and nobody can go and photograph it.
- a photograph of what happened is not a portrait  
  Six pictures of a recap say what happened to a machine.
- a photograph named for the side it shows still counts  
  RH-0001-back-left is the part's photograph the same way RH-0001-2 is, and the gallery has always thought so.
- a photograph in the wrong folder is nobody s portrait  
  A picture in parts/ is a picture of a part.
- a register that is all photographed says so  
  The end of the job is a state worth rendering, not a blank.
- an empty register claims nothing  
  "Every one of them has had its portrait taken" is true of nothing and reads as a boast on a fresh install.

**The catalogue page**

- every model in the catalogue is on it
- it says which of them are actually here  
  The other view of the catalogue: not what was made, but how much of it is on the shelf.
- a model nothing is filed as says nothing  
  Most of the catalogue is machines this collection has not got, which is the ordinary state and reads as a catalogue rather than as a gap.
- the count leads to the machines behind it  
  A board files as a model the same way a whole machine does, so both turn up here -- that is what the catalogue's board side is for.
- a model the catalogue never had is a 404
- it is public  
  The whole point of the page.
- the rest of the api is still not
- it is offered to search engines

**Search terms**

- words are separate terms
- case and spacing do not matter
- a quoted run is one term
- quoted and bare terms mix
- an empty query asks for nothing

**Searching every field**

- no query shows everything
- a word only in the notes
- a word only in the summary
- a word only in the history
- a word only in the specs
- every term must appear somewhere  
  The words may be in different fields -- maker in one, condition in another -- which is what makes it a search rather than a phrase match.
- a quoted phrase must be contiguous
- nothing matching says so
- it reports what it searched
- the browser is told what the server matched  
  Otherwise the instant filter would hide rows that matched on a field the browser's own copy does not carry.
- searching is public

**The first few matches while you type**

- it offers the matches and says how many there are
- nothing is offered for nothing typed
- an asset tag typed in full comes first  
  Typing a tag off a label is aiming at one item, whatever else mentions it -- and other items do mention it, because a part records the machine it is installed in.
- a name that starts with it beats one that merely contains it
- a hit only in the history is offered but sorts below a named one
- a disposed item is offered last and says so
- each row carries what the list draws
- a part wears its own category and icon
- a floppy drive is not drawn as a hard disk  
  The gallery tells a floppy from a disc from a disk by its Kind spec; a list of ten under the search box has the same job and the same answer.
- suggesting is public
- it is not offered to crawlers

**The big photo view**

- each photo says where it lives  
  One toolbar in the overlay serves every photo, so each carries its own item and filename.
- the zoom is not shut inside the photo shape  
  A tall photo opens with a black band either side of it, and zooming in used to magnify within that same tall rectangle -- the band stayed black and most of the screen went unused.
- a mac trackpad is answered in both of the ways it is reported  
  A pinch on a trackpad reaches the page as ctrl+wheel in Chrome and in Firefox, and as Safari's own gesture events, which are non-standard and the only report Safari sends -- so both are listened for.
- a photograph on a phone is flicked away to close it  
  A photograph at its own size on a phone is not on a page you can leave, and the close button is a small target in a corner.
- a trip home cut short still puts the overlay away  
  The overlay closes by sending the photo back into its thumbnail, and while that is running the photo is uninterruptible -- which is the flag every way out of the big view checks before doing anything.
- the double click that comes back out of a zoom is heard  
  Double click to go in, double click to come back out -- except the way back out was never heard.
- a click on a zoomed photo is not a click on the black  
  The same pointer capture makes a click on a zoomed photo arrive looking exactly like a click on the backdrop, which is the one click that means close -- so a zoomed photo dismissed itself at a touch.
- the whole overlay takes the gesture not just the photo  
  On a phone most of what is on screen is the black around the photo, so a flick that starts there is still a flick -- and left to itself the phone scrolls the page underneath while the photo sits there doing nothing.
- the movement is dropped for anyone who asked for less of it  
  The glide, the spring at the edges and the eased zoom are all feel, and feel is exactly what a reader who has asked their system for less movement does not want.
- the editing tools are only for the logged in
- the old editor page opens the big view instead  
  It was its own page; keeping the link working means one crop implementation rather than two.
- rotating from the view returns to the same photo
- cropping from the view returns to the same photo
- a nonsense crop box is refused
- an edit is recorded in the history
- one mode of the toolbar at a time  
  crop swaps its button for an apply/cancel form using the hidden attribute, and author rules that set display outrank the browser's `[hidden] { display: none }` -- which showed every control at once whatever mode it was in, and later left the upload button on screen too.
- the row offers a delete  
  Beside crop and the rotates, so a photograph that turned out badly goes from where you are looking at it rather than from the column behind.
- it asks first  
  The one tool in the row that cannot be undone, so it is the one that asks -- the same question the column's own delete asks.
- it is only for the logged in
- it carries no next because there is nowhere to return to  
  Its neighbours come back to the same photograph still open.
- deleting from the view lands back on the item  
  Not on the photograph, which is the whole difference from a rotate.
- it steps out of the row while cropping  
  Cropping puts an apply button where the row was.
- it reads as the destructive one  
  Colour is what says this tool is not like its neighbours, and the register's warning shade is unreadable on a black toolbar unlightened.
- there is no separate button to open the view  
  The photo is the way in: a button beside it did nothing that clicking it does not.

**A photograph is never half written**

- a reader never sees a fragment  
  The regression itself, read where the bug was: on disk.
- nothing half written is left lying in the folder  
  The photograph is written beside itself first.
- the crop still actually crops  
  Writing it somewhere else first must not change what comes out.
- a copy is dated by what it was made from  
  A cached copy carries the mtime of the photograph it was made from, not the clock.

**Changing A parts type**

- the form can be built for another type
- looking does not change the record  
  Nothing is saved until the form is submitted.
- a type the register does not know is ignored  
  It would render the free-text box and then become the part's type on save, which is a way to file a SIMM as a gizmo by editing a URL.
- a power supply stays one  
  A type the form does not offer is a type the form quietly changes: the select has no option to match it, so the browser sends the first one and a Delta 300W becomes a motherboard on the next save.
- what the old type recorded comes across  
  The bug behind the question.
- a key both types ask about is left to the form  
  It is the answer somebody has just given to a question they were shown.
- an ordinary edit still carries only its attributes  
  Saving without retyping behaves exactly as it did.
- the menu asks before it throws away what you typed

**Deleting A history entry**

- one entry goes
- a folded run goes as the one line it reads as  
  A run of the same thing done in one sitting reads as a single line, so it has to delete as one: "deleted 3 photographs" that removed one of them and came back saying two would not be doing what it says.
- it cannot reach another items history  
  An id on its own would let one machine's history be deleted from another machine's page.
- nothing is written about the deleting  
  The rule an entry losing a photograph already follows: editing the record is not something that happened to the machine, and a history that logged its own editing would grow a line for every line it lost.
- the photographs on it go with it  
  A photograph hung on an entry means nothing without the entry, and the file behind it is the one thing here that cannot be rolled back.
- it is only for the logged in

**A page notices it has changed**

- the page carries the token it was built with
- a change moves it
- a photograph moves it too  
  The case this is really for: the phone adds a picture, the desktop is still showing the page without it.
- deleting or cropping a photograph moves it as well  
  Every edit to a photograph is a change to the record, and the phone is not the only place they happen.
- a file moves it although it belongs to no item  
  A driver is filed against a model rather than against the card on the shelf, so nothing about it reaches that item's history -- and an item page shows it all the same.
- reading the page does not move it  
  Or every page would reload itself for ever.
- an item that is gone still answers  
  A page whose item has been deleted asks this too.
- it is asked only of an item page  
  The gallery has no one item to ask about, so it is not given the script.
- it waits rather than reloading under your hands  
  A page that reloaded itself mid-crop or mid-sentence would be worse than one that is out of date.
- it only asks while it is being looked at

**A top bench score**

- it comes back typed
- a machine it has not been run on has no score  
  Not zero: a machine nobody has benchmarked has no score, and zero is a result -- the one a machine that could not finish the run would get.
- a score that is not a number is refused
- the form takes one and gives it back
- the form can take it back off
- the page shows it
- and says nothing about a machine that has no score
- the change is recorded in the history
- the box is marked for the script that hides it  
  TopBench is a DOS program, so the box is on screen for a PC and off it for a catalogue machine -- which the machine picker's script decides, since the model is chosen without reloading the page.
- a score survives the machine being filed as a catalogue one

**The parts and what they are made of**

- the specs are not a column of a table
- each part is one card  
  Everything about a part inside one border: the tag and the kind on the strip, the name under it, the specs beneath that.
- they are shown as labelled pairs below the part
- a part with nothing recorded gets no second line
- a card s mounted parts are listed the same way  
  One list, two places: a machine's parts and a card's mounted parts are the same thing and have to read alike.
- the board above them is drawn as one too  
  A section that said a board's specs a second way would be two designs for one thing, and the board has the longest set of them on the page.

**A history that reads as one sitting**

- ten deleted photos are one line
- one of a thing is still written as one
- the same thing a week later is its own line
- a long tidying session is still one line  
  Chained, not windowed from the first: twenty photographs deleted a couple of minutes apart is one sitting however long it ran.
- two different things are not folded together
- a message naming no single thing takes a count
- a note is never folded  
  A note is a person's own words about the machine and stands as written, however like the last one it reads.
- the record behind it is untouched  
  The page reads the history this way; it does not rewrite it.
- a parts history folds the same way

**Photographs on the history**

- a note and its photographs arrive together  
  One gesture: the sentence and the pictures of what it describes.
- several photographs go on the one entry
- a part carries them the same way
- it is not one of the item s own photographs  
  The whole reason for a folder of its own.
- the count of photographs in the register does not absorb it  
  A picture of a recap is not a picture of the machine, and the figure that says how many photographs the collection has means the second thing.
- photographs with no words are an entry of their own  
  A photograph of the thing is a thing said about it.
- it gets a line and a time of its own  
  Separate entries, so the log says when the photograph was taken rather than when the sentence above it happened to be written.
- neither half needs the other  
  Words alone, photographs alone, and both together in one gesture -- three entries, and the one with words keeps its photographs as its caption.
- nothing at all still writes nothing at all  
  An empty box and no photographs is somebody pressing the button by accident, not an entry about nothing.
- the last photograph off a photograph entry takes the entry  
  The photographs are what it said.
- a worded entry keeps its line when its photograph goes
- a file that is not an image writes no entry either  
  Checked before the entry is written, as a create form's are: a refused upload should not leave a note behind saying something was photographed.
- the page shows them under the line they belong to
- it hangs in the entry s own column and not the date s  
  A row across the entry, under whatever it says.
- a photograph has no delete of its own  
  One button a line, at the right, where a line of words has it.
- one can be hung on an entry already written  
  The swap the register logged last week, photographed when the lid next came off.
- a part s entry redirects back to the part
- an entry of another asset is not somewhere to put it  
  The id in the URL is checked against the entry's.
- removing one takes the row and the file
- a photograph on another entry is not this one s to delete
- the removal is not itself written into the history  
  An entry gaining or losing a photograph is an edit to the record, not something that happened to the machine.
- an entry carrying photographs is never folded  
  Folding rewrites several entries as one sentence.
- the api lists what an entry carries
- deleting the machine takes them off the disk  
  They go the way every other photograph of a deleted record goes: the rows first, because a file cannot be rolled back.
- deleting a part takes its own with it
- the confirmation page counts them among what goes  
  The page can only promise what the delete actually does, and the delete takes these off the disk too.
- an entry s photographs cannot be claimed by a longer id  
  Entry 12's photographs are 12.jpg and 12-2.jpg; entry 120's are 120.jpg.
- they are marked like any other photograph of the collection  
  The watermark is about where a photograph goes, not which panel of the site it was shown on.
- the note bar offers the picker

**Where the files sit**

- they come before the history  
  Files are part of what the item is -- the driver disk it needs, the manual for it.

**Every section is A panel**

- the machine page says where each section starts
- and so does a part page
- a section of cards is one panel and not a box each  
  The panel draws the box, so the cards in it give theirs up and keep their bands -- a border round each inside a border round all of them is what makes a page look busy.
- the specs of a part are their own panel

**Files read like the parts do**

- a file is a card with its name on it
- it says how big it is before you click it
- the names it is filed under are still editable  
  Re-filing is the thing most often wanted here, so it stays a box rather than becoming a link to somewhere else.
- a visitor gets the names without the box

**Pages are not kept by browsers**

- a page is asked for every time
- but a stamped photograph is still kept for a year  
  The opposite rule, on purpose: those URLs carry the version in them, so they can never go stale and never need asking about.

**Photographs are served at the size asked**

- a width is smaller than the original
- the same copy is served the second time
- a width nobody asked for is not made  
  The width comes out of a URL, so a stranger could otherwise fill the disk with nine hundred copies of one photograph.
- a photograph smaller than the width is served as it is
- a stamped url may be kept and an unstamped one may not  
  ?v= names which version of the photograph the URL wants, so it can never go stale and can be cached for a year.
- the gallery asks for card sized copies and keeps the original
- the static files may be kept when the url says which version

**A serial that was never recorded**

- an unrecorded serial reads back blank
- listing survives a machine with no serial
- listing survives a part with no serial
- a null from an older database still reads as blank  
  The belt to 0034's braces, and not reachable end-to-end once the column is NOT NULL -- which is the point.


## Architecture

*test_architecture.py — 2 behaviours*

- the map lists every module and no others  
  A map that has quietly stopped matching the code is worse than none: it is read by whoever knows the code least.
- the behaviour catalogue is the one the suite would write  
  The catalogue is generated, so the only way it can be wrong is by being stale.


## Attach single item jobs

*test_attach_single_item_jobs.py — 6 behaviours*

- a single item projects loose jobs are picked
- a project about two things is left alone  
  Which of them is 'strip and clean' about?
- a job that already names something is left alone  
  So a choice made by hand survives, and a second run changes nothing.
- a project with no items is left alone  
  A project need own nothing -- the idea comes before the hardware.
- a project with no loose jobs is left alone
- only the loose ones are taken from a mixed project


## Auth secret

*test_auth_secret.py — 3 behaviours*

- uses the configured secret when present
- requires a secret when auth is enabled
- generates a throwaway secret when auth is disabled


## Autocomplete

*test_autocomplete.py — 16 behaviours*


**What is offered**

- an answer already given is offered
- the commonest comes first  
  A datalist is offered in the order it is written, and the answer given twenty times is the likelier one.
- the same answer typed two ways is one answer  
  Case and stray spaces are how one answer becomes two.
- the minority spelling does not win by being stored first  
  The one the database would have picked.
- nothing is offered for a field left blank
- machines and parts share one list  
  A job lot arrives as a machine and a box of cards together, and that is one provenance however many records it becomes.

**The forms offer them**

- the machine form offers a source
- the part form offers the same sources
- a machine is offered the makes it knows  
  Parts had this and machines did not, though a Compaq is a Compaq whether it is the box or the board out of it.
- a part is offered a make only a machine has used
- a machines model list is machines only  
  A list of every card and drive model as well would bury "PC1512" among a thousand answers to a different question.
- the three a machine is asked and a part is not
- an edit form offers them as well  
  The same boxes, and the same drift: an edit is where a spelling gets changed into a second one.

**Elsewhere**

- a project offers who things were bought from
- the files panel offers what files have been called
- a visitor is offered nothing  
  The pick lists are on the forms, and the forms are behind the login -- so a public page cannot leak the list of everybody the collection has ever bought from.


## Backup roundtrip

*test_backup_roundtrip.py — 1 behaviours*

- dump and restore roundtrip


## Branding

*test_branding.py — 8 behaviours*


**Choosing the artwork**

- the shipped one is used when there is no other
- an installations own wins
- overriding one leaves the rest shipped  
  The point of resolving name by name rather than directory by directory: replacing the header logo does not mean supplying every icon size.

**Serving it**

- a static file falls through to what ships
- a static file is replaced by the installations own
- the favicon is replaced too  
  Asked for at the domain root by browsers that never read the markup, so it is a route of its own rather than part of the static mount -- and it has to obey the same rule, or the tab keeps somebody else's mark.
- and the home screen icon
- nothing outside the two directories is reachable  
  The branding directory goes in front of the shipped one in the static mount's own search list, so the traversal checks are the ones it already makes -- this says so out loud, because a directory that can be written to from outside the image sitting in the serving path is worth a test.


## Deployment

*test_deployment.py — 10 behaviours*


**The api trusts its proxy**

- the proxy headers are read
- they are read from the proxy rather than from localhost
- the schema is brought up before the app serves  
  The other half of the entrypoint, and the reason a deploy needs no migration step of its own.

**The app does not run as root**

- the image ends as appuser
- the app owns where it writes and not its own code  
  The data directories are chowned by name, never /app as a whole: code the app can rewrite is code a compromise can rewrite.
- an older install gets its volumes back before the app starts  
  An install from before this has root-owned volumes.
- the fix reaches the two volumes and nothing else  
  It runs as root, so what it may touch is spelled out and kept small.
- it looks before it changes anything  
  A chown -R over every photograph on every start would be slow on a large collection and would churn the backup's view of what changed.

**The development override**

- it goes through the entrypoint  
  So a development run migrates first and reads the proxy headers exactly as production does, rather than carrying its own copy of the uvicorn line that drifts from the real one.
- it watches the code and not the photographs  
  uvicorn watches its whole working directory unless told otherwise, and the photograph volume is inside it: every upload would restart the server.


## Drivedb

*test_drivedb.py — 47 behaviours*


**Parsing real values**

- a segment reads as recorded
- semicolons separate drives
- a stray semicolon does not make an empty drive
- three drives of different kinds

**Inference**

- a floppy size implies a floppy  
  '2 x 5.25" 360K' names no kind, but nothing else comes in 360K.
- an emulator is a gotek even beside the word floppy
- a card capacity implies nothing  
  A bare '4GB' could be SD or CF, so neither is asserted.
- unrecognised words become the model
- descriptive noise is dropped
- form factors are written several ways
- sizes canonicalise

**Rendering**

- a count of one is not written
- a count is written when there is more than one
- the model leads
- drives are joined with semicolons
- a note comes last
- rendering a parse is stable

**The bezel**

- both are read from what was typed
- a two word shade is one shade  
  'off-white' is not 'white' with a stray word, and 'light grey' is not 'grey' after one -- either mistake would leave half of it in the model.
- a two word level is one level
- the looser words land on a label
- browning is a level not a shade  
  'brown' describes what has happened to a bezel, not what it was made in -- there is no brown in the shade list to mistake it for.
- every label answers to itself
- a bezel alone is a drive worth recording  
  Half a drive is still a drive: the bezel is beige even if nobody has written down what kind it is yet.
- neither is taken from inside a word
- it renders in brackets at the end
- either alone renders too
- a count still leads
- rendering a bezel reads back the same  
  The string is a cache of the rows, so it has to parse back into them -- a bezel that renders one way and reads another would drift on every save.

**Optical drives**

- the ways a medium is written
- every medium answers to itself
- a medium makes it an optical drive  
  Nothing but an optical drive takes a CD-RW, so the kind need not be said as well -- and the word "cd" the kind list knows has been taken out of the text by the medium on its way past.
- a medium is one designation not a kind and a stray word
- a model that begins with one keeps it  
  A drive modelled "CD-120" is an optical drive, but those two letters are its model's -- taking them would leave a bare "120" behind.
- the ways a rating is written
- every rating answers to itself
- a lone rating is the speed not a count  
  The one "N×" beside a medium is what the drive is being described by -- a 2× CD-ROM is a real drive, and two of them is not what someone writing "2x CD-ROM" means.
- a writers three figures are one rating  
  What it writes, rewrites and reads.
- a bay standing after a rating is not another figure
- a count of unrated drives is written without the mark  
  Which is how render() writes it, so that it reads back as a count.
- a rating is only read where a drive could have one  
  '2 x 5.25" 360K' is two floppies, and always was: nothing but an optical drive is rated in ×, so nothing else goes looking for one.
- a rating is not taken from inside a word  
  A model number ending in a digit beside an x is not a speed.
- it renders as it is said out loud
- the model still leads and the bezel still trails
- rendering reads back the same  
  The string is a cache of the rows, so it has to parse back into them.

**Empties**

- nothing in nothing out
- a segment of punctuation yields no drive


## Enrich ssrf

*test_enrich_ssrf.py — 2 behaviours*

- blocks internal and non http
- allows public http


## Entry

*test_entry.py — 70 behaviours*


**Amounts**

- to kb
- to kb refuses what it cannot read
- fmt kb

**Which unit A figure is said in**

- a figure that can be said exactly is said that way everywhere  
  No split to make here: the same words serve the page and the form.
- a whole number of megabytes stays in megabytes  
  2096128 KiB is the 2047 MiB BIOS limit, and calling it '2 GiB' would lose the one thing about it worth knowing.
- a figure that cannot is rounded only where it is read  
  Rounding cannot be undone, so it is offered to a page and a label and withheld from the form and the specs string, which are parsed back.
- rounding never reaches for scientific notation  
  Three significant figures via '%g' would render 1000 as '1e+03'.
- under a megabyte stays in kilobytes
- nothing is nothing rather than zero  
  A machine with no memory recorded has no memory string, not '0 KiB'.
- memory spec amounts normalise to kb

**Bezel swatches**

- a shade on its own is its own hex
- nothing recorded draws nothing
- yellowing darkens and warms the shade  
  Each step has to move the same way, or the ladder would not read as one.
- the same level reads differently on a different shade
- uneven yellowing is drawn as two tones  
  One shade in two states is the only honest way to draw a patchy bezel.
- yellowing with no shade recorded still draws  
  An unrestored find often shows only how yellow it is; it is drawn on some pale plastic, which is what almost every yellowed bezel started as.
- the swatch map covers every pair
- every entry carries what the chart needs
- no shade is also a yellowing level  
  They are separate fields; a word that meant both would make a typed drive ambiguous.

**Installed ram**

- modules render with a total
- module totals add up across types
- parity chips of a different type are not capacity  
  An Amstrad PC1640 carries 4x 4464 for data with 2x 4164 alongside for their parity.
- a bank is made of chips of the same depth  
  64K-deep and 256K-deep chips cannot share a bank, so they are counted as separate ones: 18 bits at each depth is 16 data bits at each.
- two wide chips make one byte wide bank
- a bank without parity is all data
- the ninth chip adds no capacity
- no chips is no capacity
- nine by one chips are eight of data plus parity  
  A byte-wide bank of x1 chips is 8 data chips plus a 9th for parity, so nine 32KiB chips are 256 KiB usable, not 288.
- eight chips are a plain bank
- eighteen chips are two parity banks
- a wide chip can carry parity too  
  The old rule only looked for parity among ×1 chips, so nine ×4 chips counted as 1152 KiB -- 36 data bits, four and a half bytes wide, which no byte-organised machine is.
- a bare total renders when there is no breakdown
- a breakdown hides the bare total
- a note is appended not swallowed
- empty everywhere renders empty
- zero counts are ignored

**Ports and slots**

- port letter codes expand
- an already expanded list is left alone
- a port list parses back into counts
- slot shorthand expands
- slot shorthand is order independent
- an unknown slot token is ignored
- counts render without a one

**Spec strings**

- parse specs splits on pipes and colons
- a keyless chunk keeps an empty key
- merge spec replaces a key in place
- merge spec appends a new key
- build specs drops blanks

**Names**

- deshout lowers shouted words
- deshout leaves known acronyms
- deshout leaves short words
- display name prefers an explicit name
- display name falls back to maker and model
- display name falls back to the asset id
- every vocabulary type has a written label  
  These three were missing, so type_label fell back to .title() and gave back "Psu".
- an unknown type still gets something readable

**What each kind of drive is asked**

- each kind is asked what the chart says
- every kind in the menu is in the table  
  A kind the table says nothing about would arrive with no fields at all.
- a shared question offers each kind its own answers
- only the interface is required  
  Everything else may honestly be unknown on a drive still in its box.
- a floppy is asked a designation and never a measured capacity  
  720K is what the disk is called; it is 737 KiB only by convention, and normalising it would put a number on the label nobody uses.

**Links in what people wrote**

- what becomes a link
- what does not
- where the url stops and the sentence carries on
- the rest of the sentence is kept
- a link opens in a tab of its own and an address does not
- the lines a note was typed in are left alone
- nothing out of a text box arrives as markup
- a url cannot break out of its own href
- what is not a string at all  
  The details tables hand this whole rows at a time -- a year, a date, the None of a column nobody filled in.


## Files

*test_files.py — 50 behaviours*


**Attaching one**

- a driver attached to a model reaches every card of it  
  "to a model -- every machine or card of that model".
- and a card of another model is not offered it  
  Both halves, because "not offered" is true of a file that reached nothing at all: the driver has to be on the Trident card to say anything about its being off the Tseng one.
- a card bought next year is offered it too  
  "the ones on the shelf now and the one bought next year".
- disposing of two takes nothing away from the third  
  "disposing of two of them takes nothing away from the third" -- the disposal case the old docstring was right to worry about.
- a receipt attached to one unit reaches that unit alone  
  "to one unit -- that machine, that card, by its asset tag".
- an upload is attached to the model of the page it started on  
  "Upload a file there and it is attached to the item's model where the item has one".
- an upload on something with no model is attached to that thing  
  "and to the item itself where it has not -- a custom build".
- the panel says which of the two it did  
  "The panel says which of the two it did." Both ways round, because the sentence is the only thing telling you where an upload has just gone.
- the other of the two is one click away  
  "and the other is one click away".
- one file can be attached to several things  
  "A file has as many of either as it needs, because one disk often covers a card and the machine it shipped in".
- detaching takes it off and keeps the file  
  "detach takes it off again.
- a file attached to nothing says so  
  "a file attached to nothing is unfiled, and says so on the /files page".
- and is filed from that page  
  "which is where one is found and filed".
- identifying a machine does not take its files away  
  "A machine the catalogue names is both, and answers to a file attached either way." The file was attached before the machine was identified.
- a file on a catalogue model reaches another of it  
  The other half of "both": attached to the catalogue's model, it reaches a machine identified as that model however its maker and model were typed.
- the same model written two ways is one model  
  "Case and spacing make no difference." Nobody agrees where the spaces go in SoundBlaster, and neither spelling is the wrong one to have typed.
- a model is the whole model and not a piece of it  
  A model is named or it is not.
- renaming an item does not move its files  
  "Renaming an item does not move its files" -- the fault ADR-0006 reports, where an edit silently detached one.
- correcting a parts model does move it  
  "But correcting a part's model does" -- and the manual says so plainly rather than leaving it to be discovered.
- a tag decides nothing  
  "A tag does not decide where a file appears".
- deleting an item takes the link and not the bytes  
  Detaching never deletes, and neither does deleting the thing a file was about: unfiled is a state, not a reason to bin something (ADR-0006).
- attaching to something that is not there is a 404  
  Rather than a link to nowhere, which would read as unfiled while looking filed.

**Keeping them**

- what was uploaded comes back byte for byte
- it is handed over as a download and never as a page  
  An upload is whatever somebody sent, and some of what people send is HTML.
- the name it was sent under is never a path  
  The one part of an upload chosen entirely by whoever sent it.
- two files of the same name do not land on each other
- an empty upload is not a file
- one over the limit is refused and leaves nothing behind
- deleting one takes its bytes and its names

**Tagging**

- the box is the whole list  
  What the box shows is what a save means, so a tag taken out of it is gone rather than added to.
- relabelling moves nothing  
  The whole demotion in one test: the tags box used to be how a file was re-filed, and now it is how a file is described.
- a name written twice is kept once
- the tags are shown back as they were written

**The files page**

- it lists what is there
- it can be narrowed to one name

**Over the wire**

- the api lists them with their names
- it can be asked for one name
- asking for a tag answers with what carries it  
  Equality on the fold, not containment on a name: a tag says what a file is, so following one asks for the manuals rather than for whatever a machine of that name would be offered.

**Who may do what**

- a visitor may download but not upload  
  Downloading reads like a photograph does.
- a visitor is not shown the upload box

**Publishing one**

- a new upload is not public
- ticking the box publishes it
- unticking it takes it back  
  The point of a toggle rather than a publish button: something put up by mistake has to come down, and come down everywhere.
- a file kept back is not reachable by its tag  
  The tag chips lead from an item page to /files?tag=..., which asks the same question of the same names.
- an unpublished file is missing rather than forbidden  
  404 and not 401.
- the owner is shown both  
  Whoever can publish has to be able to see what is not published, or there is no page to tick the box on.
- only the owner may publish
- an unpublished file is not cached anywhere  
  The owner is the only person who can fetch one, and unticking the box has to stop the copy being handed out -- which a cache holding it for the hour the published header asks for would carry on doing.
- the wire format says which

**Sizes read**

- a size is said the way it would be said


## For sale

*test_for_sale.py — 21 behaviours*


**Ticking an item**

- an item starts unflagged  
  A fresh install has never thought about selling anything.
- the tick sets it and unticking takes it back
- an unticked box sends nothing and that means no  
  The one form control whose off state has to be read from its silence -- the same reading files.public already takes of the same gesture.
- the tick comes back to the item
- ticking something that is not there is a 404

**The shortlist**

- it lists what is ticked and nothing else
- it holds machines and parts together
- an empty shortlist says so rather than erroring
- it is kept out of the index  
  A private page is not one a crawler should be told about, and the card a link to it previews as is the site's own -- there is nothing to advertise.

**Nobody else sees it**

- the shortlist asks a visitor to log in
- a visitor cannot tick one
- the item page shows a visitor neither tick nor marker
- a visitors search does not match on it  
  The one that would have gone unnoticed.
- the owners search does match on it  
  The other direction, so the fix is a rule about who is asking rather than a column quietly dropped from the search for everybody.
- the flag is not in the json api  
  It is set where the decision is made, so nothing carries it to a caller -- which also leaves the pinned contract (ADR-0010) alone.
- the gallery card does not carry it  
  The cards hold a condensed blob for the type-ahead filter.

**The named set rather than A habit**

- the haystack leaves out every owner only column for a visitor
- for sale is in the set
- an unflagged item reads identically for both  
  The owner-only columns are blanked, not dropped, so who is asking changes what the haystack says and never how many fields it has.

**It survives the rest of the site**

- disposing a flagged item leaves the flag alone  
  Two different facts.
- the decision is written down


## Healthz

*test_healthz.py — 3 behaviours*

- healthz ok when db reachable
- healthz reports 503 when db unreachable  
  A liveness check that returns 200 while the database is down is worse than useless -- it would let a broken deploy pass the smoke check.
- healthz is public even when auth is enabled  
  The deploy smoke check has no credentials -- it runs before any exist for that box.


## Image writes

*test_image_writes.py — 7 behaviours*

- two writers do not share a temporary file
- the photograph left behind is one of them whole  
  Not a mixture of the two.
- neither writer is left holding nothing  
  The loser used to fail on the rename, because the winner had already moved the temporary file they were both using.
- a temporary file is never left behind
- the sized copies follow the same rule  
  thumbs makes its own copies and had its own `.part`, so it had the same race on the same reload -- two widths of one photograph are two destinations, but a browser asking for one width twice is one.
- a photograph asked for by several requests at once is whole  
  The whole gesture, through the app: a photograph uploaded, then asked for by several requests together the way a reloaded page asks for it.
- two edits in the same second get different urls  
  A photograph's URL carries a stamp so it can be kept for a year and still never be stale: editing it changes the stamp, so the browser asks again.


## Keyboard and motion

*test_keyboard_and_motion.py — 12 behaviours*

- the first thing tab reaches skips to the content  
  A keyboard user tabs the whole header -- brand, five sections, search box, menus -- before reaching the page, on every page, unless the first stop is a link past it.
- an item page skips to the content too  
  The page a printed label opens is the one most often reached cold.
- the skip link has somewhere to land  
  A skip link whose target is not an id on the page moves focus nowhere and fails silently, which is the failure this whole invariant is about.
- every heading cell says which way its table runs  
  A screen reader announces a cell with the heading it sits under only when the heading says whether it runs across the top or down the side.
- no movement starts without asking whether motion is wanted  
  The register's one piece of motion of its own -- Find, scrolling a phone back to the search box -- asks for it in JavaScript, where the CSS cannot reach: a `behavior: 'smooth'` passed to scrollTo outranks `scroll-behavior` in the stylesheet, so the media query alone would leave it moving.
- the stylesheet answers a request to reduce motion  
  Nothing in the stylesheet animates today, which is exactly when the block is cheap to add: it covers the transition somebody writes next, rather than being remembered at the moment it is needed.
- a bar fixed across the bottom does not swallow the focus ring  
  Reaching a control below the fold, the browser scrolls it into view and stops it at the edge of the viewport -- which on a phone is exactly where the tab bar is fixed, so the control arrives underneath it.
- the cookie notice does not swallow it either  
  The notice is fixed above the bar and is taller than it -- 167px on a 320px screen, where the text wraps to five lines.
- the login boxes say what they are for  
  A password manager fills a form it can read: `autocomplete="username"` and `current-password` are what tell it which entry this is and which box the password goes in.
- every control says what it is  
  A control with no name is read out as "edit text, blank" and nothing else, which on the drives grid was eight of them to a row.
- every image says what it is or says it is decoration  
  `alt=""` is an answer -- it tells a screen reader to pass over a swatch or a rule.
- nothing hides where the keyboard is  
  The browser's own focus ring is what most of this site relies on, and one line of CSS anywhere would take it away everywhere it applies.


## Machines

*test_machines.py — 171 behaviours*


**Catalogue consistency**

- every model key is unique
- every key resolves
- an unknown key is none rather than an error
- a model says what it is  
  The window runs from the Altair that started it to the last machine anybody here would call retro, and its job is not to police what belongs in the catalogue -- that is the documented-model rule, and it is a judgement rather than an arithmetic.
- every memory size is a figure the register can read  
  The labels are offered on the memory box, which reads them with entry.to_kb -- so '48K' has to come back as the 48 KB the catalogue says it is, or picking a standard size would record the wrong machine.
- each socket is asked once and has something to offer
- nothing offered is longer than the column that holds it  
  A suggestion the database could not store would fail on save rather than at the keyboard.
- the machines asked for are all there  
  The list this was built for, by the names they are known by -- which is the maker and the model together, since the catalogue holds them apart.
- no model repeats its maker  
  The model field fills the machine's model box and the manufacturer fills its own, so a model named "Commodore 64" filed a C64 as "Commodore Commodore 64".
- a name its maker is inside of is said once
- a model inherits its family sockets
- a model can replace one of them  
  The +2A has Amstrad's gate array where the family has a Ferranti ULA.
- a model can say it has no such socket  
  A VIC-20 is a Commodore 8-bit but has no SID, and its sound is the VIC's.
- sockets are asked in the order a board is read in  
  A model's own additions follow the family's, rather than jumping the queue: a Spectrum +3 is asked for its CPU and ULA before its floppy controller.
- the machines a person asked for are all there  
  The second round: the 8- and 16-bit machines of Europe, America and Japan, by the names they are known by.
- the picker is in an order a person can guess  
  Seventy-odd makers and three hundred machines is only usable if you can guess where to look, so both lists are alphabetical -- worked out on load, so neither depends on the file staying tidy.
- a number in a name sorts as a number  
  Alphabetical by characters would file the Amiga 1000 before the 500 and the 1040ST before the 520ST, which is not what anyone means by it.
- the catalogue for the form covers every model
- prefill only offers what is true of every one of them
- a model offers the sizes it was sold with and no others

**Rendering**

- a machine reads as the machine it is
- the model is the subject rather than an attribute  
  It comes first and without a key, the way parse_specs keeps a keyless segment -- so a label can name it and nothing has to strip a prefix.
- what is not known is not said
- chips are said in board order whatever order they arrive in
- a chip from a socket the catalogue dropped still says what it is  
  What was seen on the board is not wrong for having gone out of the catalogue, so the role slug names itself: short ones read as the acronyms they are, longer ones as words.
- a model key the catalogue lost is still named

**Storage**

- a machine with nothing recorded reads blank
- what goes in comes back
- how a chip is held survives the chips being rewritten  
  write() replaces the chip rows wholesale, so a later call that names only the variants must not lose what was said about their sockets.
- the sockets can be answered on their own
- the cache is written from the rows
- a field not named is left as it was  
  The convention ramdb and drivedb already follow: a caller that knows one thing must not wipe the others.
- a blank chip clears that socket and leaves the others
- filing a machine out of the catalogue forgets all of it
- changing model keeps the chips the new one also has
- changing model drops the chips it has no socket for  
  A machine refiled as a Spectrum has no SID, and a record saying it has one describes a machine nobody owns.
- reading many takes two queries and gets the same answers
- deleting a machine takes its catalogue rows with it

**Api**

- the catalogue is readable over the wire
- a machine can be created as one
- sockets ride over the wire beside the chips
- a socket for a chip the model has not got is refused
- a machine that is not one says so
- it comes back on get and on the list
- a patch changes only what it names
- a patch that says nothing about it leaves it alone
- null forgets the catalogue
- a model the catalogue does not have is refused
- a socket the model does not have is refused
- a chip is checked against the model already on file
- the rendered line is read only  
  It is written from the rows, so sending one has no effect -- the rule installed_ram and drives already follow.
- a change of machine is in the history

**Form**

- the form offers every model
- a machine can be filed from the form
- the edit form comes back with what was picked
- a socket the model does not have is ignored  
  Fields left over from another model in the same tab cannot put a ULA in a Commodore 64.
- the tickbox says which chips are in a socket  
  A socketed chip can be swapped to test a fault; a soldered one is forty pins and a desoldering station.
- a socket nobody named a chip for is not answered either  
  The box is off for every socket on the form, including the ones left at "not recorded".
- unticking it says soldered rather than forgetting
- a save that could not draw the fields does not erase them  
  Without the marker the script sets, only the model choice is read: a browser that ran no JavaScript submits no variation fields, and a blank field it never drew must not read as an answer of "nothing".
- choosing not a catalogue model files it out
- a form that never asked leaves a machine alone  
  Another form posting to the same handler -- one with no machine picker on it at all -- must not clear what this one recorded.
- the machine page says what it is
- a machine outside the catalogue has no such section
- the label carries the board and the chips  
  On a sealed machine nothing inside has a tag of its own, so the label is the only place the board issue and the ULA can be printed.
- a label for a machine outside the catalogue is unchanged
- a duplicate is the same model and not the same board  
  Another one of these is another one of these; which board issue and which ULA are in it are found by opening it.
- a machine is searchable by the chip in it  
  What the rendered cache is for: the register is searched over every text column, so a part number recorded in a socket is a way back to the machine.

**Where the board and parts are asked for**

- a bare catalogue machine is not asked about either
- its edit form carries them instead
- fitting something brings them back to the page
- a pc keeps them on its page and off its form
- how a chip is held rides on the socket  
  Six sockets each ending in "— soldered to the board" is a paragraph; a tick and a cross are read at a glance.
- a socket nobody has looked in says nothing  
  Neither answer is not the same as soldered.

**A catalogue that grows**

- a chip the catalogue never heard of is offered
- the curated order is kept and discoveries follow  
  What was written down deliberately is what a person reads down first.
- one already offered is not offered twice
- a difference of case or spacing is not a different chip
- what one model teaches is not told about another  
  A ULA found in a Spectrum says nothing about a Commodore 64.
- a socket the catalogue dropped is not brought back
- the other variations grow the same way
- what machines say is read back by model
- a machine outside the catalogue teaches nothing
- a chip typed once is offered on the next machine  
  The whole point, end to end: the custom box on one machine puts the chip into the list the next machine's form is built from.
- the custom box is what gets stored
- custom with nothing typed records nothing

**A board is filed like the machine it came out of**

- what goes in comes back
- the rendered line lands on the part  
  parts.variant is the same cache computers.variant is, over the same rows -- which is why refresh() does not have to know which it has been handed.
- a bare board is created from the pickers  
  The point of the whole thing: a shelf spare is filed as "Amiga 500 board, Rev 6A, these chips" from a menu, not as a sentence in the notes.
- the form offers the catalogue to a board and to nothing else
- only a board is filed however the form arrives  
  The pickers are on no other type's form, so this can only be a hand-made post -- and it is refused there too rather than in the markup alone.
- a board is not asked the two questions a case answers  
  The script that draws the variation fields is the machine form's own, told which form it is on, and it draws neither of them for a board.
- the edit form comes back with what was picked
- the part page says which machine it is out of
- an ordinary part has no such section
- the label carries the board and its chips  
  A bare board in a box says nothing about itself; the label is the only place its revision is written where a person can read it.
- retyping it out of being a board forgets the catalogue  
  A record saying this RAM stick is an Amiga 500 board describes nothing anybody owns -- the same rule as filing a machine out of the catalogue.
- a duplicate is the same model and not the same board  
  Another one of these is another one of these; which revision it is and what is in its sockets are read off the board in your hand.
- deleting a board takes its catalogue rows with it  
  There is no foreign key to cascade any more -- an asset id is the whole register's, not one table's -- so the delete path clears them by hand.
- a board teaches the catalogue what a machine would  
  A Rev nobody had written up is the same evidence about Amiga 500 boards wherever it was read off: it is the same board either way, and which object it was found on is exactly what does not matter about it.
- a machine and its board share one pair of tables  
  Which is the whole of what keying them by asset id buys: one row each, in the same two tables, read and written by the same code.
- the line is searchable the way a machine s is

**The boards door on the api**

- a board can be created as one
- a part that is not one says so
- it comes back on get and on the list
- only a motherboard may have one  
  A card or a SIMM filed as a Commodore 64 is a mistake worth hearing about, and one the register would have nowhere to show.
- a board is not asked about a case  
  The two a machine answers are not in the shape at all, so sending one is the same mistake as sending any other field the register has not got.
- a socket the model does not have is refused
- a patch changes only what it names
- null forgets the catalogue
- anything may be asked to forget one it has not got  
  Null asks for nothing to be there, which is a request a SIMM can answer as well as a board can.
- retyping it out of being a board forgets the catalogue
- the rendered line is read only  
  Written from the rows, so sending one has no effect -- the rule installed_ram and drives already follow.

**Detaching the board**

- the board becomes an object holding the board s own answers
- the machine keeps being the machine on the shelf  
  Its id, its model, its case and its market are untouched -- what it has stopped being able to answer is which board is in it, because the board is answering for itself now.
- the rendered lines follow the rows on both  
  Two caches over one pair of tables, so the machine's line loses the board issue in the same write that puts it on the board's.
- the board is linked back into the machine it came out of  
  Detaching is about the object, not about where it is: the board is out of the case and still fitted to that machine.
- both histories name the other  
  One event, written down on both sides of it -- the register's answer to "where did this board come from" and "what happened to that machine".
- the board s history opens with where it came from  
  A detached board was not created out of nothing, and its first line says so rather than saying "created" -- the birth and the separation are one event.
- the maker and the model come across and nothing else does  
  Enough that the board has a name in a list; not so much that the register claims to know the condition of a board nobody has looked at.
- the photograph taken while it is out becomes its portrait  
  The point of the form.
- it goes through without one  
  A separation that really happened is recorded even with no camera to hand: an object with no portrait is a gap to be chased later, not a reason to write down the wrong thing now.
- a machine the catalogue does not name has nothing to move  
  A PC's board is already an object described by its chipset and its slots, and is entered as a part in the ordinary way.
- a machine has one board  
  The scope guard: one object per real separation event.
- the action is offered where the answers it moves are read
- the page says what will move before it moves
- a board lifted out and unlinked can be refitted like any part  
  One way only.
- a detached board is asked the catalogue s questions on its own form  
  It arrives filed, so its edit form comes back with what moved -- and it is the board's form, which does not ask the two a case answers.
- the memory rows stay on the machine  
  Left where they are on purpose, and noted as an open question rather than guessed at: those rows count chips rather than identify them, and they are half of how a machine's installed RAM is rendered.

**Resync**

- a board that has drifted is reported and rewritten  
  A board goes stale for the reason a machine does, and against the same catalogue: renaming a model has to reach both.
- a line that has drifted is reported and rewritten  
  The catalogue's words are not stored, so correcting one leaves every machine filed under it rendering the old wording until it is edited.

**Reading A typed record against the catalogue**

- the same name written the same way is the top match
- a trailing space is not a different manufacturer  
  Two records in the live register carry one -- "IBM " and "Amstrad " -- and a space is not a maker.
- a number is not a near miss  
  The one that made this need a scorer of its own.
- a model that says more than the catalogue does still matches  
  "Olivetti Personal Computer M21" is what is on the badge, in full.
- an aside in the model box does not hide the match  
  "GRiDCASE 2 (Philips PC200)" is somebody recording a second opinion beside the name rather than naming the machine that.
- the same name beats a name it is inside of  
  A machine typed as "BBC Micro Model B" is as wholly inside "BBC Micro Model B+" as it is inside itself, and only one of those is what somebody wrote down.
- a fuller model beats the line it belongs to  
  "Compaq Portable" is a real machine and a real prefix of the one on the record, so both are offered -- but the record carries a number and the model that shares it is the better reading.
- a machine is found under its other name  
  Half the styles in the catalogue are second names: an Olivetti M24 is an AT&T 6300 in America, a Victor 9000 is a Sirius 1 here, a VTech Laser 3000 is a Dick Smith Cat in Australia, and a Tandon PCX has TM 6001A on the plate.
- a style is only read against the whole name  
  The other half of the styles are configurations, not names -- "386SX-20", "two drives", "mono".
- a name beats the same score reached through a style  
  A style is the second answer to what a machine is called, so where a model's own name is as good a match it wins.
- a machine the catalogue does not know gets no answer  
  The point of the floor.
- nothing typed suggests nothing
- every score is a fraction
- where the record and the catalogue disagree is reported  
  Shown so a person can see it, and never acted on.
- a blank field is not a disagreement  
  A record that says nothing about its CPU is not contradicting the catalogue about it.
- an unknown model has nothing to disagree about

**The branded pcs are in the catalogue**

- a machine this collection holds can be filed
- ibms keys are its own machine types  
  Keys are forever, so they are built from the maker's own stable designation rather than from a marketing name that moved: IBM's four-digit machine type is on the plate and was never reused.
- the line is the model and not the era  
  A PC in the catalogue is not a contradiction of what the catalogue is for.

**The list of what is in it**

- it is in step with the catalogue

**The tool that adopts A machine**

- a machine with no model is what it is for
- a machine already filed is left alone  
  Not "proposed again and skipped" -- not shown at all.
- what has gone is not worth cataloguing
- one machine can be asked about on its own
- the report carries the disagreements with it  
  What the person deciding needs in front of them: the proposal, and every way the record already contradicts it.
- a machine the catalogue cannot place reports nothing

**The file the catalogue is written in**

- a good file reads
- a shared list can be named wherever a list is expected
- a misspelled field says what was meant
- a field that is no kind of typo lists the ones there are
- a memory size nothing can read is refused  
  The labels are offered on the memory box and read back with entry.to_kb, so one it cannot read would file the machine with no memory at all.
- two models cannot share a key
- a year that is not a year is refused
- a model with no name is refused
- a shared list that is not there is refused
- one socket cannot be asked twice
- an answer too long for its column is refused at the file  
  Rather than on save, in front of whoever was recording the machine.
- a file that is not yaml at all says so
- a missing file says where it looked
- the file the register ships is the one it loads


## Migrations

*test_migrations.py — 7 behaviours*

- upgrade head on empty database  
  A fresh database migrates cleanly to head.
- serials left null before 0034 are backfilled  
  0034 settles an unrecorded serial on "" for rows that predate it.
- the serial backfill can be downgraded  
  0034's downgrade puts the column back as 0028 left it.
- files already on file stay public across 0035  
  0035 keeps what is already there published, and starts everything after it private.
- the public flag can be downgraded  
  Going back drops the column, which is the state where every file is public again -- honest rather than safe, and the reason the migration says so.
- what the matcher found survives 0039  
  0039 stops a file being matched to an item by name and starts it being attached to one, and runs the old matcher once to write down what it found.
- a file the matcher reached nothing with is left unfiled  
  Unfiled is a state and not a loss: the bytes are untouched and the files page says so.


## Openapi contract

*test_openapi_contract.py — 1 behaviours*

- the published api is the one on file  
  Every route and model the API offers, against the copy in the repository.


## Photo content

*test_photo_content.py — 5 behaviours*

- a png that is not really an image is refused and stores nothing
- a real png is accepted
- a photograph from a phone is accepted
- a phone photograph uploaded to an item is accepted  
  The other door: the photo column on an item that already exists, which is where most photographs are actually added.
- a phone photograph can still be rotated  
  The write path, which re-encodes in the format the file was opened as.


## Photo tuneup

*test_photo_tuneup.py — 18 behaviours*

- a flat photograph gains contrast
- a dark photograph is lifted
- a well exposed photograph keeps its brightness  
  The fix is for the contrast, not the exposure.
- a bright photograph is not dragged down to a middle grey  
  A pale machine on a pale bench: nothing in the frame is dark, and reading that as a fault to be stretched away is what took such a photograph from an average of 192 to 127 and made a clean shot look underexposed.
- the size and mode survive
- it copes with the other modes a stored image can be in  
  Not every photograph in the collection is a plain RGB JPEG: there are greyscale scans and PNGs with an alpha channel.
- a stronger stretch setting gives more contrast not less  
  A guard on the direction of the knob, which was once backwards.
- an already colourful photograph gets less of the colour boost  
  Pushed hard, a strong single colour clips to a flat block and loses its detail -- which shows up as the measured saturation going *down*.
- the fix makes colours more saturated not less  
  The point of the whole last stage.
- tuning a photo changes it and keeps the original
- the history records it
- reverting puts the photograph back exactly
- pressing tuneup twice does not tune it twice  
  Each edit re-encodes the file, so a second press would cost another generation of JPEG for a photograph that has already had the fix.
- a later edit withdraws the offer to revert  
  Reverting after a crop would quietly undo the crop as well, which is not what the button says it does.
- deleting the photograph takes the kept original with it
- the kept original cannot be fetched  
  It lives under a dotted directory precisely so it cannot: it is an unwatermarked copy of a photograph the site only ever serves watermarked.
- a photo belonging to another item is refused
- a part can be tuned too


## Project of the day

*test_project_of_the_day.py — 17 behaviours*


**Whether there is one**

- nothing is suggested when there is nothing in hand
- a project in hand is suggested
- a finished one is not  
  What to do today is not a list of what was done.
- a search puts it away  
  The page is answering a question that was asked, and a suggestion above the answer is an interruption.
- a mistyped tag puts it away too

**Which one**

- a visitor is never offered a private one  
  The same rule the list below it follows.
- the owner can be offered their own private one
- the quiet one comes up more often  
  The weighting, which is the whole of what makes this a nudge rather than a shuffle.
- being stalled counts for something  
  Stalled is the state somebody chose to record -- waiting on a part, the weather or the will -- and those are the ones that never come up again on their own.
- the one worked on today is still in the draw  
  Weighted down, not excluded: what was worked on this morning is still a reasonable answer to what to do this afternoon.

**What it shows**

- it names the things the project is about
- it lists what is left to do
- a ticked job is not something to do
- it shows a photograph of the thing  
  A project has no photographs of its own -- it is a piece of work, and what can be photographed is the hardware it is about.
- it says how long it has been quiet  
  The reason this one was drawn and not another, said plainly.
- a project with nothing written down says so
- one waiting on a part says that instead


## Projects

*test_projects.py — 121 behaviours*


**A register asset**

- the allocator will not reuse a projects id
- items resolves a project
- items still resolves the two asset kinds
- an id that is nothing is still a 404

**Its history**

- a new project says it was created
- a note lands on it
- a photograph alone is an entry  
  The note bar's other half, which a project gets for the same free.
- an edit is recorded as a diff

**What it is about**

- a project can be about nothing
- a computer goes in and shows on both pages
- a part goes in the same way
- the note says why it is there
- adding it twice leaves it in once
- an id that is nothing is refused  
  A project is about things that exist.
- a project is not an item of another project  
  Members are computers and parts.
- taking it out says so on both
- deleting the computer forgets the membership  
  project_asset.asset_id has no foreign key behind it, so nothing in the database will do this.
- deleting a part forgets it too

**Tasks**

- one is added and shown
- a blank one is not a task
- ticking it dates it
- putting it back clears the date  
  A job that is not done has no day it was done on.
- it can be dropped
- another projects task cannot be ticked from here  
  A bare row id would otherwise reach across projects, the way a bare log entry id would reach across machines.

**Orders**

- one is added with what it cost
- it is dated today unless told otherwise
- a blank description is not an order
- marking it in dates it and back again clears it
- nothing becomes a part by arriving  
  An order is a note about a purchase, not a half-made asset.
- it can be cancelled
- another projects order cannot be ticked from here
- the total says how much of it is a total  
  A figure quietly missing the unpriced lines would look exactly as authoritative as one that was not.

**Money**

- what gets typed into a cost box
- nothing and nonsense are both not recorded
- not recorded is not zero  
  The distinction the total depends on: a line with no price is unknown, and counting it as free would make the total smaller than the truth.
- it is written back the way it is read

**The form**

- a project needs a name  
  The only thing it can be found by: a machine falls back to its manufacturer and model and then to its id, and a project has neither.
- what was typed survives the refusal
- an unknown status falls back rather than being stored
- the three dates are independent  
  A project can be finished without ever having been started -- the part turned up and it took an evening.

**The list**

- what is in hand comes before what is over
- it counts what is still coming
- an empty register says so

**The list on A phone**

- a count of nothing is an empty cell not a dash  
  The dash is drawn by the stylesheet.
- a count that exists is written in
- the columns are labelled for the stacked view  
  Stacked, a bare "0/1" under a name says nothing.

**The rest of the site knows**

- the sitemap carries the projects
- a projects lastmod comes from its own history  
  Its history is log_entry keyed by its own register id, so it reads out of the same query the machines do rather than needing one of its own.
- the new project form is kept out of the index

**Deleting**

- it takes its own history with it  
  log_entry is keyed by a plain register id with nothing to cascade from, so the route clears it by hand.
- it takes its tasks and orders
- it leaves the hardware alone  
  Deleting the plan is not disposing of the machine.
- there is no disposal step in front of it  
  Unlike a machine.

**Who sees what**

- a visitor may read the list
- a visitor is sent to the login to edit
- a visitor cannot write
- what it cost is not shown to a visitor  
  The projects are public because what is being built is worth reading about.
- a visitor sees whether it has arrived  
  The rest of the row is as public as the machine it is destined for.

**Being found**

- the suggestion list offers a project
- a suggested project links to its page
- a project is found by something on order  
  The question somebody stood in front of a parcel actually asks.
- a project is found by a job on its list
- a project is found by its status in words  
  'active' is what the column holds; 'in progress' is what a person types.
- the projects page sifts itself
- sifting reaches the orders too
- a search matching nothing says so
- the gallery says when projects match as well  
  A search bar that says 'anything' and quietly means 'the shelf' would be a search bar that lies.
- the gallery stays a gallery  
  The project matched, and did not become a card.
- a project does not leak into a machines search text  
  Both are keyed by a register id, so a history read for the wrong one would put a project's notes in a machine's haystack.

**The figures**

- the projects show up among the facts
- an empty register contributes no project figures  
  A figure is omitted rather than shown as a zero, the rule the whole pool follows.
- no figure says what anything cost  
  /stats is public and the cost column on a project page is not.
- the longest note tile survives it being on a project  
  log_entry is keyed by a register id, so the longest note can perfectly well be on a project.

**The api**

- a project is created and read back
- the status reads back in words as well  
  A caller should not have to hold this module's vocabulary to know that 'active' reads 'in progress'.
- an unknown status is stored as planned
- a project needs a name
- a patch changes only what it names
- a patch cannot take the name away
- a patch is written into the history
- the list can be narrowed to what is open
- the list can be narrowed to one status
- deleting takes the history and leaves the hardware

**The api lists**

- an item goes in and reads back with its kind
- a part reads back under its own kind  
  So a caller can build a link without knowing which table holds it.
- an asset that is nothing is refused
- adding the same one twice is not an error  
  A caller retrying a request wants the state it asked for, not a row about how it got there.
- an item comes out again
- a task is added ticked and dropped
- a blank task is refused
- another projects task is not reachable
- an order carries its cost in pence  
  Pence as an integer, because that is what the column holds and what it holds is exact.
- an order with no price reads back as null not zero
- an order is marked in and back out
- marking it in writes the history
- a blank order is refused
- an order is cancelled
- another projects order is not reachable
- the whole api is private  
  Unlike the pages.

**Its label**

- a project has one
- it comes small by default  
  A machine's is the 6x4 by default because it is read across a room.
- the full one is offered too
- the page offers both
- the code on it is the register address  
  Not /projects/<id>.
- scanning it reaches the project
- a label is not public  
  Printing is an owner's action, and the label carries the summary.
- no such project has no label
- the small one carries the state  
  What you want to know with the parcel in your hand, months later.
- the full one carries the dates it has

**The word up the end**

- each kind has its own word
- the word is on both sizes of every kind  
  Rendered rather than asserted on a string: the word is drawn as glyphs, so what this checks is that a label with one differs from the same label without, at both sizes and for all three kinds.
- a computer no longer says its type twice  
  The bullet went when the word arrived: it was saying the same thing in the most valuable line on the label.
- the word is centred by measurement not by eye  
  The glyphs stand to one side of the baseline, so the offset that centres them changes with the type size.
- the word is black  
  Not grey, which was the first attempt.
- the word keeps a wider margin than the body  
  A line of words can afford to lose a hair off a descender at the edge of the tape.
- the code still scans with the word beside it  
  The strip is taken out of the text column and not out of the QR: a code below the size a phone can see is worth less than a name that wraps.

**A small label stays on the label**

- a monitors specs all fit inside the label  
  RH-MN11's own label, which is what showed this up: the resolution line ran off the end and through the word at the other end on the way.
- the refresh gets a line of its own  
  Joined to the resolution it wrapped mid-figure -- "320x200 (CGA) 50" and then "Hz, 60 Hz" -- which reads as a fault rather than as two facts.
- a drives specs are unchanged  
  The joining that does hold: a floppy is "a 3.5-inch 1.44MB", one thing said and not two.
- a run with nowhere to break is cut and says so  
  A resolution or a part number has no space in it to wrap at.
- every kind of part stays inside


## Rate limit

*test_rate_limit.py — 6 behaviours*

- allows up to the limit then blocks
- the window slides
- keys are independent
- reset clears a key
- login blocks after too many failures
- a good login clears the count


## Reflow

*test_reflow.py — 4 behaviours*

- no list is wider than the phone it is read on  
  The invariant, stated once over every page that has a table on it: more columns than fit means the table has been given one of the two answers.
- a stacked row says what each value is  
  Stacked, a row loses its headings, and a bare date under a filename is a date for no stated reason.
- the box you type into asks for a width rather than demanding one  
  A `min-width` on a control is a floor the cell around it cannot go below, and this box is in the widest table on the site.
- a long filename cannot hold the list open  
  `overflow-wrap: break-word` on a cell breaks a word that has already been given its column, but leaves the column's minimum width at the whole word -- so the longest filename on the page decided how narrow the table could be.


## Restore script

*test_restore_script.py — 7 behaviours*


**It does nothing until the backup is whole**

- every archive is read through before the database is loaded
- it asks before replacing the database

**Its checks cannot pass by accident**

- the query in the table loop cannot read the loop s input  
  `docker compose exec` reads standard input.
- it counts the tables it checked against the dump
- a problem makes it exit non zero  
  So a cron job or a CI step that restores to prove a backup fails loudly.

**It leaves the site working not just loaded**

- it counts against the dump then migrates then checks the pages  
  In that order.
- it checks the pages the home page hid a fault behind


## Running open

*test_running_open.py — 17 behaviours*


**What it says at startup**

- a site with a login says nothing  
  The state nearly every installation is in.
- no credentials and no opt in warns
- the warning says what is wrong and what to set  
  It is read by somebody who has just found their site open, so it has to carry the consequence and both ways out without them going to look.
- opting in is said once and calmly  
  An operator who has opted in has said what they want.
- opting in while a login is configured warns it is doing nothing  
  Silently ignoring a variable somebody deliberately set is the same fault as the one this whole change is about.
- nothing logged carries a credential  
  It names the variables; it must never reach for their values.

**How it is read**

- the opt in reads the usual words
- it is off when unset  
  Unset means not opted in, which is what makes the loud state the default -- a missing .env is far likelier than a deliberate open install.

**The banner on the page**

- the pages carry it when the site is open by accident
- the pages do not when it was meant
- it is on an item page too and not only the gallery  
  Every page, because the pages somebody edits from are the item pages and a warning only on the front door is a warning most visits never see.
- the banner is the one the stylesheet already warns with  
  Reusing .banner rather than inventing a class: it is already the site's warning colour, and the stylesheet's contrast tests already cover it in both themes, so this adds no rule for them to have missed (accessibility-standards).

**The app can still speak**

- the apps logger survives the migrations
- a line the app logs actually reaches a handler  
  The property that matters, asserted directly rather than inferred from the flag above: a logger can be re-enabled and still go nowhere.

**The wiring**

- the app decided the banner from the two flags  
  The global the templates read is what _announce_auth returned, rather than a second reading of the environment that could come to disagree with it.
- the suite itself runs open and says so  
  conftest pops both credentials -- that is how the suite gets to be the owner -- and then sets RHDB_OPEN, because it meant to.
- the decision is written down


## Share cards

*test_share_cards.py — 28 behaviours*


**What A grid page shares as**

- the gallery shares a montage of the photographs on it  
  It shared as the logo, so the front page of a collection of photographs looked like every other link to the site.
- a search shares the photographs of its own results  
  Not the gallery's: the card describes the answer that was shared, which is the whole reason a search is worth previewing.
- a browse slice shares the photographs on it
- the projects list shares its projects photographs  
  A project's own page already previews as the machine it is about; the list of them previewed as the logo.
- a page with nothing photographed still shares the site card  
  The fallback SITE_CARD was added for is untouched: a page with no photographs on it has no montage to make.
- the pages with no photographs on them keep the site card  
  Even with a photographed collection behind them.

**What goes on the montage**

- a card is the 1200 by 630 every preview slot wants
- one photograph fills the whole frame  
  Three corners and the middle.
- two sit side by side with the card between them
- three go as one large and two stacked
- four go as a grid read left to right
- at most four photographs go on one card  
  A fifth stops being a photograph at the width a chat client renders a preview.
- a tile is filled rather than letterboxed  
  A tall photograph in a wide tile is cropped to it, and a wide one in a tall tile likewise.
- the card carries the sites mark once and not per tile  
  Four watermarked tiles would put four marks on one picture, each cropped to wherever its tile's corner fell.
- a placeholder drawing is never tiled onto a card  
  The same rule a project's card already holds to: an outline of a computer reads as a broken image, which is worse than the site's own card.

**The card is made once and kept**

- two searches landing on the same items share one card
- changing a photograph makes the card again  
  The key carries each photograph's modification time, so a crop is a new URL rather than something needing to be invalidated -- the bargain img_url's ?v= stamp already makes, and what lets the card be cached for a year.
- a card is served as immutable for a year
- the card route opens a file by hash and reads nothing else  
  It never searches and never writes, so there is nothing a stranger can ask it to do.
- a card is fetchable without logging in  
  The one that makes the feature exist at all, and it was wrong first time.
- a query on the card route changes nothing
- the cache is capped  
  A query string is an unbounded key space even when the photographs behind it are not, and this route is anonymous.
- cards from an older build are missed rather than served  
  The lesson the watermark cache learned twice: name the directory after what went into it, so a change to how these are made misses the old ones.

**Only public photographs go on A card**

- a private project puts no photograph on the list card
- a visitors card is made of a visitors rows  
  The whole rule, and the one that matters.
- the owners own card may show more and that is not a leak  
  The owner's page names a card built from the owner's rows, so it can carry a photograph of something on a private project.
- the photographs on a card are ones the site already serves  
  Stated as a test because it is the reason the montage needs no gate of its own: it is made of pictures anybody may already fetch one at a time.

**The map and the manual say so**

- the decision is written down


## Specstruct

*test_specstruct.py — 55 behaviours*


**Scalars**

- keys map to columns
- aliases collapse
- unknown key is kept as an attribute
- keyless value is kept verbatim
- free form type keeps everything as attributes

**Numbers**

- memory amounts become kb
- a bare capacity is megabytes
- a bare cache is kilobytes
- speeds become khz and survive fractions
- capacity renders in the unit a person would type
- whole megabytes do not become fractional gigabytes
- a value that is not a number is kept not dropped
- zero is a value not an absence

**Count lists**

- slots parse into counts
- a single item renders without a count
- ports and ram slots are separate lists

**Storage geometry**

- chs splits into three numbers
- a malformed chs is kept as text

**Canonical order**

- keys come out in display order
- formatting is idempotent
- attributes come after the known keys

**The two sorts of drive speed**

- a spindle speed is still rpm
- a rating goes to its own column
- each renders in the unit it was read in
- a speed that is neither is still not lost  
  The same fallback every unparseable quantity has: kept verbatim rather than dropped on the floor.
- a medium says what the discs are
- an optical drive renders in the canonical order
- it reads back as it renders

**A bezel**

- the two keys map to their own columns
- they come last in the canonical order
- either alone survives
- a display records the same two  
  A monitor's front is plastic that was made in a shade and has yellowed since, exactly as a drive's bezel is, so it answers in the same words.
- a type with no bezel keeps the keys verbatim  
  A card has no plastic to describe, so on a type that is not asked the keys stay attributes rather than being quietly adopted.

**Drive capacity from geometry**

- the arithmetic is sectors of 512 bytes
- a geometry alone gives a capacity
- a stated capacity is never overwritten
- a stated capacity the columns cannot read still wins  
  It is the reader's figure either way; it stays verbatim and no number is invented to replace it.
- no geometry derives nothing
- a malformed geometry derives nothing
- only drives are measured this way
- a derived capacity survives being saved again  
  The rendered figure must re-read as the same number, or it would drift every time the part was saved.

**A display**

- the technology and the tube are separate columns
- a trinitron still counts as a crt  
  The whole reason for two columns: asking for every CRT finds this one.
- a screen size is tenths of an inch
- a whole size does not render a fraction  
  A 14" monitor is a 14-inch monitor, not a 14.0-inch one.
- a fractional size survives the round trip
- a refresh rate is kept as written  
  It stopped being one whole number when a screen was allowed to say it does several: 50 Hz for a television-rate mode and 85 for its best VGA one are both true of the same tube, and an integer could hold one of them.
- a refresh range is kept as written
- a dot pitch is micrometres however it is written
- a dot pitch reads back in millimetres  
  Which is how it is written on the box and how anyone would type it.
- a resolution is kept as written  
  A multisync tube does 640x480 through 1280x1024, and picking one of those to store as two numbers would be recording a fact nobody stated.
- a size that is not a number is kept not dropped
- the canonical order runs picture size signal plastic
- it reads back as it renders
- a screen is not measured like a drive  
  Only a display has a screen size, so the key stays an attribute on anything else rather than being read as inches.


## Stylesheet

*test_stylesheet.py — 8 behaviours*

- every control given its own size is listed for touch  
  iOS zooms the page when it focuses a control whose text is under 16px, and does not zoom back out.
- a primary button reads against its own fill  
  The dark theme's accent is a light blue, chosen to carry on a dark page.
- a danger control reads against the page  
  The register's warning colour is a brown picked for a white page; on the dark one it fell to 3.7:1 against the background it sits on.
- the two dark theme blocks agree  
  Dark is declared twice: for the system preference and for the explicit toggle.
- an accent fill states the text colour on it  
  A rule that fills something with the accent and leaves the foreground to be inherited gets whatever the surrounding rule set, which in the lightbox was a fixed white -- unreadable once the dark theme made the accent a pale blue.
- a warning banner can be read  
  A banner carries the words of a disposal, a rejected form or a refused login in the page's own foreground colour.
- every colour words are written in reads against the page  
  The three pairs tested before this were the three that had already been reported broken.
- every surface words are written on holds them  
  A chip, a button, a panel's title band: each is a translucent black or white over the page, and the text on every one of them is the inherited `--fg`.


## Wanting work

*test_wanting_work.py — 119 behaviours*


**Noting something down**

- a job alone makes a project  
  A project need own nothing -- the idea comes before the hardware -- so the asset tag is the optional half of this box, not the required one.
- the item goes on it
- it is named after the item when you do not name it  
  One name for the gesture, whichever box it was typed in -- and the item's own name, not its tag.
- a name you give it wins
- with no item and no name the job names it
- it lands on the project it just made
- a mistyped tag comes back to the box  
  A 404 page would lose what was typed, and a mistyped tag is the ordinary way to get this wrong.
- the projects own history records what it took on
- the items history says what it is wanted for  
  A project made this way is public now, and an item's history names a project exactly while that project is public -- so the line goes in at the moment the project takes the item on.
- a private one leaves it quiet  
  An item page is public and so is its history, and the history is the part of the register nothing rewrites.
- the box is on the page for whoever is logged in
- a visitor is not offered it

**It is private**

- what the quick box makes is public  
  The register is a public catalogue of old machines, and what is wrong with one is a good part of what is interesting about it.
- what the form makes is too
- a visitor does not see it on the list
- its own page answers a visitor with a 404  
  Not a 403 and not the login: somebody who guessed the tag should not be told there is something there to guess at.
- a public project still opens
- a visitors search does not match it
- the same search finds it for whoever is logged in
- the gallery does not count it for a visitor  
  The line above the gallery results says how many projects also matched.
- it is not in the sitemap  
  The one of the five read by machines rather than people, where a tag is an invitation.
- it is not named on the page of the machine it is about  
  An item page is public.
- publishing one shows it everywhere at once  
  Clearing the tick is the act of publishing, and it has to reach all five doors -- otherwise it half-publishes, which is worse than either.

**Publishing and withdrawing**

- publishing writes the line that was held back
- withdrawing takes it back out  
  The one place the register rewrites its own log, and the whole point: a name taken out of publication cannot be left behind in the one public place it was written.
- the api does the same

**The api carries it**

- it reads and writes like any other column  
  The API is behind the login entire, so there is nothing to hide from it; what `private` governs is what the public pages show.
- the api lists private ones

**The migration did not announce them**

- no public history names a private project
- a private projects tag is not on the item page  
  The tag alone is a disclosure: it says there is something there, and it is the one thing needed to try the door.

**The box on an items own page**

- a line is a job here too
- the jobs can go on a project already going  
  The question this page is the right one to ask: you are looking at the board, and whether it is spoken for is a fact about the board.
- the picker offers the projects in hand
- a visitor is not asked  
  The panel is a form, and the picker would name every open project -- including the private ones -- on a public page.

**Noting work while checking in**

- a machine arrives with its faults written down
- the project is named after the item  
  The form has no name box: what is being described is the work, and the only thing known about it at that moment is which item it is for.
- a thing with no name yet falls back to its tag  
  A machine entered with nothing filled in but a fault has no name to be called after.
- two of the same machine are told apart by their own tags  
  Two projects can come out with the same name, where the collection holds two of the same model.
- it is public  
  The same rule the quick box follows, and the register is a public catalogue: what a machine needs doing is a fact about it worth reading, and the tick on the project's own form is there for the one that is not.
- it starts planned  
  Nothing has been done to it yet -- it has only just come through the door -- and calling that 'in progress' would make the in-hand list a lie.
- a line is a job  
  What somebody types while looking at a machine is a list, because faults arrive as a list.
- an empty box makes nothing  
  Most machines are checked in with nothing wrong with them, and a project per arrival would make the projects page useless.
- a part is checked in the same way
- the machine is saved either way  
  The note is a second thing the form does, not a condition of the first.

**Checking in onto A project already going**

- the item joins the project that was named
- no second project is made
- the jobs go on that project
- a project can be named with no job at all  
  "This is for that" is a complete thought.
- a public project says so on the item  
  Membership writes the item's side of the history exactly as adding it from the project's own page does -- and only for a project anybody may read, which is the invariant _member_log keeps.
- a private project stays quiet
- a tag that names no project still keeps the note  
  The picker cannot produce this; a hand-made post can.
- the form offers the projects in hand  
  A closed project is not something a machine arriving today is joining, and a picker of every project ever finished is a picker nobody reads.

**Noting work on an item that exists**

- the edit form notes work too
- saving again does not write it twice  
  The box is write-only: it is never filled in with what is already on the project, so an ordinary save leaves the jobs alone.
- a part edit notes work too

**Noting work through the api**

- a computer arrives with its faults
- a part does too
- an existing project can be named
- a project that does not exist is refused  
  Unlike the form, which cannot mistype one.
- nothing is created when it is refused  
  The refusal comes before the machine is written, so a typo'd project tag does not leave a half-entered computer behind.
- the item reads back with its project  
  What the note did, said in the reply -- otherwise a caller that has just raised a project has no way to reach it but a search.
- the list reads back with it as well

**Renaming the ones already written**

- it says what the thing is
- a name somebody chose is left alone  
  The rule is narrow on purpose: only the exact old form, built from the tag of an item the project is actually about.
- a project naming another items tag is left alone  
  Named after one thing and about another is not a project this migration knows anything about.
- a thing with no name keeps its tag  
  There is nothing else to call it, and a rename to the same thing is not a rename.
- running it twice changes nothing the second time
- it goes back  
  A downgrade reads the tag off the membership, because the name no longer holds one to read -- which is the whole of what changed.
- an empty database is left alone  
  A fresh install has none of these, and a migration that assumes rows exist is the bug ADR-0002 is about.

**Dropping the prefix from the ones already written**

- it says what the thing is called and nothing else
- a name somebody chose is left alone  
  The same narrow rule 0033 used: only the exact generated form for the item the project is actually about.
- a thing with no name comes out as its tag  
  display_name falls back to the tag, so the prefixed form for a nameless item held its tag -- and what it should say now is that tag alone.
- a project about two things is left alone  
  A project with two items on it was never named this way.
- running it twice changes nothing the second time
- it goes back
- an empty database is left alone  
  ADR-0002: a migration that assumes rows exist is the fresh-install bug.

**One project to A thing**

- the database refuses a second one  
  The rule is a unique constraint and not only a habit in the code, so a path nobody thought of cannot quietly put a thing in two places.
- putting it on another project moves it  
  Picking a project for a thing already on one can only mean moving it.
- its jobs move with it  
  A job naming a thing that is not on its own project would show on the item's page under work it has no part in.
- a second note lands on the project it already has  
  The box on an item's page asks for no project, and the thing already answers the question: a second project about the same thing is the one answer that cannot be right.
- a note on a thing with no project raises one
- a job typed on an item names that item  
  Which is what lets the item's own page list it.
- a job with no item names none

**A job may name A thing**

- it may name one the project holds
- it may name nothing  
  Most of a project's list is about the project -- 'order the caps', 'find a service manual' -- and a column that insisted would make those lie.
- it may not name something the project is not about  
  That row would surface on the item's page under work it has no part in, which is worse than no link at all.
- an item lists its own jobs and not the projects others

**When the thing goes away**

- its jobs are kept but lose the name  
  'Recap the PSU' was work somebody planned and may have done, and it belongs to the project's record of itself.

**Keeping the earliest membership**

- a thing on one project is left alone
- the earliest is kept and the rest dropped
- things do not interfere with each other
- nothing at all is nothing to do

**A private projects jobs are not on the item page**

- a visitor sees neither the name nor the jobs
- the owner sees them
- a public project is shown to a visitor  
  The filter is about privacy and not about hiding work in general.

**Saying what an existing job is about**

- the api attaches it
- it keeps the tick and the day  
  Which is the whole reason this is not delete-and-retype.
- null detaches it
- leaving it out changes nothing  
  exclude_unset: a PATCH that only rewords must not quietly detach.
- it may not name something the project is not about
- the form on the project page does it too
- the form can detach it as well
- the add form can name one on the way in

**The projects own jobs show on its things**

- they show beneath the things own
- they are marked as the projects and not the things  
  Run together they would attribute to a machine something nobody said about it.
- a job naming another thing does not show  
  Inheriting the project's own jobs is not inheriting everybody's.
- they show on every thing the project is about
- a private projects are not inherited by a visitor  
  project_for withholds the project, so there is none to take jobs from.

**Ticking A job off from the item page**

- the things own job ticks off
- it comes back to the item page  
  Not to the project's.
- the projects own job ticks off from here too  
  A job you can read and not tick is one you have to go elsewhere to finish, which is the trip this panel exists to save.
- the item page offers a tick for both kinds
- without a next it still goes to the project  
  The project's own page posts no next, and must keep working.
- it will not be sent off the site  
  _safe_next: the field is on a page, so it is a field somebody can edit.
- a visitor gets no tick

**What A projects shared link shows**

- with no items it falls back to the site card
- an item with no photograph does not supply one  
  detect_images hands back a placeholder for a thing never photographed, and a generic outline of a computer reads as a broken image in a share preview -- worse than the site's own card.
- an items photograph becomes the card
- a placeholder is skipped for a real photograph behind it  
  The first thing with a real photo, not the first thing.
