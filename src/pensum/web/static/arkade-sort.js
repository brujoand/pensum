/* Arkade sorting: one card at a time, put in the pile it belongs in.
 *
 * The round is in the page as JSON: the piles' names, and for each card what
 * it shows, what the page says aloud, and which pile is right. The card is
 * spoken when it comes. Tap a pile, or press its number; with two piles the
 * arrow keys are the piles as well. A card put right stays in its pile; a wrong
 * one spends a life, and the third ends the round. With the timer on, a bar
 * empties over `data-seconds` and the round stops when it is empty. At the end
 * the page posts the pile picked for each card, and nothing for the cards time
 * took, and shows what the server marked.
 */
(function () {
  "use strict";

  var root = document.getElementById("sort");
  var data = document.getElementById("sort-round");
  if (!root || !data) return;

  var round = JSON.parse(data.textContent);
  var items = round.items;
  var seconds = Number(root.dataset.seconds) || 120;
  /* The emptying bar is the timer. Where calm mode or the device stops
   * animation it cannot be seen, so the timer does not run (as for memory). */
  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var timed = round.timed && !still;

  /* How long the card takes to reach its pile, or to shake, before the answer
   * shows. */
  var LEAVE_MS = still ? 150 : 450;
  /* How long the answer stays before the next card comes by itself. A wrong
   * one stays a beat longer, to be noticed. */
  var NEXT_RIGHT_MS = 700;
  var NEXT_WRONG_MS = 1200;

  var position = document.getElementById("sort-position");
  var livesLine = document.getElementById("sort-lives");
  var time = document.getElementById("sort-time");
  var hear = document.getElementById("sort-hear");
  var sayButton = document.getElementById("sort-say");
  var noVoice = document.getElementById("sort-no-voice");
  var cardEl = document.getElementById("sort-card");
  var shownEl = document.getElementById("sort-shown");
  var pilesEl = document.getElementById("sort-piles");
  var feedback = document.getElementById("sort-feedback");
  var retryButton = document.getElementById("sort-retry");
  var previousButton = document.getElementById("sort-previous");
  var result = document.getElementById("sort-result");

  var picks = [];
  var index = 0;
  var lives = round.lives || 3;
  var timer = null;
  /* The card on screen has been answered. */
  var done = false;
  var over = false;
  var sending = false;
  /* The card answered last: what the question mark tells about. */
  var previous = null;
  var piles = [];

  /* --- speaking ------------------------------------------------------------ */

  var VOICE_LANGS = { nb: ["nb", "no", "nn"], nn: ["nn", "nb", "no"], en: ["en"] };
  var speech = window.speechSynthesis;

  /* The same choice as listening.js and arkade-balloons.js: an earlier
   * language in the table wins, and a voice on the device beats a remote one. */
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
    /* No voice for the language: say so. The card is shown as well, so the
     * round can still be played. */
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
    /* Voices load late in some browsers: say the first card once they arrive. */
    speech.addEventListener("voiceschanged", function () {
      if (!done && !over && index < items.length) say(items[index]);
    });
  }

  /* --- one card -------------------------------------------------------------- */

  function showLives() {
    var hearts = "";
    for (var i = 0; i < (round.lives || 3); i++) hearts += i < lives ? "♥" : "♡";
    livesLine.textContent = root.dataset.labelLives.replace("{n}", String(lives)) + " " + hearts;
  }

  function enable(on) {
    piles.forEach(function (pile) {
      pile.button.disabled = !on;
    });
  }

  function show(item) {
    done = false;
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    position.textContent = root.dataset.labelPosition
      .replace("{n}", String(index + 1))
      .replace("{total}", String(items.length));
    shownEl.textContent = item.shown;
    cardEl.className = "sort-card sort-card--deal sort-card--" + (index % 4);
    cardEl.hidden = false;
    hear.hidden = !item.spoken;
    enable(true);
    say(item);
  }

  /* Where the card has to travel to land on the pile, for the stylesheet. */
  function aim(button) {
    if (!cardEl.getBoundingClientRect || !button.getBoundingClientRect) return;
    var from = cardEl.getBoundingClientRect();
    var to = button.getBoundingClientRect();
    cardEl.style.setProperty("--dx", (to.left + to.width / 2 - from.left - from.width / 2).toFixed(0) + "px");
    cardEl.style.setProperty("--dy", (to.top + to.height / 2 - from.top - from.height / 2).toFixed(0) + "px");
  }

  function answer(pick) {
    if (done || over) return;
    done = true;
    var item = items[index];
    var pile = piles[pick];
    picks.push(pick);
    enable(false);

    var right = pick === item.pile;
    if (right) {
      aim(pile.button);
      cardEl.classList.add("sort-card--sent");
    } else {
      cardEl.classList.add("sort-card--miss");
      lives -= 1;
      showLives();
    }

    window.setTimeout(function () {
      /* Time ran out meanwhile: the line belongs to that now. */
      if (over) return;
      feedback.textContent = right ? root.dataset.labelRight : root.dataset.labelWrong;
      if (right) {
        feedback.classList.add("balloons__feedback--right");
        /* A card put right stays in its pile, and throws confetti. */
        var chip = document.createElement("span");
        chip.className = "sort-pile__chip";
        chip.textContent = item.shown;
        pile.cards.appendChild(chip);
        if (window.arkadeConfetti) window.arkadeConfetti();
      }
      cardEl.hidden = true;
      previous = item;
      previousButton.hidden = false;
      /* The next card comes by itself. */
      window.setTimeout(next, right ? NEXT_RIGHT_MS : NEXT_WRONG_MS);
    }, LEAVE_MS);
  }

  function next() {
    if (over) return;
    index += 1;
    if (lives > 0 && index < items.length) {
      show(items[index]);
      return;
    }
    end();
  }

  function end() {
    if (over) return;
    over = true;
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
    time.hidden = true;
    hear.hidden = true;
    cardEl.hidden = true;
    enable(false);
    /* The round is over: the feedback line now belongs to the save. */
    previousButton.hidden = true;
    position.textContent = "";
    send();
  }

  function send() {
    /* One save at a time, as for balloons. */
    if (sending) return;
    sending = true;
    retryButton.hidden = true;
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
        sending = false;
        feedback.className = "balloons__feedback";
        feedback.textContent = root.dataset.labelFailed;
        retryButton.hidden = false;
      });
  }

  /* --- the piles --------------------------------------------------------------- */

  round.piles.forEach(function (name, pick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "sort-pile sort-pile--" + pick;
    var label = document.createElement("span");
    label.className = "sort-pile__name";
    label.textContent = name;
    button.appendChild(label);
    /* The cards put here so far. Read out as they land by the feedback line,
     * so hidden from a screen reader here. */
    var cards = document.createElement("span");
    cards.className = "sort-pile__cards";
    cards.setAttribute("aria-hidden", "true");
    button.appendChild(cards);
    button.addEventListener("click", function () {
      answer(pick);
    });
    piles.push({ button: button, cards: cards, name: name });
    pilesEl.appendChild(button);
  });
  pilesEl.style.setProperty("--piles", String(piles.length));

  document.addEventListener("keydown", function (event) {
    var pick = -1;
    if (event.key >= "1" && event.key <= "9") pick = Number(event.key) - 1;
    /* Two piles lie left and right, so the arrows are the piles. */
    else if (piles.length === 2 && event.key === "ArrowLeft") pick = 0;
    else if (piles.length === 2 && event.key === "ArrowRight") pick = 1;
    if (pick < 0 || pick >= piles.length) return;
    event.preventDefault();
    answer(pick);
  });

  retryButton.addEventListener("click", send);

  /* The answer to the card before, when asked for. */
  previousButton.addEventListener("click", function () {
    if (!previous || over) return;
    feedback.className = "balloons__feedback";
    feedback.textContent =
      root.dataset.labelPrevious + " " + previous.shown + " → " + piles[previous.pile].name;
  });

  sayButton.addEventListener("click", function () {
    if (!done && !over && index < items.length) say(items[index]);
  });

  /* The game fills the screen and nothing scrolls while it is played. */
  document.body.classList.add("arkade-play");
  showLives();
  show(items[0]);

  if (timed) {
    time.hidden = false;
    time.style.setProperty("--pairs-seconds", seconds + "s");
    time.classList.add("pairs__time--running");
    timer = window.setTimeout(function () {
      timer = null;
      end();
      feedback.className = "balloons__feedback";
      feedback.textContent = root.dataset.labelTimeUp;
    }, seconds * 1000);
  }
})();
