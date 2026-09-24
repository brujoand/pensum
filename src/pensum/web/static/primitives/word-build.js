/* A word frame: letters, syllables or morphemes into order.
 *
 * Pure rules over a state `{slots: [...]}`, one tile index per place or -1;
 * the moves themselves are `core.js`'s shared `tiles` helpers, which sound
 * boxes and sentence building use too. The server
 * (`pensum.items.primitives.word_build`) reads the word the frame spells and
 * grades it against the item's accepted forms.
 *
 * Zones: `s0`, `s1` ... are the places, `tray` the tiles not used yet. A tile
 * tapped twice in the tray goes to the next free place; tapped twice in the
 * frame it goes back.
 */
(function () {
  "use strict";

  function wordBuildParse(json, limits) {
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
    return slots === null ? null : { slots: slots };
  }

  function wordBuildApply(state, action, limits) {
    var tiles = window.PensumActivity.tiles;
    if (action.type === "act" && tiles.slotOf(action.zone) >= 0) {
      action = { type: "move", from: action.zone, fromIndex: action.index, to: "tray" };
    }
    var next = tiles.apply(state.slots, action, limits.tiles.length, limits.slots);
    return next === null ? null : { slots: next };
  }

  function wordBuildShown(state, piece) {
    return window.PensumActivity.tiles.shown(state.slots, piece);
  }

  function wordBuildWord(state, limits) {
    return state.slots
      .filter(function (tile) {
        return tile !== window.PensumActivity.tiles.EMPTY;
      })
      .map(function (tile) {
        return limits.tiles[tile];
      })
      .join("");
  }

  function wordBuildDescribe(state, say, limits) {
    var word = wordBuildWord(state, limits);
    return word ? window.PensumActivity.fill(say.made, { word: word }) : say.empty;
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("word_build", {
      parse: wordBuildParse,
      apply: wordBuildApply,
      shown: wordBuildShown,
      describe: wordBuildDescribe,
    });
  }
})();
