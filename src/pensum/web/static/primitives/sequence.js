/* Cards in order along a line, or around a cycle.
 *
 * The rules of the board, as pure functions over a state `{order: [c, ...]}`:
 * which card is at each place, first place first, always every card once.
 * `core.js` does the page; the server (`pensum.items.primitives.sequence`)
 * grades the same state, up to rotation for a cycle.
 *
 * Zones: `p0`, `p1` ... are the places. A card is moved by a drag or tap-tap
 * onto another place (core's `move`: it is taken out and put in there, and the
 * cards between shift up one), or one step at a time with its row's buttons
 * (`up`, `down`), which are the keyboard path.
 */
(function () {
  "use strict";

  function sequenceParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || !Array.isArray(raw.order)) {
      return null;
    }
    if (raw.order.length !== limits.cards) {
      return null;
    }
    var seen = {};
    for (var i = 0; i < raw.order.length; i++) {
      var c = raw.order[i];
      if (typeof c !== "number" || c !== Math.floor(c) || c < 0 || c >= limits.cards || seen[c]) {
        return null;
      }
      seen[c] = true;
    }
    return { order: raw.order.slice() };
  }

  function sequenceAt(zone, limits) {
    var place = /^p(\d+)$/.exec(zone || "");
    return place && +place[1] < limits.cards ? +place[1] : null;
  }

  function sequenceApply(state, action, limits) {
    var order = state.order.slice();
    var from;
    var to;
    if (action.type === "up" || action.type === "down") {
      from = sequenceAt(action.zone, limits);
      if (from === null) return null;
      to = action.type === "up" ? from - 1 : from + 1;
      if (to < 0 || to >= limits.cards) return null;
      var held = order[to];
      order[to] = order[from];
      order[from] = held;
      return { order: order };
    }
    if (action.type !== "move") return null;
    from = sequenceAt(action.from, limits);
    to = sequenceAt(action.to, limits);
    if (from === null || to === null || from === to) return null;
    var card = order.splice(from, 1)[0];
    order.splice(to, 0, card);
    return { order: order };
  }

  function sequenceShown(state, piece, limits) {
    var at = sequenceAt(piece.zone, limits);
    return at !== null && state.order[at] === piece.index;
  }

  function sequenceDescribe(state, say) {
    return state.order
      .map(function (c) {
        return say.cards[c];
      })
      .join(" → ");
  }

  /* The move buttons name the card they move, so a screen reader does not
   * hear "up, up, up" down the list. */
  function sequenceRender(root, state, limits, say) {
    var buttons = root.querySelectorAll("[data-action=up], [data-action=down]");
    for (var i = 0; i < buttons.length; i++) {
      var at = sequenceAt(buttons[i].getAttribute("data-zone"), limits);
      if (at === null) continue;
      var template = buttons[i].getAttribute("data-action") === "up" ? say.up : say.down;
      buttons[i].setAttribute(
        "aria-label",
        window.PensumActivity.fill(template, { card: say.cards[state.order[at]] })
      );
    }
  }

  /* After a step, keep the keyboard on the card that moved rather than on the
   * row it left. */
  function sequenceBind(root, api) {
    root.addEventListener("click", function (event) {
      var button = event.target.closest("[data-action=up], [data-action=down]");
      if (!button) return;
      var action = button.getAttribute("data-action");
      var at = sequenceAt(button.getAttribute("data-zone"), api.limits);
      if (at === null) return;
      var to = action === "up" ? at - 1 : at + 1;
      var next = root.querySelector('[data-action="' + action + '"][data-zone="p' + to + '"]');
      if (next && next.disabled) {
        next = root.querySelector('[data-zone="p' + to + '"]:not([disabled])[data-action]');
      }
      if (next) next.focus();
    });
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("sequence", {
      parse: sequenceParse,
      apply: sequenceApply,
      shown: sequenceShown,
      describe: sequenceDescribe,
      render: sequenceRender,
      bind: sequenceBind,
    });
  }
})();
