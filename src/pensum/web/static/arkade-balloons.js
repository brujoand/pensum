/* Arkade balloons: one balloon at a time, true or false.
 *
 * The balloon carries a statement, or one spelling of a word the page speaks.
 * The sky behind it is split: the left half is "true", the right half has the
 * needle and is "false". Swipe the balloon towards a half, tap the half, or
 * press the arrow key on that side.
 *
 * Swiped left, the balloon flies off up and to the left: a true one is a
 * point, a false one costs a life. Swiped right, it travels to the needle and
 * bursts: a false one is simply right, a true one costs a life. The round ends
 * when the lives are gone. A right answer says "Riktig!"; a wrong one also
 * shows the right form (design rule 7). The next balloon then comes by
 * itself, and the question mark says again what the one before should have
 * been.
 *
 * With the timer on, the balloon rises for `data-seconds` and drifts off the
 * top: neither a point nor a life (rule 4).
 *
 * The motion is done by hand, frame by frame: the balloon follows the finger,
 * leans and stretches with it, its thread trails behind in a wave and settles, and a
 * swipe too short to count springs back past the middle before it rests. In
 * calm mode, or where the device asks for less motion, none of it runs: the
 * balloon is simply there, and simply gone.
 *
 * At the end the page posts, per balloon, 0 for flown, 1 for popped, null for
 * drifted, and nothing for the balloons after the last life; the server marks
 * that against its own copy, lives included.
 *
 * Spoken words use the browser's own SpeechSynthesis, as the listening
 * exercise does: no audio is fetched and none is sent.
 */
(function () {
  "use strict";

  var root = document.getElementById("balloons");
  var data = document.getElementById("balloons-round");
  if (!root || !data) return;

  var round = JSON.parse(data.textContent);
  var items = round.items;
  var seconds = Number(root.dataset.seconds) || 60;
  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  /* The rising balloon is the timer. Where it cannot be seen to rise, a balloon
   * that leaves with no warning breaks rule 5, so there it waits. */
  var timed = round.timed && !still;
  var raf = window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : null;
  var motion = !still && !!raf;

  var FLY = 0;
  var POP = 1;
  /* How far a swipe has to travel to count, in pixels. */
  var SWIPE = 60;
  /* How long the fly-away or the trip to the needle plays before the answer
   * shows. Without motion it is only a short pause. */
  var LEAVE_MS = motion ? 900 : 150;
  /* How long the answer stays before the next balloon comes by itself. A
   * wrong one stays longer: it shows the right form, which has to be read. */
  var NEXT_RIGHT_MS = 900;
  var NEXT_WRONG_MS = 1800;

  var position = document.getElementById("balloons-position");
  var livesLine = document.getElementById("balloons-lives");
  var ruleLine = document.getElementById("balloons-rule");
  var hear = document.getElementById("balloons-hear");
  var sayButton = document.getElementById("balloons-say");
  var sky = document.getElementById("balloons-sky");
  var balloonEl = document.getElementById("balloons-balloon");
  var stringEl = document.getElementById("balloons-string");
  var shownEl = document.getElementById("balloons-shown");
  var burstEl = document.getElementById("balloons-burst");
  var flyButton = document.getElementById("balloons-fly");
  var popButton = document.getElementById("balloons-pop");
  var feedback = document.getElementById("balloons-feedback");
  var retryButton = document.getElementById("balloons-retry");
  var previousButton = document.getElementById("balloons-previous");
  var result = document.getElementById("balloons-result");
  var noVoice = document.getElementById("balloons-no-voice");
  var rules = document.getElementById("balloons-rules").content;
  var flyName = flyButton.getAttribute("aria-label") || "";
  var popName = popButton.getAttribute("aria-label") || "";

  var picks = [];
  var index = 0;
  var lives = round.lives || 3;
  var timer = null;
  var done = false;
  var finished = false;
  /* The balloon answered last: what the question mark tells about. */
  var previous = null;
  var sending = false;

  /* --- speaking ------------------------------------------------------------ */

  var VOICE_LANGS = { nb: ["nb", "no", "nn"], nn: ["nn", "nb", "no"], en: ["en"] };
  var speech = window.speechSynthesis;

  /* The same choice as listening.js: an earlier language in the table wins,
   * and a voice on the device beats a remote one, because a remote voice sends
   * the word to whoever the browser's vendor uses. */
  function pickVoice(voices, language) {
    var wanted = VOICE_LANGS[language] || [language];
    var best = null;
    var bestRank = Infinity;
    for (var i = 0; i < voices.length; i++) {
      var tag = String(voices[i].lang || "")
        .toLowerCase()
        .replace("_", "-");
      for (var j = 0; j < wanted.length; j++) {
        if (tag === wanted[j] || tag.indexOf(wanted[j] + "-") === 0) {
          var rank = j * 2 + (voices[i].localService ? 0 : 1);
          if (rank < bestRank) {
            bestRank = rank;
            best = voices[i];
          }
          break;
        }
      }
    }
    return best;
  }

  function say(item) {
    if (!speech || !item.spoken) return;
    var voice = pickVoice(speech.getVoices() || [], item.language);
    /* No voice for the language: say so rather than let the browser read a
     * Norwegian word with an English voice, which says a different word. */
    noVoice.hidden = !!voice;
    if (!voice) return;
    speech.cancel();
    var utterance = new window.SpeechSynthesisUtterance(item.spoken);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.85;
    speech.speak(utterance);
  }

  if (speech && speech.getVoices().length === 0) {
    /* Voices load late in some browsers. The first word was asked for before
     * there were any, so say it again once they arrive. */
    speech.addEventListener("voiceschanged", function () {
      if (!done && index < items.length) say(items[index]);
    });
  }


  /* --- motion ---------------------------------------------------------------- */

  /* The thread is a chain of points below the knot. Each follows the one
   * above it on a spring of its own, so a quick move travels down the thread
   * as a wave and the end swings furthest and settles last. */
  var THREAD_POINTS = 6;

  function restState() {
    var thread = [];
    var threadV = [];
    for (var i = 0; i < THREAD_POINTS; i++) {
      thread.push(0);
      threadV.push(0);
    }
    return { x: 0, y: 0, vx: 0, vy: 0, rot: 0, sx: 1, sy: 1, thread: thread, threadV: threadV, now: 0, opacity: 1 };
  }

  /* The balloon's state, in pixels and degrees from where it rests. `thread`
   * is where each point of the thread is, sideways, in the same pixels. */
  var m = restState();
  var mode = "idle";
  var dragX = 0;
  var lastDragX = 0;
  var shownAt = 0;
  var target = { x: 0, y: 0 };

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function reset() {
    m = restState();
    mode = "idle";
  }

  function render() {
    balloonEl.style.transform =
      "translate(" + m.x.toFixed(1) + "px," + m.y.toFixed(1) + "px) rotate(" +
      m.rot.toFixed(2) + "deg) scale(" + m.sx.toFixed(3) + "," + m.sy.toFixed(3) + ")";
    balloonEl.style.opacity = String(Math.max(0, m.opacity));
    /* The thread is drawn in the balloon's own units (100 across), from the
     * knot at 121 down to 198, as one smooth line through its points. While
     * the balloon floats a faint ripple runs down it, wider towards the end. */
    var width = balloonEl.offsetWidth || 100;
    var xs = [50];
    var ys = [121];
    for (var i = 0; i < THREAD_POINTS; i++) {
      var part = (i + 1) / THREAD_POINTS;
      var bend = clamp(((m.thread[i] - m.x) * 100) / width, -45, 45);
      var ripple = motion ? Math.sin(m.now / 320 - i * 1.1) * 1.6 * part : 0;
      xs.push(50 + bend + ripple);
      ys.push(121 + 77 * part);
    }
    var d = "M50 121";
    for (var j = 1; j < THREAD_POINTS; j++) {
      d +=
        " Q" + xs[j].toFixed(1) + " " + ys[j].toFixed(1) + " " +
        ((xs[j] + xs[j + 1]) / 2).toFixed(1) + " " + ((ys[j] + ys[j + 1]) / 2).toFixed(1);
    }
    d += " L " + xs[THREAD_POINTS].toFixed(1) + " 198";
    stringEl.setAttribute("d", d);
  }

  function step(now) {
    m.now = now;
    var lead = m.x;
    for (var i = 0; i < THREAD_POINTS; i++) {
      m.threadV[i] = (m.threadV[i] + (lead - m.thread[i]) * 0.16) * 0.8;
      m.thread[i] += m.threadV[i];
      lead = m.thread[i];
    }

    /* The timer: while it rests, is dragged or springs back, the balloon is
     * as high as the time gone says, measured from when it was shown. */
    if (timed && !done && (mode === "idle" || mode === "drag" || mode === "spring")) {
      m.y = -riseDistance() * Math.min(1, (now - shownAt) / (seconds * 1000));
    }
    /* A slow sway while it waits, so it looks like it is floating. */
    var sway = Math.sin(now / 1300) * 4;

    if (mode === "idle") {
      m.x = sway;
      m.rot = Math.sin(now / 900) * 2;
    } else if (mode === "drag") {
      m.vx = dragX - lastDragX;
      lastDragX = dragX;
      m.x = dragX;
      m.rot = clamp(dragX * 0.08, -22, 22);
      /* Stretch along a quick move, the way a rubber balloon does. */
      var s = Math.min(Math.abs(m.vx) * 0.012, 0.14);
      m.sx += (1 - s - m.sx) * 0.4;
      m.sy += (1 + s - m.sy) * 0.4;
    } else if (mode === "spring") {
      /* Under-damped, so a short swipe swings back past the middle once. */
      m.vx = (m.vx - (m.x - sway) * 0.09) * 0.86;
      m.x += m.vx;
      m.rot = (m.x - sway) * 0.08;
      m.sx += (1 - m.sx) * 0.2;
      m.sy += (1 - m.sy) * 0.2;
      if (Math.abs(m.x - sway) < 0.4 && Math.abs(m.vx) < 0.4) mode = "idle";
    } else if (mode === "fly") {
      m.vx -= 0.35;
      m.vy -= 0.55;
      m.x += m.vx;
      m.y += m.vy;
      m.rot = Math.max(m.rot - 0.7, -32);
      m.sx += (0.92 - m.sx) * 0.1;
      m.sy += (1.08 - m.sy) * 0.1;
      m.opacity -= 0.012;
    } else if (mode === "needle") {
      m.x += (target.x - m.x) * 0.14;
      m.y += (target.y - m.y) * 0.14;
      m.rot += (14 - m.rot) * 0.1;
      if (Math.abs(target.x - m.x) < 3 && Math.abs(target.y - m.y) < 3) burst();
    } else if (mode === "drift") {
      m.vy -= 0.18;
      m.y += m.vy;
      m.opacity -= 0.015;
    }
  }

  function frame(now) {
    step(now);
    render();
    if (!finished) raf(frame);
  }

  function riseDistance() {
    return (sky.clientHeight || 400) * 0.45;
  }

  /* Where the needle's point is, from where the balloon rests. */
  function needleTarget() {
    var needle = popButton.querySelector ? popButton.querySelector(".balloons__needle") : null;
    if (!needle || !needle.getBoundingClientRect) return { x: 160, y: -260 };
    var n = needle.getBoundingClientRect();
    var b = balloonEl.getBoundingClientRect();
    var restLeft = b.left - m.x;
    var restTop = b.top - m.y;
    return { x: n.left + n.width / 2 - (restLeft + b.width / 2), y: n.bottom - restTop + 4 };
  }

  function burst() {
    mode = "gone";
    balloonEl.classList.add("balloon--gone");
    if (!burstEl) return;
    var b = balloonEl.getBoundingClientRect ? balloonEl.getBoundingClientRect() : null;
    var s = sky.getBoundingClientRect ? sky.getBoundingClientRect() : null;
    if (b && s) {
      burstEl.style.left = (b.left - s.left + b.width / 2).toFixed(0) + "px";
      burstEl.style.top = (b.top - s.top + b.width * 0.35).toFixed(0) + "px";
    }
    burstEl.hidden = false;
    burstEl.classList.remove("balloons__burst--go");
    void burstEl.offsetWidth;
    burstEl.classList.add("balloons__burst--go");
  }

  /* --- one balloon ------------------------------------------------------------- */

  function ruleText(rule) {
    var node = rules.querySelector('[data-rule="' + rule + '"]');
    return node ? node.textContent : "";
  }

  function showLives() {
    var hearts = "";
    for (var i = 0; i < (round.lives || 3); i++) hearts += i < lives ? "♥" : "♡";
    livesLine.textContent = root.dataset.labelLives.replace("{n}", String(lives)) + " " + hearts;
  }

  function toward(side) {
    sky.classList.remove("balloons__sky--toward-fly");
    sky.classList.remove("balloons__sky--toward-pop");
    if (side) sky.classList.add("balloons__sky--toward-" + side);
  }

  function show(item) {
    done = false;
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    position.textContent = root.dataset.labelPosition
      .replace("{n}", String(index + 1))
      .replace("{total}", String(items.length));
    ruleLine.textContent = ruleText(item.rule);
    hear.hidden = !item.spoken;
    shownEl.textContent = item.shown;
    /* The text stays on one line: the stylesheet sizes it by its length. */
    shownEl.style.setProperty("--chars", String(item.shown.length));
    /* The halves are the answers; their names say what they answer. */
    flyButton.setAttribute("aria-label", flyName + ": " + item.shown);
    popButton.setAttribute("aria-label", popName + ": " + item.shown);
    balloonEl.className = "balloon balloon--" + (index % 4) + (timed ? " balloon--rising" : "");
    if (burstEl) burstEl.hidden = true;
    flyButton.disabled = false;
    popButton.disabled = false;
    toward(null);
    reset();
    shownAt = window.performance && window.performance.now ? window.performance.now() : 0;
    render();
    if (timed) timer = window.setTimeout(function () { answer(item, null); }, seconds * 1000);
    say(item);
  }

  function answer(item, pick) {
    if (done) return;
    done = true;
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
    picks.push(pick);
    flyButton.disabled = true;
    popButton.disabled = true;
    toward(null);

    var label;
    var right = false;
    if (pick === null) {
      label = root.dataset.labelDrifted + " " + item.answer;
      leave("drift");
    } else if (pick === FLY) {
      right = item.true;
      label = right ? root.dataset.labelRight : root.dataset.labelLostFalse + " " + item.answer;
      leave("fly");
    } else {
      right = !item.true;
      label = right ? root.dataset.labelRight : root.dataset.labelLostTrue + " " + item.answer;
      leave("needle");
    }
    if (pick !== null && !right) {
      lives -= 1;
      showLives();
    }

    window.setTimeout(function () {
      feedback.textContent = label;
      if (right) {
        feedback.classList.add("balloons__feedback--right");
        /* A right answer throws a little confetti from where it says so. */
        if (window.arkadeConfetti) window.arkadeConfetti(feedback);
      }
      previous = item;
      previousButton.hidden = false;
      /* The next balloon comes by itself. */
      window.setTimeout(next, right ? NEXT_RIGHT_MS : NEXT_WRONG_MS);
    }, LEAVE_MS);
  }

  function leave(how) {
    balloonEl.classList.add("balloon--" + (how === "needle" ? "popped" : how === "fly" ? "flown" : "drifted"));
    if (!motion) {
      balloonEl.classList.add("balloon--gone");
      return;
    }
    if (how === "needle") target = needleTarget();
    m.vx = how === "fly" ? Math.min(m.vx, -2) : 0;
    m.vy = how === "fly" ? -3 : 0;
    mode = how;
  }

  function next() {
    index += 1;
    if (lives > 0 && index < items.length) {
      show(items[index]);
      return;
    }
    finish();
  }

  function finish() {
    /* One save at a time: a second click while the first is on its way would
     * find the round already taken, and its 404 would replace the result. */
    if (sending) return;
    sending = true;
    finished = true;
    ruleLine.textContent = "";
    hear.hidden = true;
    sky.hidden = true;
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    retryButton.hidden = true;
    /* The round is over: the feedback line now belongs to the save. */
    previousButton.hidden = true;
    position.textContent = "";
    fetch(root.dataset.postUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ picks: picks }),
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) throw new Error("mark failed");
        return response.text();
      })
      .then(function (html) {
        result.innerHTML = html;
      })
      .catch(function () {
        /* Say what happened and offer the same button again: pressing it
         * sends the same picks once more. */
        sending = false;
        feedback.textContent = root.dataset.labelFailed;
        retryButton.hidden = false;
      });
  }

  /* --- swiping --------------------------------------------------------------- */

  var startX = null;

  balloonEl.addEventListener("pointerdown", function (event) {
    if (done) return;
    startX = event.clientX;
    dragX = 0;
    lastDragX = 0;
    mode = "drag";
    if (balloonEl.setPointerCapture) balloonEl.setPointerCapture(event.pointerId);
  });

  balloonEl.addEventListener("pointermove", function (event) {
    if (startX === null || done) return;
    dragX = event.clientX - startX;
    toward(dragX <= -SWIPE / 2 ? "fly" : dragX >= SWIPE / 2 ? "pop" : null);
    if (!motion) {
      m.x = dragX;
      render();
    }
  });

  function release(event) {
    if (startX === null) return;
    var dx = event.clientX - startX;
    startX = null;
    if (done) return;
    if (dx <= -SWIPE) return answer(items[index], FLY);
    if (dx >= SWIPE) return answer(items[index], POP);
    toward(null);
    if (motion) {
      mode = "spring";
    } else {
      reset();
      render();
    }
  }

  balloonEl.addEventListener("pointerup", release);
  balloonEl.addEventListener("pointercancel", function () {
    startX = null;
    toward(null);
    if (done) return;
    if (motion) {
      mode = "spring";
    } else {
      reset();
      render();
    }
  });

  flyButton.addEventListener("click", function () {
    answer(items[index], FLY);
  });
  popButton.addEventListener("click", function () {
    answer(items[index], POP);
  });

  /* The left and right arrow keys do what a swipe that way does. */
  document.addEventListener("keydown", function (event) {
    if (done || finished || index >= items.length) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    answer(items[index], event.key === "ArrowLeft" ? FLY : POP);
  });

  retryButton.addEventListener("click", finish);
  /* The question mark: what the balloon before this one should have been.
   * The next balloon comes without being asked for, so this is how a pupil
   * who wants the last answer again gets it. */
  previousButton.addEventListener("click", function () {
    if (!previous) return;
    feedback.className = "balloons__feedback";
    feedback.textContent = root.dataset.labelPrevious + " " + previous.answer;
  });
  sayButton.addEventListener("click", function () {
    say(items[index]);
  });

  /* The game fills the screen and nothing scrolls while it is played. */
  document.body.classList.add("arkade-play");
  showLives();
  show(items[0]);
  if (motion) raf(frame);
})();
