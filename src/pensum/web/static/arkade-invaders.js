/* Arkade invaders: one rule for the round, one target at a time.
 *
 * A target falls from the top of space towards the ship. Shoot it (tap it, or
 * press space or the up arrow) if it matches the rule; let it pass (swipe it
 * down, press the down arrow, or the arrow button by the ship) if it does not.
 * A match shot is a point. Shooting one that does not match, or letting a
 * match pass, costs a life, and the round ends when the lives are gone.
 *
 * With the timer on the target falls by itself over `data-seconds`. One that
 * does not match and reaches the bottom has rightly been let past; a match
 * that reaches the bottom is a miss, neither a point nor a life (design rule
 * 4). A right call says "Riktig!"; a wrong one also says what the target was
 * (rule 7).
 *
 * The motion is done by hand, frame by frame, and none of it runs in calm
 * mode or where the device asks for less motion: there the target waits,
 * as with the timer off.
 *
 * At the end the page posts, per target, 0 for shot, 1 for let past, null for
 * a missed match, and nothing after the last life.
 */
(function () {
  "use strict";

  var root = document.getElementById("invaders");
  var data = document.getElementById("invaders-round");
  if (!root || !data) return;

  var round = JSON.parse(data.textContent);
  var items = round.items;
  var seconds = Number(root.dataset.seconds) || 8;
  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var timed = round.timed && !still;
  var raf = window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : null;
  var motion = !still && !!raf;

  var SHOOT = 0;
  var PASS = 1;
  /* How far down a swipe has to travel to let a target pass, in pixels. */
  var SWIPE = 50;
  var LEAVE_MS = motion ? 650 : 150;

  var position = document.getElementById("invaders-position");
  var livesLine = document.getElementById("invaders-lives");
  var ruleLine = document.getElementById("invaders-rule");
  var space = document.getElementById("invaders-space");
  var target = document.getElementById("invaders-target");
  var token = document.getElementById("invaders-token");
  var beam = document.getElementById("invaders-beam");
  var burstEl = document.getElementById("invaders-burst");
  var passButton = document.getElementById("invaders-pass");
  var feedback = document.getElementById("invaders-feedback");
  var nextButton = document.getElementById("invaders-next");
  var result = document.getElementById("invaders-result");

  var picks = [];
  var index = 0;
  var lives = round.lives || 3;
  var timer = null;
  var done = false;
  var finished = false;

  ruleLine.textContent = round.rule;

  /* --- motion ---------------------------------------------------------------- */

  /* `y` is how far the target has fallen, from 0 to 1 of the way to the ship;
   * `dy` is a swipe in progress, in pixels. */
  var m = { y: 0, dy: 0, wobble: 0, opacity: 1, vy: 0 };
  var mode = "idle";
  var shownAt = 0;

  function fallDistance() {
    return Math.max(0, (space.clientHeight || 400) - (target.offsetHeight || 80) - 70);
  }

  function render() {
    var y = m.y * fallDistance() + m.dy;
    target.style.transform =
      "translate(-50%," + y.toFixed(1) + "px) rotate(" + m.wobble.toFixed(2) + "deg)";
    target.style.opacity = String(Math.max(0, m.opacity));
  }

  function step(now) {
    if (mode === "idle") {
      m.wobble = Math.sin(now / 500) * 3;
      if (timed && !done) {
        m.y = Math.min(1, (now - shownAt) / (seconds * 1000));
      } else if (!timed) {
        /* Untimed, it hovers a quarter of the way down and bobs. */
        m.y = 0.25 + Math.sin(now / 900) * 0.01;
      }
    } else if (mode === "spring") {
      m.dy *= 0.8;
      if (Math.abs(m.dy) < 0.5) {
        m.dy = 0;
        mode = "idle";
      }
    } else if (mode === "pass") {
      m.vy += 1.2;
      m.dy += m.vy;
      m.opacity -= 0.03;
    }
  }

  function frame(now) {
    step(now);
    render();
    if (!finished) raf(frame);
  }

  function zap() {
    /* The beam runs from the ship up to the target, then the target bursts. */
    var y = m.y * fallDistance() + m.dy;
    beam.style.height = Math.max(0, (space.clientHeight || 400) - y - 90).toFixed(0) + "px";
    beam.hidden = false;
    target.classList.add("invaders__target--gone");
    burstEl.style.left = "50%";
    burstEl.style.top = (y + (target.offsetHeight || 80) / 2).toFixed(0) + "px";
    burstEl.hidden = false;
    burstEl.classList.remove("balloons__burst--go");
    void burstEl.offsetWidth;
    burstEl.classList.add("balloons__burst--go");
    window.setTimeout(function () {
      beam.hidden = true;
    }, 180);
  }

  /* --- one target ------------------------------------------------------------ */

  function showLives() {
    var hearts = "";
    for (var i = 0; i < (round.lives || 3); i++) hearts += i < lives ? "♥" : "♡";
    livesLine.textContent = root.dataset.labelLives.replace("{n}", String(lives)) + " " + hearts;
  }

  function show(item) {
    done = false;
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    nextButton.hidden = true;
    position.textContent = root.dataset.labelPosition
      .replace("{n}", String(index + 1))
      .replace("{total}", String(items.length));
    token.textContent = item.shown;
    target.className = "invaders__target" + (timed ? " invaders__target--falling" : "");
    target.disabled = false;
    passButton.disabled = false;
    beam.hidden = true;
    burstEl.hidden = true;
    m = { y: timed ? 0 : 0.25, dy: 0, wobble: 0, opacity: 1, vy: 0 };
    mode = "idle";
    shownAt = window.performance && window.performance.now ? window.performance.now() : 0;
    render();
    if (timed) timer = window.setTimeout(function () { landed(item); }, seconds * 1000);
  }

  /* With the timer on, a target that reaches the bottom: let past if it does
   * not match, missed if it does. */
  function landed(item) {
    answer(item, item.true ? null : PASS);
  }

  function answer(item, pick) {
    if (done) return;
    done = true;
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
    picks.push(pick);
    target.disabled = true;
    passButton.disabled = true;

    var right = pick === SHOOT ? item.true : pick === PASS ? !item.true : false;
    var label;
    if (pick === null) {
      label = root.dataset.labelMissed + " " + item.answer;
    } else if (right) {
      label = root.dataset.labelRight;
    } else {
      label = root.dataset.labelWrong + " " + item.answer;
      lives -= 1;
      showLives();
    }

    if (pick === SHOOT) {
      zap();
    } else if (motion) {
      mode = "pass";
    } else {
      target.classList.add("invaders__target--gone");
    }

    window.setTimeout(function () {
      if (!motion) target.classList.add("invaders__target--gone");
      feedback.textContent = label;
      if (right) feedback.classList.add("balloons__feedback--right");
      nextButton.hidden = false;
      nextButton.focus();
    }, LEAVE_MS);
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
    finished = true;
    ruleLine.textContent = "";
    space.hidden = true;
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    nextButton.hidden = true;
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
        feedback.textContent = root.dataset.labelFailed;
        nextButton.hidden = false;
      });
  }

  /* --- controls ---------------------------------------------------------------- */

  /* A tap on the target shoots it. A drag downwards lets it pass, and the
   * click that follows the drag is not a shot. */
  var startY = null;
  var swiped = false;

  target.addEventListener("pointerdown", function (event) {
    if (done) return;
    startY = event.clientY;
    swiped = false;
    if (target.setPointerCapture) target.setPointerCapture(event.pointerId);
  });

  target.addEventListener("pointermove", function (event) {
    if (startY === null || done) return;
    var dy = event.clientY - startY;
    if (dy > 8) swiped = true;
    m.dy = Math.max(0, dy);
    if (!motion) render();
  });

  target.addEventListener("pointerup", function (event) {
    if (startY === null) return;
    var dy = event.clientY - startY;
    startY = null;
    if (done) return;
    if (dy >= SWIPE) return answer(items[index], PASS);
    if (motion) {
      mode = "spring";
    } else {
      m.dy = 0;
      render();
    }
  });

  target.addEventListener("click", function () {
    if (swiped) {
      swiped = false;
      return;
    }
    answer(items[index], SHOOT);
  });

  passButton.addEventListener("click", function () {
    answer(items[index], PASS);
  });

  document.addEventListener("keydown", function (event) {
    if (done || finished || index >= items.length) return;
    var key = event.key;
    /* Space on a focused button already clicks it. */
    var onButton = event.target && event.target.tagName === "BUTTON";
    if (key === "ArrowUp" || (key === " " && !onButton)) {
      event.preventDefault();
      answer(items[index], SHOOT);
    } else if (key === "ArrowDown") {
      event.preventDefault();
      answer(items[index], PASS);
    }
  });

  nextButton.addEventListener("click", function () {
    if (finished) {
      finish();
      return;
    }
    next();
  });

  showLives();
  show(items[0]);
  if (motion) raf(frame);
})();
