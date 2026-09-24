/* Labels on the numbered places of a picture.
 *
 * The rules of the board, as pure functions over a state `{slots: [j, ...]}`:
 * per numbered place, the label on it, or -1. A label is on one place at most.
 * `core.js` does the page; the server (`pensum.items.primitives.label`) grades
 * the same state.
 *
 * Zones: `tray` is where the labels start, `s0`, `s1` ... are the places. A
 * label is moved by a drag or tap-tap onto a place (a label already there goes
 * back to the tray), or back onto the tray to take it off. Each place's menu
 * under the board is the keyboard path.
 */
(function () {
  "use strict";

  function labelParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || !Array.isArray(raw.slots)) {
      return null;
    }
    if (raw.slots.length !== limits.cards) {
      return null;
    }
    var seen = {};
    for (var i = 0; i < raw.slots.length; i++) {
      var j = raw.slots[i];
      if (typeof j !== "number" || j !== Math.floor(j) || j < -1 || j >= limits.cards) {
        return null;
      }
      if (j >= 0 && seen[j]) return null;
      seen[j] = true;
    }
    return { slots: raw.slots.slice() };
  }

  function labelSlot(zone, limits) {
    var slot = /^s(\d+)$/.exec(zone || "");
    return slot && +slot[1] < limits.cards ? +slot[1] : null;
  }

  /* Put label `card` on place `slot` (-1 takes the place's label off). */
  function labelPut(state, slot, card, limits) {
    if (slot === null || slot < 0 || slot >= limits.cards) return null;
    if (typeof card !== "number" || card < -1 || card >= limits.cards) return null;
    if (state.slots[slot] === card) return null;
    var next = state.slots.map(function (j) {
      return card >= 0 && j === card ? -1 : j;
    });
    next[slot] = card;
    return { slots: next };
  }

  function labelApply(state, action, limits) {
    if (action.type === "place") {
      return labelPut(state, action.slot, action.card, limits);
    }
    if (action.type !== "move") return null;
    var card = action.fromIndex;
    var from = labelSlot(action.from, limits);
    if (action.from !== "tray" && from === null) return null;
    if (from !== null && state.slots[from] !== card) return null;
    var to = labelSlot(action.to, limits);
    if (to !== null) return labelPut(state, to, card, limits);
    if (action.to === "tray" && from !== null) return labelPut(state, from, -1, limits);
    return null;
  }

  function labelShown(state, piece, limits) {
    if (piece.zone === "tray") return state.slots.indexOf(piece.index) < 0;
    var slot = labelSlot(piece.zone, limits);
    return slot !== null && state.slots[slot] === piece.index;
  }

  function labelDescribe(state, say) {
    return state.slots
      .map(function (j, k) {
        return k + 1 + ": " + (j >= 0 ? say.labels[j] : say.none);
      })
      .join("; ");
  }

  function labelRender(root, state) {
    var menus = root.querySelectorAll("select[data-slot]");
    for (var i = 0; i < menus.length; i++) {
      var j = state.slots[+menus[i].getAttribute("data-slot")];
      menus[i].value = j >= 0 ? String(j) : "none";
    }
  }

  function labelBind(root, api) {
    var menus = root.querySelectorAll("select[data-slot]");
    for (var i = 0; i < menus.length; i++) {
      menus[i].addEventListener("change", function (event) {
        var menu = event.currentTarget;
        var card = menu.value === "none" ? -1 : +menu.value;
        if (!api.dispatch({ type: "place", slot: +menu.getAttribute("data-slot"), card: card })) {
          labelRender(root, api.state());
        }
      });
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("label", {
      parse: labelParse,
      apply: labelApply,
      shown: labelShown,
      describe: labelDescribe,
      render: labelRender,
      bind: labelBind,
    });
  }
})();
