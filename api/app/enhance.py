"""One-touch tuneup: the automatic levels-and-colour fix a phone does.

Global adjustments only -- a white point per channel, black and white points, and
a midtone gamma, then more saturation and a little more contrast. The local,
region-aware work a phone also does (shadow and highlight recovery, subject
detection) would need numpy or OpenCV; for a photograph of an object on a bench
under one light, the global part is nearly all of the improvement, and it keeps
Pillow, which is here already, as the only dependency.

Conservative about the exposure and the colour cast, and not about the colour
itself -- they are separate questions, and damping them together is what made the
first version of this come out muted. These are catalogue photographs: what is in
front of the camera is usually beige, grey or black plastic filling most of the
frame, which is exactly the case where an eager automatic fix decides the subject
is a fault and corrects it away. But a green board, a yellow warning label and the
red buttons on a console are what the photograph is *of*, and those should carry.
"""

from PIL import Image, ImageEnhance, ImageStat

# How much of each channel's top end to write off before believing it. A specular
# highlight off a bare chip, a blown window behind the bench, or one hot pixel is
# not the white point of the photograph, and taking the very brightest value would
# let any of them set it.
_WHITE_CUT = 0.005

# How far towards a common white point each channel is actually moved. A room lit
# by one warm bulb is *meant* to look warm, and this collection's machines are
# often genuinely yellowed by sunlight -- that yellowing is a fact about the item
# worth recording, not a fault in the photograph. Half-correcting takes the cast
# off a badly-lit frame while leaving a real colour where it is.
_BALANCE = 0.6

# Where the ends of the picture are taken from, as a share of the pixels written
# off at each. More at the bottom than the top: noise in the shadows is dark
# speckle spread over many pixels, while a clipped highlight is usually real.
_BLACK_CUT, _BLACK_TOP = 0.004, 0.001

# How much of a full black-and-white-point stretch to apply, blended against doing
# nothing: 0 leaves the picture alone, 1 maps its ends onto 0 and 255. Short of the
# whole way because the ends were measured with a cut taken off each (_BLACK_CUT),
# so a full stretch clips whatever sits beyond them. See _levels for why this is
# expressed as a blend rather than by moving the ends part of the way, which is the
# natural-looking form and is inverted.
_STRETCH = 0.85

# The band of average brightness a photograph is allowed to end up in. A frame
# already inside it keeps the brightness it had; one outside is brought to the
# near edge and no further. See _key.
_KEY_LO, _KEY_HI = 96.0, 168.0

# How far the midtone gamma may go in either direction. A frame needing more than
# this is not one an automatic fix should be rescuing on its own.
_GAMMA_MIN, _GAMMA_MAX = 0.6, 1.7

# The most the range may be multiplied by. Only a frame with almost no range at
# all reaches this -- a photograph of one flat surface, where the honest scale is
# sixteen and what would actually be amplified sixteenfold is the sensor noise and
# the JPEG banding. A real photograph is nowhere near it: the ones in this
# collection already span so much of the range that the scale works out at about
# 1.02, which is why the stretch is nearly a no-op on them and the life in the
# picture comes from the colour and the contrast below.
_GAIN_MAX = 4.0

# The last of it: more colour, and a little more bite. The colour is worth having
# -- a green board, a yellow warning label, the red buttons on a console are what
# the photograph is of -- but a flat frame and a vivid one want very different
# amounts of it, and one figure for both is what makes an automatic fix look
# cheap. So the boost is full on a flat frame and eases off as the frame is
# already colourful: pushed hard, a saturated green cutting mat clips to a single
# flat teal and *loses* detail, which measures as saturation going down.
_COLOUR_MAX, _COLOUR_MIN = 1.34, 1.10
_SAT_FLAT, _SAT_VIVID = 40.0, 95.0
_CONTRAST = 1.12


def _mean(im: Image.Image) -> float:
    return ImageStat.Stat(im.convert("L")).mean[0]


def _white_points(im: Image.Image) -> list[int]:
    """The value each channel's highlights reach, ignoring the top _WHITE_CUT."""
    hist = im.histogram()
    tops = []
    for channel in range(3):
        counts = hist[channel * 256 : (channel + 1) * 256]
        cut, seen, top = sum(counts) * _WHITE_CUT, 0, 255
        for value in range(255, -1, -1):
            seen += counts[value]
            if seen >= cut:
                top = value
                break
        tops.append(max(top, 1))  # never zero: it divides
    return tops


def _balanced(im: Image.Image) -> Image.Image:
    """Neutralise a colour cast by bringing each channel's highlights together.

    A white-patch balance: whatever the brightest thing in the frame is, the three
    channels should agree about how bright it is, and a channel that falls short
    is the cast. Only the channels below the leading one are lifted, so nothing
    clips that was not clipping already.
    """
    tops = _white_points(im)
    target = max(tops)
    lut: list[int] = []
    for top in tops:
        gain = 1 + (target / top - 1) * _BALANCE
        lut += [min(255, round(value * gain)) for value in range(256)]
    return im.point(lut)


def _ends(hist: list[int], total: int) -> tuple[int, int]:
    """The values the picture actually reaches, ignoring a share at each end."""
    low, seen = 0, 0
    for value in range(256):
        seen += hist[value]
        if seen >= total * _BLACK_CUT:
            low = value
            break
    high, seen = 255, 0
    for value in range(255, -1, -1):
        seen += hist[value]
        if seen >= total * _BLACK_TOP:
            high = value
            break
    return low, high


def _levels(im: Image.Image) -> Image.Image:
    """Pull the black and white points out to the ends of the range.

    Worked out on the luminance and then applied to all three channels rather than
    per channel: a per-channel stretch would undo the damping in _balanced and put
    the cast back, because the channel with the least range is the one that would
    be stretched the most.

    This step is free to darken a photograph, because _keyed puts the brightness
    back afterwards. It is the contrast that is wanted from it.
    """
    grey = im.convert("L")
    hist = grey.histogram()
    total = sum(hist) or 1
    low, high = _ends(hist, total)
    if high - low < 16:  # no range to speak of; the gain would be absurd
        return im
    scale = min(255 / (high - low), _GAIN_MAX)
    # Blended against doing nothing, rather than by moving the ends part of the
    # way. Moving the ends is the tempting way to write this and it is inverted:
    # pushing `high` towards 255 *widens* the range being mapped onto 0..255 and
    # so stretches less, which made a larger _STRETCH mean a weaker fix.
    curve = []
    for value in range(256):
        full = (value - low) * scale
        curve.append(min(255, max(0, round(value + (full - value) * _STRETCH))))
    return im.point(curve * 3)


def _curve(gamma: float) -> list[int]:
    return [min(255, round(255 * (value / 255) ** (1 / gamma))) for value in range(256)]


def _keyed(im: Image.Image, aim: float) -> Image.Image:
    """Gamma until the average brightness is `aim`.

    Searched for rather than solved for. The obvious closed form -- the gamma that
    maps the current average onto the wanted one -- is wrong, because a curve does
    not carry an average through it: bending every pixel and then averaging is not
    the same as bending the average, and across a wide spread the difference is
    large. It took a frame asked for 168 to 127. Twenty bisections over the
    histogram cost nothing and land where they were aimed.
    """
    grey = im.convert("L")
    hist = grey.histogram()
    total = sum(hist) or 1
    if not 4 < _mean(grey) < 250:
        return im  # an unlit room or a blown white; a gamma means nothing here
    lo, hi = _GAMMA_MIN, _GAMMA_MAX
    for _ in range(20):  # higher gamma is brighter, so bisect in that direction
        mid = (lo + hi) / 2
        curve = _curve(mid)
        got = sum(n * curve[v] for v, n in enumerate(hist)) / total
        lo, hi = (mid, hi) if got < aim else (lo, mid)
    return im.point(_curve((lo + hi) / 2) * 3)


def _key(mean: float) -> float:
    """The brightness a photograph should end up at: the one it already has.

    This is the guard against the high-key frame -- a pale machine on a pale bench,
    lit well, whose darkest pixel is a mid grey because there is genuinely nothing
    dark in the picture. Stretching that to a full range is right for the contrast
    and wrong for the exposure, and aiming afterwards at a fixed middle grey is
    worse still: it lands a clean, bright photograph at the same brightness as a
    dim one and calls both corrected. So the target is what the photographer got,
    and the band only catches a frame that was actually badly exposed.
    """
    return min(_KEY_HI, max(_KEY_LO, mean))


def _colour_boost(im: Image.Image) -> float:
    """How much more colour this particular frame can take. See _COLOUR_MAX."""
    saturation = ImageStat.Stat(im.convert("HSV").getchannel("S")).mean[0]
    spread = (saturation - _SAT_FLAT) / (_SAT_VIVID - _SAT_FLAT)
    eased = min(1.0, max(0.0, spread))
    return _COLOUR_MAX - (_COLOUR_MAX - _COLOUR_MIN) * eased


def tuneup(im: Image.Image) -> Image.Image:
    """The whole fix, on an already upright image. Returns a new RGB image."""
    im = im.convert("RGB")
    im = _balanced(im)
    aim = _key(_mean(im))
    im = _keyed(_levels(im), aim)
    im = ImageEnhance.Color(im).enhance(_colour_boost(im))
    return ImageEnhance.Contrast(im).enhance(_CONTRAST)
