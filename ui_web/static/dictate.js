/* Dictation (REQ-053): speak into a text field instead of typing. Uses the
   browser's own speech-to-text (Web Speech API: Chrome, Edge, Safari). Where
   it isn't available the button stays hidden and typing works as before.
   Final phrases are appended to the field and an `input` event is fired, so
   Alpine x-model fields stay in sync. A window `dictate-stop` event stops any
   running dictation (e.g. when a step changes). */
function dictate(fieldId) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  return {
    supported: !!SR,
    on: false,
    _rec: null,
    toggle() { this.on ? this.stop() : this.start(); },
    start() {
      if (!SR) return;
      const rec = new SR();
      rec.continuous = true;
      rec.interimResults = false;
      rec.lang = document.documentElement.lang || 'en';
      rec.onresult = (e) => {
        let said = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          if (e.results[i].isFinal) said += e.results[i][0].transcript;
        }
        const f = document.getElementById(fieldId);
        if (!f || !said.trim()) return;
        f.value = (f.value.trim() + ' ' + said.trim()).trim();
        f.dispatchEvent(new Event('input', { bubbles: true }));
      };
      rec.onend = () => { this.on = false; };
      rec.onerror = () => { this.on = false; };
      this._rec = rec;
      try { rec.start(); this.on = true; document.getElementById(fieldId)?.focus(); } catch (_) { this.on = false; }
    },
    stop() { try { this._rec && this._rec.stop(); } catch (_) {} this.on = false; },
  };
}
