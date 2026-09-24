/* An array sized by dragging its corner.
 *
 * State: `{rows: r, cols: c, split: s}`, as the server grades it
 * (`pensum.items.primitives.array`): 1..max rows and columns, and a split line
 * after column s, 0 for none, always inside the array.
 *
 * The handle is dragged, or the pupil taps the square the corner should reach;
 * either way the corner lands on a grid line, never between two. A tap on the
 * strip above the columns puts the split line at the nearest column boundary.
 * On the keyboard the handle takes focus: the arrow keys add and remove rows
 * and columns, and Shift with left and right moves the split line.
 *
 * This primitive does its own pointer handling (`pointer: false`), because a
 * corner is dragged to a position rather than a piece to a zone. The numbers it
 * needs to turn a pointer into rows and columns -- the cell size and where the
 * grid starts -- come from the server in `limits`, not from constants here.
 */
(function () {
  "use strict";

  function arrayParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object") return null;
    var count = window.PensumActivity.count;
    var rows = count(raw.rows, limits.max);
    var cols = count(raw.cols, limits.max);
    var split = count(raw.split === undefined ? 0 : raw.split, limits.max - 1);
    if (!rows || !cols || split === null || split >= cols) return null;
    return { rows: rows, cols: cols, split: split };
  }

  function arrayClamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  /* A resized array keeps its split line only while it is still inside. */
  function arraySized(state, rows, cols, limits) {
    rows = arrayClamp(rows, 1, limits.max);
    cols = arrayClamp(cols, 1, limits.max);
    if (rows === state.rows && cols === state.cols) return null;
    return { rows: rows, cols: cols, split: state.split < cols ? state.split : 0 };
  }

  function arrayApply(state, action, limits) {
    if (action.type === "rows") return arraySized(state, state.rows + action.by, state.cols, limits);
    if (action.type === "cols") return arraySized(state, state.rows, state.cols + action.by, limits);
    if (action.type === "resize") return arraySized(state, action.rows, action.cols, limits);
    if (action.type === "split" || action.type === "split_at") {
      if (!limits.split) return null;
      var next = action.type === "split" ? state.split + action.by : action.at;
      if (next < 0 || next >= state.cols || next === state.split) return null;
      return { rows: state.rows, cols: state.cols, split: next };
    }
    return null;
  }

  function arrayShown(state, piece) {
    return piece.row < state.rows && piece.col < state.cols;
  }

  function arrayDescribe(state, say) {
    var P = window.PensumActivity;
    var text = P.fill(state.rows === 1 ? say.made_one : say.made, { rows: state.rows, cols: state.cols });
    if (state.split) {
      text += ", " + P.fill(say.made_split, { left: state.split, right: state.cols - state.split });
    }
    return text;
  }

  /* The grid line nearest a point, as a count of cells from the grid's edge.
   * Used for the corner, which sits on a line: 1 to max. */
  function arrayLineAt(position, origin, cell, max) {
    return arrayClamp(Math.round((position - origin) / cell), 1, max);
  }

  /* The cell a point is in, counted from 1: tapping a square puts the corner
   * at its far edge, so the square tapped is in the array. */
  function arrayCellAt(position, origin, cell, max) {
    return arrayClamp(Math.floor((position - origin) / cell) + 1, 1, max);
  }

  function arrayKey(state, key, shift) {
    if (shift && key === "ArrowRight") return { type: "split", by: 1 };
    if (shift && key === "ArrowLeft") return { type: "split", by: -1 };
    if (key === "ArrowRight") return { type: "cols", by: 1 };
    if (key === "ArrowLeft") return { type: "cols", by: -1 };
    if (key === "ArrowDown") return { type: "rows", by: 1 };
    if (key === "ArrowUp") return { type: "rows", by: -1 };
    return null;
  }

  function arrayRender(root, state, limits) {
    var handle = root.querySelector("[data-handle]");
    if (handle) {
      handle.removeAttribute("hidden");
      handle.setAttribute("cx", (limits.left + state.cols * limits.cell).toFixed(2));
      handle.setAttribute("cy", (limits.top + state.rows * limits.cell).toFixed(2));
    }
    var line = root.querySelector("[data-split]");
    if (line) {
      if (state.split) {
        var x = limits.left + state.split * limits.cell;
        line.setAttribute(
          "d",
          "M" + x.toFixed(2) + "," + (limits.top - 6).toFixed(2) +
            "L" + x.toFixed(2) + "," + (limits.top + state.rows * limits.cell + 6).toFixed(2)
        );
        line.removeAttribute("hidden");
      } else {
        line.setAttribute("hidden", "");
      }
    }
    var caption = root.querySelector(".figure-array-caption");
    if (caption) {
      caption.textContent = state.rows + " × " + state.cols;
    }
  }

  function arrayBind(root, api) {
    var board = api.board;
    var handle = root.querySelector("[data-handle]");
    var limits = api.limits;
    if (handle) {
      handle.setAttribute("tabindex", "0");
      handle.setAttribute("role", "button");
      handle.removeAttribute("aria-hidden");
      board.setAttribute("role", "group");
      handle.addEventListener("keydown", function (event) {
        var action = arrayKey(api.state(), event.key, event.shiftKey);
        if (action) {
          event.preventDefault();
          api.dispatch(action);
        }
      });
    }

    var drag = null;
    board.addEventListener("pointerdown", function (event) {
      var at = api.toBoard(event);
      if (!at) return;
      if (handle && event.target === handle) {
        drag = { id: event.pointerId, before: api.state() };
        board.setPointerCapture(event.pointerId);
        handle.classList.add("is-dragging");
        event.preventDefault();
        return;
      }
      var zone = event.target.closest && event.target.closest("[data-drop]");
      var name = zone ? zone.getAttribute("data-drop") : "";
      if (name === "strip") {
        api.dispatch({ type: "split_at", at: Math.round((at.x - limits.left) / limits.cell) });
      } else if (name === "grid" || event.target.closest("[data-piece]")) {
        api.dispatch({
          type: "resize",
          rows: arrayCellAt(at.y, limits.top, limits.cell, limits.max),
          cols: arrayCellAt(at.x, limits.left, limits.cell, limits.max),
        });
      }
    });
    board.addEventListener("pointermove", function (event) {
      if (!drag || drag.id !== event.pointerId) return;
      var at = api.toBoard(event);
      if (!at) return;
      api.preview(
        arrayApply(
          api.state(),
          {
            type: "resize",
            rows: arrayLineAt(at.y, limits.top, limits.cell, limits.max),
            cols: arrayLineAt(at.x, limits.left, limits.cell, limits.max),
          },
          limits
        )
      );
    });
    function end(event) {
      if (!drag || drag.id !== event.pointerId) return;
      handle.classList.remove("is-dragging");
      api.settle(drag.before);
      drag = null;
    }
    board.addEventListener("pointerup", end);
    board.addEventListener("pointercancel", end);
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("array", {
      parse: arrayParse,
      apply: arrayApply,
      shown: arrayShown,
      describe: arrayDescribe,
      render: arrayRender,
      bind: arrayBind,
      pointer: false,
    });
  }
})();
