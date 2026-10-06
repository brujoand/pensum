/* Arkade balloons: one balloon at a time, true or false.
 *
 * The balloon carries a statement, or one spelling of a word the page speaks.
 * Swipe it left (or press the left arrow or the left button) to let it fly
 * away: that says it is true, and a true one earns a point. Swipe it right to
 * send it up to the needle: that says it is false. Getting either wrong costs
 * a life, and the round ends when the lives are gone. Popping a false balloon
 * is right and does nothing else.
 *
 * With the timer on, the balloon floats up for `data-seconds` and drifts off
 * the top: neither a point nor a life (design rule 4). Every balloon ends on
 * its correct form (rule 7), and the next one comes when the pupil asks.
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
  /* The rising balloon is the timer. Where calm mode or the device stops
   * animation it cannot be seen, and a balloon that leaves with no warning
   * breaks rule 5 -- so there it waits, as with the timer off. */
  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var timed = round.timed && !still;

  var FLY = 0;
  var POP = 1;
  /* How far a swipe has to travel to count, in pixels. Less is a tap or a
   * wobble, and the balloon goes back. */
  var SWIPE = 60;
  /* How long the fly-away or the trip to the needle plays before the answer
   * shows. Without animation it is only a short pause. */
  var LEAVE_MS = still ? 150 : 700;

  var position = document.getElementById("balloons-position");
  var livesLine = document.getElementById("balloons-lives");
  var ruleLine = document.getElementById("balloons-rule");
  var hear = document.getElementById("balloons-hear");
  var sayButton = document.getElementById("balloons-say");
  var balloonEl = document.getElementById("balloons-balloon");
  var shownEl = document.getElementById("balloons-shown");
  var choices = document.getElementById("balloons-choices");
  var flyButton = document.getElementById("balloons-fly");
  var popButton = document.getElementById("balloons-pop");
  var feedback = document.getElementById("balloons-feedback");
  var nextButton = document.getElementById("balloons-next");
  var result = document.getElementById("balloons-result");
  var noVoice = document.getElementById("balloons-no-voice");
  var rules = document.getElementById("balloons-rules").content;

  var picks = [];
  var index = 0;
  var lives = round.lives || 3;
  var timer = null;
  var done = false;
  var finished = false;

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

  /* --- one balloon ---------------------------------------------------------- */

  function ruleText(rule) {
    var node = rules.querySelector('[data-rule="' + rule + '"]');
    return node ? node.textContent : "";
  }

  function showLives() {
    var hearts = "";
    for (var i = 0; i < (round.lives || 3); i++) hearts += i < lives ? "♥" : "♡";
    livesLine.textContent = root.dataset.labelLives.replace("{n}", String(lives)) + " " + hearts;
  }

  function setBalloonClass(extra) {
    balloonEl.className = "balloon balloon--" + (index % 4) + (extra ? " " + extra : "");
  }

  function show(item) {
    done = false;
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    nextButton.hidden = true;
    choices.hidden = false;
    position.textContent = root.dataset.labelPosition
      .replace("{n}", String(index + 1))
      .replace("{total}", String(items.length));
    ruleLine.textContent = ruleText(item.rule);
    hear.hidden = !item.spoken;
    shownEl.textContent = item.shown;
    balloonEl.disabled = false;
    balloonEl.style.transform = "";
    balloonEl.style.setProperty("--balloon-seconds", seconds + "s");
    setBalloonClass(timed ? "balloon--rising" : "");
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
    balloonEl.disabled = true;
    choices.hidden = true;
    balloonEl.style.transform = "";

    var label;
    var right = false;
    if (pick === null) {
      setBalloonClass("balloon--drifted");
      label = root.dataset.labelDrifted;
    } else if (pick === FLY) {
      setBalloonClass("balloon--fly");
      right = item.true;
      label = item.true ? root.dataset.labelPoint : root.dataset.labelLostFalse;
    } else {
      setBalloonClass("balloon--to-needle");
      right = !item.true;
      label = item.true ? root.dataset.labelLostTrue : root.dataset.labelPoppedFalse;
    }
    if (pick !== null && !right) {
      lives -= 1;
      showLives();
    }

    window.setTimeout(function () {
      if (pick === POP) setBalloonClass("balloon--popped");
      feedback.textContent = label + " " + item.answer;
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
    hear.hidden = true;
    choices.hidden = true;
    balloonEl.hidden = true;
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
        /* Say what happened and offer the same button again: pressing it
         * sends the same picks once more. */
        feedback.textContent = root.dataset.labelFailed;
        nextButton.hidden = false;
      });
  }

  /* --- swiping -------------------------------------------------------------- */

  var startX = null;

  balloonEl.addEventListener("pointerdown", function (event) {
    if (done) return;
    startX = event.clientX;
    if (balloonEl.setPointerCapture) balloonEl.setPointerCapture(event.pointerId);
  });

  balloonEl.addEventListener("pointermove", function (event) {
    if (startX === null || done) return;
    balloonEl.style.transform = "translateX(" + (event.clientX - startX) + "px)";
  });

  function release(event) {
    if (startX === null) return;
    var dx = event.clientX - startX;
    startX = null;
    if (done) return;
    balloonEl.style.transform = "";
    if (dx <= -SWIPE) answer(items[index], FLY);
    else if (dx >= SWIPE) answer(items[index], POP);
  }

  balloonEl.addEventListener("pointerup", release);
  balloonEl.addEventListener("pointercancel", function () {
    startX = null;
    balloonEl.style.transform = "";
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

  nextButton.addEventListener("click", function () {
    if (finished) {
      finish();
      return;
    }
    next();
  });
  sayButton.addEventListener("click", function () {
    say(items[index]);
  });

  showLives();
  show(items[0]);
})();
