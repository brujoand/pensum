/* Arkade memory pairs: turn two cards, keep them if they belong together.
 *
 * The board is in the page as JSON: twelve cards, each naming the pair it
 * belongs to. Two cards of one pair stay face up and the pair's sum is shown in
 * full (design rule 7). Two that do not are turned back after a moment. With
 * the timer on, a bar empties over `data-seconds`; when it is empty the board
 * stops. At the end the page posts, per pair, 0 where it was found and null
 * where it was not, and shows what the server marked.
 */
(function () {
  "use strict";

  var root = document.getElementById("pairs");
  var data = document.getElementById("pairs-round");
  if (!root || !data) return;

  var round = JSON.parse(data.textContent);
  var seconds = Number(root.dataset.seconds) || 120;
  /* The emptying bar is the timer. Where calm mode or the device stops
   * animation it cannot be seen, so the timer does not run (as for balloons). */
  var still =
    document.documentElement.hasAttribute("data-calm") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var timed = round.timed && !still;

  var board = document.getElementById("pairs-board");
  var status = document.getElementById("pairs-status");
  var time = document.getElementById("pairs-time");
  var retry = document.getElementById("pairs-retry");
  var result = document.getElementById("pairs-result");

  /* How long two cards that do not match stay face up. Long enough to read
   * both, which is the point of the game. */
  var SHOW_MS = 1200;
  /* How long a pair's pop takes, so a cleared board waves after it. */
  var WAVE_AFTER_MS = 750;

  var total = round.answers.length;
  var found = {};
  var foundCount = 0;
  var first = null;
  var busy = false;
  var over = false;
  var sending = false;
  var timer = null;
  var cards = [];

  function left() {
    status.textContent = root.dataset.labelLeft.replace("{n}", String(total - foundCount));
  }

  /* The card turns over in 3D: its face carries the text all along and the
   * back hides it, so the text is never seen to appear or vanish mid-turn.
   * Face down, a card is named by its number; face up, by what it says. */
  function faceUp(card) {
    card.button.classList.add("pair-card--up");
    card.button.removeAttribute("aria-label");
    card.face.removeAttribute("aria-hidden");
  }

  function faceDown(card) {
    card.button.classList.remove("pair-card--up");
    card.button.setAttribute("aria-label", card.label);
    card.face.setAttribute("aria-hidden", "true");
  }

  function turn(card) {
    if (over || busy || card.up || found[card.pair]) return;
    card.up = true;
    faceUp(card);
    if (!first) {
      first = card;
      return;
    }
    var other = first;
    first = null;
    if (other.pair === card.pair) {
      found[card.pair] = true;
      foundCount += 1;
      other.button.classList.add("pair-card--found");
      card.button.classList.add("pair-card--found");
      other.button.disabled = true;
      card.button.disabled = true;
      /* A pair found throws a little confetti from each of its cards. */
      if (window.arkadeConfetti) {
        window.arkadeConfetti(other.button);
        window.arkadeConfetti(card.button);
      }
      status.textContent = root.dataset.labelFound + " " + round.answers[card.pair];
      if (foundCount === total) end();
      return;
    }
    busy = true;
    /* Not a pair: both shake, then turn back. */
    other.button.classList.add("pair-card--miss");
    card.button.classList.add("pair-card--miss");
    window.setTimeout(function () {
      busy = false;
      other.button.classList.remove("pair-card--miss");
      card.button.classList.remove("pair-card--miss");
      /* The board ended meanwhile and turned every unfound card up: leave it. */
      if (over) return;
      other.up = false;
      card.up = false;
      faceDown(other);
      faceDown(card);
      left();
    }, SHOW_MS);
  }

  function end() {
    if (over) return;
    over = true;
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
    time.hidden = true;
    /* Rule 7: the board ends on every pair's right form. Cards of a pair not
     * found are turned up and marked, so the pupil sees what belonged together. */
    cards.forEach(function (card) {
      card.button.disabled = true;
      if (found[card.pair]) return;
      card.up = true;
      faceUp(card);
      card.button.classList.add("pair-card--missed");
    });
    /* A cleared board waves, card by card. */
    /* After the last pair has popped: the wave would replace its pop. */
    if (foundCount === total) {
      window.setTimeout(function () {
        board.classList.add("pairs__board--cleared");
      }, WAVE_AFTER_MS);
    }
    send();
  }

  function send() {
    /* One save at a time, as for balloons. */
    if (sending) return;
    sending = true;
    retry.hidden = true;
    var picks = [];
    for (var i = 0; i < total; i++) picks.push(found[i] ? 0 : null);
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
        status.textContent = root.dataset.labelFailed;
        retry.hidden = false;
      });
  }

  round.cards.forEach(function (entry, index) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "pair-card pair-card--deal";
    button.setAttribute("aria-label", String(index + 1));
    /* Its place in the deal: the cards land one after another. */
    button.style.setProperty("--i", String(index));
    var face = document.createElement("span");
    face.className = "pair-card__face";
    face.textContent = entry.text;
    face.setAttribute("aria-hidden", "true");
    button.appendChild(face);
    var back = document.createElement("span");
    back.className = "pair-card__back";
    back.setAttribute("aria-hidden", "true");
    button.appendChild(back);
    var card = {
      button: button,
      face: face,
      text: entry.text,
      pair: entry.pair,
      label: String(index + 1),
      up: false,
    };
    button.addEventListener("click", function () {
      turn(card);
    });
    cards.push(card);
    board.appendChild(button);
  });

  retry.addEventListener("click", send);
  left();

  if (timed) {
    time.hidden = false;
    time.style.setProperty("--pairs-seconds", seconds + "s");
    time.classList.add("pairs__time--running");
    timer = window.setTimeout(function () {
      status.textContent = root.dataset.labelTimeUp;
      end();
    }, seconds * 1000);
  }
})();
