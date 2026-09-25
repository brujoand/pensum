/* A scripted conversation: the pupil picks each of their lines.
 *
 * Pure rules over a state `{picks: [...]}`, the option index of every pick in
 * order, wrong ones included. The graph is in `limits.nodes`: for each node,
 * one opaque token per option, which decodes to where the option leads ("" to
 * stay) and the partner's reply to it. Right and wrong options are the same
 * length and alphabet, so the page source does not say which line is right;
 * `dialogueCrypt` must stay the same function as `outcome_token` on the
 * server. The server (`pensum.items.primitives.dialogue`) walks the same picks
 * through its own graph and grades on reaching an end.
 *
 * There are no pieces to show and hide. The conversation so far is written
 * into the log from the script's own text, the option buttons for the line
 * the conversation is at are shown and the rest hidden, and the drawn board,
 * which is the same conversation for the feedback, stands down. The browser's
 * voice can say the partner's last line; nothing is recorded.
 */
(function () {
  "use strict";

  /* XOR with a keystream seeded from the node and the option's place: FNV-1a
   * of the seed, then xorshift32. Its own inverse, so it encodes and decodes. */
  function dialogueCrypt(bytes, node, index) {
    var seed = new TextEncoder().encode("pensum-dialogue\x1f" + node + "\x1f" + index);
    var x = 0x811c9dc5;
    for (var i = 0; i < seed.length; i++) {
      x = Math.imul(x ^ seed[i], 0x01000193) >>> 0;
    }
    x = x || 0x9e3779b9;
    var out = [];
    for (var j = 0; j < bytes.length; j++) {
      x = (x ^ (x << 13)) >>> 0;
      x = (x ^ (x >>> 17)) >>> 0;
      x = (x ^ (x << 5)) >>> 0;
      out.push(bytes[j] ^ (x & 0xff));
    }
    return out;
  }

  /* What picking option `index` at `node` does: {n: next node or "", r:
   * {nb, en} reply or {}}. null for a token that does not decode. */
  function dialogueOutcome(limits, node, index) {
    var token = (limits.nodes[node] || [])[index];
    if (typeof token !== "string" || !/^([0-9a-f]{2})*$/.test(token)) return null;
    var bytes = [];
    for (var i = 0; i < token.length; i += 2) {
      bytes.push(parseInt(token.slice(i, i + 2), 16));
    }
    try {
      var outcome = JSON.parse(String.fromCharCode.apply(null, dialogueCrypt(bytes, node, index)));
      return outcome && typeof outcome.n === "string" ? outcome : null;
    } catch (error) {
      return null;
    }
  }

  /* The node a list of picks ends at, or null if one of them was impossible. */
  function dialogueAt(picks, limits) {
    var node = limits.start;
    for (var i = 0; i < picks.length; i++) {
      var options = limits.nodes[node];
      var pick = picks[i];
      if (!options || typeof pick !== "number" || pick !== Math.floor(pick)) return null;
      if (pick < 0 || pick >= options.length) return null;
      var outcome = dialogueOutcome(limits, node, pick);
      if (outcome === null) return null;
      if (outcome.n) node = outcome.n;
    }
    return node;
  }

  function dialogueParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object") {
      return null;
    }
    var picks = raw.picks === undefined ? [] : raw.picks;
    if (!Array.isArray(picks) || picks.length > limits.max) {
      return null;
    }
    return dialogueAt(picks, limits) === null ? null : { picks: picks.slice() };
  }

  function dialogueApply(state, action, limits) {
    if (action.type !== "pick") return null;
    var at = dialogueAt(state.picks, limits);
    var options = limits.nodes[at] || [];
    if (at !== action.zone || !(action.by >= 0 && action.by < options.length)) return null;
    if (state.picks.length >= limits.max) return null;
    return { picks: state.picks.concat([action.by]) };
  }

  function dialogueShown() {
    return false;
  }

  function dialogueDescribe(state, say, limits) {
    var done = (limits.nodes[dialogueAt(state.picks, limits)] || []).length === 0;
    return window.PensumActivity.plural(say, done ? "made" : "open", state.picks.length);
  }

  /* The conversation so far as [who, line] pairs, from the script's text. */
  function dialogueLines(state, limits, script) {
    var node = limits.start;
    var lines = [[script.partner, script.nodes[node].says]];
    for (var i = 0; i < state.picks.length; i++) {
      var pick = state.picks[i];
      var outcome = dialogueOutcome(limits, node, pick);
      lines.push([script.you, script.nodes[node].options[pick]]);
      if (outcome.n) {
        node = outcome.n;
        lines.push([script.partner, script.nodes[node].says]);
      } else {
        lines.push([script.partner, outcome.r[script.locale] || outcome.r.nb]);
      }
    }
    return lines;
  }

  function dialogueScript(root) {
    var log = root.querySelector("[data-log]");
    try {
      return log ? JSON.parse(log.getAttribute("data-script")) : null;
    } catch (error) {
      return null;
    }
  }

  function dialogueRender(root, state, limits) {
    var log = root.querySelector("[data-log]");
    var script = dialogueScript(root);
    if (!log || !script) return;
    var lines = dialogueLines(state, limits, script);
    while (log.firstChild) {
      log.removeChild(log.firstChild);
    }
    for (var i = 0; i < lines.length; i++) {
      var item = document.createElement("li");
      item.className = lines[i][0] === script.you ? "dialogue-line dialogue-line--you" : "dialogue-line";
      var who = document.createElement("strong");
      who.textContent = lines[i][0] + ": ";
      item.appendChild(who);
      item.appendChild(document.createTextNode(lines[i][1]));
      log.appendChild(item);
    }
    var at = dialogueAt(state.picks, limits);
    var buttons = root.querySelectorAll('[data-action="pick"]');
    for (var b = 0; b < buttons.length; b++) {
      buttons[b].hidden = buttons[b].getAttribute("data-zone") !== at;
    }
    root.setAttribute("data-last-line", lines[lines.length - 1][0] === script.partner ? lines[lines.length - 1][1] : "");
  }

  function dialogueBind(root, api) {
    /* The log is the live view; the drawn board is the feedback's. */
    api.board.style.display = "none";
    var say = window.PensumActivity.speech.setup(root, api.limits.language);
    var hear = root.querySelectorAll('[data-speak="line"]');
    for (var i = 0; i < hear.length; i++) {
      hear[i].addEventListener("click", function () {
        say(root.getAttribute("data-last-line"));
      });
    }
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("dialogue", {
      parse: dialogueParse,
      apply: dialogueApply,
      shown: dialogueShown,
      describe: dialogueDescribe,
      render: dialogueRender,
      bind: dialogueBind,
      pointer: false,
    });
  }
})();
