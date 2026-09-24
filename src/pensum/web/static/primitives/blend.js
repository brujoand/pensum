/* The sound slide: tiles joined one at a time, then the word's meaning picked.
 *
 * Pure rules over a state `{joined: n, pick: "id" or ""}`; `core.js` does the
 * page. The server (`pensum.items.primitives.blend`) grades the pick, and
 * refuses a pick made before every tile was on the slide, as these rules do.
 *
 * Zones: `apart` is where the tiles start, `joined` the slide, `pick` the card
 * that shows what was chosen. Touching a tile says its sound with the browser's
 * own voice, and the joined word is said once when the last tile goes on (if the
 * item wants it). Without a voice for the language the page says so and the
 * slide works as letters. Nothing is recorded.
 */
(function () {
  "use strict";

  function blendParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object") {
      return null;
    }
    var joined = window.PensumActivity.count(raw.joined, limits.count);
    var pick = raw.pick === undefined ? "" : raw.pick;
    if (joined === null || typeof pick !== "string") {
      return null;
    }
    if (pick && (limits.choices.indexOf(pick) < 0 || joined !== limits.count)) {
      return null;
    }
    return { joined: joined, pick: pick };
  }

  function blendApply(state, action, limits) {
    var join =
      action.type === "join" ||
      (action.type === "act" && action.zone === "apart") ||
      (action.type === "move" && action.from === "apart" && action.to === "joined");
    if (join) {
      /* One at a time, from the left: dragging the third tile first is not a
       * blend, so it does nothing. */
      if (state.joined >= limits.count) return null;
      if (action.type !== "join" && action.fromIndex !== undefined && action.fromIndex !== state.joined) {
        return null;
      }
      if (action.type === "act" && action.index !== state.joined) return null;
      return { joined: state.joined + 1, pick: "" };
    }
    var split =
      action.type === "split" ||
      (action.type === "move" && action.from === "joined" && action.to === "apart");
    if (split) {
      if (state.joined === 0) return null;
      return { joined: state.joined - 1, pick: "" };
    }
    if (action.type === "pick") {
      if (state.joined !== limits.count || limits.choices.indexOf(action.zone) < 0) return null;
      /* Picking the chosen one again takes the pick back. */
      return { joined: state.joined, pick: state.pick === action.zone ? "" : action.zone };
    }
    return null;
  }

  function blendShown(state, piece, limits) {
    if (piece.zone === "joined") return piece.index < state.joined;
    if (piece.zone === "apart") return piece.index >= state.joined;
    if (piece.zone === "pick") return limits.choices[piece.index] === state.pick;
    return false;
  }

  function blendDescribe(state, say) {
    if (!state.pick) {
      return say.none;
    }
    return window.PensumActivity.fill(say.made, { choice: say["choice_" + state.pick] });
  }

  /* Per board: its voice, and how many tiles were joined when it last drew, so
   * the word is said on the join that completes it and not on every redraw. */
  var voices = typeof WeakMap === "function" ? new WeakMap() : null;

  function blendRender(root, state, limits) {
    var picks = root.querySelectorAll('[data-action="pick"]');
    for (var i = 0; i < picks.length; i++) {
      picks[i].setAttribute("aria-pressed", picks[i].getAttribute("data-zone") === state.pick ? "true" : "false");
    }
    /* The word is said once it has been built, not before. */
    var word = root.querySelectorAll('[data-speak="word"]');
    for (var w = 0; w < word.length; w++) {
      word[w].disabled = state.joined !== limits.count;
    }
    var board = voices && voices.get(root);
    if (!board) return;
    if (state.joined === limits.count && board.joined < limits.count) {
      board.say(limits.word);
    }
    board.joined = state.joined;
  }

  function blendBind(root, api) {
    var say = window.PensumActivity.speech.setup(root, api.limits.language);
    if (voices) {
      voices.set(root, { say: say, joined: api.state().joined });
    }
    var tiles = root.querySelectorAll("[data-speak-tile]");
    for (var i = 0; i < tiles.length; i++) {
      tiles[i].addEventListener("click", function (event) {
        say(api.limits.sounds[+event.currentTarget.getAttribute("data-speak-tile")]);
      });
    }
    var word = root.querySelectorAll('[data-speak="word"]');
    for (var w = 0; w < word.length; w++) {
      word[w].addEventListener("click", function () {
        say(api.limits.word);
      });
    }
    /* Touching a tile says it, before any drag or tap decides what it does. */
    api.board.addEventListener("pointerdown", function (event) {
      var piece = event.target.closest("[data-piece]");
      if (!piece) return;
      var zone = piece.getAttribute("data-zone");
      if (zone === "apart" || zone === "joined") {
        say(api.limits.sounds[+piece.getAttribute("data-index")]);
      }
    });
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("blend", {
      parse: blendParse,
      apply: blendApply,
      shown: blendShown,
      describe: blendDescribe,
      render: blendRender,
      bind: blendBind,
    });
  }
})();
