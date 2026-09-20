/* Where a small label goes when the print button is pressed.
 *
 * The button is a link to a PDF in the markup, and if none of this runs that is
 * exactly what it stays -- a browser with no JavaScript gets the file it always
 * got. What follows is this deciding to do something else instead: put the label
 * on a print agent's queue, or send it to a printer over Bluetooth.
 *
 * The choice is the device's, kept in localStorage and never sent anywhere. The
 * site's own default comes down in the data island; the device's answer overrules
 * it, because which printer is within reach is a fact about the thing you are
 * holding (ADR-0023).
 */
(function () {
  "use strict";

  var KEY = "rhdb.labelDestination";
  var node = document.getElementById("label-data");
  if (!node) return;

  var data;
  try {
    data = JSON.parse(node.textContent);
  } catch (e) {
    return;
  }

  /* localStorage throws in a private window and in a browser told to keep no site
     data, and the register has to work in both -- so every read and write of it is
     wrapped, and the answer when it fails is the site's default rather than an
     error. */
  function remembered() {
    try {
      return window.localStorage.getItem(KEY) || "";
    } catch (e) {
      return "";
    }
  }

  function remember(value) {
    try {
      if (value) window.localStorage.setItem(KEY, value);
      else window.localStorage.removeItem(KEY);
    } catch (e) {
      /* Nothing to do about it, and nothing worth saying: the choice simply does
         not outlive the page, which is the browser's decision and not a fault. */
    }
  }

  /* The driver's URL, with the version the register gave us. Falling back to the
     bare path if an older page is still open somewhere: a stale driver is better
     than none. */
  function driver() {
    return data.driver || "/static/niimbot.js";
  }

  function destination() {
    var chosen = remembered();
    var known = data.destinations || [];
    for (var i = 0; i < known.length; i++) {
      if (known[i][0] === chosen) return chosen;
    }
    /* A device remembering a printer that has since been taken out of the settings
       falls back to the site's answer rather than failing at the moment somebody
       presses print. */
    return data.default || "pdf";
  }

  /* --- saying what happened ---------------------------------------------- */

  function sayer(near) {
    var said = document.createElement("p");
    said.className = "hint";
    said.setAttribute("aria-live", "polite");
    near.parentNode.insertBefore(said, near.nextSibling);
    var say = function (text, bad) {
      said.textContent = text;
      said.classList.toggle("warn", !!bad);
    };
    /* A second go at something, offered as a button rather than done automatically:
       the browser only opens its device chooser in answer to a press, so an offer
       nobody presses is the only kind that can be made. */
    say.offer = function (label, go) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn";
      button.textContent = label;
      button.addEventListener("click", function () {
        button.remove();
        go();
      });
      said.appendChild(document.createTextNode(" "));
      said.appendChild(button);
    };
    return say;
  }

  /* --- the destinations --------------------------------------------------- */

  function toQueue(agent, kind, assetId, say) {
    say("sending to " + agent + "…");
    return fetch("/api/print/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent: agent, kind: kind, asset_id: assetId }),
    })
      .then(function (r) {
        if (r.ok) return r.json();
        throw new Error(r.status === 404 ? "no printer called " + agent : "the register said " + r.status);
      })
      .then(function (job) {
        say("queued for " + agent + " (job " + job.id + ")");
      })
      .catch(function (err) {
        say(String(err.message || err), true);
      });
  }

  function toBluetooth(kind, assetId, say, showEverything) {
    if (!navigator.bluetooth) {
      /* The one case worth naming a browser for: no browser on iOS exposes this,
         and somebody standing there with an iPhone needs to be told what to do
         rather than that it is unsupported. */
      say(
        /iPhone|iPad|iPod/.test(navigator.userAgent)
          ? "Safari cannot reach Bluetooth — open this site in Bluefy, or choose a PDF"
          : "this browser has no Bluetooth — try Chrome, or choose a PDF",
        true
      );
      return Promise.resolve();
    }
    var media = data.bluetoothMedia || "niimbot-50x30";
    say("fetching the label…");
    return fetch("/" + kind + "s/" + assetId + "/label.png?media=" + encodeURIComponent(media))
      .then(function (r) {
        if (!r.ok) throw new Error("the register said " + r.status);
        return r.blob();
      })
      .then(function (blob) {
        return import(driver()).then(function (driver) {
          say("connecting…");
          return driver.print(blob, media, say, showEverything);
        });
      })
      .catch(function (err) {
        say(String(err.message || err), true);
        if (err && err.showEverything) {
          /* The narrow chooser found nothing. On iOS that is as likely to be the
             filter as the printer -- see niimbot.js -- so the wide one is offered
             rather than left to be discovered by somebody reading the source. */
          say.offer("show every Bluetooth device", function () {
            toBluetooth(kind, assetId, say, true);
          });
        }
      });
  }

  /* --- the button on an item page ----------------------------------------- */

  var button = document.querySelector("a.lbl-s[data-asset]");
  if (button) {
    var say = sayer(button.parentNode);
    button.addEventListener("click", function (event) {
      var where = destination();
      if (where === "pdf") return; /* the link does what it says it does */
      event.preventDefault();
      var kind = button.getAttribute("data-kind");
      var assetId = button.getAttribute("data-asset");
      if (where === "bluetooth") toBluetooth(kind, assetId, say);
      else if (where.indexOf("agent:") === 0) toQueue(where.slice(6), kind, assetId, say);
    });
    /* So the button says where it is about to send, on hover and to a screen
       reader, rather than promising a PDF it is not going to hand over. */
    var where = destination();
    for (var i = 0; i < (data.destinations || []).length; i++) {
      if (data.destinations[i][0] === where && where !== "pdf") {
        button.title = "Small label → " + data.destinations[i][1];
        button.setAttribute("aria-label", "Small label to " + data.destinations[i][1]);
      }
    }
  }

  /* --- finding out what the browser can see ------------------------------- */

  var test = document.getElementById("bt-test");
  var report = document.getElementById("bt-report");
  if (test && report) {
    test.addEventListener("click", function () {
      report.hidden = false;
      report.textContent = "choose the printer…";
      import(driver())
        .then(function (driver) {
          return driver.probe();
        })
        .then(function (found) {
          report.textContent =
            (found.usable ? "This looks printable.\n\n" : "Nothing on this can be printed to.\n\n") +
            JSON.stringify(found, null, 2);
        })
        .catch(function (err) {
          report.textContent =
            "Nothing came back: " +
            String((err && err.message) || err) +
            "\n\n" +
            "An empty chooser means the printer is not advertising: the NIIMBOT app may\n" +
            "still be holding it (close it, do not just background it), it may be asleep,\n" +
            "or this browser may not have permission to use Bluetooth.";
        });
    });
  }

  var pattern = document.getElementById("bt-pattern");
  if (pattern && report) {
    pattern.addEventListener("click", function () {
      report.hidden = false;
      report.textContent = "choose the printer…";
      var say = function (text) {
        report.textContent = text;
      };
      /* The stock decides the shape, so the register is asked for it rather than
         the numbers being written here a second time. */
      var media = data.bluetoothMedia || "niimbot-50x30";
      fetch("/api/label-media/" + encodeURIComponent(media))
        .then(function (r) {
          if (!r.ok) throw new Error("the register does not know " + media);
          return r.json();
        })
        .then(function (stock) {
          return import(driver()).then(function (mod) {
            return mod.tracePattern(stock.dots, stock.rows, say);
          });
        })
        .then(function (trace) {
          report.textContent =
            "What should come out, if everything is right:\n" +
            "  - a solid square in the TOP LEFT\n" +
            "  - a thin line down the LEFT edge\n" +
            "  - a thick bar along the TOP edge\n" +
            "  - five evenly spaced rungs down the RIGHT edge\n\n" +
            "And everything that was said on the wire:\n\n" +
            (trace || []).join("\n");
        })
        .catch(function (err) {
          report.textContent = "Nothing came back: " + String((err && err.message) || err);
        });
    });
  }

  /* --- the menu on the settings page -------------------------------------- */

  var menu = document.getElementById("device_destination");
  if (menu) {
    (data.destinations || []).forEach(function (pair) {
      var option = document.createElement("option");
      option.value = pair[0];
      option.textContent = pair[1];
      menu.appendChild(option);
    });
    menu.value = remembered();
    menu.addEventListener("change", function () {
      remember(menu.value);
    });
    var box = document.getElementById("device-box");
    if (box) box.hidden = false;
  }
})();
