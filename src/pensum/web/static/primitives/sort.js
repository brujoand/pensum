/* Cards into bins, or into the three regions of a Venn diagram.
 *
 * The rules of the board, as pure functions over a state `{place: [p, ...]}`,
 * one entry per card in authored order: -1 for not sorted yet, otherwise the
 * bin (or Venn region) it is in. `core.js` does the page; the server
 * (`pensum.items.primitives.sort`) grades the same state.
 *
 * Zones: `tray` is where every card starts, `r0`, `r1` ... are the bins. A
 * card is moved by a drag or tap-tap (core's `move`), or by its own menu under
 * the board (`place`), which is the keyboard path.
 */
(function () {
  "use strict";

  function sortParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || !Array.isArray(raw.place)) {
      return null;
    }
    if (raw.place.length !== limits.cards) {
      return null;
    }
    for (var i = 0; i < raw.place.length; i++) {
      var p = raw.place[i];
      if (typeof p !== "number" || p !== Math.floor(p) || p < -1 || p >= limits.regions) {
        return null;
      }
    }
    return { place: raw.place.slice() };
  }

  /* The region a zone stands for: -1 for the tray, null for no such zone. */
  function sortRegion(zone, limits) {
    if (zone === "tray") return -1;
    var bin = /^r(\d+)$/.exec(zone || "");
    return bin && +bin[1] < limits.regions ? +bin[1] : null;
  }

  function sortApply(state, action, limits) {
    var card;
    var to;
    if (action.type === "move") {
      card = action.fromIndex;
      to = sortRegion(action.to, limits);
    } else if (action.type === "place") {
      card = action.index;
      to = sortRegion(action.zone, limits);
    } else {
      return null;
    }
    if (typeof card !== "number" || card < 0 || card >= limits.cards || to === null) {
      return null;
    }
    if (state.place[card] === to) return null;
    var next = state.place.slice();
    next[card] = to;
    return { place: next };
  }

  function sortShown(state, piece, limits) {
    var region = sortRegion(piece.zone, limits);
    return region !== null && state.place[piece.index] === region;
  }

  function sortDescribe(state, say) {
    function cardsIn(region) {
      var out = [];
      for (var i = 0; i < state.place.length; i++) {
        if (state.place[i] === region) out.push(say.cards[i]);
      }
      return out;
    }
    var parts = say.titles.map(function (title, region) {
      return title + ": " + (window.PensumActivity.joinNumbers(cardsIn(region), say.and) || say.none);
    });
    var left = cardsIn(-1);
    if (left.length) {
      parts.push(say.tray + ": " + window.PensumActivity.joinNumbers(left, say.and));
    }
    return parts.join("; ");
  }

  /* The menus under the board follow the board, whichever way it changed. */
  function sortRender(root, state) {
    var menus = root.querySelectorAll("select[data-card]");
    for (var i = 0; i < menus.length; i++) {
      var p = state.place[+menus[i].getAttribute("data-card")];
      menus[i].value = p === -1 ? "tray" : "r" + p;
    }
  }

  function sortBind(root, api) {
    var menus = root.querySelectorAll("select[data-card]");
    for (var i = 0; i < menus.length; i++) {
      menus[i].addEventListener("change", function (event) {
        var menu = event.currentTarget;
        if (!api.dispatch({ type: "place", index: +menu.getAttribute("data-card"), zone: menu.value })) {
          sortRender(root, api.state());
        }
      });
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("sort", {
      parse: sortParse,
      apply: sortApply,
      shown: sortShown,
      describe: sortDescribe,
      render: sortRender,
      bind: sortBind,
    });
  }
})();
