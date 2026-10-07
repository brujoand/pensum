/* Memory pairs, played through a stub DOM.
 *
 * Like the balloon harness: build the elements arkade-pairs.js reads, run the
 * shipped file against them, turn cards, and check what it posts.
 *
 * Run directly with `node tests/js/arkade_pairs.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(__dirname, "..", "..", "src", "pensum", "web", "static", "arkade-pairs.js");
const src = fs.readFileSync(SOURCE, "utf8");

let failures = 0;
function check(what, condition) {
  if (condition) return;
  failures++;
  console.error(`FAIL: ${what}`);
}

function element(id) {
  const classes = new Set();
  const attrs = {};
  return {
    id,
    dataset: {},
    hidden: false,
    disabled: false,
    children: [],
    listeners: {},
    innerHTML: "",
    textContent: "",
    style: {
      setProperty(name, value) {
        this[name] = value;
      },
    },
    set className(value) {
      classes.clear();
      value.split(" ").filter(Boolean).forEach((c) => classes.add(c));
    },
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
    },
    setAttribute: (name, value) => {
      attrs[name] = value;
    },
    removeAttribute: (name) => {
      delete attrs[name];
    },
    getAttribute: (name) => (name in attrs ? attrs[name] : null),
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener(type, fn) {
      this.listeners[type] = fn;
    },
    click() {
      if (!this.disabled && this.listeners.click) this.listeners.click();
    },
  };
}

function page(round, { calm = false, failFirst = false } = {}) {
  const ids = ["pairs", "pairs-round", "pairs-board", "pairs-status", "pairs-time", "pairs-retry", "pairs-result"];
  const els = Object.fromEntries(ids.map((id) => [id, element(id)]));
  Object.assign(els.pairs.dataset, {
    postUrl: "/nb/arkade/runde/r1",
    seconds: "120",
    labelFound: "Par!",
    labelLeft: "{n} par igjen",
    labelTimeUp: "Tiden er ute.",
    labelFailed: "Vi fikk ikke lagret brettet.",
  });
  els["pairs-round"].textContent = JSON.stringify(round);
  /* As the template renders them. */
  els["pairs-time"].hidden = true;
  els["pairs-retry"].hidden = true;

  const timers = [];
  const posted = [];
  /* What arkade-confetti.js was asked to throw from; it has its own harness. */
  const thrown = [];
  const document = {
    getElementById: (id) => els[id] || null,
    createElement: () => element(""),
    documentElement: { hasAttribute: (name) => calm && name === "data-calm" },
    body: element("body"),
  };
  const window = {
    setTimeout: (fn, ms) => timers.push({ fn, ms }) && timers.length,
    clearTimeout: (n) => {
      timers[n - 1] = null;
    },
    matchMedia: () => ({ matches: false }),
    arkadeConfetti: (from) => thrown.push(from),
  };
  const fetch = (url, options) => {
    posted.push({ url, body: JSON.parse(options.body) });
    const ok = !(failFirst && posted.length === 1);
    return Promise.resolve({ ok, text: () => Promise.resolve("<p>resultat</p>") });
  };

  new Function("document", "window", "fetch", src)(document, window, fetch);
  const cards = els["pairs-board"].children;
  /* What a card shows: its face when it is turned up, nothing when it is down. */
  const face = (i) => (cards[i].classList.contains("pair-card--up") ? cards[i].children[0].textContent : "");
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  return { els, timers, posted, thrown, body: document.body, cards, face, flush };
}

/* Two pairs, laid out A1 B1 A2 B2. */
const ROUND = {
  round: "r1",
  timed: true,
  cards: [
    { text: "7 · 8", pair: 0 },
    { text: "3 · 4", pair: 1 },
    { text: "56", pair: 0 },
    { text: "12", pair: 1 },
  ],
  answers: ["7 · 8 = 56", "3 · 4 = 12"],
};

(async () => {
  /* --- a board cleared ---------------------------------------------------- */
  const game = page(ROUND);
  check("every card is on the board", game.cards.length === 4);
  check("the game fills the screen", game.body.classList.contains("arkade-play"));
  check("dealt one after another", game.cards[3].classList.contains("pair-card--deal") && game.cards[3].style["--i"] === "3");
  check("a face carries its text from the start, hidden by the back", game.cards[0].children[0].textContent === "7 · 8");
  check("and hidden from a screen reader while the card is down", game.cards[0].children[0].getAttribute("aria-hidden") === "true");
  check("cards start face down", game.face(0) === "" && game.cards[0].getAttribute("aria-label") === "1");
  check("the pairs left are shown", game.els["pairs-status"].textContent === "2 par igjen");
  check("the timer bar runs", game.els["pairs-time"].hidden === false && game.els["pairs-time"].style["--pairs-seconds"] === "120s");
  const boardTimer = game.timers.length;
  check("one timer for the board", boardTimer === 1);

  game.cards[0].click();
  check("a turned card shows its text", game.face(0) === "7 · 8");
  check("and its text is what a screen reader reads", game.cards[0].getAttribute("aria-label") === null && game.cards[0].children[0].getAttribute("aria-hidden") === null);
  game.cards[1].click();
  check("two that do not match stay up for a moment", game.face(1) === "3 · 4");
  check("and throw no confetti", game.thrown.length === 0);
  check("and shake", game.cards[0].classList.contains("pair-card--miss") && game.cards[1].classList.contains("pair-card--miss"));
  game.cards[2].click();
  check("a third card cannot be turned meanwhile", game.face(2) === "");
  game.timers[game.timers.length - 1].fn();
  check("then both turn back", game.face(0) === "" && game.face(1) === "");
  check("and stop shaking", !game.cards[0].classList.contains("pair-card--miss"));

  game.cards[0].click();
  game.cards[2].click();
  check("a pair stays up", game.face(0) === "7 · 8" && game.face(2) === "56");
  check("and pops", game.cards[0].classList.contains("pair-card--found") && game.cards[2].classList.contains("pair-card--found"));
  check("and says the sum in full", game.els["pairs-status"].textContent === "Par! 7 · 8 = 56");
  check("a found card cannot be turned again", game.cards[0].disabled && game.cards[2].disabled);
  check("a pair found throws confetti from both its cards", game.thrown.length === 2 && game.thrown[0] === game.cards[0] && game.thrown[1] === game.cards[2]);

  game.cards[1].click();
  game.cards[1].click();
  check("the same card twice is not a pair", game.posted.length === 0);
  game.cards[3].click();
  await game.flush();
  check("the last pair ends the board", game.posted.length === 1);
  check("posting both pairs found", JSON.stringify(game.posted[0].body.picks) === JSON.stringify([0, 0]));
  check("and stopping the clock", game.timers[0] === null);
  check("the result is shown", game.els["pairs-result"].innerHTML === "<p>resultat</p>");
  check("the last pair pops before the board waves", !game.els["pairs-board"].classList.contains("pairs__board--cleared"));
  game.timers.find((t) => t && t.ms === 750).fn();
  check("then the cleared board waves", game.els["pairs-board"].classList.contains("pairs__board--cleared"));

  /* --- time running out --------------------------------------------------- */
  const late = page(ROUND);
  late.cards[1].click();
  late.cards[3].click();
  late.timers[0].fn();
  await late.flush();
  check("time up says so", late.els["pairs-status"].textContent === "Tiden er ute.");
  check("and posts the missing pair as null", JSON.stringify(late.posted[0].body.picks) === JSON.stringify([null, 0]));
  check(
    "the pair not found is turned up, so the board ends on every right form",
    late.face(0) === "7 · 8" && late.face(2) === "56" && late.cards[0].classList.contains("pair-card--missed")
  );
  check("a found pair is not marked missed", !late.cards[1].classList.contains("pair-card--missed"));
  check("every card is disabled", late.cards.every((card) => card.disabled));

  /* Time runs out while two cards that do not match are up. */
  const midway = page(ROUND);
  midway.cards[0].click();
  midway.cards[1].click();
  const flipBack = midway.timers[midway.timers.length - 1];
  midway.timers[0].fn();
  flipBack.fn();
  check("the turn-back does not hide the revealed cards", midway.face(0) === "7 · 8" && midway.face(1) === "3 · 4");

  /* --- a save that fails ---------------------------------------------------- */
  const failing = page({ ...ROUND, timed: false }, { failFirst: true });
  failing.cards[0].click();
  failing.cards[2].click();
  failing.cards[1].click();
  failing.cards[3].click();
  await failing.flush();
  check("a failed save says so", failing.els["pairs-status"].textContent === "Vi fikk ikke lagret brettet.");
  check("and offers to try again", failing.els["pairs-retry"].hidden === false);
  failing.els["pairs-retry"].click();
  failing.els["pairs-retry"].click();
  await failing.flush();
  check("which sends the same picks, once however often it is pressed", failing.posted.length === 2 && JSON.stringify(failing.posted[1].body) === JSON.stringify(failing.posted[0].body));

  /* --- untimed ------------------------------------------------------------- */
  check("untimed has no clock", failing.timers.every((t) => !t || t.ms !== 120000));
  const calm = page(ROUND, { calm: true });
  check("calm mode cannot draw the bar, so there is no clock", calm.timers.length === 0 && calm.els["pairs-time"].hidden === true);

  if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("ok");
})();
