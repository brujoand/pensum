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
  const document = {
    getElementById: (id) => els[id] || null,
    createElement: () => element(""),
    documentElement: { hasAttribute: (name) => calm && name === "data-calm" },
  };
  const window = {
    setTimeout: (fn, ms) => timers.push({ fn, ms }) && timers.length,
    clearTimeout: (n) => {
      timers[n - 1] = null;
    },
    matchMedia: () => ({ matches: false }),
  };
  const fetch = (url, options) => {
    posted.push({ url, body: JSON.parse(options.body) });
    const ok = !(failFirst && posted.length === 1);
    return Promise.resolve({ ok, text: () => Promise.resolve("<p>resultat</p>") });
  };

  new Function("document", "window", "fetch", src)(document, window, fetch);
  const cards = els["pairs-board"].children;
  const face = (i) => cards[i].children[0].textContent;
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  return { els, timers, posted, cards, face, flush };
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
  check("cards start face down", game.face(0) === "" && game.cards[0].getAttribute("aria-label") === "1");
  check("the pairs left are shown", game.els["pairs-status"].textContent === "2 par igjen");
  check("the timer bar runs", game.els["pairs-time"].hidden === false && game.els["pairs-time"].style["--pairs-seconds"] === "120s");
  const boardTimer = game.timers.length;
  check("one timer for the board", boardTimer === 1);

  game.cards[0].click();
  check("a turned card shows its text", game.face(0) === "7 · 8");
  check("and its text is what a screen reader reads", game.cards[0].getAttribute("aria-label") === null);
  game.cards[1].click();
  check("two that do not match stay up for a moment", game.face(1) === "3 · 4");
  game.cards[2].click();
  check("a third card cannot be turned meanwhile", game.face(2) === "");
  game.timers[game.timers.length - 1].fn();
  check("then both turn back", game.face(0) === "" && game.face(1) === "");

  game.cards[0].click();
  game.cards[2].click();
  check("a pair stays up", game.face(0) === "7 · 8" && game.face(2) === "56");
  check("and says the sum in full", game.els["pairs-status"].textContent === "Par! 7 · 8 = 56");
  check("a found card cannot be turned again", game.cards[0].disabled && game.cards[2].disabled);

  game.cards[1].click();
  game.cards[1].click();
  check("the same card twice is not a pair", game.posted.length === 0);
  game.cards[3].click();
  await game.flush();
  check("the last pair ends the board", game.posted.length === 1);
  check("posting both pairs found", JSON.stringify(game.posted[0].body.picks) === JSON.stringify([0, 0]));
  check("and stopping the clock", game.timers[0] === null);
  check("the result is shown", game.els["pairs-result"].innerHTML === "<p>resultat</p>");

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
