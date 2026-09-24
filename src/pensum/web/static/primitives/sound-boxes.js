/* Sound boxes: a counter in a box for each sound heard, then the letters.
 *
 * The rules as pure functions over a state `{counters: n, slots: [...]}`;
 * `core.js` does the page, and its `tiles` helpers the letters. The server
 * (`pensum.items.primitives.sound_boxes`) grades the same state and refuses
 * one these rules could not have produced: at most `capacity` counters, and a
 * letter only in a box that has a counter.
 *
 * Zones: `s0`, `s1` ... are the boxes, `counters` the counters in them,
 * `supply` the spare counters and `tray` the letter tiles. The word is said by
 * the browser's own voice; nothing is recorded.
 */
(function () {
  "use strict";

  function soundBoxesParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object") {
      return null;
    }
    var api = window.PensumActivity;
    var counters = api.count(raw.counters, limits.capacity);
    var slots = api.tiles.parse(raw.slots, limits.capacity, limits.tiles.length);
    if (counters === null || slots === null) {
      return null;
    }
    for (var i = counters; i < slots.length; i++) {
      if (slots[i] !== api.tiles.EMPTY) return null;
    }
    return { counters: counters, slots: slots };
  }

  function soundBoxesApply(state, action, limits) {
    var tiles = window.PensumActivity.tiles;
    var adds =
      (action.type === "move" && action.from === "supply" && action.to !== "supply") ||
      (action.type === "add" && tiles.slotOf(action.zone) >= 0) ||
      (action.type === "act" && action.zone === "supply");
    if (adds) {
      if (state.counters >= limits.capacity) return null;
      return { counters: state.counters + 1, slots: state.slots.slice() };
    }
    if (action.type === "move" && action.from === "counters") {
      /* The last counter goes, and a letter on it goes back to the tray. */
      if (action.to !== "supply" || state.counters === 0) return null;
      var slots = state.slots.slice();
      slots[state.counters - 1] = tiles.EMPTY;
      return { counters: state.counters - 1, slots: slots };
    }
    if (!limits.letters) {
      return null;
    }
    var next = tiles.apply(state.slots, action, limits.tiles.length, state.counters);
    return next === null ? null : { counters: state.counters, slots: next };
  }

  function soundBoxesShown(state, piece) {
    if (piece.zone === "counters") {
      return piece.index < state.counters;
    }
    return window.PensumActivity.tiles.shown(state.slots, piece);
  }

  /* "3 lyder", and with letters "3 lyder: s-o-_". */
  function soundBoxesDescribe(state, say, limits) {
    var text = window.PensumActivity.plural(say, "made", state.counters);
    if (limits.letters && state.counters) {
      var letters = state.slots.slice(0, state.counters).map(function (tile) {
        return tile === window.PensumActivity.tiles.EMPTY ? "_" : limits.tiles[tile];
      });
      text += ": " + letters.join("-");
    }
    return text;
  }

  function soundBoxesBind(root, api) {
    var say = window.PensumActivity.speech.setup(root, api.limits.language);
    var hear = root.querySelectorAll('[data-speak="word"]');
    for (var i = 0; i < hear.length; i++) {
      hear[i].addEventListener("click", function () {
        say(api.limits.word);
      });
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("sound_boxes", {
      parse: soundBoxesParse,
      apply: soundBoxesApply,
      shown: soundBoxesShown,
      describe: soundBoxesDescribe,
      bind: soundBoxesBind,
    });
  }
})();
