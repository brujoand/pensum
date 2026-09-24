/* The shared half of every hands-on question: counters, frames, blocks, arrays,
 * balances.
 *
 * Written by hand and vendored like everything else on this site: no bundler,
 * no dependency, no third-party origin.
 *
 * A primitive's own file registers a small spec with this one:
 *
 *   PensumActivity.register("base_ten", {
 *     parse: function (json, limits) { ... return state or null },
 *     apply: function (state, action, limits) { ... return next state or null },
 *     shown: function (state, piece, limits) { ... return true or false },
 *     describe: function (state, say, limits) { ... return a sentence },
 *     render: function (root, state, limits) { ... optional extras },
 *     bind: function (root, api) { ... optional keys and pointers of its own },
 *   });
 *
 * `parse`, `apply`, `shown` and `describe` are pure: a state in, a state or a
 * sentence out, no DOM. That is what the tests under tests/js/ run, and it is
 * the whole of what a primitive decides. Everything that touches the page is
 * here, once:
 *
 *   * Taking over from the no-script question. The server renders the board as
 *     a picture with a typed answer under it. This shows the controls, enables
 *     the hidden state field and disables the typed one, so a page where this
 *     never runs is still a whole question.
 *   * Buttons. Every `[data-action]` button is dispatched as an action, and is
 *     disabled whenever `apply` says that action would do nothing. The buttons
 *     are the keyboard path for every primitive.
 *   * Tap-tap and drag, which are the same move. Tap a piece to pick it up, tap
 *     where it goes; or press on a piece, drag it, and let go over where it
 *     goes. Tapping a picked-up piece again is its own action (a rod breaks
 *     into ones). Tapping an empty place adds one there. Where a piece may land
 *     was decided by the server, so the drop always snaps.
 *   * Undo, never counted (activity rule 3), and the live status line.
 *
 * Nothing here grades. The answer is whatever state the board is in when the
 * pupil presses the ordinary Check button (activity rule 4).
 */
(function () {
  "use strict";

  var READY = "data-activity-ready";
  /* How far a press has to travel before it is a drag rather than a tap, in
   * screen pixels. Generous, because a child's tap wanders. */
  var DRAG_SLOP = 8;

  var specs = {};

  /* --- pure helpers, also run by the tests ------------------------------- */

  /* "{count} tiere" with count filled in. Unknown names are left as written,
   * which is louder than an empty string when a template and a caller drift. */
  function fill(template, values) {
    return String(template || "").replace(/\{(\w+)\}/g, function (match, name) {
      return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match;
    });
  }

  /* "5, 4 og 3". */
  function joinNumbers(values, and) {
    var words = values.map(String);
    if (words.length <= 1) {
      return words.join("");
    }
    return words.slice(0, -1).join(", ") + " " + and + " " + words[words.length - 1];
  }

  /* `key_one` for exactly one, `key` otherwise. */
  function plural(say, key, count, extra) {
    var values = { count: count };
    for (var name in extra || {}) {
      values[name] = extra[name];
    }
    return fill(count === 1 && say[key + "_one"] ? say[key + "_one"] : say[key], values);
  }

  /* A whole number from 0 to max, or null. States arrive from a field anybody
   * can edit, so every count is checked rather than trusted. */
  function count(value, max) {
    return typeof value === "number" && value === Math.floor(value) && value >= 0 && value <= max
      ? value
      : null;
  }

  /* The action a button stands for, read off its data attributes. */
  function actionOf(element) {
    var data = element.dataset || {};
    var action = { type: data.action };
    if (data.zone !== undefined) action.zone = data.zone;
    if (data.from !== undefined) action.from = data.from;
    if (data.to !== undefined) action.to = data.to;
    if (data.by !== undefined) action.by = parseInt(data.by, 10);
    return action;
  }

  /* --- the page ------------------------------------------------------------ */

  function readJSON(element, name) {
    try {
      return JSON.parse(element.getAttribute(name) || "{}");
    } catch (error) {
      return {};
    }
  }

  function setup(root) {
    if (root.hasAttribute(READY)) {
      return;
    }
    var spec = specs[root.getAttribute("data-activity")];
    if (!spec) {
      return;
    }
    root.setAttribute(READY, "");

    var limits = readJSON(root, "data-limits");
    var say = readJSON(root, "data-say");
    var field = root.querySelector("[data-state]");
    var board = root.querySelector("[data-board]");
    var status = root.querySelector("[data-status]");
    var fallback = root.querySelector("[data-fallback]");
    if (!field || !board) {
      return;
    }

    var state = spec.parse(field.value, limits);
    if (state === null) {
      /* The server's own starting state did not parse. Leave the typed
       * question in place rather than offer a board that cannot answer. */
      return;
    }

    /* Take over from the no-script question. */
    field.disabled = false;
    if (fallback) {
      fallback.hidden = true;
      var typed = fallback.querySelectorAll("input");
      for (var t = 0; t < typed.length; t++) {
        typed[t].disabled = true;
      }
    }
    var live = root.querySelectorAll("[data-live]");
    for (var l = 0; l < live.length; l++) {
      live[l].hidden = false;
    }

    var history = [];
    var pieces = board.querySelectorAll("[data-piece]");
    var buttons = root.querySelectorAll("[data-action]");
    var selected = null;

    function piece(element) {
      return {
        zone: element.getAttribute("data-zone"),
        index: parseInt(element.getAttribute("data-index"), 10),
        row: parseInt(element.getAttribute("data-row"), 10),
        col: parseInt(element.getAttribute("data-col"), 10),
      };
    }

    function render() {
      for (var i = 0; i < pieces.length; i++) {
        var p = piece(pieces[i]);
        /* The tray's pieces are always there: they are where new ones come
         * from, not part of the answer. */
        var on = p.zone.indexOf("supply") === 0 || spec.shown(state, p, limits);
        if (on) {
          pieces[i].removeAttribute("hidden");
        } else {
          pieces[i].setAttribute("hidden", "");
        }
      }
      if (spec.render) {
        spec.render(root, state, limits);
      }
      for (var b = 0; b < buttons.length; b++) {
        var action = actionOf(buttons[b]);
        buttons[b].disabled =
          action.type === "undo" ? history.length === 0 : spec.apply(state, action, limits) === null;
      }
      field.value = JSON.stringify(state);
      if (status) {
        status.textContent = spec.describe(state, say, limits);
      }
    }

    /* Every change goes through here, so every change can be undone. */
    function commit(next) {
      if (next === null || next === undefined) {
        return false;
      }
      history.push(state);
      state = next;
      render();
      return true;
    }

    function undo() {
      if (history.length) {
        state = history.pop();
        render();
      }
    }

    function dispatch(action) {
      return commit(spec.apply(state, action, limits));
    }

    function select(element) {
      if (selected) {
        selected.classList.remove("is-selected");
      }
      selected = element;
      if (selected) {
        selected.classList.add("is-selected");
      }
    }

    for (var k = 0; k < buttons.length; k++) {
      buttons[k].addEventListener("click", function (event) {
        var action = actionOf(event.currentTarget);
        select(null);
        if (action.type === "undo") {
          undo();
        } else {
          dispatch(action);
        }
      });
    }

    root.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && (event.key === "z" || event.key === "Z")) {
        event.preventDefault();
        undo();
      } else if (event.key === "Escape") {
        select(null);
      }
    });

    /* A drop target under a point: a piece stands for its own zone, so a
     * counter let go over another counter lands in that one's ring. */
    function targetAt(x, y) {
      var hit = document.elementFromPoint(x, y);
      if (!hit || !board.contains(hit)) {
        return null;
      }
      var over = hit.closest("[data-piece]");
      if (over) {
        return piece(over);
      }
      var zone = hit.closest("[data-drop]");
      if (!zone) {
        return null;
      }
      var index = zone.getAttribute("data-index");
      return { zone: zone.getAttribute("data-drop"), index: index === null ? -1 : parseInt(index, 10) };
    }

    function move(from, to) {
      return dispatch({
        type: "move",
        from: from.zone,
        fromIndex: from.index,
        to: to.zone,
        toIndex: to.index,
      });
    }

    /* A tap: pick up, put down, act, or add. */
    function tap(element, target) {
      if (element) {
        var here = piece(element);
        if (selected === element) {
          select(null);
          dispatch({ type: "act", zone: here.zone, index: here.index });
          return;
        }
        if (selected && piece(selected).zone !== here.zone) {
          var from = piece(selected);
          select(null);
          move(from, here);
          return;
        }
        select(element);
        return;
      }
      if (!target) {
        select(null);
        return;
      }
      if (selected) {
        var picked = piece(selected);
        select(null);
        move(picked, target);
        return;
      }
      dispatch({ type: "add", zone: target.zone, index: target.index });
    }

    var press = null;

    if (spec.pointer !== false) {
      board.addEventListener("pointerdown", function (event) {
        var element = event.target.closest("[data-piece]");
        press = {
          id: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          element: element,
          dragging: false,
        };
        if (element) {
          /* Captured on the board, not the piece, so the piece can be hidden
           * from hit-testing while it follows the finger. */
          board.setPointerCapture(event.pointerId);
          event.preventDefault();
        }
      });

      board.addEventListener("pointermove", function (event) {
        if (!press || press.id !== event.pointerId || !press.element) {
          return;
        }
        var dx = event.clientX - press.x;
        var dy = event.clientY - press.y;
        if (!press.dragging && Math.abs(dx) + Math.abs(dy) < DRAG_SLOP) {
          return;
        }
        press.dragging = true;
        press.element.classList.add("is-dragging");
        /* Screen pixels to board units, so the piece stays under the finger
         * at any rendered size. */
        var box = board.getBoundingClientRect();
        var view = board.viewBox.baseVal;
        var scale = box.width ? view.width / box.width : 1;
        press.element.setAttribute(
          "transform",
          "translate(" + (dx * scale).toFixed(1) + " " + (dy * scale).toFixed(1) + ")"
        );
      });

      function release(event) {
        if (!press || press.id !== event.pointerId) {
          return;
        }
        var done = press;
        press = null;
        if (done.element) {
          done.element.classList.remove("is-dragging");
          done.element.removeAttribute("transform");
        }
        if (event.type === "pointercancel") {
          return;
        }
        if (done.dragging) {
          var to = targetAt(event.clientX, event.clientY);
          select(null);
          if (to) {
            move(piece(done.element), to);
          }
          return;
        }
        var at = targetAt(event.clientX, event.clientY);
        /* A tap on a piece is a tap on that piece even if the finger drifted
         * a few pixels off it. */
        tap(done.element, done.element ? null : at);
      }

      board.addEventListener("pointerup", release);
      board.addEventListener("pointercancel", release);
    }

    if (spec.bind) {
      spec.bind(root, {
        board: board,
        limits: limits,
        say: say,
        state: function () {
          return state;
        },
        dispatch: dispatch,
        commit: commit,
        /* For a drag that should undo as one step: show each position as it
         * passes, and record the step once at the end with `settle`. */
        preview: function (next) {
          if (next) {
            state = next;
            render();
          }
        },
        settle: function (before) {
          if (JSON.stringify(before) !== JSON.stringify(state)) {
            history.push(before);
            render();
          }
        },
        announce: function (text) {
          if (status) {
            status.textContent = text;
          }
        },
        /* A pointer event in board units. */
        toBoard: function (event) {
          var box = board.getBoundingClientRect();
          var view = board.viewBox.baseVal;
          if (!box.width) {
            return null;
          }
          return {
            x: view.x + ((event.clientX - box.left) / box.width) * view.width,
            y: view.y + ((event.clientY - box.top) / box.height) * view.height,
          };
        },
      });
    }

    render();
  }

  function scan() {
    var roots = document.querySelectorAll("[data-activity]");
    for (var i = 0; i < roots.length; i++) {
      setup(roots[i]);
    }
  }

  window.PensumActivity = {
    register: function (kind, spec) {
      specs[kind] = spec;
      scan();
    },
    fill: fill,
    joinNumbers: joinNumbers,
    plural: plural,
    count: count,
  };

  document.addEventListener("DOMContentLoaded", scan);

  /* Every question after the first arrives by htmx. Scanning the whole
   * document is free, because a board already set up is marked. */
  document.addEventListener("htmx:afterSwap", scan);
})();
