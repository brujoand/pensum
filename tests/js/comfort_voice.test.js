/* comfort.js carries its own copy of the listening screen's voice picker.
 *
 * Copied rather than shared, because both scripts are IIFEs with no module
 * system between them. A copy is only safe if it stays a copy: a fix to one
 * that never reaches the other would leave read-aloud speaking Norwegian text
 * in an English voice, which is the silent failure listening.js exists to
 * avoid. So this compares the two, character for character after whitespace,
 * and then runs the copy against the cases that matter.
 *
 * Run directly with `node tests/js/comfort_voice.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const STATIC = path.join(__dirname, "..", "..", "src", "pensum", "web", "static");
const comfort = fs.readFileSync(path.join(STATIC, "comfort.js"), "utf8");
const listening = fs.readFileSync(path.join(STATIC, "listening.js"), "utf8");

function grabFunction(src, file, name) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error(`${file} no longer defines ${name}()`);
  let depth = 0;
  for (let j = src.indexOf("{", start); j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(start, j + 1);
  }
  throw new Error(`unbalanced braces in ${name}()`);
}

function grabObject(src, file, name) {
  const start = src.indexOf("var " + name + " = {");
  if (start < 0) throw new Error(`${file} no longer defines ${name}`);
  return src.slice(start, src.indexOf("};", start) + 2);
}

const squash = (s) => s.replace(/\s+/g, " ").trim();

let failures = 0;

function check(what, condition) {
  if (condition) return;
  failures++;
  console.error(`FAIL: ${what}`);
}

for (const name of ["pickVoice", "withVoices"]) {
  check(
    `${name}() is the same in comfort.js and listening.js`,
    squash(grabFunction(comfort, "comfort.js", name)) ===
      squash(grabFunction(listening, "listening.js", name))
  );
}
check(
  "VOICE_LANGS is the same in comfort.js and listening.js",
  squash(grabObject(comfort, "comfort.js", "VOICE_LANGS")) ===
    squash(grabObject(listening, "listening.js", "VOICE_LANGS"))
);

const pickVoice = new Function(
  [
    grabObject(comfort, "comfort.js", "VOICE_LANGS"),
    grabFunction(comfort, "comfort.js", "pickVoice"),
    "return pickVoice;",
  ].join("\n")
)();

const voice = (lang, name, localService = true) => ({ lang, name, localService });

check("no voices, no voice", pickVoice([], "nb") === null);
check(
  "an English voice is never used for bokmål",
  pickVoice([voice("en-GB", "Daniel")], "nb") === null
);
check(
  "a Norwegian voice is found for bokmål",
  pickVoice([voice("en-US", "Samantha"), voice("nb-NO", "Nora")], "nb").name === "Nora"
);
check(
  "nynorsk falls back to a bokmål voice",
  pickVoice([voice("nb-NO", "Nora")], "nn").name === "Nora"
);

/* The button must not appear without a voice, and must not submit the form it
 * sits in. Both are one line each in comfort.js; reading them is the check. */
check("no voice means no buttons", /if \(!voice\) return;\s*decorate/.test(comfort));
check("the button is type=button", comfort.indexOf('b.type = "button"') >= 0);
check(
  "comfort.js does nothing unless read aloud is on",
  comfort.indexOf('if (!html.hasAttribute("data-read-aloud")) return;') >= 0
);

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("comfort.js voice: all checks passed");
