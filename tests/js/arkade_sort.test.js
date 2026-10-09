/* Sorting, played through a stub DOM.
 *
 * Like the memory harness: build the elements arkade-sort.js reads, run the
 * shipped file against them, put cards in piles, and check what it posts.
 *
 * Run directly with `node tests/js/arkade_sort.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(__dirname, "..", "..", "src", "pensum", "web", "static", "arkade-sort.js");
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

const IDS = [
  "sort", "sort-round", "sort-position", "sort-lives", "sort-time", "sort-hear", "sort-say",
  "sort-no-voice", "sort-card", "sort-shown", "sort-piles", "sort-feedback", "sort-retry",
  "sort-previous", "sort-result",
];

function page(round, { calm = false, failFirst = false, voices = [{ lang: "nb-NO", localService: true }] } = {}) {
  const els = Object.fromEntries(IDS.map((id) => [id, element(id)]));
  Object.assign(els.sort.dataset, {
    postUrl: "/nb/arkade/runde/r1",
    seconds: "120",
    labelRight: "Riktig!",
    labelWrong: "Feil!",
    labelPosition: "Kort {n} av {total}",
    labelLives: "Liv: {n}",
    labelPrevious: "Forrige kort:",
    labelTimeUp: "Tiden er ute.",
    labelFailed: "Vi fikk ikke lagret runden.",
  });
  els["sort-round"].textContent = JSON.stringify(round);
  /* As the template renders them. */
  for (const id of ["sort-time", "sort-hear", "sort-no-voice", "sort-retry", "sort-previous"]) els[id].hidden = true;

  const timers = [];
  const posted = [];
  const thrown = [];
  const said = [];
  const keys = {};
  const document = {
    getElementById: (id) => els[id] || null,
    createElement: () => element(""),
    documentElement: { hasAttribute: (name) => calm && name === "data-calm" },
    body: element("body"),
    addEventListener: (type, fn) => {
      keys[type] = fn;
    },
  };
  const window = {
    setTimeout: (fn, ms) => timers.push({ fn, ms }) && timers.length,
    clearTimeout: (n) => {
      timers[n - 1] = null;
    },
    matchMedia: () => ({ matches: false }),
    arkadeConfetti: (...from) => thrown.push(from),
    speechSynthesis: {
      getVoices: () => voices,
      cancel() {},
      speak: (utterance) => said.push(utterance),
      addEventListener() {},
    },
    SpeechSynthesisUtterance: function (text) {
      this.text = text;
    },
  };
  const fetch = (url, options) => {
    posted.push({ url, body: JSON.parse(options.body) });
    const ok = !(failFirst && posted.length === 1);
    return Promise.resolve({ ok, text: () => Promise.resolve("<p>resultat</p>") });
  };

  new Function("document", "window", "fetch", src)(document, window, fetch);
  const piles = els["sort-piles"].children;
  /* What lies in a pile: the cards put there. */
  const inPile = (i) => piles[i].children[1].children.map((chip) => chip.textContent);
  /* Run what is waiting: the card's way to the pile, then the next card. */
  const settle = () => {
    timers[timers.length - 1].fn();
    timers[timers.length - 1].fn();
  };
  const press = (key) => {
    let prevented = false;
    keys.keydown({ key, preventDefault: () => (prevented = true) });
    return prevented;
  };
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  return { els, timers, posted, thrown, said, body: document.body, piles, inPile, settle, press, flush };
}

/* Three cards over two piles: odd, even, odd. */
const ROUND = {
  round: "r1",
  timed: true,
  lives: 3,
  piles: ["Partall", "Oddetall"],
  items: [
    { shown: "7", pile: 1, spoken: "7", language: "nb" },
    { shown: "12", pile: 0, spoken: "12", language: "nb" },
    { shown: "3", pile: 1, spoken: "3", language: "nb" },
  ],
};

(async () => {
  /* --- a round put right ---------------------------------------------------- */
  const game = page(ROUND);
  check("the game fills the screen", game.body.classList.contains("arkade-play"));
  check("a pile for each name", game.piles.length === 2 && game.piles[1].children[0].textContent === "Oddetall");
  check("the stylesheet is told how many", game.els["sort-piles"].style["--piles"] === "2");
  check("the first card is shown", game.els["sort-shown"].textContent === "7");
  check("and dealt", game.els["sort-card"].classList.contains("sort-card--deal"));
  check("and spoken, by a voice for its language", game.said.length === 1 && game.said[0].text === "7" && game.said[0].lang === "nb-NO");
  check("it can be heard again", game.els["sort-hear"].hidden === false);
  check("its place in the round is shown", game.els["sort-position"].textContent === "Kort 1 av 3");
  check("the lives are shown", game.els["sort-lives"].textContent === "Liv: 3 ♥♥♥");
  check("the timer bar runs", game.els["sort-time"].hidden === false && game.els["sort-time"].style["--pairs-seconds"] === "120s");
  check("one timer for the round", game.timers.length === 1 && game.timers[0].ms === 120000);

  game.els["sort-say"].click();
  check("hearing it again says it again", game.said.length === 2 && game.said[1].text === "7");

  game.piles[1].click();
  check("a card put right travels to its pile", game.els["sort-card"].classList.contains("sort-card--sent"));
  check("the piles wait meanwhile", game.piles[0].disabled && game.piles[1].disabled);
  game.piles[0].click();
  check("so a second tap is not a second answer", game.timers.length === 2);
  game.timers[game.timers.length - 1].fn();
  check("then it says right, and no more", game.els["sort-feedback"].textContent === "Riktig!");
  check("and the card lies in its pile", JSON.stringify(game.inPile(1)) === JSON.stringify(["7"]) && game.inPile(0).length === 0);
  check("and confetti is thrown once", game.thrown.length === 1);
  check("the question mark appears", game.els["sort-previous"].hidden === false);
  game.timers[game.timers.length - 1].fn();
  check("the next card comes by itself", game.els["sort-shown"].textContent === "12" && game.els["sort-card"].hidden === false);
  check("and is spoken", game.said[game.said.length - 1].text === "12");
  check("with the piles open again", !game.piles[0].disabled);

  game.els["sort-previous"].click();
  check("the question mark gives the card before and its pile", game.els["sort-feedback"].textContent === "Forrige kort: 7 → Oddetall");

  check("the left arrow is the left pile", game.press("ArrowLeft") === true);
  game.settle();
  check("and puts the card there", JSON.stringify(game.inPile(0)) === JSON.stringify(["12"]));
  check("another key is not an answer", game.press("a") === false && game.timers.length === 5);
  check("nor a number with no pile", game.press("3") === false);
  check("a pile's number is the pile", game.press("2") === true);
  game.settle();
  await game.flush();
  check("the last card ends the round", game.posted.length === 1);
  check("posting the pile picked for each card", JSON.stringify(game.posted[0].body.picks) === JSON.stringify([1, 0, 1]));
  check("and stopping the clock", game.timers[0] === null && game.els["sort-time"].hidden === true);
  check("the result is shown", game.els["sort-result"].innerHTML === "<p>resultat</p>");
  check("the question mark goes with the round", game.els["sort-previous"].hidden === true);
  check("a key after the round is not an answer", game.press("1") === true && game.posted.length === 1);

  /* --- wrong piles, and the lives -------------------------------------------- */
  const wrong = page({ ...ROUND, timed: false });
  wrong.piles[0].click();
  check("a card put wrong shakes", wrong.els["sort-card"].classList.contains("sort-card--miss"));
  check("and does not travel", !wrong.els["sort-card"].classList.contains("sort-card--sent"));
  check("and spends a life at once", wrong.els["sort-lives"].textContent === "Liv: 2 ♥♥♡");
  wrong.timers[wrong.timers.length - 1].fn();
  check("it says wrong, and no more", wrong.els["sort-feedback"].textContent === "Feil!");
  check("no card lands in either pile", wrong.inPile(0).length === 0 && wrong.inPile(1).length === 0);
  check("and no confetti", wrong.thrown.length === 0);
  check("a wrong answer stays a beat longer", wrong.timers[wrong.timers.length - 1].ms === 1200);
  wrong.timers[wrong.timers.length - 1].fn();
  wrong.piles[1].click();
  wrong.settle();
  wrong.piles[0].click();
  wrong.settle();
  await wrong.flush();
  check("three wrong answers are sent as they were", JSON.stringify(wrong.posted[0].body.picks) === JSON.stringify([0, 1, 0]));
  check("untimed has no clock", wrong.timers.every((t) => t.ms !== 120000) && wrong.els["sort-time"].hidden === true);

  const short = page({ ...ROUND, lives: 1, timed: false });
  short.piles[0].click();
  short.settle();
  await short.flush();
  check("the last life ends the round early", JSON.stringify(short.posted[0].body.picks) === JSON.stringify([0]));

  /* --- time running out ------------------------------------------------------ */
  const late = page(ROUND);
  late.piles[1].click();
  late.settle();
  late.timers[0].fn();
  await late.flush();
  check("time up says so", late.els["sort-feedback"].textContent === "Tiden er ute.");
  check("and posts only the cards answered", JSON.stringify(late.posted[0].body.picks) === JSON.stringify([1]));
  check("the card is taken away and the piles closed", late.els["sort-card"].hidden === true && late.piles[0].disabled);
  late.piles[0].click();
  check("a tap after time is not an answer", late.posted.length === 1);

  /* Time runs out while a card is on its way to a pile. */
  const midway = page(ROUND);
  midway.piles[1].click();
  const landing = midway.timers[midway.timers.length - 1];
  midway.timers[0].fn();
  landing.fn();
  await midway.flush();
  check("the answer given counts", JSON.stringify(midway.posted[0].body.picks) === JSON.stringify([1]));
  check("and the landing does not replace the line or bring a card", midway.els["sort-feedback"].textContent === "Tiden er ute." && midway.timers.length === 2);

  /* --- a save that fails ------------------------------------------------------ */
  const failing = page({ ...ROUND, timed: false, items: ROUND.items.slice(0, 1) }, { failFirst: true });
  failing.piles[1].click();
  failing.settle();
  await failing.flush();
  check("a failed save says so", failing.els["sort-feedback"].textContent === "Vi fikk ikke lagret runden.");
  check("and offers to try again", failing.els["sort-retry"].hidden === false);
  failing.els["sort-retry"].click();
  failing.els["sort-retry"].click();
  await failing.flush();
  check("which sends the same picks, once however often it is pressed", failing.posted.length === 2 && JSON.stringify(failing.posted[1].body) === JSON.stringify(failing.posted[0].body));

  /* --- calm mode, and no voice ------------------------------------------------- */
  const calm = page(ROUND, { calm: true });
  check("calm mode cannot draw the bar, so there is no clock", calm.timers.length === 0 && calm.els["sort-time"].hidden === true);

  const mute = page(ROUND, { voices: [{ lang: "en-GB", localService: true }] });
  check("no voice for the language says nothing", mute.said.length === 0);
  check("and says so", mute.els["sort-no-voice"].hidden === false);
  check("the card is still shown, so the round can be played", mute.els["sort-shown"].textContent === "7");

  if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("ok");
})();
