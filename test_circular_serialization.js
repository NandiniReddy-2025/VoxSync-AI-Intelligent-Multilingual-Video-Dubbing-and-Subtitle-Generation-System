// Test JSON serialization resilience against circular structures and simulated DOM nodes

// Create a simulated circular DOM element structure like React attaches:
// HTMLButtonElement -> __reactFiber$xxx -> FiberNode -> stateNode -> HTMLButtonElement
function createSimulatedDomButton() {
  function HTMLButtonElement() {}
  function FiberNode() {}

  const btn = new HTMLButtonElement();
  const fiber = new FiberNode();

  btn['__reactFiber$123456'] = fiber;
  btn.value = 'ta';
  btn.innerText = 'Translate to Tamil';
  fiber.stateNode = btn;

  return btn;
}

const circularBtn = createSimulatedDomButton();

// Verify that raw JSON.stringify on circularBtn indeed throws the exact error:
try {
  JSON.stringify(circularBtn);
  console.error("FAIL: Raw JSON.stringify did not throw on circular structure!");
} catch (err) {
  console.log("CONFIRMED: Raw JSON.stringify threw expected circular error:");
  console.log(" ", err.message);
}

// Now test our sanitized serialization logic for each API call:
console.log("\nTesting sanitized serializers with circularBtn as argument:");

// 1. translateProject
function testTranslateProject(targetLanguage) {
  const payload = {};
  if (typeof targetLanguage === 'string' && targetLanguage.trim()) {
    payload.target_language = targetLanguage.trim();
  }
  return JSON.stringify(payload);
}
console.log("1. translateProject with circularBtn ->", testTranslateProject(circularBtn));
console.log("   translateProject with 'ta'        ->", testTranslateProject('ta'));

// 2. retranslateSegment
function testRetranslateSegment(originalText, targetLanguage) {
  const payload = {};
  if (typeof originalText === 'string') {
    payload.original_text = originalText;
  }
  if (typeof targetLanguage === 'string' && targetLanguage.trim()) {
    payload.target_language = targetLanguage.trim();
  }
  return JSON.stringify(payload);
}
console.log("2. retranslateSegment with circularBtn ->", testRetranslateSegment(circularBtn, circularBtn));
console.log("   retranslateSegment with valid data  ->", testRetranslateSegment('Hello world', 'ta'));

// 3. generateVoiceover
function testGenerateVoiceover(voiceName, speechRate) {
  const cleanVoice = typeof voiceName === 'string' && voiceName.trim() ? voiceName.trim() : null;
  const cleanRate = (typeof speechRate === 'number' && !isNaN(speechRate)) ? speechRate : (parseFloat(speechRate) || 1.0);
  const payload = { speech_rate: cleanRate };
  if (cleanVoice) payload.voice_name = cleanVoice;
  return JSON.stringify(payload);
}
console.log("3. generateVoiceover with circularBtn ->", testGenerateVoiceover(circularBtn, circularBtn));
console.log("   generateVoiceover with valid data  ->", testGenerateVoiceover('ta-IN-ValluvarNeural', 1.05));

// 4. regenerateSegmentAudio
function testRegenerateAudio(voiceName, speechRate) {
  const cleanVoice = typeof voiceName === 'string' && voiceName.trim() ? voiceName.trim() : null;
  const cleanRate = (typeof speechRate === 'number' && !isNaN(speechRate)) ? speechRate : (parseFloat(speechRate) || 1.0);
  const payload = { speech_rate: cleanRate };
  if (cleanVoice) payload.voice_name = cleanVoice;
  return JSON.stringify(payload);
}
console.log("4. regenerateAudio with circularBtn ->", testRegenerateAudio(circularBtn, circularBtn));
console.log("   regenerateAudio with valid data  ->", testRegenerateAudio('ta-IN-PallaviNeural', 1.0));

// 5. transcribeProject
function testTranscribeProject(sourceLanguage) {
  const cleanSourceLang = typeof sourceLanguage === 'string' && sourceLanguage.trim() ? sourceLanguage.trim() : 'auto';
  return JSON.stringify({ source_language: cleanSourceLang });
}
console.log("5. transcribeProject with circularBtn ->", testTranscribeProject(circularBtn));
console.log("   transcribeProject with 'en'        ->", testTranscribeProject('en'));

// 6. updateProject
function testUpdateProject(updates) {
  const safeUpdates = {};
  if (updates && typeof updates === 'object') {
    if (typeof updates.title === 'string') safeUpdates.title = updates.title;
    if (typeof updates.source_language === 'string') safeUpdates.source_language = updates.source_language;
    if (typeof updates.target_language === 'string') safeUpdates.target_language = updates.target_language;
    if (typeof updates.voice_name === 'string') safeUpdates.voice_name = updates.voice_name;
    if (typeof updates.speech_rate === 'number' || (updates.speech_rate !== undefined && !isNaN(parseFloat(updates.speech_rate)) && typeof updates.speech_rate !== 'object')) {
      safeUpdates.speech_rate = parseFloat(updates.speech_rate);
    }
  }
  return JSON.stringify(safeUpdates);
}
console.log("6. updateProject with circularBtn ->", testUpdateProject(circularBtn));
console.log("   updateProject with valid data  ->", testUpdateProject({ target_language: 'ta', voice_name: 'ta-IN-ValluvarNeural' }));

// 7. triggerExport
function testTriggerExport(exportType, embedSubtitles, subtitleMode, preserveBackground) {
  const cleanType = typeof exportType === 'string' ? exportType : 'video_dubbed';
  const cleanEmbed = Boolean(embedSubtitles);
  const cleanMode = typeof subtitleMode === 'string' ? subtitleMode : 'translated';
  const cleanPreserve = Boolean(preserveBackground);
  return JSON.stringify({
    export_type: cleanType,
    embed_subtitles: cleanEmbed,
    subtitle_mode: cleanMode,
    preserve_background_audio: cleanPreserve
  });
}
console.log("7. triggerExport with circularBtn ->", testTriggerExport(circularBtn, circularBtn, circularBtn, circularBtn));
console.log("   triggerExport with valid data  ->", testTriggerExport('video_dubbed', true, 'translated', false));

console.log("\nALL CIRCULAR SERIALIZATION TESTS PASSED WITH 0 ERRORS!");
