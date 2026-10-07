/* Arkade confetti: a little of it for a right move, in every game.
 *
 * A game calls `window.arkadeConfetti(element)` and a handful of pieces fly up
 * and outwards from the middle of that element, then fall. The pieces sit in
 * one layer over the page, which catches no clicks.
 *
 * Confetti is decoration, so in calm mode, or where the device asks for less
 * motion, none is made (design rule 9).
 */
(function () {
  "use strict";

  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var PIECES = 10;
  /* How long a piece is on the page: the 200 ms wait and 900 ms flight the
   * stylesheet gives it, and a margin. */
  var LIFE_MS = 1200;

  var layer = null;

  window.arkadeConfetti = function (from) {
    if (still || !from || !from.getBoundingClientRect) return;
    if (!layer) {
      layer = document.createElement("div");
      layer.className = "arkade-confetti";
      layer.setAttribute("aria-hidden", "true");
      document.body.appendChild(layer);
    }
    var box = from.getBoundingClientRect();
    var pieces = [];
    for (var i = 0; i < PIECES; i++) {
      var piece = document.createElement("span");
      piece.className = "arkade-confetti__piece arkade-confetti__piece--" + (i % 4);
      piece.style.setProperty("--x", box.left + box.width / 2 + "px");
      piece.style.setProperty("--y", box.top + box.height / 2 + "px");
      piece.style.setProperty("--dx", Math.round((Math.random() - 0.5) * 140) + "px");
      piece.style.setProperty("--dy", Math.round(-30 - Math.random() * 70) + "px");
      piece.style.setProperty("--turn", Math.round((Math.random() - 0.5) * 720) + "deg");
      layer.appendChild(piece);
      pieces.push(piece);
    }
    window.setTimeout(function () {
      pieces.forEach(function (piece) {
        layer.removeChild(piece);
      });
    }, LIFE_MS);
  };
})();
