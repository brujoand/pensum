/* Counters on a mat, and rings to share them into.
 *
 * The rules of the board, as pure functions over a state
 * `{loose: n, groups: [a, b, ...]}`; `core.js` does the page. The server
 * (`pensum.items.primitives.counters`) grades the same state and refuses one
 * these rules could not have produced, so the two are kept to the same limits:
 * `capacity` counters on the board in all, `ring` in any one ring.
 *
 * Zones: `loose` is the mat, `g0`, `g1` ... are the rings, `supply` is the box
 * of spare counters. Moving from the box adds a counter; moving to it takes one
 * away.
 */
(function () {
  "use strict";

  function countersParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || !Array.isArray(raw.groups)) {
      return null;
    }
    if (raw.groups.length !== limits.groups) {
      return null;
    }
    var loose = window.PensumActivity.count(raw.loose, limits.capacity);
    var groups = raw.groups.map(function (size) {
      return window.PensumActivity.count(size, limits.ring);
    });
    if (loose === null || groups.indexOf(null) >= 0) {
      return null;
    }
    return { loose: loose, groups: groups };
  }

  function countersTotal(state) {
    return state.groups.reduce(function (sum, size) {
      return sum + size;
    }, state.loose);
  }

  /* How many a zone holds, and how many it may. -1 for a zone that is not on
   * this board. */
  function countersIn(state, zone) {
    if (zone === "loose") return state.loose;
    var ring = /^g(\d+)$/.exec(zone || "");
    if (ring && +ring[1] < state.groups.length) return state.groups[+ring[1]];
    return -1;
  }

  function countersWith(state, zone, delta) {
    var next = { loose: state.loose, groups: state.groups.slice() };
    if (zone === "loose") {
      next.loose += delta;
    } else {
      next.groups[+zone.slice(1)] += delta;
    }
    return next;
  }

  function countersRoom(zone, limits) {
    return zone === "loose" ? limits.capacity : limits.ring;
  }

  function countersApply(state, action, limits) {
    var from = action.from;
    var to = action.to;
    if (action.type === "add") {
      /* A tap on an empty place, or a ring's own button: a ring fills from
       * the mat first, because sharing out is moving what is already there. */
      to = action.zone;
      from = to !== "loose" && state.loose > 0 ? "loose" : "supply";
    } else if (action.type === "act") {
      /* Tapping the box twice puts a counter on the mat. */
      if (action.zone !== "supply") return null;
      from = "supply";
      to = "loose";
    } else if (action.type !== "move") {
      return null;
    }
    if (from === to) return null;

    if (from === "supply") {
      if (countersIn(state, to) < 0 || countersTotal(state) >= limits.capacity) return null;
      if (countersIn(state, to) >= countersRoom(to, limits)) return null;
      return countersWith(state, to, 1);
    }
    if (countersIn(state, from) <= 0) return null;
    if (to === "supply") {
      return countersWith(state, from, -1);
    }
    if (countersIn(state, to) < 0 || countersIn(state, to) >= countersRoom(to, limits)) {
      return null;
    }
    return countersWith(countersWith(state, from, -1), to, 1);
  }

  function countersShown(state, piece) {
    var held = countersIn(state, piece.zone);
    return held > piece.index;
  }

  function countersDescribe(state, say) {
    var total = countersTotal(state);
    if (!state.groups.length) {
      return window.PensumActivity.plural(say, "made", total);
    }
    var text = window.PensumActivity.fill(say.made_groups, {
      count: total,
      sizes: window.PensumActivity.joinNumbers(state.groups, say.and),
    });
    if (state.loose) {
      text += ", " + window.PensumActivity.fill(say.made_loose, { loose: state.loose });
    }
    return text;
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("counters", {
      parse: countersParse,
      apply: countersApply,
      shown: countersShown,
      describe: countersDescribe,
    });
  }
})();
