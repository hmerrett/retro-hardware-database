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
    return function (text, bad) {
      said.textContent = text;
      said.classList.toggle("warn", !!bad);
    };
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

  function toBluetooth(kind, assetId, say) {
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
        return import("/static/niimbot.js").then(function (driver) {
          say("connecting…");
          return driver.print(blob, media, say);
        });
      })
      .catch(function (err) {
        say(String(err.message || err), true);
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
