/* Gangetabellen, played through a stub DOM.
 *
 * Like the sorting harness: build the elements arkade-table.js reads, run the
 * shipped file against them, type answers, and check what it posts.
 *
 * Run directly with `node tests/js/arkade_table.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(__dirname, "..", "..", "src", "pensum", "web", "static", "arkade-table.js");
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
  "times", "times-round", "times-position", "times-time", "times-ask", "times-question",
  "times-typed", "times-keys", "times-feedback", "times-retry", "times-previous", "times-result",
];

function page(round, { calm = false, failFirst = false, known = [] } = {}) {
  const els = Object.fromEntries(IDS.map((id) => [id, element(id)]));
  Object.assign(els.times.dataset, {
    postUrl: "/nb/arkade/runde/r1",
    seconds: "120",
    labelRight: "Riktig!",
    labelWrong: "Feil!",
    labelPosition: "Gangestykke {n} av {total}",
    labelPrevious: "Forrige gangestykke:",
    labelTimeUp: "Tiden er ute.",
    labelFailed: "Vi fikk ikke lagret runden.",
    labelErase: "Visk ut",
    labelEnter: "Svar",
  });
  els["times-round"].textContent = JSON.stringify(round);
  /* As the template renders them: the table's cells, and what starts hidden. */
  for (const item of round.items) {
    const cell = element("times-cell-" + item.cell);
    cell.classList.add(known.includes(item.cell) ? "times-cell--known" : "times-cell--unasked");
    els[cell.id] = cell;
  }
  for (const id of ["times-time", "times-retry", "times-previous"]) els[id].hidden = true;

  const timers = [];
  const posted = [];
  const thrown = [];
  const keysDown = {};
  const document = {
    getElementById: (id) => els[id] || null,
    createElement: () => element(""),
    documentElement: { hasAttribute: (name) => calm && name === "data-calm" },
    body: element("body"),
    addEventListener: (type, fn) => {
      keysDown[type] = fn;
    },
  };
  const window = {
    setTimeout: (fn, ms) => timers.push({ fn, ms }) && timers.length,
    clearTimeout: (n) => {
      timers[n - 1] = null;
    },
    matchMedia: () => ({ matches: false }),
    arkadeConfetti: (...from) => thrown.push(from),
  };
  const fetch = (url, options) => {
    posted.push({ url, body: JSON.parse(options.body) });
    const ok = !(failFirst && posted.length === 1);
    return Promise.resolve({ ok, text: () => Promise.resolve("<p>resultat</p>") });
  };

  new Function("document", "window", "fetch", src)(document, window, fetch);
  const keys = els["times-keys"].children;
  /* The page's own key that says `text`. */
  const key = (text) => keys.find((k) => k.textContent === text);
  const tap = (...texts) => texts.forEach((text) => key(text).click());
  const press = (name) => {
    let prevented = false;
    keysDown.keydown({ key: name, preventDefault: () => (prevented = true) });
    return prevented;
  };
  const cell = (id) => els["times-cell-" + id];
  /* Bring the next product. */
  const next = () => timers[timers.length - 1].fn();
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  return { els, timers, posted, thrown, body: document.body, keys, key, tap, press, cell, next, flush };
}

const ROUND = {
  round: "r1",
  timed: true,
  items: [
    { shown: "7 · 8", value: 56, answer: "7 · 8 = 56", cell: "7-8" },
    { shown: "3 · 3", value: 9, answer: "3 · 3 = 9", cell: "3-3" },
    { shown: "10 · 10", value: 100, answer: "10 · 10 = 100", cell: "10-10" },
  ],
};

(async () => {
  /* --- a round answered ------------------------------------------------------ */
  const game = page(ROUND);
  check("the game fills the screen", game.body.classList.contains("arkade-play"));
  check("twelve keys, laid out as a phone's", game.keys.map((k) => k.textContent).join(" ") === "1 2 3 4 5 6 7 8 9 ⌫ 0 OK");
  check("the keys that are not digits are named", game.key("⌫").getAttribute("aria-label") === "Visk ut" && game.key("OK").getAttribute("aria-label") === "Svar");
  check("the first product is asked", game.els["times-question"].textContent === "7 · 8 =");
  check("with nothing typed yet", game.els["times-typed"].textContent === "?");
  check("its place in the round is shown", game.els["times-position"].textContent === "Gangestykke 1 av 3");
  check("its cell is marked in the table", game.cell("7-8").classList.contains("times-cell--now"));
  check("the timer bar runs", game.els["times-time"].hidden === false && game.els["times-time"].style["--pairs-seconds"] === "120s");
  check("one timer for the round", game.timers.length === 1 && game.timers[0].ms === 120000);

  game.tap("OK");
  check("OK with nothing typed is not an answer", game.timers.length === 1);
  game.tap("5", "7");
  check("digits are typed", game.els["times-typed"].textContent === "57");
  game.tap("⌫");
  check("and erased", game.els["times-typed"].textContent === "5");
  game.tap("6", "OK");
  check("a right answer says right, and no more", game.els["times-feedback"].textContent === "Riktig!");
  check("its cell turns known and shows the product", game.cell("7-8").classList.contains("times-cell--known") && game.cell("7-8").textContent === "56");
  check("and is no longer unasked or marked", !game.cell("7-8").classList.contains("times-cell--unasked") && !game.cell("7-8").classList.contains("times-cell--now"));
  check("and confetti is thrown once", game.thrown.length === 1);
  check("the keys wait meanwhile", game.key("1").disabled);
  check("the question mark appears", game.els["times-previous"].hidden === false);
  game.next();
  check("the next product comes by itself", game.els["times-question"].textContent === "3 · 3 =" && game.els["times-typed"].textContent === "?");
  check("with the keys open again", !game.key("1").disabled);
  check("and its cell marked", game.cell("3-3").classList.contains("times-cell--now"));

  game.els["times-previous"].click();
  check("the question mark gives the sum before in full", game.els["times-feedback"].textContent === "Forrige gangestykke: 7 · 8 = 56");

  check("the keyboard types too", game.press("6") === true && game.els["times-typed"].textContent === "6");
  check("and erases", game.press("Backspace") === true && game.els["times-typed"].textContent === "?");
  check("another key is left alone", game.press("a") === false && game.press("F5") === false);
  game.press("8");
  game.press("Enter");
  check("a wrong answer says wrong, and no more", game.els["times-feedback"].textContent === "Feil!");
  check("its cell turns not known yet and shows nothing", game.cell("3-3").classList.contains("times-cell--not_yet") && game.cell("3-3").textContent === "");
  check("no confetti for it", game.thrown.length === 1);
  check("a wrong answer stays a beat longer", game.timers[game.timers.length - 1].ms === 1200);
  game.press("9");
  check("typing while the answer shows does nothing", game.els["times-typed"].textContent === "8");
  game.next();

  game.tap("1", "0", "0", "0");
  check("no more digits than a product has", game.els["times-typed"].textContent === "100");
  game.tap("OK");
  game.next();
  await game.flush();
  check("the last product ends the round", game.posted.length === 1);
  check("posting the number typed for each", JSON.stringify(game.posted[0].body.picks) === JSON.stringify([56, 8, 100]));
  check("and stopping the clock", game.timers[0] === null && game.els["times-time"].hidden === true);
  check("the keys go and the table stays", game.els["times-ask"].hidden === true);
  check("the result is shown", game.els["times-result"].innerHTML === "<p>resultat</p>");
  check("a key after the round is left alone", game.press("1") === false && game.posted.length === 1);

  /* --- a known cell answered wrong --------------------------------------------- */
  const slipped = page({ ...ROUND, timed: false }, { known: ["7-8"] });
  slipped.cell("7-8").textContent = "56";
  slipped.tap("5", "4", "OK");
  check("a known cell answered wrong is not known yet", slipped.cell("7-8").classList.contains("times-cell--not_yet") && !slipped.cell("7-8").classList.contains("times-cell--known"));
  check("and no longer shows its product", slipped.cell("7-8").textContent === "");
  check("untimed has no clock", slipped.timers.every((t) => t.ms !== 120000) && slipped.els["times-time"].hidden === true);

  /* --- time running out --------------------------------------------------------- */
  const late = page(ROUND);
  late.tap("5", "6", "OK");
  late.next();
  late.tap("9");
  late.timers[0].fn();
  await late.flush();
  check("time up says so", late.els["times-feedback"].textContent === "Tiden er ute.");
  check("and posts only the products answered, not what was half typed", JSON.stringify(late.posted[0].body.picks) === JSON.stringify([56]));
  check("the cell being asked about is no longer marked", !late.cell("3-3").classList.contains("times-cell--now"));
  check("and keeps the state it had", late.cell("3-3").classList.contains("times-cell--unasked"));
  late.tap("OK");
  check("a tap after time is not an answer", late.posted.length === 1);

  /* Time runs out while an answer is showing. */
  const midway = page(ROUND);
  midway.tap("5", "6", "OK");
  const coming = midway.timers[midway.timers.length - 1];
  midway.timers[0].fn();
  coming.fn();
  await midway.flush();
  check("the answer given counts", JSON.stringify(midway.posted[0].body.picks) === JSON.stringify([56]));
  check("and no product comes after time", midway.els["times-question"].textContent === "7 · 8 =" && midway.els["times-feedback"].textContent === "Tiden er ute.");

  /* --- a save that fails --------------------------------------------------------- */
  const failing = page({ ...ROUND, timed: false, items: ROUND.items.slice(0, 1) }, { failFirst: true });
  failing.tap("5", "6", "OK");
  failing.next();
  await failing.flush();
  check("a failed save says so", failing.els["times-feedback"].textContent === "Vi fikk ikke lagret runden.");
  check("and offers to try again", failing.els["times-retry"].hidden === false);
  failing.els["times-retry"].click();
  failing.els["times-retry"].click();
  await failing.flush();
  check("which sends the same picks, once however often it is pressed", failing.posted.length === 2 && JSON.stringify(failing.posted[1].body) === JSON.stringify(failing.posted[0].body));

  /* --- calm mode ------------------------------------------------------------------ */
  const calm = page(ROUND, { calm: true });
  check("calm mode cannot draw the bar, so there is no clock", calm.timers.length === 0 && calm.els["times-time"].hidden === true);

  if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("ok");
})();
