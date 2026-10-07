/* Arkade confetti: a burst of it for a right move, in every game.
 *
 * A game calls `window.arkadeConfetti()` and the pieces burst from the middle
 * of the screen, up and outwards across most of it, then fall. The pieces sit
 * in one layer over the page, which catches no clicks.
 *
 * Confetti is decoration, so in calm mode, or where the device asks for less
 * motion, none is made (design rule 9).
 */
(function () {
  "use strict";

  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var PIECES = 48;
  /* How long a piece is on the page: the 150 ms wait and 1400 ms flight the
   * stylesheet gives it, and a margin. */
  var LIFE_MS = 1800;

  var layer = null;

  window.arkadeConfetti = function () {
    if (still) return;
    if (!layer) {
      layer = document.createElement("div");
      layer.className = "arkade-confetti";
      layer.setAttribute("aria-hidden", "true");
      document.body.appendChild(layer);
    }
    /* The burst is as wide as the screen allows, and rises about a third of
     * its height. The stylesheet starts every piece at the layer's middle. */
    var width = window.innerWidth || 360;
    var height = window.innerHeight || 640;
    var pieces = [];
    for (var i = 0; i < PIECES; i++) {
      var piece = document.createElement("span");
      piece.className = "arkade-confetti__piece arkade-confetti__piece--" + (i % 4);
      piece.style.setProperty("--dx", Math.round((Math.random() - 0.5) * width * 0.9) + "px");
      piece.style.setProperty("--dy", Math.round(-(0.08 + Math.random() * 0.34) * height) + "px");
      piece.style.setProperty("--fall", Math.round((0.2 + Math.random() * 0.25) * height) + "px");
      piece.style.setProperty("--turn", Math.round((Math.random() - 0.5) * 1080) + "deg");
      piece.style.setProperty("--size", (0.7 + Math.random() * 0.6).toFixed(2));
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
