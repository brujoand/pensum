/* A sentence frame: word tiles and punctuation tiles into order.
 *
 * Pure rules over a state `{slots: [...], flipped: [...]}`: which tile is in
 * each place, and which tiles have their first letter turned. The moves are
 * `core.js`'s shared `tiles` helpers; what is this primitive's own is the flip.
 * A capital is a tile flip, not a separate rule: a tile tapped twice in the
 * frame turns, the button turns the first word, and a tile put back in the tray
 * turns back. The server (`pensum.items.primitives.sentence_build`) grades the
 * exact tokens against the item's accepted sentences.
 *
 * Every tile is drawn twice in each place, plain (row 0) and turned (row 1), and
 * the state says which one shows.
 */
(function () {
  "use strict";

  function sentenceBuildTurn(text) {
    var first = text.charAt(0);
    var turned = first === first.toUpperCase() ? first.toLowerCase() : first.toUpperCase();
    return turned + text.slice(1);
  }

  function sentenceBuildFlippable(text) {
    var first = text.charAt(0);
    return first.toUpperCase() !== first.toLowerCase();
  }

  function sentenceBuildParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object") {
      return null;
    }
    var slots = window.PensumActivity.tiles.parse(raw.slots, limits.slots, limits.tiles.length);
    var flipped = raw.flipped === undefined ? [] : raw.flipped;
    if (slots === null || !Array.isArray(flipped)) {
      return null;
    }
    for (var i = 0; i < flipped.length; i++) {
      var tile = flipped[i];
      if (slots.indexOf(tile) < 0 || typeof tile !== "number" || tile < 0) return null;
      if (!sentenceBuildFlippable(limits.tiles[tile])) return null;
      if (i > 0 && flipped[i - 1] >= tile) return null;
    }
    return { slots: slots, flipped: flipped.slice() };
  }

  function sentenceBuildToggle(state, tile, limits) {
    if (tile === window.PensumActivity.tiles.EMPTY || tile === undefined) return null;
    if (!sentenceBuildFlippable(limits.tiles[tile])) return null;
    var flipped = state.flipped.filter(function (t) {
      return t !== tile;
    });
    if (flipped.length === state.flipped.length) {
      flipped.push(tile);
      flipped.sort(function (a, b) {
        return a - b;
      });
    }
    return { slots: state.slots.slice(), flipped: flipped };
  }

  function sentenceBuildApply(state, action, limits) {
    var tiles = window.PensumActivity.tiles;
    if (action.type === "flip") {
      /* The button turns the first word in the frame, wherever it sits. */
      var first = state.slots.filter(function (t) {
        return t !== tiles.EMPTY;
      })[0];
      return sentenceBuildToggle(state, first, limits);
    }
    if (action.type === "act" && tiles.slotOf(action.zone) >= 0) {
      return sentenceBuildToggle(state, state.slots[tiles.slotOf(action.zone)], limits);
    }
    var slots = tiles.apply(state.slots, action, limits.tiles.length, limits.slots);
    if (slots === null) {
      return null;
    }
    /* A tile back in the tray loses its turn. */
    var flipped = state.flipped.filter(function (t) {
      return slots.indexOf(t) >= 0;
    });
    return { slots: slots, flipped: flipped };
  }

  function sentenceBuildShown(state, piece) {
    if (!window.PensumActivity.tiles.shown(state.slots, piece)) return false;
    if (piece.zone === "tray") return true;
    return (piece.row === 1) === (state.flipped.indexOf(piece.index) >= 0);
  }

  function sentenceBuildWords(state, limits) {
    var words = [];
    for (var i = 0; i < state.slots.length; i++) {
      var tile = state.slots[i];
      if (tile === window.PensumActivity.tiles.EMPTY) continue;
      var text = limits.tiles[tile];
      words.push(state.flipped.indexOf(tile) >= 0 ? sentenceBuildTurn(text) : text);
    }
    return words;
  }

  /* "Hvor bor du?": a mark goes straight after the word before it. */
  function sentenceBuildText(words, marks) {
    var out = "";
    for (var i = 0; i < words.length; i++) {
      if (out && marks.indexOf(words[i]) < 0) out += " ";
      out += words[i];
    }
    return out;
  }

  function sentenceBuildDescribe(state, say, limits) {
    var words = sentenceBuildWords(state, limits);
    if (!words.length) {
      return say.empty;
    }
    return window.PensumActivity.fill(say.made, {
      sentence: sentenceBuildText(words, limits.marks),
    });
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("sentence_build", {
      parse: sentenceBuildParse,
      apply: sentenceBuildApply,
      shown: sentenceBuildShown,
      describe: sentenceBuildDescribe,
    });
  }
})();
