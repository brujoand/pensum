/* Words or sentences in a text, tapped to mark them.
 *
 * The rules of the board, as pure functions over a state `{marked: [i, ...]}`:
 * the marked words or sentences by position, in increasing order. `core.js`
 * does the page; the server (`pensum.items.primitives.highlight`) grades the
 * same state as an exact set.
 *
 * Every word or sentence is a button, drawn disabled so it is no focus stop
 * without the script; `bind` enables them. Pressing one toggles it. Nothing is
 * dragged here, so core's pointer handling is switched off, and the buttons'
 * own clicks (and Enter and Space) are the whole of the input. The pieces are
 * the rings drawn round a marked one.
 */
(function () {
  "use strict";

  function highlightParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || !Array.isArray(raw.marked)) {
      return null;
    }
    for (var i = 0; i < raw.marked.length; i++) {
      var t = raw.marked[i];
      if (typeof t !== "number" || t !== Math.floor(t) || t < 0 || t >= limits.tokens) {
        return null;
      }
      if (i > 0 && t <= raw.marked[i - 1]) return null;
    }
    return { marked: raw.marked.slice() };
  }

  function highlightApply(state, action, limits) {
    if (action.type !== "toggle") return null;
    var t = action.index;
    if (typeof t !== "number" || t !== Math.floor(t) || t < 0 || t >= limits.tokens) {
      return null;
    }
    var marked = state.marked.filter(function (m) {
      return m !== t;
    });
    if (marked.length === state.marked.length) {
      marked.push(t);
      marked.sort(function (a, b) {
        return a - b;
      });
    }
    return { marked: marked };
  }

  function highlightShown(state, piece) {
    return piece.zone === "mark" && state.marked.indexOf(piece.index) >= 0;
  }

  function highlightDescribe(state, say) {
    var words = state.marked.map(function (t) {
      return "«" + say.tokens[t] + "»";
    });
    return window.PensumActivity.joinNumbers(words, say.and) || say.nothing;
  }

  function highlightRender(root, state) {
    var tokens = root.querySelectorAll("[data-token]");
    for (var i = 0; i < tokens.length; i++) {
      var on = state.marked.indexOf(+tokens[i].getAttribute("data-token")) >= 0;
      tokens[i].setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  function highlightBind(root, api) {
    var tokens = root.querySelectorAll("[data-token]");
    for (var i = 0; i < tokens.length; i++) {
      tokens[i].disabled = false;
      tokens[i].addEventListener("click", function (event) {
        api.dispatch({ type: "toggle", index: +event.currentTarget.getAttribute("data-token") });
      });
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("highlight", {
      parse: highlightParse,
      apply: highlightApply,
      shown: highlightShown,
      describe: highlightDescribe,
      render: highlightRender,
      bind: highlightBind,
      pointer: false,
    });
  }
})();
