/* Arkade gangetabellen: one product at a time, typed.
 *
 * The round is in the page as JSON: for each product what is asked, its value,
 * the sum in full, and which cell of the table it is. The table is drawn by
 * the server; the cell asked about is marked, and takes its colour the moment
 * it is answered. The answer is typed on the page's own keys or the
 * keyboard's, and sent with OK or Enter. There are no lives: the round is
 * there to find out what is known. With the timer on, a bar empties over
 * `data-seconds` and the round stops when it is empty. At the end the page
 * posts the number typed for each product, and nothing for the ones time took,
 * and shows what the server marked.
 */
(function () {
  "use strict";

  var root = document.getElementById("times");
  var data = document.getElementById("times-round");
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

  /* How long the answer stays before the next product comes by itself. A wrong
   * one stays a beat longer, to be noticed. */
  var NEXT_RIGHT_MS = 700;
  var NEXT_WRONG_MS = 1200;
  /* No product in the table has more digits than this. */
  var MAX_DIGITS = 3;
  var STATES = ["times-cell--unasked", "times-cell--known", "times-cell--not_yet"];

  var position = document.getElementById("times-position");
  var time = document.getElementById("times-time");
  var ask = document.getElementById("times-ask");
  var question = document.getElementById("times-question");
  var typedEl = document.getElementById("times-typed");
  var keysEl = document.getElementById("times-keys");
  var feedback = document.getElementById("times-feedback");
  var retryButton = document.getElementById("times-retry");
  var previousButton = document.getElementById("times-previous");
  var result = document.getElementById("times-result");

  var picks = [];
  var index = 0;
  var typed = "";
  var timer = null;
  /* The product on screen has been answered. */
  var done = false;
  var over = false;
  var sending = false;
  /* The product answered last: what the question mark tells about. */
  var previous = null;
  var keys = [];

  function cellOf(item) {
    return document.getElementById("times-cell-" + item.cell);
  }

  function showTyped() {
    /* An empty answer still takes its place, so the line does not jump. */
    typedEl.textContent = typed === "" ? "?" : typed;
  }

  function enable(on) {
    keys.forEach(function (key) {
      key.disabled = !on;
    });
  }

  function show(item) {
    done = false;
    typed = "";
    feedback.textContent = "";
    feedback.className = "balloons__feedback";
    position.textContent = root.dataset.labelPosition
      .replace("{n}", String(index + 1))
      .replace("{total}", String(items.length));
    question.textContent = item.shown + " =";
    showTyped();
    var cell = cellOf(item);
    if (cell) cell.classList.add("times-cell--now");
    enable(true);
  }

  function press(key) {
    if (done || over) return;
    if (key === "enter") {
      if (typed !== "") answer(Number(typed));
      return;
    }
    if (key === "erase") typed = typed.slice(0, -1);
    else if (typed.length < MAX_DIGITS) typed += key;
    showTyped();
  }

  function answer(pick) {
    if (done || over) return;
    done = true;
    var item = items[index];
    picks.push(pick);
    enable(false);

    var right = pick === item.value;
    /* The cell takes its colour at once. A known cell shows its product; one
     * not known yet shows nothing, and the question mark has the sum. */
    var cell = cellOf(item);
    if (cell) {
      cell.classList.remove("times-cell--now");
      STATES.forEach(function (state) {
        cell.classList.remove(state);
      });
      cell.classList.add(right ? "times-cell--known" : "times-cell--not_yet");
      cell.textContent = right ? String(item.value) : "";
    }
    feedback.textContent = right ? root.dataset.labelRight : root.dataset.labelWrong;
    if (right) {
      feedback.classList.add("balloons__feedback--right");
      if (window.arkadeConfetti) window.arkadeConfetti();
    }
    previous = item;
    previousButton.hidden = false;
    /* The next product comes by itself. */
    window.setTimeout(next, right ? NEXT_RIGHT_MS : NEXT_WRONG_MS);
  }

  function next() {
    if (over) return;
    index += 1;
    if (index < items.length) {
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
    /* The table stays: it is what the round was for. */
    ask.hidden = true;
    enable(false);
    if (index < items.length) {
      var cell = cellOf(items[index]);
      if (cell) cell.classList.remove("times-cell--now");
    }
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

  /* --- the keys ---------------------------------------------------------------- */

  /* Laid out as a phone's: 1 to 9, then erase, 0 and OK. */
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "erase", "0", "enter"].forEach(function (key) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "times-key";
    if (key === "erase") {
      button.textContent = "⌫";
      button.setAttribute("aria-label", root.dataset.labelErase);
    } else if (key === "enter") {
      button.textContent = "OK";
      button.setAttribute("aria-label", root.dataset.labelEnter);
      button.classList.add("times-key--enter");
    } else {
      button.textContent = key;
    }
    button.addEventListener("click", function () {
      press(key);
    });
    keys.push(button);
    keysEl.appendChild(button);
  });

  document.addEventListener("keydown", function (event) {
    var key = null;
    if (event.key >= "0" && event.key <= "9" && event.key.length === 1) key = event.key;
    else if (event.key === "Backspace") key = "erase";
    else if (event.key === "Enter") key = "enter";
    if (key === null || over) return;
    event.preventDefault();
    press(key);
  });

  retryButton.addEventListener("click", send);

  /* The answer to the product before, when asked for. */
  previousButton.addEventListener("click", function () {
    if (!previous || over) return;
    feedback.className = "balloons__feedback";
    feedback.textContent = root.dataset.labelPrevious + " " + previous.answer;
  });

  /* The game fills the screen and nothing scrolls while it is played. */
  document.body.classList.add("arkade-play");
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
