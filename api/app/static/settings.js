/* Moving a detail up or down a label's list, in the page (MANUAL §13, "What's on
 * it").
 *
 * Without this, each up and down is a post of its own to /settings/labels/move and
 * is kept as it is pressed. With it the row moves where it is, its hidden name
 * going with it, and Save keeps the new order with everything else on the page --
 * which is what any other change on a settings page needs, and what somebody who
 * has just ticked three boxes expects of the fourth thing they do.
 */
(function () {
  "use strict";

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
  });
})();
