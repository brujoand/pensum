/* A number line a pupil answers on, by putting a marker on a tick.
 *
 * Written by hand and vendored like everything else on this site: no bundler,
 * no dependency, no third-party origin.
 *
 * Two things this deliberately does not do.
 *
 * It does not draw the line. The server already did, from the same constants
 * that decide where the ticks fall, and this script is handed the few numbers
 * it needs as data attributes. A second copy of that geometry in here would
 * drift the first time one of them moved.
 *
 * It does not let the marker rest between two ticks. That is the whole reason
 * the interaction is safe to score: dragging is a motor skill, sharpest in the
 * children this question is aimed at, and a marker that can land three pixels
 * short would mark a child wrong for their finger rather than their arithmetic.
 * Snapping turns "how precisely did you drag" back into "which number did you
 * mean". The server grades by tick index for the same reason and will not
 * accept a value that sits between two.
 *
 * The typing box next to the line is not a fallback that appears when something
 * fails. It is always there, it writes the same field, and the two stay in
 * step. A pupil who cannot place a pointer accurately gets a road to the same
 * answer without having to find it.
 */
(function () {
  "use strict";

  /* Marked on the element rather than kept in a list: htmx swaps a question in
   * and out, and a list would hold the old ones forever. */
  var READY = "data-number-line-ready";

  function parse(element, name) {
    return parseFloat(element.getAttribute(name));
  }

  /* --- the arithmetic ----------------------------------------------------
   *
   * Out here rather than inside `setup` so a test can reach it without a
   * browser, and so the four numbers it works from are visible as arguments:
   * every one of them came from the server, and none is a constant this file
   * decided on its own. `tests/js/number_line_snap.test.js` runs these against
   * the values `snap_to_tick` produces in Python. */

  function clampTick(index, lastTick) {
    return Math.max(0, Math.min(index, lastTick));
  }

  /* Which tick a point along the line is nearest. The inverse of the server's
   * `line_x`, and the reason a drag cannot land between two. */
  function tickAt(x, left, right, lastTick) {
    return clampTick(Math.round(((x - left) / (right - left)) * lastTick), lastTick);
  }

  /* Rebuilt from the tick index rather than accumulated, so repeated arrow
   * presses cannot drift the way `value += step` does in binary. The rounding
   * matches the 1e-6 the server grades with. */
  function valueAt(index, start, step) {
    return Math.round((start + index * step) * 1e6) / 1e6;
  }

  /* Which tick a typed number is, or -1 if it is not on one. A pupil halfway
   * through typing "35" has written "3", and moving the marker to the nearest
   * tick under it would answer the question for them. */
  function tickOf(value, start, step, lastTick) {
    var scaled = (value - start) / step;
    if (Math.abs(scaled - Math.round(scaled)) > 1e-6) {
      return -1;
    }
    var index = Math.round(scaled);
    return index < 0 || index > lastTick ? -1 : index;
  }

  /* Decimals are written with a comma in Norwegian, and the server reads
   * either. The tick values arrive as plain numbers, so the only place a comma
   * is produced is here, on the way back out. */
  function show(value) {
    return Number.isInteger(value) ? String(value) : String(value).replace(".", ",");
  }

  function setup(root) {
    if (root.hasAttribute(READY)) {
      return;
    }
    root.setAttribute(READY, "");

    var svg = root.querySelector(".number-line-track");
    var marker = root.querySelector(".number-line-marker");
    var field = root.querySelector("input[name='response']");
    if (!svg || !marker || !field) {
      return;
    }

    var left = parse(root, "data-left");
    var right = parse(root, "data-right");
    var start = parse(root, "data-start");
    var end = parse(root, "data-end");
    var step = parse(root, "data-step");
    var labelUnset = root.getAttribute("data-label-unset") || "";
    var labelAt = root.getAttribute("data-label-at") || "{value}";
    var lastTick = Math.round((end - start) / step);

    /* The page is the one operating the line now, so it takes the slider role
     * the template left off. Done here rather than in the markup because a
     * focus stop that cannot be operated is worse than no focus stop, and
     * without this script there is nothing to operate. */
    svg.setAttribute("role", "slider");
    svg.setAttribute("tabindex", "0");
    svg.setAttribute("aria-valuenow", String(start));
    svg.setAttribute("aria-valuetext", labelUnset);

    var placed = false;
    var index = 0;

    function place(next, fromField) {
      index = clampTick(next, lastTick);
      placed = true;
      var value = valueAt(index, start, step);

      marker.setAttribute("cx", (left + ((right - left) * index) / lastTick).toFixed(2));
      marker.removeAttribute("hidden");
      svg.setAttribute("aria-valuenow", String(value));
      svg.setAttribute("aria-valuetext", labelAt.replace("{value}", show(value)));

      /* Typing is what moved the marker, so writing the box again would fight
       * the caret mid-number. */
      if (!fromField) {
        field.value = show(value);
      }
    }

    /* A pointer arrives in screen pixels and the line is drawn in view units.
     * Going through the SVG's own coordinate system means this holds at any
     * rendered width and needs no assumption about page layout or zoom. */
    function tickUnder(event) {
      var box = svg.getBoundingClientRect();
      if (!box.width) {
        return null;
      }
      var view = svg.viewBox.baseVal;
      var x = view.x + ((event.clientX - box.left) / box.width) * view.width;
      return tickAt(x, left, right, lastTick);
    }

    function pointerPlace(event) {
      var tick = tickUnder(event);
      if (tick === null) {
        return;
      }
      event.preventDefault();
      place(tick, false);
    }

    svg.addEventListener("pointerdown", function (event) {
      svg.setPointerCapture(event.pointerId);
      pointerPlace(event);
    });

    svg.addEventListener("pointermove", function (event) {
      /* buttons is 0 for a hover, so a mouse crossing the line does not move a
       * marker the pupil has not grabbed. */
      if (event.buttons) {
        pointerPlace(event);
      }
    });

    /* Arrow keys are the non-dragging path WCAG 2.5.7 asks for, and snapping is
     * what makes them mean anything: one press is one tick. Home and End are
     * the ends of the line, which is how every other slider behaves. */
    svg.addEventListener("keydown", function (event) {
      var key = event.key;
      var next = null;
      if (key === "ArrowRight" || key === "ArrowUp") {
        next = placed ? index + 1 : 0;
      } else if (key === "ArrowLeft" || key === "ArrowDown") {
        next = placed ? index - 1 : lastTick;
      } else if (key === "Home") {
        next = 0;
      } else if (key === "End") {
        next = lastTick;
      }
      if (next !== null) {
        event.preventDefault();
        place(next, false);
      }
    });

    /* Typed and dragged are the same answer, so the marker follows the box. A
     * number that is not on a tick leaves the marker where it was rather than
     * snapping the pupil's half-typed "3" to the nearest one. */
    field.addEventListener("input", function () {
      var typed = parseFloat(field.value.replace(",", "."));
      if (!isFinite(typed)) {
        return;
      }
      var tick = tickOf(typed, start, step, lastTick);
      if (tick >= 0) {
        place(tick, true);
      }
    });
  }

  function scan(root) {
    var lines = (root || document).querySelectorAll("[data-number-line]");
    for (var i = 0; i < lines.length; i++) {
      setup(lines[i]);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    scan(document);
  });

  /* Every question after the first arrives by htmx, so the swap is where most
   * of these are found. Scanning the whole document rather than the swapped
   * subtree: `querySelectorAll` does not match the root it is called on, and
   * the guard above makes a rescan of the page free. */
  document.body.addEventListener("htmx:afterSwap", function () {
    scan(document);
  });
})();
