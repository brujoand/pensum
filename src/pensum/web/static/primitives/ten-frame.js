/* One or two ten-frames.
 *
 * State: `{frames: [[cells], [cells]]}`, the filled cells of each frame
 * numbered in reading order 0..9, the same shape the server grades
 * (`pensum.items.primitives.ten_frame`). Zones `f0` and `f1` are the frames;
 * a zone's index is its cell.
 *
 * Tap an empty cell to put a dot there; tap a dot to pick it up and again to
 * take it away; drag a dot to another cell. With a keyboard the frame itself
 * takes focus: the arrow keys move a cursor over the cells and Space or Enter
 * puts a dot down or takes one away.
 */
(function () {
  "use strict";

  function tenFrameParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || !Array.isArray(raw.frames) || raw.frames.length !== limits.frames) {
      return null;
    }
    var frames = [];
    for (var f = 0; f < raw.frames.length; f++) {
      var cells = raw.frames[f];
      if (!Array.isArray(cells)) return null;
      var seen = {};
      for (var c = 0; c < cells.length; c++) {
        var cell = cells[c];
        if (typeof cell !== "number" || cell !== Math.floor(cell) || cell < 0 || cell >= limits.cells) {
          return null;
        }
        if (seen[cell]) return null;
        seen[cell] = true;
      }
      frames.push(cells.slice().sort(function (a, b) { return a - b; }));
    }
    return { frames: frames };
  }

  function tenFrameHas(state, frame, cell) {
    return state.frames[frame] !== undefined && state.frames[frame].indexOf(cell) >= 0;
  }

  function tenFrameFrame(zone) {
    var match = /^f(\d+)$/.exec(zone || "");
    return match ? +match[1] : -1;
  }

  function tenFrameSet(state, frame, cell, on) {
    var frames = state.frames.map(function (cells) { return cells.slice(); });
    if (on) {
      frames[frame].push(cell);
      frames[frame].sort(function (a, b) { return a - b; });
    } else {
      frames[frame] = frames[frame].filter(function (c) { return c !== cell; });
    }
    return { frames: frames };
  }

  function tenFrameValid(state, frame, cell, limits) {
    return frame >= 0 && frame < state.frames.length && cell >= 0 && cell < limits.cells;
  }

  function tenFrameApply(state, action, limits) {
    var frame;
    var f;
    var c;
    if (action.type === "add") {
      if (action.zone !== undefined && action.index !== undefined && action.index >= 0) {
        frame = tenFrameFrame(action.zone);
        if (!tenFrameValid(state, frame, action.index, limits)) return null;
        if (tenFrameHas(state, frame, action.index)) return null;
        return tenFrameSet(state, frame, action.index, true);
      }
      /* The button: the first empty cell in reading order. */
      for (f = 0; f < state.frames.length; f++) {
        for (c = 0; c < limits.cells; c++) {
          if (!tenFrameHas(state, f, c)) return tenFrameSet(state, f, c, true);
        }
      }
      return null;
    }
    if (action.type === "remove" || action.type === "act") {
      if (action.type === "act") {
        frame = tenFrameFrame(action.zone);
        if (!tenFrameValid(state, frame, action.index, limits)) return null;
        if (!tenFrameHas(state, frame, action.index)) return null;
        return tenFrameSet(state, frame, action.index, false);
      }
      /* The button: the last filled cell in reading order. */
      for (f = state.frames.length - 1; f >= 0; f--) {
        var cells = state.frames[f];
        if (cells.length) return tenFrameSet(state, f, cells[cells.length - 1], false);
      }
      return null;
    }
    if (action.type === "toggle") {
      frame = tenFrameFrame(action.zone);
      if (!tenFrameValid(state, frame, action.index, limits)) return null;
      return tenFrameSet(state, frame, action.index, !tenFrameHas(state, frame, action.index));
    }
    if (action.type === "move") {
      var from = tenFrameFrame(action.from);
      var to = tenFrameFrame(action.to);
      if (!tenFrameValid(state, from, action.fromIndex, limits)) return null;
      if (!tenFrameValid(state, to, action.toIndex, limits)) return null;
      if (!tenFrameHas(state, from, action.fromIndex) || tenFrameHas(state, to, action.toIndex)) {
        return null;
      }
      return tenFrameSet(tenFrameSet(state, from, action.fromIndex, false), to, action.toIndex, true);
    }
    return null;
  }

  function tenFrameShown(state, piece) {
    return tenFrameHas(state, tenFrameFrame(piece.zone), piece.index);
  }

  function tenFrameDescribe(state, say) {
    var total = state.frames.reduce(function (sum, cells) { return sum + cells.length; }, 0);
    return window.PensumActivity.plural(say, "made", total);
  }

  /* Where the keyboard cursor goes from `at` on a key, across `frames`
   * frames of two rows of `perRow`. Up and down move a row, and cross from
   * one frame into the next. -1 for a key that does not move it. */
  function tenFrameStep(at, key, frames, perRow) {
    var last = frames * 2 * perRow - 1;
    var next = -1;
    if (key === "ArrowRight") next = at + 1;
    else if (key === "ArrowLeft") next = at - 1;
    else if (key === "ArrowDown") next = at + perRow;
    else if (key === "ArrowUp") next = at - perRow;
    else if (key === "Home") next = 0;
    else if (key === "End") next = last;
    else return -1;
    return Math.max(0, Math.min(last, next));
  }

  function tenFrameBind(root, api) {
    var board = api.board;
    var zones = board.querySelectorAll("[data-drop]");
    var cursor = 0;
    board.setAttribute("tabindex", "0");
    board.setAttribute("role", "application");

    function show() {
      for (var i = 0; i < zones.length; i++) {
        zones[i].classList.toggle("is-cursor", i === cursor);
      }
      var frame = Math.floor(cursor / api.limits.cells);
      var cell = cursor % api.limits.cells;
      api.announce(
        window.PensumActivity.fill(api.say.cell, {
          frame: frame + 1,
          cell: cell + 1,
          state: tenFrameHas(api.state(), frame, cell) ? api.say.full : api.say.empty,
        })
      );
    }

    board.addEventListener("focus", show);
    board.addEventListener("blur", function () {
      for (var i = 0; i < zones.length; i++) zones[i].classList.remove("is-cursor");
    });
    board.addEventListener("keydown", function (event) {
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        var frame = Math.floor(cursor / api.limits.cells);
        api.dispatch({ type: "toggle", zone: "f" + frame, index: cursor % api.limits.cells });
        show();
        return;
      }
      var next = tenFrameStep(cursor, event.key, api.limits.frames, api.limits.perRow);
      if (next >= 0) {
        event.preventDefault();
        cursor = next;
        show();
      }
    });
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("ten_frame", {
      parse: tenFrameParse,
      apply: tenFrameApply,
      shown: tenFrameShown,
      describe: tenFrameDescribe,
      bind: tenFrameBind,
    });
  }
})();
