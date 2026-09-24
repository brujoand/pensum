/* A pan balance with weights and boxes.
 *
 * State: `{left: {boxes, weights}, right: {boxes, weights}, box: n}`, as the
 * server grades it (`pensum.items.primitives.balance`). The pans only ever
 * change by the same amount on both sides, so a state is always the declared
 * balance with some weights and boxes taken off each side equally; `start` in
 * `limits` is not needed for that, because every move here keeps it true.
 *
 * Zones: `left` and `right` are the pans, `left-w` and `left-b` their weights
 * and boxes, `away` the take-away tray, `supply` the spare weights of an open
 * box. Moving a weight or a box to `away`, or from one pan onto the other,
 * takes one from both sides. With an open box, moving a spare weight onto a box
 * puts one more in it.
 */
(function () {
  "use strict";

  function balancePan(raw) {
    var count = window.PensumActivity.count;
    if (!raw || typeof raw !== "object") return null;
    var boxes = count(raw.boxes === undefined ? 0 : raw.boxes, 3);
    var weights = count(raw.weights === undefined ? 0 : raw.weights, 20);
    return boxes === null || weights === null ? null : { boxes: boxes, weights: weights };
  }

  function balanceParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object") return null;
    var left = balancePan(raw.left);
    var right = balancePan(raw.right);
    var box = window.PensumActivity.count(raw.box, limits.maxBox);
    if (!left || !right || box === null) return null;
    return { left: left, right: right, box: box };
  }

  function balanceTake(state, kind) {
    if (state.left[kind] < 1 || state.right[kind] < 1) return null;
    var next = {
      left: { boxes: state.left.boxes, weights: state.left.weights },
      right: { boxes: state.right.boxes, weights: state.right.weights },
      box: state.box,
    };
    next.left[kind] -= 1;
    next.right[kind] -= 1;
    return next;
  }

  function balanceBox(state, by, limits) {
    var box = state.box + by;
    if (box < 0 || box > limits.maxBox) return null;
    return { left: state.left, right: state.right, box: box };
  }

  /* "left-w" is a weight on the left pan; "left" is the pan itself. */
  function balanceParts(zone) {
    var match = /^(left|right)(?:-(w|b))?$/.exec(zone || "");
    if (!match) return null;
    return { side: match[1], kind: match[2] === "b" ? "boxes" : match[2] === "w" ? "weights" : null };
  }

  function balanceApply(state, action, limits) {
    if (action.type === "take") {
      if (limits.open) return null;
      return balanceTake(state, action.zone === "boxes" ? "boxes" : "weights");
    }
    if (action.type === "box") {
      return balanceBox(state, action.by, limits);
    }
    if (action.type === "move") {
      var from = balanceParts(action.from);
      var to = balanceParts(action.to);
      if (limits.open) {
        /* An open box is filled from the spare weights and emptied back. */
        if (action.from === "supply" && to && (to.kind === "boxes" || to.kind === null)) {
          return balanceBox(state, 1, limits);
        }
        if (from && from.kind === "boxes" && action.to === "supply") {
          return balanceBox(state, -1, limits);
        }
        return null;
      }
      if (!from || !from.kind) return null;
      /* To the tray, or across to the other pan: the same from both sides. */
      if (action.to === "away" || (to && to.side !== from.side)) {
        return balanceTake(state, from.kind);
      }
      return null;
    }
    if (action.type === "add" && limits.open) {
      /* A tap on a box, or on the pan it stands in, adds a weight to it. */
      var parts = balanceParts(action.zone);
      if (parts && parts.kind !== "weights") return balanceBox(state, 1, limits);
    }
    if (action.type === "act" && limits.open && action.zone === "supply") {
      return balanceBox(state, 1, limits);
    }
    return null;
  }

  function balanceShown(state, piece) {
    var parts = balanceParts(piece.zone);
    if (!parts || !parts.kind) return false;
    return state[parts.side][parts.kind] > piece.index;
  }

  function balanceSide(pan) {
    var terms = [];
    for (var i = 0; i < pan.boxes; i++) terms.push("☐");
    if (pan.weights) terms.push(String(pan.weights));
    return terms.length ? terms.join(" + ") : "0";
  }

  function balanceWeighs(pan, box) {
    return pan.boxes * box + pan.weights;
  }

  /* -1 when the left is heavier, 1 for the right, 0 when level. A closed box
   * never moves the beam: the task says the pans balance. */
  function balanceTilt(state, open) {
    if (!open) return 0;
    var left = balanceWeighs(state.left, state.box);
    var right = balanceWeighs(state.right, state.box);
    return (left < right) - (left > right);
  }

  function balanceDescribe(state, say) {
    return window.PensumActivity.fill(say.status, {
      equation: balanceSide(state.left) + " = " + balanceSide(state.right),
      box: state.box,
    });
  }

  function balanceRender(root, state, limits) {
    var tilt = balanceTilt(state, limits.open);
    var beam = root.querySelector(".balance-beam");
    var pivot = limits.pivot || [0, 0];
    if (beam) {
      if (tilt) beam.setAttribute("transform", "rotate(" + tilt * limits.tilt + " " + pivot[0] + " " + pivot[1] + ")");
      else beam.removeAttribute("transform");
    }
    var sides = [["left", -1], ["right", 1]];
    for (var i = 0; i < sides.length; i++) {
      var pan = root.querySelector(".balance-pan--" + sides[i][0]);
      if (!pan) continue;
      if (tilt) pan.setAttribute("transform", "translate(0 " + sides[i][1] * tilt * limits.drop + ")");
      else pan.removeAttribute("transform");
    }
    if (limits.open) {
      var labels = root.querySelectorAll("[data-piece-label]");
      for (var j = 0; j < labels.length; j++) labels[j].textContent = String(state.box);
    }
    var readout = root.querySelector("[data-box-value]");
    if (readout) readout.textContent = String(state.box);
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("balance", {
      parse: balanceParse,
      apply: balanceApply,
      shown: balanceShown,
      describe: balanceDescribe,
      render: balanceRender,
    });
  }
})();
