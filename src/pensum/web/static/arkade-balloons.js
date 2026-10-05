/* Arkade balloons: pop the balloon that fits the rule.
 *
 * The round is in the page as JSON. One item at a time: its balloons grow for
 * `data-seconds` and pop by themselves when the timer is on, and wait when it
 * is off. Whatever happens, the item ends on its correct form (design rule 7),
 * and the next one starts only when the pupil asks for it. At the end the page
 * sends which balloon was popped for each item, null where time ran out, and
 * shows what the server marked.
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
  /* The growing balloon is the timer. Where calm mode or the device stops
   * animation, it cannot be seen, and a balloon that pops with no warning
   * breaks rule 5 -- so there the balloons wait, as with the timer off. */
  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var timed = round.timed && !still;

  var position = document.getElementById("balloons-position");
  var ruleLine = document.getElementById("balloons-rule");
  var hear = document.getElementById("balloons-hear");
  var sayButton = document.getElementById("balloons-say");
  var sky = document.getElementById("balloons-sky");
  var feedback = document.getElementById("balloons-feedback");
  var nextButton = document.getElementById("balloons-next");
  var result = document.getElementById("balloons-result");
  var noVoice = document.getElementById("balloons-no-voice");
  var rules = document.getElementById("balloons-rules").content;

  var picks = [];
  var index = 0;
  var timer = null;
  var done = false;

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

  /* --- one item ------------------------------------------------------------ */

  function ruleText(rule) {
    var node = rules.querySelector('[data-rule="' + rule + '"]');
    return node ? node.textContent : "";
  }

  function show(item) {
    done = false;
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    nextButton.hidden = true;
    position.textContent = root.dataset.labelPosition
      .replace("{n}", String(index + 1))
      .replace("{total}", String(items.length));
    ruleLine.textContent = ruleText(item.rule);
    hear.hidden = !item.spoken;

    sky.textContent = "";
    item.candidates.forEach(function (text, i) {
      var balloon = document.createElement("button");
      balloon.type = "button";
      balloon.className = "balloon balloon--" + (i % 4);
      if (timed) {
        balloon.classList.add("balloon--growing");
        balloon.style.setProperty("--balloon-seconds", seconds + "s");
      }
      var label = document.createElement("span");
      label.className = "balloon__label";
      label.textContent = text;
      balloon.appendChild(label);
      balloon.addEventListener("click", function () {
        answer(item, i);
      });
      sky.appendChild(balloon);
    });

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

    var balloons = sky.querySelectorAll(".balloon");
    Array.prototype.forEach.call(balloons, function (balloon, i) {
      balloon.disabled = true;
      balloon.classList.remove("balloon--growing");
      if (item.matches.indexOf(i) !== -1) balloon.classList.add("balloon--answer");
      if (i === pick || pick === null) balloon.classList.add("balloon--popped");
    });

    var right = pick !== null && item.matches.indexOf(pick) !== -1;
    if (right) {
      feedback.textContent = root.dataset.labelRight + " " + item.answer;
      feedback.classList.add("balloons__feedback--right");
    } else {
      var label = pick === null ? root.dataset.labelPopped : root.dataset.labelWrong;
      feedback.textContent = label + " " + item.answer;
    }
    nextButton.hidden = false;
    nextButton.focus();
  }

  function next() {
    index += 1;
    if (index < items.length) {
      show(items[index]);
      return;
    }
    finish();
  }

  function finish() {
    ruleLine.textContent = "";
    hear.hidden = true;
    sky.textContent = "";
    feedback.textContent = "";
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
        /* The board is already cleared, so say what happened and offer the
         * same button again: pressing it sends the same picks once more. */
        feedback.textContent = root.dataset.labelFailed;
        nextButton.hidden = false;
      });
  }

  /* The left and right arrow keys pop the left and right balloon. */
  document.addEventListener("keydown", function (event) {
    if (done || index >= items.length) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    var last = items[index].candidates.length - 1;
    answer(items[index], event.key === "ArrowLeft" ? 0 : last);
  });

  nextButton.addEventListener("click", next);
  sayButton.addEventListener("click", function () {
    say(items[index]);
  });

  show(items[0]);
})();
