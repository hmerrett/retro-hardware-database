/* Where each of the two labels goes when its print button is pressed.
 *
 * Each button is a link to its label's PDF in the markup, and if none of this runs
 * that is exactly what it stays -- a browser with no JavaScript gets the file it
 * always got. What follows is this deciding to do something else instead: put the
 * label on a print agent's queue, or send it to a printer over Bluetooth.
 *
 * The choice is the device's, one for each label, kept in localStorage and never
 * sent anywhere. The site's own defaults come down in the data island; the device's
 * answer overrules them, because which printer is within reach is a fact about the
 * thing you are holding (ADR-0023, ADR-0037).
 */
(function () {
  "use strict";

  /* The first label keeps the key there was when there was only one, so a choice a
     device made before there were two still means what it meant. */
  var KEYS = { small: "rhdb.labelDestination", full: "rhdb.labelDestination.full" };
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
  function remembered(label) {
    try {
      return window.localStorage.getItem(KEYS[label] || KEYS.small) || "";
    } catch (e) {
      return "";
    }
  }

  function remember(label, value) {
    var key = KEYS[label] || KEYS.small;
    try {
      if (value) window.localStorage.setItem(key, value);
      else window.localStorage.removeItem(key);
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

  function destination(label) {
    var chosen = remembered(label);
    var known = data.destinations || [];
    for (var i = 0; i < known.length; i++) {
      if (known[i][0] === chosen) return chosen;
    }
    /* A device remembering a printer that has since been taken out of the settings
       falls back to the site's answer rather than failing at the moment somebody
       presses print. */
    return (data.defaults || {})[label] || "pdf";
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

  function toQueue(agent, kind, assetId, label, say) {
    say("sending to " + agent + "…");
    return fetch("/api/print/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent: agent, kind: kind, asset_id: assetId, label: label }),
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

  function toBluetooth(kind, assetId, label, say, showEverything) {
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
    var which = label === "full" ? "0" : "1";
    return fetch(
      "/" + kind + "s/" + assetId + "/label.png?media=" + encodeURIComponent(media) + "&small=" + which
    )
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
            toBluetooth(kind, assetId, label, say, true);
          });
        }
      });
  }

  /* --- the buttons on an item page ---------------------------------------- */

  var buttons = document.querySelectorAll("a.lbl[data-asset]");
  var say = null;
  Array.prototype.forEach.call(buttons, function (button) {
    var label = button.getAttribute("data-label") || "small";
    var called = button.textContent.trim();
    /* One line under the row for both, saying what the last press did. */
    say = say || sayer(button.parentNode);
    var speak = say;
    button.addEventListener("click", function (event) {
      var where = destination(label);
      if (where === "pdf") return; /* the link does what it says it does */
      event.preventDefault();
      var kind = button.getAttribute("data-kind");
      var assetId = button.getAttribute("data-asset");
      if (where === "bluetooth") toBluetooth(kind, assetId, label, speak);
      else if (where.indexOf("agent:") === 0) toQueue(where.slice(6), kind, assetId, label, speak);
    });
    /* So the button says where it is about to send, on hover and to a screen
       reader, rather than promising a PDF it is not going to hand over. */
    var where = destination(label);
    for (var i = 0; i < (data.destinations || []).length; i++) {
      if (data.destinations[i][0] === where && where !== "pdf") {
        button.title = called + " → " + data.destinations[i][1];
        button.setAttribute("aria-label", called + " to " + data.destinations[i][1]);
      }
    }
  });

  /* --- the picture over the buttons --------------------------------------- */

  /* The markup's picture is the PDF's, because the markup's button is a link to
     the PDF. Where this browser is going to send the label somewhere else, the
     picture becomes that printer's -- drawn on its stock, in the layout it is
     sent -- from the map the tag carries, so what is on the screen is what comes
     out (MANUAL §13). A destination with no picture keeps the one there is. */
  var picture = document.querySelector("img.lblpic[data-pictures]");
  if (picture) {
    var pictures = {};
    try {
      pictures = JSON.parse(picture.getAttribute("data-pictures")) || {};
    } catch (e) {
      pictures = {};
    }
    var drawn = pictures[destination("small")];
    if (drawn && drawn.src !== picture.getAttribute("src")) {
      picture.width = drawn.w;
      picture.height = drawn.h;
      picture.src = drawn.src;
    }
  }

  /* --- the menu on the settings page -------------------------------------- */

  var menus = document.querySelectorAll("select[id^='device_destination_'][data-label]");
  Array.prototype.forEach.call(menus, function (menu) {
    var label = menu.getAttribute("data-label");
    (data.destinations || []).forEach(function (pair) {
      var option = document.createElement("option");
      option.value = pair[0];
      option.textContent = pair[1];
      menu.appendChild(option);
    });
    menu.value = remembered(label);
    menu.addEventListener("change", function () {
      remember(label, menu.value);
    });
  });
  if (menus.length) {
    var box = document.getElementById("device-box");
    if (box) box.hidden = false;
  }
})();
