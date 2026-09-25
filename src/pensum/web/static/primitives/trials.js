/* Trials: predict, then spin a spinner or roll dice and watch the tally.
 *
 * Pure rules over a state `{prediction, seed, done, tally}`; `core.js` does the
 * page. The seed came from the server with the page, and every draw is made
 * from it by xorshift32, the same generator as `simulate` in
 * `pensum.items.primitives.trials`, so the server can replay the seed and check
 * the tally it is sent. It grades the prediction alone.
 *
 * A trial runs only after a prediction, and the first one seals it: `sealed`
 * tells core.js to forget the undo history across that step, so the
 * prediction cannot be reopened after the result is seen.
 *
 * Pieces: `t0`, `t1` ... are the bars, one per outcome, with a piece for every
 * height in twentieths of all trials so far. Exactly one is shown, or none.
 */
(function () {
  "use strict";

  function trialsNext(x) {
    x = (x ^ (x << 13)) >>> 0;
    x = (x ^ (x >>> 17)) >>> 0;
    x = (x ^ (x << 5)) >>> 0;
    return x;
  }

  /* The tally after `count` trials from `seed`. Draw for draw the same as the
   * server: one number per spin modulo the sizes' total, one per die modulo 6. */
  function trialsSimulate(seed, count, limits) {
    var x = seed >>> 0 || 1;
    var tally = [];
    var i;
    for (i = 0; i < limits.outcomes; i++) tally.push(0);
    var weights = limits.weights || [];
    var total = 0;
    for (i = 0; i < weights.length; i++) total += weights[i];
    for (var n = 0; n < count; n++) {
      x = trialsNext(x);
      if (weights.length) {
        var r = x % total;
        for (i = 0; i < weights.length; i++) {
          if (r < weights[i]) {
            tally[i]++;
            break;
          }
          r -= weights[i];
        }
      } else {
        var roll = x % 6;
        if (limits.dice === 2) {
          x = trialsNext(x);
          roll += x % 6;
        }
        tally[roll]++;
      }
    }
    return tally;
  }

  function trialsParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    var prediction = raw.prediction === undefined ? null : raw.prediction;
    if (prediction !== null && limits.choices.indexOf(prediction) < 0) return null;
    var seed = raw.seed === undefined ? 1 : raw.seed;
    if (typeof seed !== "number" || seed !== Math.floor(seed) || seed < 1 || seed > 2147483647) return null;
    var done = window.PensumActivity.count(raw.done === undefined ? 0 : raw.done, limits.max);
    if (done === null || (done > 0 && prediction === null)) return null;
    var tally = raw.tally;
    if (!Array.isArray(tally) || tally.length !== limits.outcomes) return null;
    var replay = trialsSimulate(seed, done, limits);
    for (var i = 0; i < tally.length; i++) {
      if (tally[i] !== replay[i]) return null;
    }
    return { prediction: prediction, seed: seed, done: done, tally: replay };
  }

  function trialsApply(state, action, limits) {
    if (action.type === "predict") {
      /* Locked once anything has run. */
      if (state.done > 0 || limits.choices.indexOf(action.zone) < 0) return null;
      if (state.prediction === action.zone) return null;
      return { prediction: action.zone, seed: state.seed, done: 0, tally: state.tally.slice() };
    }
    if (action.type === "run") {
      var by = action.by;
      if (state.prediction === null || [1, 10, 100].indexOf(by) < 0) return null;
      if (state.done + by > limits.max) return null;
      var done = state.done + by;
      return {
        prediction: state.prediction,
        seed: state.seed,
        done: done,
        tally: trialsSimulate(state.seed, done, limits),
      };
    }
    return null;
  }

  /* The bar step nearest count/total, in twentieths, as `bar_level` does. */
  function trialsLevel(count, total, levels) {
    return total > 0 ? Math.floor((2 * levels * count + total) / (2 * total)) : 0;
  }

  function trialsShown(state, piece, limits) {
    var match = /^t(\d+)$/.exec(piece.zone || "");
    if (!match) return false;
    var i = +match[1];
    return i < state.tally.length && piece.index === trialsLevel(state.tally[i], state.done, limits.levels);
  }

  function trialsJoin(words, and) {
    if (words.length <= 1) return words.join("");
    return words.slice(0, -1).join(", ") + " " + and + " " + words[words.length - 1];
  }

  function trialsDescribe(state, say) {
    var fill = window.PensumActivity.fill;
    var text =
      state.prediction === null ? say.none : fill(say.made, { choice: say.choices[state.prediction] });
    if (state.done > 0) {
      var counts = state.tally.map(function (n, i) {
        return fill(say.count, { label: say.labels[i], count: n });
      });
      text += ", " + fill(state.done === 1 ? say.after_one : say.after, {
        count: state.done,
        tally: trialsJoin(counts, say.and),
      });
    }
    return text;
  }

  function trialsSealed(state) {
    return state.done > 0;
  }

  function trialsRender(root, state) {
    var picks = root.querySelectorAll('[data-action="predict"]');
    for (var i = 0; i < picks.length; i++) {
      picks[i].setAttribute(
        "aria-pressed",
        picks[i].getAttribute("data-zone") === state.prediction ? "true" : "false"
      );
    }
    var cells = root.querySelectorAll("[data-count]");
    for (var c = 0; c < cells.length; c++) {
      cells[c].textContent = String(state.tally[+cells[c].getAttribute("data-count")] || 0);
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("trials", {
      parse: trialsParse,
      apply: trialsApply,
      shown: trialsShown,
      describe: trialsDescribe,
      render: trialsRender,
      sealed: trialsSealed,
      pointer: false,
    });
  }
})();
