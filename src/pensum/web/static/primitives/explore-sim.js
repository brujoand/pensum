/* Explore a simulation: predict, move one slider and watch, then explain.
 *
 * Pure rules over a state `{prediction, locked, stop, explain}`; `core.js`
 * does the page. The order is the rule: the slider moves only once there is a
 * prediction, its first move locks the prediction (`locked`, and `sealed` so
 * undo cannot reopen it), and the explanation can be picked only after that.
 * The server (`pensum.items.primitives.explore_sim`) refuses a state out of
 * that order and grades the explanation alone.
 *
 * Every stop's still is already in the board, one layer each, and the page
 * shows the one at the slider by taking `is-off` from it and giving it to the
 * rest. Nothing moves between them.
 */
(function () {
  "use strict";

  function exploreSimParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    var prediction = raw.prediction === undefined ? null : raw.prediction;
    var explain = raw.explain === undefined ? null : raw.explain;
    var locked = raw.locked === undefined ? false : raw.locked;
    var stop = raw.stop === undefined ? 0 : raw.stop;
    if (prediction !== null && limits.predict.indexOf(prediction) < 0) return null;
    if (explain !== null && limits.explain.indexOf(explain) < 0) return null;
    if (typeof locked !== "boolean") return null;
    if (window.PensumActivity.count(stop, limits.stops - 1) === null) return null;
    if (stop !== limits.start && !locked) return null;
    if (locked && prediction === null) return null;
    if (explain !== null && !locked) return null;
    return { prediction: prediction, locked: locked, stop: stop, explain: explain };
  }

  function exploreSimWith(state, changes) {
    var next = { prediction: state.prediction, locked: state.locked, stop: state.stop, explain: state.explain };
    for (var key in changes) next[key] = changes[key];
    return next;
  }

  function exploreSimApply(state, action, limits) {
    if (action.type === "predict") {
      if (state.locked || limits.predict.indexOf(action.zone) < 0) return null;
      if (state.prediction === action.zone) return null;
      return exploreSimWith(state, { prediction: action.zone });
    }
    if (action.type === "slide" || action.type === "step") {
      if (state.prediction === null) return null;
      var to = action.type === "slide" ? action.by : state.stop + action.by;
      if (typeof to !== "number" || to !== Math.floor(to) || to < 0 || to >= limits.stops) return null;
      if (to === state.stop) return null;
      return exploreSimWith(state, { stop: to, locked: true });
    }
    if (action.type === "explain") {
      if (!state.locked || limits.explain.indexOf(action.zone) < 0) return null;
      if (state.explain === action.zone) return null;
      return exploreSimWith(state, { explain: action.zone });
    }
    return null;
  }

  function exploreSimShown() {
    return false;
  }

  function exploreSimDescribe(state, say) {
    if (state.explain !== null) return window.PensumActivity.fill(say.made, { choice: say.explain[state.explain] });
    if (state.locked) return say.observed;
    if (state.prediction !== null) return say.predicted;
    return say.none;
  }

  function exploreSimSealed(state) {
    return state.locked;
  }

  function exploreSimRender(root, state, limits) {
    var stills = root.querySelectorAll(".board-layer.still");
    for (var i = 0; i < stills.length; i++) {
      var on = stills[i].classList.contains("still-" + state.stop);
      stills[i].classList.toggle("is-off", !on);
    }
    var groups = { predict: state.prediction, explain: state.explain };
    for (var type in groups) {
      var buttons = root.querySelectorAll('[data-action="' + type + '"]');
      for (var b = 0; b < buttons.length; b++) {
        buttons[b].setAttribute("aria-pressed", buttons[b].getAttribute("data-zone") === groups[type] ? "true" : "false");
      }
    }
    var slider = root.querySelector("[data-slider]");
    var say = exploreSimSay(root);
    if (slider) {
      slider.value = String(state.stop);
      slider.disabled = state.prediction === null;
      if (say && say.stops) slider.setAttribute("aria-valuetext", say.stops[state.stop]);
    }
    var seen = root.querySelector("[data-seen]");
    if (seen && say && say.stops) seen.textContent = say.stops[state.stop];
  }

  function exploreSimSay(root) {
    try {
      return JSON.parse(root.getAttribute("data-say") || "{}");
    } catch (error) {
      return null;
    }
  }

  function exploreSimBind(root, api) {
    var slider = root.querySelector("[data-slider]");
    if (!slider) return;
    slider.addEventListener("input", function () {
      var to = parseInt(slider.value, 10);
      if (!api.dispatch({ type: "slide", by: to })) slider.value = String(api.state().stop);
    });
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("explore_sim", {
      parse: exploreSimParse,
      apply: exploreSimApply,
      shown: exploreSimShown,
      describe: exploreSimDescribe,
      render: exploreSimRender,
      bind: exploreSimBind,
      sealed: exploreSimSealed,
      pointer: false,
    });
  }
})();
