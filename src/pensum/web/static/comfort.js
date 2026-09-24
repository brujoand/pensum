/* Read aloud: a button next to every question and every answer choice.
 *
 * Loaded only when the comfort profile asks for it, so a page without this
 * setting is exactly the page it always was. The voice is the browser's own,
 * as on the listening screen, and nothing is sent to this site: the text is
 * already on the page.
 *
 * Questions arrive by HTMX swap as often as by page load, so the buttons are
 * added by watching the document rather than once at start-up. Adding one is
 * idempotent -- a prompt that already has its button is left alone.
 *
 * VOICE_LANGS, pickVoice() and withVoices() are copied from listening.js rather
 * than shared. listening.js is an IIFE with no module system to share through,
 * and splitting a third file out of it for three functions would change a
 * shipped page to suit this one. tests/js/comfort_voice.test.js fails if the
 * two copies of the table or the picker ever differ.
 */
(function () {
  "use strict";

  /* The same pace as the listening screen, for the same reason: a sentence
   * read at conversational speed is one a young reader has to ask for twice. */
  var RATE = 0.85;
  var VOICE_WAIT_MS = 1500;

  /* Which BCP-47 prefixes count as a voice for one of our languages. Norwegian
   * voices label themselves `nb-NO`, `no-NO` or, rarely, `nn-NO`, and all three
   * read bokmål text correctly; nynorsk has no voice of its own anywhere, and a
   * bokmål voice is much closer than silence. */
  var VOICE_LANGS = {
    nb: ["nb", "no", "nn"],
    nn: ["nn", "nb", "no"],
    en: ["en"],
  };

  var html = document.documentElement;
  if (!html.hasAttribute("data-read-aloud")) return;

  var speech = window.speechSynthesis;
  if (!speech || !window.SpeechSynthesisUtterance) return;

  var language = html.lang;
  var label = html.getAttribute("data-speak-label") || "";
  var voice = null;

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
          /* Earlier in `wanted` wins; a local voice beats a remote one at the
           * same language. */
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

  function withVoices(then) {
    if (!speech) return then([]);
    var settled = false;
    function done() {
      if (settled) return;
      settled = true;
      then(speech.getVoices() || []);
    }
    var have = speech.getVoices() || [];
    if (have.length) return done();
    speech.addEventListener("voiceschanged", done);
    window.setTimeout(done, VOICE_WAIT_MS);
  }

  function say(text) {
    /* One thing at a time: a second press starts over rather than queueing. */
    speech.cancel();
    var utterance = new window.SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = RATE;
    speech.speak(utterance);
  }

  function button(textOf) {
    var b = document.createElement("button");
    /* type=button, or it would submit the question it sits in. */
    b.type = "button";
    b.className = "speak-button";
    b.textContent = label;
    b.addEventListener("click", function () {
      say(textOf());
    });
    return b;
  }

  /* Next to the prompt, and after each choice's label rather than inside it: a
   * button inside a label is a second control in the first one's hit area. */
  function decorate(scope) {
    Array.prototype.forEach.call(scope.querySelectorAll(".prompt"), function (prompt) {
      if (prompt.dataset.speakable) return;
      prompt.dataset.speakable = "1";
      prompt.insertAdjacentElement(
        "afterend",
        button(function () {
          return prompt.textContent.trim();
        })
      );
    });
    Array.prototype.forEach.call(scope.querySelectorAll(".choices label"), function (choice) {
      if (choice.dataset.speakable) return;
      /* The settings page lists its theme choices the same way; those are not
       * a question. */
      if (choice.closest(".comfort-form")) return;
      choice.dataset.speakable = "1";
      choice.insertAdjacentElement(
        "afterend",
        button(function () {
          return choice.textContent.trim();
        })
      );
    });
  }

  withVoices(function (voices) {
    voice = pickVoice(voices, language);
    /* No voice for this language: no buttons. A button that says the text in
     * the wrong language says a different text, which is worse than silence --
     * the stance the listening screen takes too. */
    if (!voice) return;
    decorate(document);
    new MutationObserver(function () {
      decorate(document);
    }).observe(document.body, { childList: true, subtree: true });
  });
})();
