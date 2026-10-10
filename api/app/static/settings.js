/* The Labels tab, in the page (MANUAL §13).
 *
 * Moving a detail up or down a label's list ("What's on it"). Without this, each up
 * and down is a post of its own to /settings/labels/move and is kept as it is
 * pressed. With it the row moves where it is, its hidden name going with it, and
 * Save keeps the new order with everything else on the page -- which is what any
 * other change on a settings page needs, and what somebody who has just ticked
 * three boxes expects of the fourth thing they do.
 *
 * And each label's picture, drawn again as its settings change ("Seeing it as you
 * set it up"). Without this, it is the label as saved, for the example the label
 * starts on.
 */
(function () {
  "use strict";

  var redraw = function () {};

  function settle(list) {
    var rows = list.children;
    for (var i = 0; i < rows.length; i++) {
      var up = rows[i].querySelector('button[value$=":up"]');
      var down = rows[i].querySelector('button[value$=":down"]');
      if (up) up.disabled = i === 0;
      if (down) down.disabled = i === rows.length - 1;
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest('button[name="move"][form="label-moves"]');
    if (!button) return;
    var row = button.closest("li");
    var list = row && row.parentElement;
    if (!list) return;
    event.preventDefault();
    var up = /:up$/.test(button.value);
    var other = up ? row.previousElementSibling : row.nextElementSibling;
    if (!other) return;
    if (up) list.insertBefore(row, other);
    else list.insertBefore(other, row);
    settle(list);
    /* The press stays where it was, on the row that moved -- unless that took the
       row to the end it was moving towards, where its button is now disabled and
       cannot hold the focus, so the other one in the same row takes it. */
    var stay = button.disabled
      ? row.querySelector(up ? 'button[value$=":down"]' : 'button[value$=":up"]')
      : button;
    if (stay) stay.focus();
    var said = document.getElementById(list.id + "-said");
    var name = row.querySelector("label");
    if (said && name) {
      var at = Array.prototype.indexOf.call(list.children, row) + 1;
      said.textContent = name.textContent.trim() + ", " + at + " of " + list.children.length;
    }
    redraw();
  });

  /* --- each label's picture --------------------------------------------------

     Asked for again with the page's own fields in its address: the server reads
     them the way Save would and keeps none of them, so the picture is what saving
     would print. Only the fields that are drawn -- the label's own, less its name,
     and the size the Bluetooth printer is loaded with -- so a change to one label
     does not ask again for the other's. The words under it and its size come from
     the data island, which is how they change with the picture rather than a
     request behind it. */
  var form = document.getElementById("settings-form");
  var island = document.getElementById("label-preview-data");
  var data = null;
  try {
    data = island ? JSON.parse(island.textContent) : null;
  } catch (e) {
    data = null;
  }
  if (!form || !data) return;
  var pictures = document.querySelectorAll("img[id^='preview_'][data-label]");
  if (!pictures.length) return;

  function field(name) {
    var control = form.elements.namedItem(name);
    return control && typeof control.value === "string" ? control.value : "";
  }

  /* Where the label goes decides the stock it is drawn on, as the server decides it:
     its own Stock for a PDF, the Bluetooth printer's size, an agent's own. */
  function stockOf(key) {
    var own = field("label_" + key + "_stock");
    var goes = field("label_" + key + "_destination");
    var stock = goes === "bluetooth" ? field("label_bluetooth_media") : (data.agents || {})[goes] || own;
    return data.media[stock] ? stock : own;
  }

  function address(key, kind) {
    var query = new URLSearchParams();
    query.append("label", key);
    query.append("kind", kind);
    var own = "label_" + key + "_";
    new FormData(form).forEach(function (value, name) {
      if ((name.indexOf(own) === 0 && name !== own + "name") || name === "label_bluetooth_media") {
        query.append(name, value);
      }
    });
    return "/settings/labels/preview.png?" + query.toString();
  }

  /* The example each menu says, remembered for as long as the tab is open: Save
     comes back to this page, and the example somebody chose should come back with
     it. sessionStorage throws where a browser keeps no site data, and then the menu
     simply starts where the page starts it. */
  function remembered(key) {
    try {
      return window.sessionStorage.getItem("rhdb.labelPreview." + key) || "";
    } catch (e) {
      return "";
    }
  }

  function remember(key, kind) {
    try {
      window.sessionStorage.setItem("rhdb.labelPreview." + key, kind);
    } catch (e) {
      /* Forgotten with the page, which is all that is lost. */
    }
  }

  var asked = {};
  var good = {};

  function draw(img) {
    var key = img.getAttribute("data-label");
    var menu = document.getElementById("preview_" + key + "_kind");
    var kind = menu ? menu.value : "";
    var src = address(key, kind);
    if (src === asked[key]) return;
    asked[key] = src;
    /* The old picture stays until the new one has arrived, so a run of changes is a
       run of pictures rather than a blank; the size and the words change with it. */
    img.onload = function () {
      if (asked[key] !== src) return;
      var stock = data.media[stockOf(key)];
      if (stock) {
        img.width = stock.w;
        img.height = stock.h;
      }
      var caption = document.getElementById("preview_" + key + "_stock");
      if (caption && stock && caption.textContent !== stock.what) caption.textContent = stock.what;
      img.alt = img.getAttribute("data-called") + " for an example " + ((data.kinds || {})[kind] || kind);
      good[key] = src;
    };
    /* A picture that cannot be drawn leaves the last one that could. */
    img.onerror = function () {
      if (asked[key] === src && good[key] && good[key] !== src) {
        asked[key] = good[key];
        img.src = good[key];
      }
    };
    img.src = src;
    /* And what the picture cannot say: the details ticked that the label has no room
       for, asked of the same settings. An answer overtaken by a later change is
       dropped, as a picture is. */
    var room = document.getElementById("preview_" + key + "_room");
    if (room && window.fetch) {
      window
        .fetch(src.replace("/preview.png?", "/preview.json?"), { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (said) {
          if (!said || asked[key] !== src) return;
          room.textContent = said.room || "";
          room.hidden = !said.room;
        })
        .catch(function () {
          /* The line keeps what it said; the picture is still right. */
        });
    }
  }

  var timer = null;
  redraw = function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      Array.prototype.forEach.call(pictures, draw);
    }, 200);
  };

  /* A browser that put back what was in the fields when the page was last open --
     Firefox does, on a reload -- has a picture of the saved label beside settings
     that are not; this is how it is told. */
  function putBack() {
    var controls = form.elements;
    for (var i = 0; i < controls.length; i++) {
      var control = controls[i];
      if (control.type === "checkbox" && control.checked !== control.defaultChecked) return true;
      if (control.tagName === "SELECT") {
        for (var j = 0; j < control.options.length; j++) {
          if (control.options[j].selected !== control.options[j].defaultSelected) return true;
        }
      }
    }
    return false;
  }

  var stale = putBack();
  Array.prototype.forEach.call(pictures, function (img) {
    var key = img.getAttribute("data-label");
    var menu = document.getElementById("preview_" + key + "_kind");
    if (!menu) return;
    /* What the markup's picture is a picture of, so that it is not asked for a
       second time -- unless the fields are not what it was drawn from. */
    good[key] = img.getAttribute("src");
    asked[key] = stale ? "" : address(key, menu.value);
    var kept = remembered(key);
    for (var i = 0; i < menu.options.length; i++) {
      if (menu.options[i].value === kept) menu.value = kept;
    }
    menu.addEventListener("change", function () {
      remember(key, menu.value);
      draw(img);
    });
    var box = document.getElementById("preview_" + key + "_example");
    if (box) box.hidden = false;
    draw(img);
  });

  form.addEventListener("change", redraw);
  form.addEventListener("input", redraw);
})();
