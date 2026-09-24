/* Two columns, linked in pairs.
 *
 * The rules of the board, as pure functions over a state `{pairs: [j, ...]}`:
 * per left-hand row, the right-hand card linked to it, or -1. A right-hand
 * card is in one row at most. `core.js` does the page; the server
 * (`pensum.items.primitives.match`) grades the same state.
 *
 * Zones: `supply-left` holds the left-hand terms and `supply` the right-hand
 * column, both always shown; `l0`, `l1` ... are the rows, where a linked card
 * is written beside its term. Tap a term and then a card, or a card and then a
 * term or a row, or drag a card onto a row; drop a linked card back on the
 * column to unlink it. Each row's menu under the board is the keyboard path.
 */
(function () {
  "use strict";

  function matchParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || !Array.isArray(raw.pairs)) {
      return null;
    }
    if (raw.pairs.length !== limits.cards) {
      return null;
    }
    var seen = {};
    for (var i = 0; i < raw.pairs.length; i++) {
      var j = raw.pairs[i];
      if (typeof j !== "number" || j !== Math.floor(j) || j < -1 || j >= limits.cards) {
        return null;
      }
      if (j >= 0 && seen[j]) return null;
      seen[j] = true;
    }
    return { pairs: raw.pairs.slice() };
  }

  function matchRow(zone, limits) {
    var row = /^l(\d+)$/.exec(zone || "");
    return row && +row[1] < limits.cards ? +row[1] : null;
  }

  /* Link row `row` to card `card`, taking the card out of any other row. */
  function matchLink(state, row, card, limits) {
    if (row === null || row < 0 || row >= limits.cards) return null;
    if (typeof card !== "number" || card < -1 || card >= limits.cards) return null;
    if (state.pairs[row] === card) return null;
    var next = state.pairs.map(function (j) {
      return card >= 0 && j === card ? -1 : j;
    });
    next[row] = card;
    return { pairs: next };
  }

  function matchApply(state, action, limits) {
    if (action.type === "pair") {
      return matchLink(state, action.row, action.card, limits);
    }
    if (action.type !== "move") return null;
    var from = action.from;
    var to = action.to;
    var fromRow = matchRow(from, limits);
    var toRow = matchRow(to, limits);
    if (from === "supply-left") {
      /* A term, then a card: in the column, or already in another row. */
      if (to === "supply" || (toRow !== null && action.toIndex >= 0)) {
        return matchLink(state, action.fromIndex, action.toIndex, limits);
      }
      return null;
    }
    if (from === "supply" || fromRow !== null) {
      var card = action.fromIndex;
      if (fromRow !== null && state.pairs[fromRow] !== card) return null;
      if (to === "supply-left") return matchLink(state, action.toIndex, card, limits);
      if (toRow !== null) return matchLink(state, toRow, card, limits);
      if (to === "supply" && fromRow !== null) return matchLink(state, fromRow, -1, limits);
    }
    return null;
  }

  function matchShown(state, piece, limits) {
    var row = matchRow(piece.zone, limits);
    return row !== null && state.pairs[row] === piece.index;
  }

  function matchDescribe(state, say) {
    return say.left
      .map(function (term, row) {
        var j = state.pairs[row];
        return term + " – " + (j >= 0 ? say.right[j] : say.none);
      })
      .join("; ");
  }

  function matchSync(root, state, limits, say) {
    var menus = root.querySelectorAll("select[data-row]");
    for (var i = 0; i < menus.length; i++) {
      var j = state.pairs[+menus[i].getAttribute("data-row")];
      menus[i].value = j >= 0 ? String(j) : "none";
    }
    /* A card in the column that is already linked says where, in words. */
    var cards = root.querySelectorAll('[data-zone="supply"]');
    for (var c = 0; c < cards.length; c++) {
      var used = cards[c].querySelector("[data-used]");
      var row = state.pairs.indexOf(+cards[c].getAttribute("data-index"));
      if (!used) continue;
      if (row >= 0 && say) {
        used.textContent = " " + window.PensumActivity.fill(say.used, { n: row + 1, term: say.left[row] });
        used.hidden = false;
        cards[c].classList.add("is-used");
      } else {
        used.textContent = "";
        used.hidden = true;
        cards[c].classList.remove("is-used");
      }
    }
  }

  function matchBind(root, api) {
    var menus = root.querySelectorAll("select[data-row]");
    for (var i = 0; i < menus.length; i++) {
      menus[i].addEventListener("change", function (event) {
        var menu = event.currentTarget;
        var card = menu.value === "none" ? -1 : +menu.value;
        if (!api.dispatch({ type: "pair", row: +menu.getAttribute("data-row"), card: card })) {
          matchSync(root, api.state(), api.limits, api.say);
        }
      });
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("match", {
      parse: matchParse,
      apply: matchApply,
      shown: matchShown,
      describe: matchDescribe,
      render: matchSync,
      bind: matchBind,
    });
  }
})();
