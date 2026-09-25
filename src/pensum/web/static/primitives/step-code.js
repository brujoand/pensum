/* Step code: command tiles that move a robot through a grid.
 *
 * Pure rules over a state `{program, cursor}`; `core.js` does the page. The
 * program is nested JSON -- "step", "left", "right", {repeat: n, do: [...]},
 * {if_wall: [...]} -- and the cursor is where the next tile goes, as a path of
 * indices into the nesting. The server (`pensum.items.primitives.step_code`)
 * refuses a program these rules could not have built and grades by running it
 * with the same rules as `stepCodeTrace` below.
 *
 * The board shows the robot at the start. Run, one step and back to start move
 * it by showing and hiding the pieces the server drew, one pose per frame;
 * they change nothing that is submitted. Under the calm setting, or when the
 * device asks for less motion, Run shows the last frame at once, and one step
 * is always one frame.
 *
 * The program is written into a list whose every line is a button: tapping a
 * line puts the marker after it, and a tile's button inserts at the marker.
 * Dragging a tile onto a line inserts it after that line. The keyboard path is
 * the same buttons.
 */
(function () {
  "use strict";

  var DX = [0, 1, 0, -1];
  var DY = [-1, 0, 1, 0];
  var SIMPLE = ["step", "left", "right"];
  var FRAME_MS = 450;
  var DRAG_SLOP = 8;

  function stepCodeBody(command) {
    if (command && typeof command === "object") {
      if (Array.isArray(command.do)) return command.do;
      if (Array.isArray(command.if_wall)) return command.if_wall;
    }
    return null;
  }

  function stepCodeCount(program) {
    var total = 0;
    for (var i = 0; i < program.length; i++) {
      total += 1;
      var inner = stepCodeBody(program[i]);
      if (inner) total += stepCodeCount(inner);
    }
    return total;
  }

  /* Whether a program is one this item's tiles could build: its tiles, its
   * repeat counts, blocks no deeper than depth - 1, and no keys beyond. */
  function stepCodeAllowed(program, limits, depth) {
    if (!Array.isArray(program)) return false;
    for (var i = 0; i < program.length; i++) {
      var c = program[i];
      if (typeof c === "string") {
        if (SIMPLE.indexOf(c) < 0 || limits.tiles.indexOf(c) < 0) return false;
        continue;
      }
      if (!c || typeof c !== "object" || Array.isArray(c)) return false;
      var keys = Object.keys(c).sort().join(",");
      if (depth >= limits.depth) return false;
      if (keys === "do,repeat") {
        if (limits.tiles.indexOf("repeat") < 0 || limits.repeats.indexOf(c.repeat) < 0) return false;
        if (!stepCodeAllowed(c.do, limits, depth + 1)) return false;
      } else if (keys === "if_wall") {
        if (limits.tiles.indexOf("if_wall") < 0) return false;
        if (!stepCodeAllowed(c.if_wall, limits, depth + 1)) return false;
      } else {
        return false;
      }
    }
    return depth > 1 || stepCodeCount(program) <= limits.max;
  }

  /* The list a cursor points into, or null if the path is not one. */
  function stepCodeListAt(program, path) {
    var here = program;
    for (var i = 0; i < path.length; i++) {
      var index = path[i];
      if (!here || typeof index !== "number" || index !== Math.floor(index)) return null;
      if (index < 0 || index >= here.length) return null;
      here = stepCodeBody(here[index]);
    }
    return here;
  }

  function stepCodeValidCursor(program, cursor, limits) {
    if (!Array.isArray(cursor) || cursor.length < 1 || cursor.length > limits.depth) return false;
    var list = stepCodeListAt(program, cursor.slice(0, -1));
    var last = cursor[cursor.length - 1];
    return !!list && typeof last === "number" && last === Math.floor(last) && last >= 0 && last <= list.length;
  }

  function stepCodeParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    var program = raw.program === undefined ? [] : raw.program;
    var cursor = raw.cursor === undefined ? [0] : raw.cursor;
    if (!stepCodeAllowed(program, limits, 1)) return null;
    if (!stepCodeValidCursor(program, cursor, limits)) return null;
    return { program: JSON.parse(JSON.stringify(program)), cursor: cursor.slice() };
  }

  /* "0.2.1" as a path, or null. */
  function stepCodePath(text) {
    if (typeof text !== "string" || !/^\d+(\.\d+)*$/.test(text)) return null;
    return text.split(".").map(Number);
  }

  function stepCodeApply(state, action, limits) {
    var program = JSON.parse(JSON.stringify(state.program));
    var cursor = state.cursor.slice();
    var list;
    var last;
    if (action.type === "cursor") {
      var to = stepCodePath(action.zone);
      if (!to || !stepCodeValidCursor(program, to, limits)) return null;
      if (to.join(".") === cursor.join(".")) return null;
      return { program: program, cursor: to };
    }
    if (action.type === "add") {
      if (action.at !== undefined) {
        var at = stepCodePath(action.at);
        if (!at || !stepCodeValidCursor(program, at, limits)) return null;
        cursor = at;
      }
      var tile = action.zone;
      if (limits.tiles.indexOf(tile) < 0) return null;
      if (stepCodeCount(program) + 1 > limits.max) return null;
      var command = tile;
      if (tile === "repeat") {
        if (limits.repeats.indexOf(action.by) < 0) return null;
        command = { repeat: action.by, do: [] };
      } else if (tile === "if_wall") {
        command = { if_wall: [] };
      }
      var block = typeof command !== "string";
      if (block && cursor.length >= limits.depth) return null;
      list = stepCodeListAt(program, cursor.slice(0, -1));
      last = cursor[cursor.length - 1];
      list.splice(last, 0, command);
      /* After a simple tile the marker moves past it; into a block's body
       * after a block, which is where its first tile belongs. */
      cursor = block ? cursor.slice(0, -1).concat([last, 0]) : cursor.slice(0, -1).concat([last + 1]);
      return { program: program, cursor: cursor };
    }
    if (action.type === "out") {
      if (cursor.length < 2) return null;
      var outer = cursor.slice(0, -1);
      outer[outer.length - 1] += 1;
      return { program: program, cursor: outer };
    }
    if (action.type === "remove") {
      list = stepCodeListAt(program, cursor.slice(0, -1));
      last = cursor[cursor.length - 1];
      if (last > 0) {
        list.splice(last - 1, 1);
        cursor[cursor.length - 1] = last - 1;
        return { program: program, cursor: cursor };
      }
      /* At the start of an empty block: the block itself goes. */
      if (cursor.length < 2 || list.length) return null;
      var parent = stepCodeListAt(program, cursor.slice(0, -2));
      var index = cursor[cursor.length - 2];
      parent.splice(index, 1);
      return { program: program, cursor: cursor.slice(0, -2).concat([index]) };
    }
    return null;
  }

  function stepCodeBlocked(limits, x, y) {
    if (x < 0 || y < 0 || x >= limits.width || y >= limits.height) return true;
    for (var i = 0; i < limits.walls.length; i++) {
      if (limits.walls[i][0] === x && limits.walls[i][1] === y) return true;
    }
    return false;
  }

  /* Run a program on the grid: every pose, and how it ended. The same rules as
   * `StepCodeActivity.trace`, command for command and count for count. */
  function stepCodeTrace(program, limits) {
    var pose = limits.start.slice();
    var poses = [pose.slice()];
    var budget = limits.limit;

    function run(body) {
      for (var i = 0; i < body.length; i++) {
        var c = body[i];
        budget -= 1;
        if (budget < 0) return "limit";
        var f = pose[2];
        if (c === "step") {
          var nx = pose[0] + DX[f];
          var ny = pose[1] + DY[f];
          if (stepCodeBlocked(limits, nx, ny)) return "wall";
          pose = [nx, ny, f];
          poses.push(pose.slice());
        } else if (c === "left" || c === "right") {
          pose = [pose[0], pose[1], (f + (c === "left" ? 3 : 1)) % 4];
          poses.push(pose.slice());
        } else if (c && Array.isArray(c.do)) {
          for (var n = 0; n < c.repeat; n++) {
            var stop = run(c.do);
            if (stop) return stop;
            budget -= 1;
            if (budget < 0) return "limit";
          }
        } else if (c && Array.isArray(c.if_wall)) {
          if (stepCodeBlocked(limits, pose[0] + DX[f], pose[1] + DY[f])) {
            var inner = run(c.if_wall);
            if (inner) return inner;
          }
        }
      }
      return null;
    }

    var stopped = run(program);
    if (stopped) return { poses: poses, outcome: stopped };
    var home = pose[0] === limits.goal[0] && pose[1] === limits.goal[1];
    return { poses: poses, outcome: home ? "goal" : "short" };
  }

  function stepCodePoseIndex(pose, limits) {
    return (pose[1] * limits.width + pose[0]) * 4 + pose[2];
  }

  /* The board as drawn: the robot at the start, no trail. */
  function stepCodeShown(state, piece, limits) {
    if (piece.zone === "bot") return piece.index === stepCodePoseIndex(limits.start, limits);
    return false;
  }

  function stepCodeHead(command, say) {
    var fill = window.PensumActivity.fill;
    return Array.isArray(command.do) ? fill(say.repeat, { n: command.repeat }) : say.if_wall;
  }

  /* The program in one line, as `words` says it on the server. */
  function stepCodeWords(program, say) {
    var fill = window.PensumActivity.fill;
    return program
      .map(function (c) {
        if (typeof c === "string") return say[c];
        var inner = stepCodeBody(c);
        return fill(say.block, {
          head: stepCodeHead(c, say),
          body: inner.length ? stepCodeWords(inner, say) : "—",
        });
      })
      .join(", ");
  }

  function stepCodeDescribe(state, say) {
    var n = stepCodeCount(state.program);
    if (!n) return say.empty;
    return window.PensumActivity.plural(say, "made", n, { tiles: stepCodeWords(state.program, say) });
  }

  /* The program as Python-like text, as `as_text` writes it. */
  function stepCodeText(program, say, depth) {
    var fill = window.PensumActivity.fill;
    var pad = new Array((depth || 0) + 1).join("    ");
    var lines = [];
    for (var i = 0; i < program.length; i++) {
      var c = program[i];
      if (typeof c === "string") {
        lines.push(pad + say["py_" + c]);
        continue;
      }
      lines.push(pad + (Array.isArray(c.do) ? fill(say.py_repeat, { n: c.repeat }) : say.py_if));
      var inner = stepCodeBody(c);
      lines.push(inner.length ? stepCodeText(inner, say, (depth || 0) + 1) : pad + "    " + say.py_pass);
    }
    return lines.join("\n");
  }

  /* The lines the program list shows. `after` is where the marker goes when
   * the line is tapped: straight after it in reading order, which for a
   * block's first line is inside its body. Every `after` is different. */
  function stepCodeLines(program, say, prefix, depth, out) {
    out = out || [{ text: say.start_line, depth: 0, after: [0] }];
    prefix = prefix || [];
    depth = depth || 0;
    for (var i = 0; i < program.length; i++) {
      var c = program[i];
      if (typeof c === "string") {
        out.push({ text: say[c], depth: depth, after: prefix.concat([i + 1]) });
        continue;
      }
      out.push({ text: stepCodeHead(c, say), depth: depth, after: prefix.concat([i, 0]) });
      stepCodeLines(stepCodeBody(c), say, prefix.concat([i]), depth + 1, out);
      out.push({ text: say.end, depth: depth, after: prefix.concat([i + 1]) });
    }
    return out;
  }

  /* --- the page -------------------------------------------------------------- */

  var players = typeof WeakMap === "function" ? new WeakMap() : null;

  function stepCodeCalm() {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    return reduce || document.documentElement.hasAttribute("data-calm");
  }

  function stepCodeRender(root, state) {
    var player = players && players.get(root);
    if (player) player.stop();
    var list = root.querySelector("[data-program]");
    var say = player ? player.say : null;
    if (!list || !say) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    var lines = stepCodeLines(state.program, say);
    var here = state.cursor.join(".");
    for (var i = 0; i < lines.length; i++) {
      var item = document.createElement("li");
      item.className = "code-line code-depth-" + Math.min(lines[i].depth, 3);
      var button = document.createElement("button");
      button.type = "button";
      button.className = "code-line-button";
      button.setAttribute("data-at", lines[i].after.join("."));
      button.textContent = lines[i].text;
      item.appendChild(button);
      list.appendChild(item);
      if (lines[i].after.join(".") === here) {
        var marker = document.createElement("li");
        marker.className = "code-cursor code-depth-" + Math.min(state.cursor.length - 1, 3);
        marker.setAttribute("aria-current", "step");
        marker.textContent = say.cursor;
        list.appendChild(marker);
      }
    }
    var text = root.querySelector("[data-text]");
    if (text) text.textContent = stepCodeText(state.program, say);
  }

  function stepCodeBind(root, api) {
    var limits = api.limits;
    var pieces = api.board.querySelectorAll("[data-piece]");
    var timer = null;
    var frame = 0;

    function show(poses, k) {
      var visited = {};
      for (var j = 0; j <= k; j++) visited[poses[j][1] * limits.width + poses[j][0]] = true;
      var at = stepCodePoseIndex(poses[k], limits);
      for (var i = 0; i < pieces.length; i++) {
        var zone = pieces[i].getAttribute("data-zone");
        var index = parseInt(pieces[i].getAttribute("data-index"), 10);
        var on = zone === "bot" ? index === at : zone === "trail" ? !!visited[index] : true;
        if (on) pieces[i].removeAttribute("hidden");
        else pieces[i].setAttribute("hidden", "");
      }
    }

    function stop() {
      if (timer) window.clearTimeout(timer);
      timer = null;
      frame = 0;
    }

    function traced() {
      return stepCodeTrace(api.state().program, limits);
    }

    function settleAt(result, k) {
      frame = k;
      show(result.poses, k);
      if (k === result.poses.length - 1) api.announce(api.say["run_" + result.outcome]);
    }

    function play() {
      stop();
      var result = traced();
      if (stepCodeCalm()) {
        settleAt(result, result.poses.length - 1);
        return;
      }
      var k = 0;
      (function next() {
        settleAt(result, k);
        if (k < result.poses.length - 1) {
          k += 1;
          timer = window.setTimeout(next, FRAME_MS);
        } else {
          timer = null;
        }
      })();
    }

    if (players) {
      players.set(root, { say: api.say, stop: stop });
    }

    function on(selector, handler) {
      var found = root.querySelector(selector);
      if (found) found.addEventListener("click", handler);
    }
    on("[data-run]", play);
    /* The board already shows the start, so one step shows the next pose. */
    on("[data-frame]", function () {
      if (timer) window.clearTimeout(timer);
      timer = null;
      var result = traced();
      settleAt(result, Math.min(frame + 1, result.poses.length - 1));
    });
    on("[data-reset]", function () {
      stop();
      show(traced().poses, 0);
    });

    var list = root.querySelector("[data-program]");
    if (list) {
      list.addEventListener("click", function (event) {
        var line = event.target.closest("[data-at]");
        if (line) api.dispatch({ type: "cursor", zone: line.getAttribute("data-at") });
      });
    }

    /* Drag a tile onto a line: it goes in after that line. A drag that lands
     * nowhere does nothing, and the click that follows a drag is swallowed so
     * the tile is not also added at the marker. */
    var press = null;
    var swallow = false;
    root.addEventListener(
      "click",
      function (event) {
        if (swallow) {
          swallow = false;
          event.stopPropagation();
          event.preventDefault();
        }
      },
      true
    );
    var tiles = root.querySelectorAll('[data-action="add"]');
    for (var t = 0; t < tiles.length; t++) {
      tiles[t].addEventListener("pointerdown", function (event) {
        press = { id: event.pointerId, x: event.clientX, y: event.clientY, tile: event.currentTarget, dragging: false };
        event.currentTarget.setPointerCapture(event.pointerId);
      });
      tiles[t].addEventListener("pointermove", function (event) {
        if (!press || press.id !== event.pointerId) return;
        if (!press.dragging && Math.abs(event.clientX - press.x) + Math.abs(event.clientY - press.y) >= DRAG_SLOP) {
          press.dragging = true;
          press.tile.classList.add("is-dragging");
        }
      });
      tiles[t].addEventListener("pointerup", function (event) {
        if (!press || press.id !== event.pointerId) return;
        var done = press;
        press = null;
        done.tile.classList.remove("is-dragging");
        if (!done.dragging) return;
        swallow = true;
        var hit = document.elementFromPoint(event.clientX, event.clientY);
        var line = hit && hit.closest ? hit.closest("[data-at]") : null;
        if (line && root.contains(line)) {
          var data = done.tile.dataset;
          api.dispatch({
            type: "add",
            zone: data.zone,
            by: data.by !== undefined ? parseInt(data.by, 10) : undefined,
            at: line.getAttribute("data-at"),
          });
        }
      });
      tiles[t].addEventListener("pointercancel", function () {
        if (press) press.tile.classList.remove("is-dragging");
        press = null;
      });
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("step_code", {
      parse: stepCodeParse,
      apply: stepCodeApply,
      shown: stepCodeShown,
      describe: stepCodeDescribe,
      render: stepCodeRender,
      bind: stepCodeBind,
      pointer: false,
    });
  }
})();
