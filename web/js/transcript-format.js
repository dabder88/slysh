/**
 * Keep in sync with src/slysh/transcript.py (see tests/test_transcript.py).
 */

const LINE_RE = /^\[(\d{2}:\d{2}:\d{2})\](?:\s+([^:\n]{1,40}):\s+)?(.*)$/;

function clockToMs(clock) {
  const parts = String(clock || "").trim().split(":");
  if (parts.length !== 3) {
    return 0;
  }
  const hours = Number(parts[0]);
  const minutes = Number(parts[1]);
  const seconds = Number(parts[2]);
  if ([hours, minutes, seconds].some((n) => Number.isNaN(n))) {
    return 0;
  }
  return ((hours * 3600) + minutes * 60 + seconds) * 1000;
}

/**
 * @param {string} text
 * @returns {Array<{ start_ms: number, end_ms: number, text: string, speaker: string | null }>}
 */
export function parseTranscript(text) {
  const parsed = [];
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim();
    if (!line) {
      continue;
    }
    const match = LINE_RE.exec(line);
    if (!match) {
      if (parsed.length) {
        const prev = parsed[parsed.length - 1];
        prev.text = `${prev.text} ${line}`.trim();
      }
      continue;
    }
    const [, clock, speaker, body] = match;
    const startMs = clockToMs(clock);
    parsed.push({
      start_ms: startMs,
      end_ms: startMs + 1000,
      text: (body || "").trim(),
      speaker: speaker || null,
    });
  }
  for (let index = 0; index < parsed.length; index += 1) {
    const segment = parsed[index];
    if (index + 1 < parsed.length) {
      const endMs = Math.max(segment.start_ms + 1, parsed[index + 1].start_ms);
      parsed[index] = { ...segment, end_ms: endMs };
    }
  }
  return parsed;
}
